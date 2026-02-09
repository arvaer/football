"""Stage C: Club statistics extraction for competitions.

This module takes Stage A/B JSONL output (competition metadata) and enriches each
competition with detailed club statistics by:
1. Fetching each competition's page
2. Extracting club-level stats (squad size, age, foreigners, market values)
3. Including summary totals

Output includes all Stage A/B fields plus detailed club data.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import asyncio
import httpx
import structlog

from scraper.extractors.transfermarkt_bs import parse_competition_clubs

logger = structlog.get_logger()

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def fetch_html(url: str, session: httpx.AsyncClient) -> Optional[str]:
    """Fetch HTML from URL with proper headers.
    
    Args:
        url: URL to fetch
        session: httpx async client session
        
    Returns:
        HTML content as string or None if failed
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    try:
        response = await session.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error("fetch_failed", url=url, error=str(e))
        return None


async def enrich_competition_with_clubs(
    competition_row: Dict[str, Any],
    session: httpx.AsyncClient
) -> Dict[str, Any]:
    """Enrich a single competition row with club statistics.
    
    Args:
        competition_row: Row from Stage A/B with competition metadata
        session: httpx async client session
        
    Returns:
        Enriched row with clubs data added
    """
    # Start with the original row
    enriched = competition_row.copy()
    
    # Get competition URL (prefer url_com for consistency)
    competition_data = competition_row.get('competition', {})
    url = competition_data.get('url_com') or competition_data.get('url_path')
    
    if not url:
        logger.warning("no_competition_url", competition=competition_data)
        return enriched
    
    # Ensure full URL
    if not url.startswith('http'):
        url = f"https://www.transfermarkt.us{url}"
    
    logger.info("fetching_competition_clubs",
               code=competition_data.get('code'),
               name=competition_data.get('name'),
               url=url)
    
    # Fetch HTML
    html = await fetch_html(url, session)
    if not html:
        enriched['clubs_extraction_failed'] = True
        return enriched
    
    # Extract club stats
    try:
        clubs_data = parse_competition_clubs(html, url)
        
        # Add clubs and summary to enriched row
        enriched['clubs'] = clubs_data.get('clubs', [])
        enriched['summary'] = clubs_data.get('summary', {})
        enriched['clubs_count'] = len(clubs_data.get('clubs', []))
        enriched['clubs_extracted_at'] = datetime.utcnow().isoformat() + 'Z'
        
        logger.info("extracted_clubs",
                   code=competition_data.get('code'),
                   clubs_count=enriched['clubs_count'],
                   has_summary=bool(enriched['summary']))
        
    except Exception as e:
        logger.error("extraction_failed",
                    code=competition_data.get('code'),
                    url=url,
                    error=str(e),
                    exc_info=True)
        enriched['clubs_extraction_error'] = str(e)
    
    return enriched


async def enrich_competitions_batch(
    stage_ab_rows: List[Dict[str, Any]],
    max_concurrent: int = 5,
    delay_between: float = 1.0
) -> List[Dict[str, Any]]:
    """Enrich multiple competitions with club statistics.
    
    Args:
        stage_ab_rows: Rows from Stage A/B
        max_concurrent: Maximum concurrent requests
        delay_between: Delay in seconds between batches
        
    Returns:
        List of enriched rows with club data
    """
    enriched_rows = []
    
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=max_concurrent)
    ) as session:
        
        # Process in batches to be respectful
        for i in range(0, len(stage_ab_rows), max_concurrent):
            batch = stage_ab_rows[i:i + max_concurrent]
            
            logger.info("processing_batch",
                       batch_start=i,
                       batch_size=len(batch),
                       total=len(stage_ab_rows))
            
            # Process batch concurrently
            tasks = [
                enrich_competition_with_clubs(row, session)
                for row in batch
            ]
            batch_results = await asyncio.gather(*tasks)
            enriched_rows.extend(batch_results)
            
            # Delay between batches
            if i + max_concurrent < len(stage_ab_rows):
                await asyncio.sleep(delay_between)
    
    return enriched_rows


def write_clubs_enriched_jsonl(output_path: Path, enriched_rows: List[Dict[str, Any]]) -> None:
    """Write Stage C output to JSONL file.
    
    Args:
        output_path: Path to output JSONL file
        enriched_rows: Enriched competition rows with club data
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for row in enriched_rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    
    logger.info("wrote_clubs_enriched_jsonl",
               path=str(output_path),
               rows=len(enriched_rows))


def generate_stage_c_report(enriched_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary report for Stage C extraction.
    
    Args:
        enriched_rows: Enriched competition rows
        
    Returns:
        Dictionary with summary statistics
    """
    total_competitions = len(enriched_rows)
    successful_extractions = sum(1 for row in enriched_rows if 'clubs' in row and row['clubs'])
    failed_extractions = sum(1 for row in enriched_rows if row.get('clubs_extraction_failed') or row.get('clubs_extraction_error'))
    
    total_clubs = sum(row.get('clubs_count', 0) for row in enriched_rows)
    competitions_with_summary = sum(1 for row in enriched_rows if row.get('summary'))
    
    # Stats by tier
    by_tier = {}
    for row in enriched_rows:
        tier = row.get('tier', 'unknown')
        if tier not in by_tier:
            by_tier[tier] = {
                'competitions': 0,
                'total_clubs': 0,
                'avg_clubs_per_competition': 0
            }
        by_tier[tier]['competitions'] += 1
        by_tier[tier]['total_clubs'] += row.get('clubs_count', 0)
    
    # Calculate averages
    for tier_data in by_tier.values():
        if tier_data['competitions'] > 0:
            tier_data['avg_clubs_per_competition'] = round(
                tier_data['total_clubs'] / tier_data['competitions'], 1
            )
    
    return {
        "total_competitions": total_competitions,
        "successful_extractions": successful_extractions,
        "failed_extractions": failed_extractions,
        "success_rate": round(successful_extractions / total_competitions * 100, 1) if total_competitions > 0 else 0,
        "total_clubs_extracted": total_clubs,
        "competitions_with_summary": competitions_with_summary,
        "by_tier": dict(sorted(by_tier.items())),
    }
