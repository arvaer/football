#!/usr/bin/env python3
"""Standalone runner for league tier extraction pipeline.

This script runs the league tier firehose independently from the main scraping workers.

Usage:
    python scripts/run_league_tier_extraction.py
    
Output:
    - data/extracted/league_index_rows_YYYY-MM-DD.jsonl (Stage A)
    - data/extracted/league_index_enriched_YYYY-MM-DD.jsonl (Stage B)
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
import httpx
import structlog

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.workers.league_tier_extractor import (
    extract_league_index_rows,
    write_jsonl,
    generate_stage_a_report,
)
from scraper.workers.league_tier_enricher import (
    enrich_competition_batch,
    write_enriched_jsonl,
    generate_stage_b_report,
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()


# Source URLs to scrape
SOURCE_URLS = [
    "https://www.transfermarkt.us/wettbewerbe/europa",
    "https://www.transfermarkt.us/wettbewerbe/amerika",
]

# User agent for requests
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


async def fetch_html(url: str) -> str:
    """Fetch HTML from URL with proper headers.
    
    Args:
        url: URL to fetch
        
    Returns:
        HTML content as string
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    logger.info("fetching_url", url=url)
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        
        logger.info("fetched_successfully", 
                   url=url, 
                   status=response.status_code,
                   size_kb=len(response.text) // 1024)
        
        return response.text


async def run_stage_a() -> tuple[Path, list]:
    """Run Stage A: deterministic extraction.
    
    Returns:
        Tuple of (output_path, all_rows)
    """
    logger.info("=== STAGE A: Deterministic Extraction ===")
    
    all_rows = []
    
    for url in SOURCE_URLS:
        try:
            # Fetch HTML
            html = await fetch_html(url)
            
            # Extract competitions
            rows = extract_league_index_rows(html, url)
            all_rows.extend(rows)
            
            logger.info("extracted_from_url",
                       url=url,
                       competitions=len(rows))
            
        except Exception as e:
            logger.error("extraction_failed",
                        url=url,
                        error=str(e),
                        exc_info=True)
            continue
    
    # Write Stage A output
    date_str = datetime.utcnow().strftime('%Y-%m-%d')
    output_dir = Path('data/extracted')
    output_path = output_dir / f'league_index_rows_{date_str}.jsonl'
    
    write_jsonl(output_path, all_rows)
    
    # Generate and display report
    report = generate_stage_a_report(all_rows)
    logger.info("stage_a_complete", **report)
    
    print("\n" + "="*60)
    print("STAGE A REPORT")
    print("="*60)
    print(f"Total competitions extracted: {report['total_competitions']}")
    print(f"\nBy confederation:")
    for conf, count in report['by_confederation'].items():
        print(f"  {conf}: {count}")
    print(f"\nBy tier:")
    for tier, count in report['by_tier'].items():
        print(f"  Tier {tier}: {count}")
    print(f"\nTop countries:")
    for country, count in list(report['by_country'].items())[:10]:
        print(f"  {country}: {count}")
    print(f"\nOutput written to: {output_path}")
    print("="*60 + "\n")
    
    return output_path, all_rows


async def run_stage_b(stage_a_rows: list) -> Path:
    """Run Stage B: LLM enrichment (stub).
    
    Args:
        stage_a_rows: Rows from Stage A
        
    Returns:
        Path to Stage B output
    """
    logger.info("=== STAGE B: LLM Enrichment (STUB) ===")
    
    try:
        # Enrich competitions (stub implementation)
        enriched_rows = enrich_competition_batch(stage_a_rows, llm_model="stub-heuristic")
        
        # Write Stage B output
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        output_dir = Path('data/extracted')
        output_path = output_dir / f'league_index_enriched_{date_str}.jsonl'
        
        write_enriched_jsonl(output_path, enriched_rows)
        
        # Generate and display report
        report = generate_stage_b_report(enriched_rows)
        logger.info("stage_b_complete", **report)
        
        print("\n" + "="*60)
        print("STAGE B REPORT (STUB)")
        print("="*60)
        print(f"Total competitions enriched: {report['total_enriched']}")
        print(f"\nBy competition kind:")
        for kind, count in report['by_competition_kind'].items():
            print(f"  {kind}: {count}")
        print(f"\nFlagged anomalies: {report['flagged_anomalies']}")
        if report['flags_summary']:
            print(f"Flags breakdown:")
            for flag, count in report['flags_summary'].items():
                print(f"  {flag}: {count}")
        print(f"\nOutput written to: {output_path}")
        print(f"\nNOTE: Stage B is currently using stub heuristics.")
        print(f"      Replace with actual LLM when ready.")
        print("="*60 + "\n")
        
        return output_path
        
    except Exception as e:
        logger.error("stage_b_failed",
                    error=str(e),
                    exc_info=True)
        logger.warning("stage_b_nonblocking", 
                      message="Stage A output is still valid system of record")
        return None


async def main():
    """Run the complete league tier extraction pipeline."""
    logger.info("starting_league_tier_extraction_pipeline")
    
    start_time = datetime.utcnow()
    
    # Run Stage A (deterministic)
    stage_a_path, stage_a_rows = await run_stage_a()
    
    # Run Stage B (enrichment) - non-blocking
    stage_b_path = await run_stage_b(stage_a_rows)
    
    # Final summary
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "="*60)
    print("PIPELINE COMPLETE")
    print("="*60)
    print(f"Duration: {duration:.2f} seconds")
    print(f"Stage A output: {stage_a_path}")
    if stage_b_path:
        print(f"Stage B output: {stage_b_path}")
    else:
        print(f"Stage B: Failed (Stage A is still valid)")
    print(f"\nNext steps:")
    print(f"  1. Review {stage_a_path}")
    print(f"  2. Verify tier assignments are correct")
    print(f"  3. Check URL normalization to .com")
    print(f"  4. Implement actual LLM enrichment in Stage B")
    print("="*60 + "\n")
    
    logger.info("pipeline_complete", 
               duration_seconds=duration,
               stage_a_output=str(stage_a_path),
               stage_b_output=str(stage_b_path) if stage_b_path else None)


if __name__ == "__main__":
    asyncio.run(main())
