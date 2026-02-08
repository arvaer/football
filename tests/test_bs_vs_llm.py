"""Quick test of BS extraction vs LLM extraction.

This script:
1. Fetches a sample page
2. Extracts with BS
3. Extracts with LLM
4. Compares key fields
"""

import asyncio
import json
from scraper.workers.extraction_worker import ExtractionAgent
from scraper.models import PageType
from scraper.workers.discovery_worker import DiscoveryAgent


async def test_extraction():
    """Test BS vs LLM extraction."""
    
    # Test URLs
    test_cases = [
        {
            "url": "https://www.transfermarkt.com/manchester-city/transfers/verein/281",
            "page_type": PageType.CLUB_TRANSFERS,
            "name": "Manchester City Transfers",
        },
        {
            "url": "https://www.transfermarkt.com/erling-haaland/profil/spieler/418560",
            "page_type": PageType.PLAYER_PROFILE,
            "name": "Erling Haaland Profile",
        },
    ]
    
    agent = ExtractionAgent()
    discovery = DiscoveryAgent()
    await discovery.start_session()
    
    try:
        for test_case in test_cases:
            print(f"\n{'='*80}")
            print(f"Testing: {test_case['name']}")
            print(f"URL: {test_case['url']}")
            print(f"{'='*80}")
            
            # Fetch HTML
            html = await discovery.fetch_page(test_case['url'])
            if not html:
                print(f"❌ Failed to fetch {test_case['url']}")
                continue
            
            print(f"✓ Fetched {len(html)} chars")
            
            # Extract with BS
            print("\n--- BS Extraction ---")
            bs_result = await agent.extract_from_page_bs(
                html,
                test_case['url'],
                test_case['page_type']
            )
            
            print(f"Success: {bs_result.success}")
            if bs_result.success:
                print(f"Backend: {bs_result.extraction_backend}")
                print(f"Players: {len(bs_result.players)}")
                print(f"Clubs: {len(bs_result.clubs)}")
                print(f"Transfers: {len(bs_result.transfers)}")
                if bs_result.validation:
                    print(f"Validation warnings: {len(bs_result.validation.get('warnings', []))}")
                    if bs_result.validation.get('warnings'):
                        for warning in bs_result.validation['warnings'][:3]:
                            print(f"  - {warning}")
                
                # Show sample data
                print("\nSample data:")
                print(json.dumps(bs_result.data, indent=2)[:500])
            else:
                print(f"Error: {bs_result.error}")
            
            # Extract with LLM (for comparison)
            print("\n--- LLM Extraction ---")
            llm_result = await agent.extract_from_page_llm(
                html,
                test_case['url'],
                test_case['page_type']
            )
            
            print(f"Success: {llm_result.success}")
            if llm_result.success:
                print(f"Backend: {llm_result.extraction_backend}")
                print(f"Players: {len(llm_result.players)}")
                print(f"Clubs: {len(llm_result.clubs)}")
                print(f"Transfers: {len(llm_result.transfers)}")
                
                # Show sample data
                print("\nSample data:")
                print(json.dumps(llm_result.data, indent=2)[:500])
            else:
                print(f"Error: {llm_result.error}")
            
            # Compare
            if bs_result.success and llm_result.success:
                print("\n--- Comparison ---")
                
                # Compare counts
                if test_case['page_type'] == PageType.CLUB_TRANSFERS:
                    bs_count = len(bs_result.transfers)
                    llm_count = len(llm_result.transfers)
                    print(f"Transfer count - BS: {bs_count}, LLM: {llm_count}, Diff: {abs(bs_count - llm_count)}")
                    
                    # Compare first transfer (if exists)
                    if bs_result.transfers and llm_result.transfers:
                        bs_first = bs_result.transfers[0]
                        llm_first = llm_result.transfers[0]
                        
                        print("\nFirst transfer comparison:")
                        print(f"  Player - BS: {bs_first.player_name}, LLM: {llm_first.player_name}")
                        
                        if bs_first.fee and llm_first.fee:
                            print(f"  Fee - BS: {bs_first.fee.amount}{bs_first.fee.currency}")
                            print(f"  Fee - LLM: {llm_first.fee.amount}{llm_first.fee.currency}")
                
                elif test_case['page_type'] == PageType.PLAYER_PROFILE:
                    if bs_result.players and llm_result.players:
                        bs_player = bs_result.players[0]
                        llm_player = llm_result.players[0]
                        
                        print("\nPlayer comparison:")
                        print(f"  Name - BS: {bs_player.name}, LLM: {llm_player.name}")
                        print(f"  ID - BS: {bs_player.tm_id}, LLM: {llm_player.tm_id}")
                        print(f"  Position - BS: {bs_player.position}, LLM: {llm_player.position}")
                        print(f"  Height - BS: {bs_player.height_cm}, LLM: {llm_player.height_cm}")
            
            # Wait between tests
            await asyncio.sleep(2)
    
    finally:
        await discovery.close_session()


if __name__ == "__main__":
    print("BS vs LLM Extraction Test")
    print("=" * 80)
    print("\nThis will fetch and extract pages using both methods.")
    print("Make sure vLLM is running for LLM extraction to work.")
    print("\nStarting test...\n")
    
    asyncio.run(test_extraction())
    
    print("\n" + "=" * 80)
    print("Test complete!")
