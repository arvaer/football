#!/usr/bin/env python3
"""Monitor vLLM request patterns and circuit breaker status."""

import json
import sys
from collections import defaultdict, deque
from datetime import datetime
import time

def parse_log_line(line):
    """Parse a JSON log line."""
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None

def main():
    """Monitor logs for vLLM throttling events."""
    
    print("🔍 Monitoring vLLM Throttling...")
    print("=" * 60)
    print()
    
    # Stats tracking
    stats = {
        'total_requests': 0,
        'successful_requests': 0,
        'failed_requests': 0,
        'retries': 0,
        'rate_limit_waits': 0,
        'circuit_breaker_opens': 0,
        'circuit_breaker_closes': 0,
    }
    
    # Track request timing (last 100)
    request_times = deque(maxlen=100)
    
    # Track per-operation stats
    operation_stats = defaultdict(lambda: {'success': 0, 'failure': 0, 'retries': 0})
    
    circuit_breaker_open = False
    
    try:
        for line in sys.stdin:
            log = parse_log_line(line.strip())
            if not log:
                continue
            
            event = log.get('event', '')
            
            # Track LLM extraction events
            if event == 'llm_extraction_success':
                stats['successful_requests'] += 1
                stats['total_requests'] += 1
                request_times.append(time.time())
                
                page_type = log.get('page_type', 'unknown')
                operation_stats[page_type]['success'] += 1
                
                elapsed = log.get('elapsed_ms', 0)
                tokens = log.get('tokens_used', 0)
                
                print(f"✅ {page_type}: {elapsed:.0f}ms, {tokens} tokens")
                
            elif event == 'llm_extraction_error':
                stats['failed_requests'] += 1
                stats['total_requests'] += 1
                
                page_type = log.get('page_type', 'unknown')
                operation_stats[page_type]['failure'] += 1
                
                error = log.get('error', 'unknown')
                print(f"❌ {page_type}: {error[:60]}")
                
            # Track retry events
            elif event == 'llm_request_retry':
                stats['retries'] += 1
                
                operation = log.get('operation', 'unknown')
                attempt = log.get('attempt', 0)
                backoff = log.get('backoff_seconds', 0)
                error = log.get('error', '')
                
                operation_stats[operation]['retries'] += 1
                
                print(f"🔄 Retry #{attempt} for {operation}: waiting {backoff:.2f}s ({error[:40]})")
                
            # Track rate limiting
            elif event == 'rate_limit_waiting':
                stats['rate_limit_waits'] += 1
                
                wait_time = log.get('wait_time', 0)
                tokens = log.get('tokens', 0)
                
                print(f"⏳ Rate limit: waiting {wait_time:.2f}s (tokens: {tokens:.2f})")
                
            # Track circuit breaker
            elif event == 'circuit_breaker_opened':
                stats['circuit_breaker_opens'] += 1
                circuit_breaker_open = True
                
                failures = log.get('failures', 0)
                threshold = log.get('threshold', 0)
                
                print(f"🔴 CIRCUIT BREAKER OPENED: {failures}/{threshold} failures")
                print("   ⚠️  Server is likely overloaded or down!")
                
            elif event == 'circuit_breaker_half_open':
                stats['circuit_breaker_closes'] += 1
                circuit_breaker_open = False
                
                print(f"🟡 Circuit breaker half-open: testing recovery...")
                
            # Print stats every 10 successful requests
            if stats['successful_requests'] % 10 == 0 and stats['successful_requests'] > 0:
                print()
                print("=" * 60)
                print(f"📊 Stats (as of {datetime.now().strftime('%H:%M:%S')})")
                print("-" * 60)
                print(f"Total Requests:    {stats['total_requests']}")
                print(f"  ✅ Successful:   {stats['successful_requests']}")
                print(f"  ❌ Failed:       {stats['failed_requests']}")
                print(f"  🔄 Retries:      {stats['retries']}")
                print(f"  ⏳ Rate Limits:  {stats['rate_limit_waits']}")
                print(f"  🔴 CB Opens:     {stats['circuit_breaker_opens']}")
                
                # Calculate request rate
                if len(request_times) > 1:
                    time_span = request_times[-1] - request_times[0]
                    if time_span > 0:
                        rate = len(request_times) / time_span * 60
                        print(f"  📈 Current Rate: {rate:.1f} req/min")
                
                # Success rate
                if stats['total_requests'] > 0:
                    success_rate = stats['successful_requests'] / stats['total_requests'] * 100
                    print(f"  🎯 Success Rate: {success_rate:.1f}%")
                
                # Per-operation breakdown
                if operation_stats:
                    print()
                    print("Per-Operation:")
                    for op, op_stats in sorted(operation_stats.items()):
                        total = op_stats['success'] + op_stats['failure']
                        if total > 0:
                            success_pct = op_stats['success'] / total * 100
                            print(f"  {op:25s} {op_stats['success']:3d}✅ {op_stats['failure']:3d}❌ {op_stats['retries']:3d}🔄 ({success_pct:.0f}%)")
                
                print("=" * 60)
                print()
                
                if circuit_breaker_open:
                    print("⚠️  WARNING: Circuit breaker is OPEN - requests are being blocked!")
                    print()
                    
    except KeyboardInterrupt:
        print()
        print("=" * 60)
        print("📊 Final Stats")
        print("-" * 60)
        print(f"Total Requests:    {stats['total_requests']}")
        print(f"  ✅ Successful:   {stats['successful_requests']}")
        print(f"  ❌ Failed:       {stats['failed_requests']}")
        print(f"  🔄 Retries:      {stats['retries']}")
        print(f"  ⏳ Rate Limits:  {stats['rate_limit_waits']}")
        print(f"  🔴 CB Opens:     {stats['circuit_breaker_opens']}")
        if stats['total_requests'] > 0:
            success_rate = stats['successful_requests'] / stats['total_requests'] * 100
            print(f"  🎯 Success Rate: {success_rate:.1f}%")
        print("=" * 60)

if __name__ == '__main__':
    main()
