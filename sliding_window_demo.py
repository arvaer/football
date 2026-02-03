#!/usr/bin/env python3
"""
Demo showing the sliding window extraction feature.

This demonstrates how the LLMClient can process large HTML files
by breaking them into overlapping windows.
"""

import asyncio
from scraper.llm_client import LLMClient
from scraper.models import PageType

# Example HTML (normally much larger)
EXAMPLE_HTML = """
<html>
<head><title>Player Profile - John Doe</title></head>
<body>
  <div class="player-profile">
    <h1>John Doe</h1>
    <div class="info-block">
      <span class="label">Date of Birth:</span>
      <span class="value">1995-05-15</span>
    </div>
    <div class="info-block">
      <span class="label">Nationality:</span>
      <span class="value">German</span>
    </div>
    <div class="info-block">
      <span class="label">Position:</span>
      <span class="value">Center Back</span>
    </div>
    <div class="info-block">
      <span class="label">Height:</span>
      <span class="value">185 cm</span>
    </div>
    <div class="market-value">
      <h3>Market Value History</h3>
      <table>
        <tr>
          <td class="date">2024-01-15</td>
          <td class="value">€5.5M</td>
        </tr>
        <tr>
          <td class="date">2023-06-20</td>
          <td class="value">€4.8M</td>
        </tr>
      </table>
    </div>
  </div>
</body>
</html>
"""


async def demo_window_creation():
    """Demonstrate window creation."""
    client = LLMClient()
    
    # Create large HTML by repeating content
    large_html = EXAMPLE_HTML * 200  # ~200KB of content
    
    print(f"\n=== SLIDING WINDOW DEMO ===")
    print(f"Total HTML size: {len(large_html):,} characters")
    print(f"Window size: {client.window_size:,} characters")
    print(f"Overlap: {client.overlap:,} characters")
    print(f"Step size: {client.window_size - client.overlap:,} characters")
    
    windows = client._create_sliding_windows(large_html)
    
    print(f"\nGenerated {len(windows)} windows:")
    for i, window in enumerate(windows):
        print(f"  Window {i+1}: {len(window):,} characters")
    
    print("\nBenefits of sliding windows:")
    print("  ✓ Process entire HTML files regardless of size")
    print("  ✓ Overlap between windows preserves context continuity")
    print("  ✓ Automatic deduplication of extracted data")
    print("  ✓ Robust to page structure variations")
    

async def demo_result_merging():
    """Demonstrate result merging."""
    client = LLMClient()
    
    results = [
        {
            "player": {
                "name": "John Doe",
                "date_of_birth": "1995-05-15",
                "position": "CB",
                "tm_id": "123456"
            },
            "market_values": [
                {"date": "2024-01-15", "value": 5.5, "currency": "EUR"}
            ]
        },
        {
            "player": {
                "name": "John Doe",  # Duplicate
                "nationality": "German",
                "height_cm": 185,
                "tm_id": "123456"  # Same player
            },
            "market_values": [
                {"date": "2023-06-20", "value": 4.8, "currency": "EUR"}
            ]
        }
    ]
    
    print(f"\n=== RESULT MERGING DEMO ===")
    print(f"Results from {len(results)} windows:")
    for i, result in enumerate(results, 1):
        print(f"\n  Window {i}:")
        import json
        print(f"    {json.dumps(result, indent=6)}")
    
    merged = client._merge_extraction_results(results)
    
    print(f"\nMerged result (deduplicated):")
    import json
    print(json.dumps(merged, indent=2))


if __name__ == "__main__":
    print("Sliding Window Processing Demo")
    print("=" * 50)
    
    asyncio.run(demo_window_creation())
    asyncio.run(demo_result_merging())
    
    print("\n" + "=" * 50)
    print("Usage in extraction_worker.py:")
    print("""
    # Automatically uses sliding windows for large HTML
    data = await llm.extract_structured_data(
        html_content=huge_html_file,
        page_type="player_profile",
        schema_description=schema,
        use_sliding_window=True  # Enable sliding windows
    )
    
    # Or disable for small content
    data = await llm.extract_structured_data(
        html_content=small_html,
        page_type="player_profile",
        schema_description=schema,
        use_sliding_window=False
    )
    """)
