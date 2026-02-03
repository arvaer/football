#!/usr/bin/env python3
"""
Build club name normalization cache using vLLM.

This script scans all scraped data, extracts unique club names,
and uses the LLM to build a normalization mapping that handles
variants like "AC Le Havre" vs "Le Havre AC".

Run this once after scraping to generate the normalization cache.
"""

import asyncio
import json
from pathlib import Path
import structlog

from graph_builder.llm_normalizer import normalize_club_names_from_data

logger = structlog.get_logger()


async def main():
    """Build club name normalization cache."""
    logger.info("building_club_normalization_cache")
    
    # Check if vLLM is running
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(base_url="http://localhost:8000/v1", api_key="token")
        models = await client.models.list()
        logger.info("vllm_connection_ok", models=[m.id for m in models.data])
    except Exception as e:
        logger.error(
            "vllm_connection_failed",
            error=str(e),
            hint="Make sure vLLM server is running: make vllm or ./scripts/start_vllm.sh"
        )
        return
    
    # Build normalization cache
    cache = await normalize_club_names_from_data("data/extracted")
    
    # Save to file
    cache_file = Path("data/club_normalization_cache.json")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(cache_file, 'w') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    
    logger.info("normalization_cache_saved", 
                path=str(cache_file),
                entries=len(cache))
    
    # Print some examples
    print("\n=== Sample Normalizations ===")
    sample_items = list(cache.items())[:20]
    for variant, canonical in sample_items:
        if variant != canonical:
            print(f"  {variant:40} → {canonical}")
    
    print(f"\nTotal club variants: {len(cache)}")
    print(f"Unique canonical clubs: {len(set(cache.values()))}")
    print(f"Cache saved to: {cache_file}")


if __name__ == "__main__":
    asyncio.run(main())
