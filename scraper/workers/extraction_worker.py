"""Extraction worker - uses LLM to extract structured data."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import structlog

from bs4 import BeautifulSoup

from scraper.config import settings
from scraper.models import (
    ScrapingTask, ExtractionResult, PageType,
    Transfer, Player, Club, Fee, Currency, TransferType, Position,
    ValidationReport
)
from scraper.queue import get_queue_manager, publish_repair_task
from scraper.llm_client import get_llm_client
from scraper.workers.discovery_worker import DiscoveryAgent
from scraper.extractors.transfermarkt_bs import (
    parse_player_profile,
    parse_player_transfers,
    parse_club_transfers,
    parse_club_profile,
    ExtractionError
)
from scraper.validators.transfermarkt_llm_validator import get_validator

logger = structlog.get_logger()


class ExtractionAgent:
    """Agent for LLM-based data extraction."""
    
    def __init__(self):
        self.llm = get_llm_client()
        self.validator = get_validator()
        self.discovery = DiscoveryAgent()
        # Clear visited URLs from discovery to allow extraction to fetch
        self.discovery.visited.clear()
        self.output_dir = Path(settings.storage.data_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def get_schema_for_page_type(self, page_type: PageType) -> str:
        """Get extraction schema description for page type."""
        schemas = {
            PageType.PLAYER_PROFILE: """
{
  "player": {
    "tm_id": "string (extract from URL)",
    "name": "string",
    "date_of_birth": "YYYY-MM-DD or null",
    "nationality": "string or null",
    "height_cm": "integer or null",
    "position": "string - USE ONLY THESE: GK, CB, LB, RB, DM, CM, AM, LW, RW, CF, ST (convert: Goalkeeper→GK, Centre-Back/Defender→CB, Left-Back→LB, Right-Back→RB, Defensive Midfield→DM, Central Midfield→CM, Attacking Midfield→AM, Left Winger→LW, Right Winger→RW, Centre-Forward→CF, Striker/Forward→ST)",
    "dominant_foot": "string or null",
    "current_club": "string or null"
  },
  "market_values": [
    {
      "value": "float (numeric only)",
      "currency": "EUR/GBP/USD",
      "date": "YYYY-MM-DD",
      "club": "string or null"
    }
  ]
}
""",
            PageType.PLAYER_TRANSFERS: """
{
  "player_name": "string",
  "player_tm_id": "string (from URL)",
  "transfers": [
    {
      "from_club": "string or null",
      "from_club_tm_id": "string or null",
      "to_club": "string or null",
      "to_club_tm_id": "string or null",
      "transfer_date": "YYYY-MM-DD or null",
      "season": "string (e.g., '23/24') or null",
      "transfer_type": "permanent/loan/free/end_of_loan",
      "fee": {
        "amount": "float or null",
        "currency": "EUR/GBP/USD",
        "is_disclosed": "boolean",
        "has_addons": "boolean",
        "is_loan_fee": "boolean",
        "notes": "string or null"
      },
      "market_value_at_transfer": "float or null"
    }
  ]
}
""",
            PageType.CLUB_TRANSFERS: """
{
  "club_name": "string",
  "club_tm_id": "string (from URL)",
  "season": "string or null",
  "transfers": [
    {
      "player_name": "string",
      "player_tm_id": "string or null",
      "from_club": "string or null",
      "to_club": "string or null",
      "transfer_date": "YYYY-MM-DD or null",
      "fee": {
        "amount": "float in MILLIONS (e.g., €15.5m = 15.5, NOT 15500000) or null for free/loan",
        "currency": "EUR/GBP/USD (default EUR if not specified)",
        "is_disclosed": "boolean (true if amount shown, false if undisclosed/free)",
        "notes": "string or null (e.g., 'loan fee', 'free transfer', 'undisclosed')"
      }
    }
  ]
}
""",
            PageType.CLUB_PROFILE: """
{
  "club": {
    "tm_id": "string (from URL)",
    "name": "string",
    "country": "string or null",
    "league": "string or null",
    "division": "integer or null"
  }
}
"""
        }
        
        return schemas.get(page_type, "{}")
    
    def extract_relevant_html(self, html: str, page_type: PageType) -> str:
        """Extract only the relevant sections from HTML to reduce token usage."""
        soup = BeautifulSoup(html, 'html.parser')
        
        if page_type == PageType.CLUB_TRANSFERS:
            # Look for transfer tables - Transfermarkt uses specific classes/IDs
            relevant_parts = []
            
            # Get the main content box
            content = soup.find('div', class_='box') or soup.find('div', class_='responsive-table')
            if content:
                relevant_parts.append(str(content))
            
            # Get all tables (transfers are in tables)
            tables = soup.find_all('table', class_='items')
            for table in tables:
                relevant_parts.append(str(table))
            
            # Get transfer boxes
            transfer_boxes = soup.find_all('div', class_='box')
            for box in transfer_boxes[:3]:  # Limit to first 3 boxes
                if 'transfer' in str(box).lower():
                    relevant_parts.append(str(box))
            
            if relevant_parts:
                extracted = '\n'.join(relevant_parts)
                print(f"HTML EXTRACTION: Extracted {len(extracted)} chars from {len(html)} chars for club_transfers")
                return extracted[:30000]  # Cap at 30k chars
        
        elif page_type == PageType.PLAYER_PROFILE:
            # Get player info box and market value chart
            relevant_parts = []
            
            info_box = soup.find('div', class_='info-table')
            if info_box:
                relevant_parts.append(str(info_box))
            
            # Get data boxes
            data_boxes = soup.find_all('div', class_='box')
            for box in data_boxes[:2]:
                relevant_parts.append(str(box))
                
            if relevant_parts:
                extracted = '\n'.join(relevant_parts)
                print(f"HTML EXTRACTION: Extracted {len(extracted)} chars from {len(html)} chars for player_profile")
                return extracted[:30000]
        
        # Fallback: return first 20k chars
        print(f"HTML EXTRACTION: Using fallback (first 20k chars) for {page_type}")
        return html[:20000]
    
    def is_transfermarkt_url(self, url: str) -> bool:
        """Check if URL is a Transfermarkt URL."""
        return 'transfermarkt.com' in url.lower()
    
    def should_use_bs_for_page_type(self, page_type: PageType) -> bool:
        """Check if BS extraction should be used for this page type."""
        # Check global flag
        if not settings.scraper.use_bs_extractors:
            return False
        
        # Check per-page-type flag
        allowed_types = settings.scraper.use_bs_extractors_for
        if allowed_types:
            page_type_str = page_type.value if isinstance(page_type, PageType) else page_type
            return page_type_str in allowed_types
        
        # If use_bs_extractors is True but no specific types, use for all
        return True
    
    async def extract_from_page_bs(
        self,
        html: str,
        url: str,
        page_type: PageType,
    ) -> ExtractionResult:
        """
        Extract structured data from HTML using BeautifulSoup (deterministic).
        
        Args:
            html: HTML content
            url: Page URL
            page_type: Type of page
        
        Returns:
            ExtractionResult with extraction_backend='bs'
        """
        print(f"BS: Extracting {page_type} from {len(html)} chars")
        logger.info("bs_extracting_data", url=url, page_type=page_type)
        
        try:
            # Route to appropriate BS parser
            if page_type == PageType.PLAYER_PROFILE:
                data = parse_player_profile(html, url)
            elif page_type == PageType.PLAYER_TRANSFERS:
                data = parse_player_transfers(html, url)
            elif page_type == PageType.CLUB_TRANSFERS:
                data = parse_club_transfers(html, url)
            elif page_type == PageType.CLUB_PROFILE:
                data = parse_club_profile(html, url)
            else:
                raise ExtractionError(f"BS extraction not implemented for {page_type}")
            
            print(f"BS: Extracted data keys: {list(data.keys())}")
            
            # Create result
            result = ExtractionResult(
                success=True,
                page_type=page_type,
                url=url,
                data=data,
                extraction_backend="bs",
            )
            
            # Convert to typed models based on page type
            self._populate_typed_models(result, data, url)
            
            # Validate with LLM if enabled
            if settings.scraper.enable_llm_validation:
                try:
                    validation_report = await self.validator.validate(
                        extracted_data=data,
                        page_type=page_type,
                        html_snippet=None  # Don't send HTML to LLM
                    )
                    result.validation = validation_report.model_dump()
                    
                    if validation_report.needs_review:
                        logger.warning(
                            "bs_extraction_needs_review",
                            url=url,
                            warnings=validation_report.warnings
                        )
                except Exception as ve:
                    logger.error("validation_error", url=url, error=str(ve))
            
            logger.info(
                "bs_extraction_success",
                url=url,
                page_type=page_type,
                players=len(result.players),
                clubs=len(result.clubs),
                transfers=len(result.transfers),
            )
            
            return result
            
        except ExtractionError as e:
            logger.error(
                "bs_extraction_failed",
                url=url,
                page_type=page_type,
                error=str(e),
            )
            
            return ExtractionResult(
                success=False,
                page_type=page_type,
                url=url,
                error=str(e),
                extraction_backend="bs",
            )
        except Exception as e:
            logger.error(
                "bs_extraction_error",
                url=url,
                page_type=page_type,
                error=str(e),
                exc_info=True,
            )
            
            return ExtractionResult(
                success=False,
                page_type=page_type,
                url=url,
                error=str(e),
                extraction_backend="bs",
            )
    
    def _populate_typed_models(self, result: ExtractionResult, data: Dict[str, Any], url: str):
        """Populate typed Pydantic models from extracted data dict."""
        page_type = result.page_type
        
        if page_type == PageType.PLAYER_PROFILE:
            if "player" in data:
                player_data = data["player"]
                # Remove None values and let Pydantic use defaults
                player_data = {k: v for k, v in player_data.items() if v is not None}
                player = Player(**player_data)
                result.players.append(player)
                
        elif page_type == PageType.PLAYER_TRANSFERS:
            for transfer_data in data.get("transfers", []):
                # Remove None values
                transfer_data = {k: v for k, v in transfer_data.items() if v is not None}
                transfer = Transfer(
                    player_tm_id=data.get("player_tm_id"),
                    player_name=data.get("player_name"),
                    source_url=url,
                    **transfer_data
                )
                result.transfers.append(transfer)
                
        elif page_type == PageType.CLUB_TRANSFERS:
            for transfer_data in data.get("transfers", []):
                # Remove None values
                transfer_data = {k: v for k, v in transfer_data.items() if v is not None}
                try:
                    transfer = Transfer(
                        source_url=url,
                        **transfer_data
                    )
                    result.transfers.append(transfer)
                except Exception as e:
                    print(f"ERROR: Failed to create Transfer from {transfer_data}: {e}")
                    continue
                
        elif page_type == PageType.CLUB_PROFILE:
            if "club" in data:
                club_data = data["club"]
                # Remove None values and let Pydantic use defaults
                club_data = {k: v for k, v in club_data.items() if v is not None}
                club = Club(**club_data)
                result.clubs.append(club)
    
    def _convert_llm_data_to_typed_models(self, result: ExtractionResult, data: Dict[str, Any], url: str):
        """Convert LLM-extracted data to typed Pydantic models (with LLM-specific fixes)."""
        page_type = result.page_type
        
        if page_type == PageType.PLAYER_PROFILE:
            if "player" in data:
                player_data = data["player"]
                player_data = {k: v for k, v in player_data.items() if v is not None}
                player = Player(**player_data)
                result.players.append(player)
                
        elif page_type == PageType.PLAYER_TRANSFERS:
            for transfer_data in data.get("transfers", []):
                transfer_data = {k: v for k, v in transfer_data.items() if v is not None}
                transfer = Transfer(
                    player_tm_id=data.get("player_tm_id"),
                    player_name=data.get("player_name"),
                    source_url=url,
                    **transfer_data
                )
                result.transfers.append(transfer)
                
        elif page_type == PageType.CLUB_TRANSFERS:
            for transfer_data in data.get("transfers", []):
                # Fix common LLM extraction errors
                if "fee" in transfer_data and transfer_data["fee"]:
                    fee = transfer_data["fee"]
                    # Fix: LLM extracting amounts in wrong units (€2.87m as 287000000 instead of 2.87)
                    if fee.get("amount") and fee["amount"] > 10000:
                        print(f"WARNING: Suspicious fee amount {fee['amount']} - likely in wrong units, dividing by 1M")
                        fee["amount"] = fee["amount"] / 1000000
                    # Set defaults for missing fields
                    if "currency" not in fee or fee["currency"] is None:
                        fee["currency"] = "EUR"
                    if "is_disclosed" not in fee or fee["is_disclosed"] is None:
                        fee["is_disclosed"] = fee.get("amount") is not None
                
                transfer_data = {k: v for k, v in transfer_data.items() if v is not None}
                try:
                    transfer = Transfer(
                        source_url=url,
                        **transfer_data
                    )
                    result.transfers.append(transfer)
                except Exception as e:
                    print(f"ERROR: Failed to create Transfer from {transfer_data}: {e}")
                    continue
                    
        elif page_type == PageType.CLUB_PROFILE:
            if "club" in data:
                club_data = data["club"]
                club_data = {k: v for k, v in club_data.items() if v is not None}
                club = Club(**club_data)
                result.clubs.append(club)
    
    async def extract_from_page(
        self,
        html: str,
        url: str,
        page_type: PageType,
    ) -> ExtractionResult:
        """
        Extract structured data from HTML page.
        
        Routes to either BS (deterministic) or LLM extraction based on config.
        
        Args:
            html: HTML content
            url: Page URL
            page_type: Type of page
        
        Returns:
            ExtractionResult
        """
        # Check if we should use BS extraction
        use_bs = (
            self.is_transfermarkt_url(url) and
            self.should_use_bs_for_page_type(page_type)
        )
        
        if use_bs:
            print(f"ROUTING: Using BS extraction for {page_type}")
            result = await self.extract_from_page_bs(html, url, page_type)
            
            # Fallback to LLM if BS fails and fallback is enabled
            if not result.success and settings.scraper.bs_fallback_to_llm:
                print(f"FALLBACK: BS failed, falling back to LLM for {page_type}")
                logger.warning("bs_fallback_to_llm", url=url, error=result.error)
                result = await self.extract_from_page_llm(html, url, page_type)
                result.extraction_backend = "bs_fallback_llm"
        else:
            print(f"ROUTING: Using LLM extraction for {page_type}")
            result = await self.extract_from_page_llm(html, url, page_type)
        
        return result
    
    async def extract_from_page_llm(
        self,
        html: str,
        url: str,
        page_type: PageType,
    ) -> ExtractionResult:
        """Extract structured data from HTML page using LLM."""
        print(f"LLM: Extracting {page_type} from {len(html)} chars")
        logger.info("extracting_data", url=url, page_type=page_type)
        
        # Extract only relevant HTML sections
        html = self.extract_relevant_html(html, page_type)
        print(f"LLM: Reduced to {len(html)} chars after HTML extraction")
        
        schema = self.get_schema_for_page_type(page_type)
        print(f"LLM: Using schema for {page_type}")
        print(f"LLM: Schema preview: {schema[:100]}...")
        
        try:
            # Use LLM to extract data
            page_type_value = page_type.value if isinstance(page_type, PageType) else page_type
            print(f"LLM: Calling llm.extract_structured_data with page_type={page_type_value}")
            
            import asyncio
            try:
                data = await asyncio.wait_for(
                    self.llm.extract_structured_data(
                        html_content=html,
                        page_type=page_type_value,
                        schema_description=schema,
                    ),
                    timeout=120.0  # 120 second timeout (increased for slower GPU)
                )
                print(f"LLM: Received data keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            except asyncio.TimeoutError:
                print(f"LLM: TIMEOUT after 60s for {url}")
                raise Exception(f"LLM extraction timeout for {url}")
            except Exception as llm_error:
                print(f"LLM: ERROR during extraction: {type(llm_error).__name__}: {llm_error}")
                raise
            
            # Parse into Pydantic models
            result = ExtractionResult(
                success=True,
                page_type=page_type,
                url=url,
                data=data,
                extraction_backend="llm",
            )
            
            # Convert to typed models based on page type - LLM version with fixes
            self._convert_llm_data_to_typed_models(result, data, url)
                    
            logger.info(
                "extraction_success",
                url=url,
                page_type=page_type,
                players=len(result.players),
                clubs=len(result.clubs),
                transfers=len(result.transfers),
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "extraction_failed",
                url=url,
                page_type=page_type,
                error=str(e),
                exc_info=True,
            )
            
            return ExtractionResult(
                success=False,
                page_type=page_type,
                url=url,
                error=str(e),
            )
            
    def save_result(self, result: ExtractionResult):
        """Save extraction result to JSON file."""
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        # Handle page_type as either enum or string
        page_type_str = result.page_type.value if isinstance(result.page_type, PageType) else result.page_type
        filename = f"{page_type_str}_{date_str}.jsonl"
        filepath = self.output_dir / filename
        
        with open(filepath, "a") as f:
            f.write(result.model_dump_json() + "\n")
            
        logger.info("result_saved", filepath=str(filepath))
        
    async def process_task(self, task_data: Dict[str, Any]):
        """Process an extraction task."""
        task = ScrapingTask(**task_data)
        # Ensure page_type is a PageType enum, not a string
        if isinstance(task.page_type, str):
            task.page_type = PageType(task.page_type)
        
        print(f"\n=== EXTRACTION TASK: {task.url} ({task.page_type}) ===")
        logger.info("processing_extraction_task", url=task.url, page_type=task.page_type)
        
        # Fetch page
        html = await self.discovery.fetch_page(task.url)
        if not html:
            print(f"EXTRACTION: FAILED TO FETCH (returned None): {task.url}")
            logger.warning("failed_to_fetch", url=task.url)
            return
        
        print(f"EXTRACTION: Fetched {len(html)} chars, extracting...")
            
        # Extract data
        result = await self.extract_from_page(html, task.url, task.page_type)
        
        # Save result
        self.save_result(result)
        
        # If extraction failed, send to repair queue
        if not result.success and task.retry_count < settings.scraper.max_retries:
            from scraper.models import RepairTask
            
            repair_task = RepairTask(
                url=task.url,
                page_type=task.page_type,
                html_snippet=html[:5000],
                failed_selectors={},
                error_message=result.error or "Unknown error",
                original_task=task,
            )
            
            await publish_repair_task(repair_task)
            logger.info("sent_to_repair", url=task.url)


async def run_extraction_worker(worker_id: int):
    """Run extraction worker process."""
    logger.info("extraction_worker_starting", worker_id=worker_id)
    
    agent = ExtractionAgent()
    await agent.discovery.start_session()
    
    try:
        qm = await get_queue_manager()
        
        # Start multiple concurrent consumers
        tasks = []
        for i in range(settings.workers.concurrent_consumers):
            consumer_tag = f"extraction_worker_{worker_id}_consumer_{i}"
            task = asyncio.create_task(
                qm.consume_tasks(
                    settings.queues.extraction_queue,
                    agent.process_task,
                    consumer_tag=consumer_tag,
                )
            )
            tasks.append(task)
            
        # Wait for all consumers
        await asyncio.gather(*tasks)
        
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("extraction_worker_stopping", worker_id=worker_id)
    finally:
        await agent.discovery.close_session()


if __name__ == "__main__":
    import sys
    worker_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    
    asyncio.run(run_extraction_worker(worker_id))
