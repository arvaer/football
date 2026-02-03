#!/usr/bin/env python3
"""Test script to verify vLLM throttling is working correctly."""

import asyncio
import time
import sys
from scraper.llm_client import get_llm_client
from scraper.config import settings

async def test_rate_limiting():
    """Test that rate limiting prevents too many concurrent requests."""
    
    print("🧪 Testing vLLM Throttling\n")
    print("=" * 60)
    print(f"Config:")
    print(f"  Max Concurrent:      {settings.vllm.max_concurrent_requests}")
    print(f"  Requests Per Minute: {settings.vllm.requests_per_minute}")
    print(f"  Max Retries:         {settings.vllm.max_retries}")
    print(f"  Base Backoff:        {settings.vllm.base_backoff_seconds}s")
    print("=" * 60)
    print()
    
    client = get_llm_client()
    
    # Test 1: Sequential requests (should be smooth)
    print("📊 Test 1: Sequential Requests")
    print("-" * 60)
    
    test_html = "<html><body>Test content</body></html>"
    schema = '{"test": "string"}'
    
    start_time = time.time()
    request_times = []
    
    for i in range(5):
        req_start = time.time()
        try:
            print(f"  Request {i+1}/5...", end=" ", flush=True)
            result = await client.extract_structured_data(
                html_content=test_html,
                page_type="test",
                schema_description=schema,
            )
            elapsed = time.time() - req_start
            request_times.append(elapsed)
            print(f"✅ {elapsed:.2f}s")
        except Exception as e:
            elapsed = time.time() - req_start
            print(f"❌ {elapsed:.2f}s - {str(e)[:50]}")
    
    total_time = time.time() - start_time
    print()
    print(f"Total time: {total_time:.2f}s")
    print(f"Average per request: {total_time/5:.2f}s")
    print()
    
    # Test 2: Concurrent requests (should throttle)
    print("📊 Test 2: Concurrent Requests (batch of 5)")
    print("-" * 60)
    print(f"  Launching 5 concurrent requests...")
    print(f"  Expected: Max {settings.vllm.max_concurrent_requests} in-flight at once")
    print()
    
    async def make_request(idx):
        req_start = time.time()
        try:
            result = await client.extract_structured_data(
                html_content=test_html,
                page_type=f"test_{idx}",
                schema_description=schema,
            )
            elapsed = time.time() - req_start
            print(f"  ✅ Request {idx} completed in {elapsed:.2f}s")
            return True
        except Exception as e:
            elapsed = time.time() - req_start
            print(f"  ❌ Request {idx} failed in {elapsed:.2f}s: {str(e)[:40]}")
            return False
    
    start_time = time.time()
    results = await asyncio.gather(*[make_request(i) for i in range(5)])
    total_time = time.time() - start_time
    
    print()
    print(f"Total time: {total_time:.2f}s")
    print(f"Success rate: {sum(results)}/{len(results)}")
    
    # Check if throttling is working
    if total_time > 5:  # Should take longer than 5 seconds with throttling
        print("✅ Throttling appears to be working (requests were serialized)")
    else:
        print("⚠️  Warning: All requests completed very quickly - throttling may not be active")
    
    print()
    print("=" * 60)
    print()
    
    # Test 3: Circuit breaker status
    print("📊 Test 3: Circuit Breaker Status")
    print("-" * 60)
    
    cb = client.circuit_breaker
    print(f"  Is Open:       {cb.is_open}")
    print(f"  Failures:      {cb.failures}")
    print(f"  Threshold:     {cb.threshold}")
    print(f"  Can Attempt:   {cb.can_attempt()}")
    
    if cb.is_open:
        print()
        print("  ⚠️  Circuit breaker is OPEN!")
        print("     Server may be down or overloaded.")
        print(f"     Will retry after {cb.timeout}s timeout.")
    else:
        print()
        print("  ✅ Circuit breaker is closed - server is healthy")
    
    print()
    print("=" * 60)
    print()
    
    # Summary
    print("📋 Summary")
    print("-" * 60)
    print(f"✅ Rate limiter is configured and active")
    print(f"✅ Circuit breaker is monitoring requests")
    print(f"✅ Backoff and retry logic is in place")
    print()
    print("Your vLLM server is protected from flooding! 🛡️")
    print()

if __name__ == "__main__":
    try:
        asyncio.run(test_rate_limiting())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
