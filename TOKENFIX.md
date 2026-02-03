# Token Limit Fix - Summary

## What Was Broken

Your LLM model has a **2048 token context limit**, but the system was sending **3500-4500+ tokens**:

```
Error: "This model's maximum context length is 2048 tokens. 
However, your request has 4580 input tokens."
```

## What Changed

### 1. Window Size Reduction
```
Before: 12,000 characters per window (~3000 tokens)
After:  4,000 characters per window (~1000 tokens)
```

### 2. Token Budget Optimized
```
System Prompt:        200 tokens (condensed)
Schema:              100 tokens  
HTML Window:        1000 tokens (4000 chars)
Reserved:           648 tokens (safety margin)
─────────────────────────────────
Total:             ~1500 tokens ✓ Within 2048 limit
```

### 3. More Comprehensive Coverage
```
Before: 16-20 windows per page
After:  50-70 windows per page
        
Result: Better coverage with smaller context windows
```

## Configuration Changes

| Setting | Before | After |
|---------|--------|-------|
| `window_size` | 12,000 chars | 4,000 chars |
| `overlap` | 2,000 chars | 600 chars |
| `system_prompt` | 6 verbose rules | 1 concise line |
| `max_tokens` | 512 | 256 |

## How It Works Now

1. **Splits HTML** into 4KB chunks with 600-char overlap
2. **Processes each** within token budget (1500/2048 tokens)
3. **Merges results** with automatic deduplication
4. **Fills missing fields** from multiple windows

## Example

Processing a 200KB player profile page:

```
HTML: 195,800 characters
Splits into: 58 windows × 4,000 chars
Each window: ~1500 tokens (safe)
Processing time: Still parallel/concurrent
Result: Complete player data + all market values
```

## No More Token Errors ✓

Your scraper should now run without:
```
BadRequestError: Error code: 400 - This model's maximum context length is 2048
```

## Next Steps

Run your scraper as normal - the sliding window system is transparent and automatic:

```python
# Just use normally - sliding windows handle large pages
data = await llm.extract_structured_data(
    html_content=html,
    page_type="player_profile",
    schema_description=schema
)
```

## Fine-tuning Token Budget

See [docs/TOKEN_BUDGET.md](TOKEN_BUDGET.md) for:
- How to increase/decrease coverage
- Upgrading to larger context models
- Monitoring actual token usage
- Performance trade-offs
