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
from typing import Optional
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
from scraper.workers.league_tier_clubs_extractor import (
    enrich_competitions_batch,
    write_clubs_enriched_jsonl,
    generate_stage_c_report,
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()


# Source URLs to scrape - country-specific pages have all tier levels
SOURCE_URLS = [
    # Major European countries
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/GB", "europa", "England"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/ES", "europa", "Spain"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/IT", "europa", "Italy"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/L1", "europa", "Germany"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/FR", "europa", "France"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/PO", "europa", "Portugal"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/TR", "europa", "Turkey"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/NL", "europa", "Netherlands"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/RU", "europa", "Russia"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/BE", "europa", "Belgium"),
    
    # Americas
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/BR", "amerika", "Brazil"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/AR", "amerika", "Argentina"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/MX", "amerika", "Mexico"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/US", "amerika", "United States"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/CO", "amerika", "Colombia"),
    ("https://www.transfermarkt.us/wettbewerbe/national/wettbewerbe/CL", "amerika", "Chile"),
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
    
    for url_tuple in SOURCE_URLS:
        url, confederation, country = url_tuple
        try:
            # Fetch HTML
            html = await fetch_html(url)
            
            # Extract competitions
            rows = extract_league_index_rows(html, url)
            
            # Override confederation and country from our known list
            for row in rows:
                row['confederation'] = confederation
                if not row.get('country'):
                    row['country'] = country
            
            all_rows.extend(rows)
            
            logger.info("extracted_from_url",
                       url=url,
                       country=country,
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


async def run_stage_b(stage_a_rows: list) -> Optional[Path]:
    """Run Stage B: LLM enrichment (stub).
    
    Args:
        stage_a_rows: Rows from Stage A
        
    Returns:
        Path to Stage B output or None if failed
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


async def run_stage_c(stage_ab_rows: list, max_concurrent: int = 3) -> Optional[Path]:
    """Run Stage C: Club statistics extraction.
    
    Args:
        stage_ab_rows: Rows from Stage A or B
        max_concurrent: Maximum concurrent requests to Transfermarkt
        
    Returns:
        Path to Stage C output or None if failed
    """
    logger.info("=== STAGE C: Club Statistics Extraction ===")
    
    try:
        # Enrich competitions with club stats
        enriched_rows = await enrich_competitions_batch(
            stage_ab_rows,
            max_concurrent=max_concurrent,
            delay_between=1.0
        )
        
        # Write Stage C output
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        output_dir = Path('data/extracted')
        output_path = output_dir / f'league_clubs_enriched_{date_str}.jsonl'
        
        write_clubs_enriched_jsonl(output_path, enriched_rows)
        
        # Generate and display report
        report = generate_stage_c_report(enriched_rows)
        logger.info("stage_c_complete", **report)
        
        print("\n" + "="*60)
        print("STAGE C REPORT")
        print("="*60)
        print(f"Total competitions processed: {report['total_competitions']}")
        print(f"Successful extractions: {report['successful_extractions']}")
        print(f"Failed extractions: {report['failed_extractions']}")
        print(f"Success rate: {report['success_rate']}%")
        print(f"\nTotal clubs extracted: {report['total_clubs_extracted']}")
        print(f"Competitions with summary: {report['competitions_with_summary']}")
        print(f"\nBy tier:")
        for tier, stats in report['by_tier'].items():
            print(f"  Tier {tier}: {stats['competitions']} competitions, "
                  f"{stats['total_clubs']} clubs "
                  f"(avg {stats['avg_clubs_per_competition']} per competition)")
        print(f"\nOutput written to: {output_path}")
        print("="*60 + "\n")
        
        return output_path
        
    except Exception as e:
        logger.error("stage_c_failed",
                    error=str(e),
                    exc_info=True)
        return None


async def main():
    """Run the complete league tier extraction pipeline."""
    logger.info("starting_league_tier_extraction_pipeline")
    
    start_time = datetime.utcnow()
    
    # Run Stage A (deterministic)
    stage_a_path, stage_a_rows = await run_stage_a()
    
    # Run Stage B (enrichment) - non-blocking
    stage_b_path = await run_stage_b(stage_a_rows)
    
    # Use Stage B output if available, otherwise use Stage A
    rows_for_stage_c = stage_a_rows  # We'll use Stage A for now since B is stub
    
    # Run Stage C (club statistics) - optional but recommended
    print("\nStage C will fetch each competition page to extract club statistics.")
    print("This will make HTTP requests to Transfermarkt (respectfully, with delays).")
    print(f"Estimated time: ~{len(stage_a_rows) * 1.5 / 60:.1f} minutes for {len(stage_a_rows)} competitions")
    
    # For testing, you might want to limit this
    # Uncomment to process only first N competitions:
    # rows_for_stage_c = stage_a_rows[:10]
    
    stage_c_path = await run_stage_c(rows_for_stage_c, max_concurrent=3)
    
    # Final summary
    end_time = datetime.utcnow()
    duration = (end_time - start_time).total_seconds()
    
    print("\n" + "="*60)
    print("PIPELINE COMPLETE")
    print("="*60)
    print(f"Duration: {duration:.2f} seconds ({duration/60:.1f} minutes)")
    print(f"Stage A output: {stage_a_path}")
    if stage_b_path:
        print(f"Stage B output: {stage_b_path}")
    else:
        print(f"Stage B: Failed (Stage A is still valid)")
    if stage_c_path:
        print(f"Stage C output: {stage_c_path}")
    else:
        print(f"Stage C: Failed or skipped")
    print(f"\nNext steps:")
    print(f"  1. Review {stage_c_path if stage_c_path else stage_a_path}")
    print(f"  2. Verify club statistics are accurate")
    print(f"  3. Use this data for analysis or further processing")
    print("="*60 + "\n")
    
    logger.info("pipeline_complete", 
               duration_seconds=duration,
               stage_a_output=str(stage_a_path),
               stage_b_output=str(stage_b_path) if stage_b_path else None,
               stage_c_output=str(stage_c_path) if stage_c_path else None)


if __name__ == "__main__":
    asyncio.run(main())
