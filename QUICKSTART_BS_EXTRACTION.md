# Quick Start Guide - BeautifulSoup Extraction

## Test the Implementation

### 1. Run Determinism Tests
```bash
cd /home/galo/all_fb/fb
python tests/test_determinism.py
```

Expected output:
```
✓ PLAYER_PROFILE: deterministic=True, markers=True
✓ PLAYER_TRANSFERS: deterministic=True, markers=True
✓ CLUB_TRANSFERS: deterministic=True, markers=True
✓ CLUB_PROFILE: deterministic=True, markers=True
```

### 2. Test BS vs LLM Extraction
```bash
# Make sure vLLM is running
python tests/test_bs_vs_llm.py
```

This will:
- Fetch sample Transfermarkt pages
- Extract with BS (deterministic)
- Extract with LLM (for comparison)
- Show comparison of results

### 3. Enable BS Extraction (Test Mode)

Edit your `.env` file or export environment variables:

```bash
# Enable BS for club transfers only (safest test)
export USE_BS_EXTRACTORS=true
export USE_BS_EXTRACTORS_FOR="club_transfers"
export BS_FALLBACK_TO_LLM=true
export ENABLE_LLM_VALIDATION=true
```

Or copy the example:
```bash
cp .env.bs_extraction_example .env.local
# Edit .env.local with your settings
```

### 4. Run Extraction Worker

```bash
# Start the extraction worker
python -m scraper.workers.extraction_worker 0
```

Monitor logs for:
- `ROUTING: Using BS extraction for club_transfers`
- `BS: Extracting club_transfers from...`
- `bs_extraction_success`

### 5. Check Output Files

```bash
# View latest extractions
ls -lh data/extracted/

# Check extraction backend used
jq '.extraction_backend' data/extracted/club_transfers_*.jsonl | head

# Check for validation warnings
jq '.validation.warnings' data/extracted/club_transfers_*.jsonl | grep -v null | head
```

## Common Commands

### Parse Money Examples
```python
from scraper.extractors.utils import parse_money

# Test fee parsing
parse_money("€15.5m")      # (15.5, 'EUR', True)
parse_money("£500k")       # (0.5, 'GBP', True)
parse_money("free transfer") # (None, 'EUR', False)
parse_money("undisclosed")  # (None, 'EUR', False)
```

### Extract IDs
```python
from scraper.extractors.utils import extract_id_from_url

# Test ID extraction
extract_id_from_url("/profil/spieler/418560", "player")  # "418560"
extract_id_from_url("/verein/281", "club")  # "281"
```

### Normalize Position
```python
from scraper.extractors.utils import normalize_position

normalize_position("Goalkeeper")  # "GK"
normalize_position("Centre-Back")  # "CB"
normalize_position("Attacking Midfield")  # "AM"
```

## Troubleshooting

### BS Extraction Failing?

Check logs for:
```
bs_extraction_failed: Could not extract ... from URL
```

Common issues:
- Missing HTML markers (page structure changed)
- URL pattern mismatch
- Empty tables

Solution:
- Fallback to LLM is automatic if `BS_FALLBACK_TO_LLM=true`
- Check `extraction_backend` field in output (should be "bs_fallback_llm")

### Validation Warnings?

Check validation report:
```bash
jq '.validation' data/extracted/*.jsonl | jq -c 'select(.needs_review == true)'
```

Common warnings:
- Missing IDs
- Suspicious fee amounts
- Position normalization failures

These are non-blocking - data is still saved.

### Compare BS vs LLM

```python
import json

# Load results
with open('data/extracted/club_transfers_2026-02-08.jsonl') as f:
    for line in f:
        result = json.loads(line)
        print(f"Backend: {result['extraction_backend']}")
        print(f"Transfers: {len(result['transfers'])}")
        if result.get('validation'):
            print(f"Warnings: {len(result['validation']['warnings'])}")
```

## Configuration Examples

### Development (BS enabled, safe fallback)
```bash
USE_BS_EXTRACTORS=true
USE_BS_EXTRACTORS_FOR="club_transfers"
BS_FALLBACK_TO_LLM=true
ENABLE_LLM_VALIDATION=true
```

### Production (BS only for proven types)
```bash
USE_BS_EXTRACTORS=true
USE_BS_EXTRACTORS_FOR="club_transfers,player_profile"
BS_FALLBACK_TO_LLM=false
ENABLE_LLM_VALIDATION=true
```

### Cost Optimization (minimal LLM usage)
```bash
USE_BS_EXTRACTORS=true
USE_BS_EXTRACTORS_FOR=""  # All types
BS_FALLBACK_TO_LLM=false
ENABLE_LLM_VALIDATION=false  # No validation
```

## Next Steps

1. ✅ Run determinism tests
2. ✅ Test BS vs LLM on sample pages
3. ✅ Enable BS for one page type
4. ⏳ Monitor extraction_backend field in outputs
5. ⏳ Compare BS vs LLM results (transfer counts, fee amounts)
6. ⏳ Check validation warnings
7. ⏳ Gradually expand to more page types
8. ⏳ Disable LLM fallback when confident
9. ⏳ Add regression tests with fixtures

## Support

See [BS_EXTRACTION_SUMMARY.md](BS_EXTRACTION_SUMMARY.md) for full implementation details.
