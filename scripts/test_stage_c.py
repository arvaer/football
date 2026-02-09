#!/usr/bin/env python3
"""Quick test of Stage C club extraction on a few competitions."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.workers.league_tier_clubs_extractor import (
    enrich_competitions_batch,
    generate_stage_c_report,
)


async def test_stage_c():
    """Test Stage C on a few sample competitions."""
    
    # Sample competitions from different leagues
    test_competitions = [
        {
            "confederation": "amerika",
            "tier": 1,
            "competition": {
                "code": "MLS1",
                "name": "MLS",
                "url_com": "https://www.transfermarkt.com/major-league-soccer/startseite/wettbewerb/MLS1"
            },
            "country": "Major League Soccer"
        },
        {
            "confederation": "amerika",
            "tier": 2,
            "competition": {
                "code": "USL",
                "name": "USLC",
                "url_com": "https://www.transfermarkt.com/usl-championship/startseite/wettbewerb/USL"
            },
            "country": "USL Championship"
        },
        {
            "confederation": "amerika",
            "tier": 3,
            "competition": {
                "code": "USC3",
                "name": "USL1",
                "url_com": "https://www.transfermarkt.com/usl-league-one/startseite/wettbewerb/USC3"
            },
            "country": "USL League One"
        }
    ]
    
    print("\n" + "="*80)
    print("Testing Stage C: Club Statistics Extraction")
    print("="*80)
    print(f"\nProcessing {len(test_competitions)} test competitions...")
    
    # Run Stage C
    enriched = await enrich_competitions_batch(
        test_competitions,
        max_concurrent=2,
        delay_between=1.0
    )
    
    # Generate report
    report = generate_stage_c_report(enriched)
    
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    print(f"Successful: {report['successful_extractions']}/{report['total_competitions']}")
    print(f"Total clubs: {report['total_clubs_extracted']}")
    
    # Show sample data
    for row in enriched:
        comp = row['competition']
        print(f"\n{comp['name']} ({comp['code']}):")
        print(f"  Clubs: {row.get('clubs_count', 0)}")
        if row.get('summary'):
            summary = row['summary']
            print(f"  Summary - Total Squad: {summary.get('squad_size', 'N/A')}, "
                  f"Avg Age: {summary.get('average_age', 'N/A')}, "
                  f"Total Value: €{summary.get('total_market_value', 'N/A')}m")
        
        # Show first 2 clubs
        for i, club in enumerate(row.get('clubs', [])[:2], 1):
            print(f"    {i}. {club['name']}: Squad {club.get('squad_size', '?')}, "
                  f"Age {club.get('average_age', '?')}, "
                  f"Value €{club.get('total_market_value', '?')}m")
    
    # Save output
    output_dir = Path('data/extracted')
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / 'test_stage_c.jsonl'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for row in enriched:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    
    print(f"\n" + "="*80)
    print(f"Full output saved to: {output_file}")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(test_stage_c())
