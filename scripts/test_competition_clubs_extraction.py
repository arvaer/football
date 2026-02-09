#!/usr/bin/env python3
"""Test script for competition clubs extraction.

This script tests the parse_competition_clubs function on a sample URL.

Usage:
    python scripts/test_competition_clubs_extraction.py [URL]
    
Example:
    python scripts/test_competition_clubs_extraction.py https://www.transfermarkt.us/major-league-soccer/startseite/wettbewerb/MLS1
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional
import httpx
import structlog

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.extractors.transfermarkt_bs import parse_competition_clubs

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def fetch_html(url: str) -> str:
    """Fetch HTML from URL with proper headers."""
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


async def main(url: Optional[str] = None):
    """Test competition clubs extraction."""
    
    # Default URL if none provided
    if not url:
        url = "https://www.transfermarkt.us/major-league-soccer/startseite/wettbewerb/MLS1"
    
    print(f"\n{'='*80}")
    print(f"Testing Competition Clubs Extraction")
    print(f"{'='*80}")
    print(f"URL: {url}\n")
    
    try:
        # Fetch HTML
        html = await fetch_html(url)
        
        # Extract competition clubs data
        result = parse_competition_clubs(html, url)
        
        # Display results
        print(f"\n{'='*80}")
        print(f"EXTRACTION RESULTS")
        print(f"{'='*80}")
        print(f"\nCompetition: {result['competition']['name']} ({result['competition']['code']})")
        print(f"Total clubs: {len(result['clubs'])}")
        print(f"Has summary: {bool(result['summary'])}")
        
        # Display first few clubs
        print(f"\n{'-'*80}")
        print(f"CLUBS (showing first 10):")
        print(f"{'-'*80}")
        for i, club in enumerate(result['clubs'][:10], 1):
            print(f"\n{i}. {club.get('name', 'N/A')}")
            if club.get('tm_id'):
                print(f"   ID: {club['tm_id']}")
            if club.get('squad_size') is not None:
                print(f"   Squad: {club['squad_size']}")
            if club.get('average_age') is not None:
                print(f"   Avg Age: {club['average_age']}")
            if club.get('foreigners') is not None:
                print(f"   Foreigners: {club['foreigners']}")
            if club.get('average_market_value') is not None:
                print(f"   Avg Market Value: {club.get('average_market_value_currency', '€')}{club['average_market_value']}")
            if club.get('total_market_value') is not None:
                print(f"   Total Market Value: {club.get('total_market_value_currency', '€')}{club['total_market_value']}")
        
        # Display summary if available
        if result['summary']:
            print(f"\n{'-'*80}")
            print(f"SUMMARY TOTALS:")
            print(f"{'-'*80}")
            summary = result['summary']
            if summary.get('squad_size') is not None:
                print(f"Total Squad: {summary['squad_size']}")
            if summary.get('average_age') is not None:
                print(f"Overall Avg Age: {summary['average_age']}")
            if summary.get('foreigners') is not None:
                print(f"Total Foreigners: {summary['foreigners']}")
            if summary.get('average_market_value') is not None:
                print(f"Avg Market Value: {summary.get('average_market_value_currency', '€')}{summary['average_market_value']}")
            if summary.get('total_market_value') is not None:
                print(f"Total Market Value: {summary.get('total_market_value_currency', '€')}{summary['total_market_value']}")
        
        # Save to JSON file
        output_dir = Path('data/extracted')
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / 'test_competition_clubs.json'
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'-'*80}")
        print(f"Full results saved to: {output_file}")
        print(f"{'='*80}\n")
        
    except Exception as e:
        logger.error("extraction_failed", error=str(e), exc_info=True)
        print(f"\nERROR: {e}\n")
        return 1
    
    return 0


if __name__ == "__main__":
    # Get URL from command line if provided
    url = sys.argv[1] if len(sys.argv) > 1 else None
    exit_code = asyncio.run(main(url))
    sys.exit(exit_code)
