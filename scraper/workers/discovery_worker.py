"""Discovery worker - fetches pages and extracts links."""

import asyncio
import logging
import random
import re
from typing import Set, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
import aiohttp
from bs4 import BeautifulSoup
import structlog

from scraper.config import settings
from scraper.models import ScrapingTask, PageType, TaskPriority
from scraper.queue import get_queue_manager, publish_discovery_task, publish_extraction_task

logger = structlog.get_logger()


class DiscoveryAgent:
    """Agent for discovering and classifying Transfermarkt pages."""
    
    # URL patterns for page classification
    PATTERNS = {
        PageType.LEAGUE_INDEX: re.compile(r"/wettbewerbe/(europa|amerika|asien|afrika)"),
        PageType.LEAGUE_CLUBS: re.compile(r"/(startseite|vereine)/wettbewerb/\w+"),
        PageType.CLUB_PROFILE: re.compile(r"/[a-z\-]+/startseite/verein/\d+"),
        PageType.CLUB_TRANSFERS: re.compile(r"/[a-z\-]+/(transfers|zugaenge)/verein/\d+"),
        PageType.PLAYER_PROFILE: re.compile(r"/[a-z\-]+/profil/spieler/\d+"),
        PageType.PLAYER_TRANSFERS: re.compile(r"/[a-z\-]+/transfers/spieler/\d+"),
        PageType.COMPETITION_PAGE: re.compile(r"/wettbewerb/\w+"),
    }
    
    def __init__(self):
        self.visited: Set[str] = set()
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def start_session(self):
        """Initialize HTTP session."""
        headers = {
            "User-Agent": settings.scraper.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }
        self.session = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=settings.scraper.request_timeout),
        )
        
    async def close_session(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            
    def classify_url(self, url: str) -> PageType:
        """Classify URL into page type."""
        for page_type, pattern in self.PATTERNS.items():
            if pattern.search(url):
                return page_type
        return PageType.UNKNOWN
        
    def extract_transfermarkt_id(self, url: str) -> Optional[str]:
        """Extract Transfermarkt ID from URL."""
        match = re.search(r"/(spieler|verein|wettbewerb)/(\d+)", url)
        if match:
            return match.group(2)
        return None
        
    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page content with retries and politeness delay."""
        if url in self.visited:
            print(f"ALREADY VISITED: {url}")  # DEBUG
            logger.warning("url_already_visited", url=url)
            return None
        
        if not self.session:
            print(f"SESSION NOT INITIALIZED: {url}")  # DEBUG
            logger.error("session_not_initialized", url=url)
            return None
        
        print(f"STARTING FETCH: {url}")  # DEBUG
            
        # Politeness delay
        delay = random.uniform(
            settings.scraper.request_delay_min,
            settings.scraper.request_delay_max,
        )
        await asyncio.sleep(delay)
        
        for attempt in range(settings.scraper.max_retries):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        self.visited.add(url)
                        content = await response.text()
                        logger.info(
                            "page_fetched",
                            url=url,
                            status=response.status,
                            size=len(content),
                        )
                        return content
                    elif response.status == 429:  # Rate limit
                        wait_time = 30 * (attempt + 1)
                        logger.warning(
                            "rate_limited",
                            url=url,
                            wait_time=wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        response_text = await response.text()
                        logger.warning(
                            "http_error",
                            url=url,
                            status=response.status,
                            attempt=attempt + 1,
                            response_preview=response_text[:200] if response_text else None,
                        )
                        
            except asyncio.TimeoutError:
                print(f"TIMEOUT ERROR: {url}")  # DEBUG
                logger.warning(
                    "request_timeout",
                    url=url,
                    attempt=attempt + 1,
                    timeout=settings.scraper.request_timeout,
                )
            except aiohttp.ClientError as e:
                print(f"CLIENT ERROR: {url} - {type(e).__name__}: {e}")  # DEBUG
                logger.error(
                    "client_error",
                    url=url,
                    error=str(e),
                    error_type=type(e).__name__,
                    attempt=attempt + 1,
                )
            except Exception as e:
                print(f"FETCH ERROR: {url} - {type(e).__name__}: {e}")  # DEBUG
                logger.error(
                    "fetch_error",
                    url=url,
                    error=str(e),
                    error_type=type(e).__name__,
                    attempt=attempt + 1,
                )
        
        # All retries exhausted
        logger.error(
            "fetch_failed_all_retries",
            url=url,
            max_retries=settings.scraper.max_retries,
        )
        return None
        
    def extract_links(self, html: str, base_url: str) -> Set[str]:
        """Extract Transfermarkt links from HTML."""
        soup = BeautifulSoup(html, "lxml")
        links = set()
        
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            
            # Make absolute URL
            full_url = urljoin(base_url, href)
            
            # Only Transfermarkt URLs
            if "transfermarkt.com" not in full_url:
                continue
                
            # Remove query params and fragments
            parsed = urlparse(full_url)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
            # Filter for relevant pages
            if any(pattern.search(clean_url) for pattern in self.PATTERNS.values()):
                links.add(clean_url)
                
        return links
        
    def prioritize_url(self, url: str, page_type: PageType) -> int:
        """Assign priority to URL based on type."""
        priority_map = {
            PageType.LEAGUE_INDEX: TaskPriority.CRITICAL,
            PageType.LEAGUE_CLUBS: TaskPriority.HIGH,
            PageType.CLUB_TRANSFERS: TaskPriority.HIGH,
            PageType.PLAYER_TRANSFERS: TaskPriority.MEDIUM,
            PageType.CLUB_PROFILE: TaskPriority.MEDIUM,
            PageType.PLAYER_PROFILE: TaskPriority.MEDIUM,
            PageType.COMPETITION_PAGE: TaskPriority.LOW,
            PageType.UNKNOWN: TaskPriority.LOW,
        }
        return priority_map.get(page_type, TaskPriority.LOW)
        
    async def process_task(self, task_data: Dict[str, Any]):
        """Process a discovery task."""
        task = ScrapingTask(**task_data)
        
        print(f"\n=== DISCOVERY TASK: {task.url} ===")
        logger.info("processing_discovery_task", url=task.url, page_type=task.page_type)
        
        # Fetch page
        html = await self.fetch_page(task.url)
        if not html:
            print(f"FAILED TO FETCH (returned None): {task.url}")
            logger.warning("failed_to_fetch", url=task.url)
            return
        
        print(f"SUCCESS: Fetched {len(html)} chars from {task.url}")
            
        # Extract links
        links = self.extract_links(html, task.url)
        logger.info("links_extracted", url=task.url, count=len(links))
        
        # Classify and queue links
        for link in links:
            page_type = self.classify_url(link)
            priority = self.prioritize_url(link, page_type)
            
            new_task = ScrapingTask(
                url=link,
                page_type=page_type,
                priority=priority,
                metadata={
                    "discovered_from": task.url,
                    "tm_id": self.extract_transfermarkt_id(link),
                }
            )
            
            # High-value pages go to extraction queue
            if page_type in [
                PageType.CLUB_TRANSFERS,
                PageType.PLAYER_TRANSFERS,
                PageType.PLAYER_PROFILE,
            ]:
                await publish_extraction_task(new_task)
                logger.debug("queued_for_extraction", url=link, page_type=page_type)
            else:
                # Others go back to discovery for more crawling
                await publish_discovery_task(new_task)
                logger.debug("queued_for_discovery", url=link, page_type=page_type)


async def run_discovery_worker(worker_id: int):
    """Run discovery worker process."""
    logger.info("discovery_worker_starting", worker_id=worker_id)
    
    agent = DiscoveryAgent()
    await agent.start_session()
    
    try:
        qm = await get_queue_manager()
        
        # Start multiple concurrent consumers
        tasks = []
        for i in range(settings.workers.concurrent_consumers):
            consumer_tag = f"discovery_worker_{worker_id}_consumer_{i}"
            task = asyncio.create_task(
                qm.consume_tasks(
                    settings.queues.discovery_queue,
                    agent.process_task,
                    consumer_tag=consumer_tag,
                )
            )
            tasks.append(task)
            
        # Wait for all consumers
        await asyncio.gather(*tasks)
        
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("discovery_worker_stopping", worker_id=worker_id)
    finally:
        await agent.close_session()
        

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
    
    asyncio.run(run_discovery_worker(worker_id))
