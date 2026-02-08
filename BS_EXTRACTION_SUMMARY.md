# BeautifulSoup Deterministic Extraction - Implementation Summary

## Overview

Successfully refactored the Transfermarkt extraction pipeline to support **deterministic BeautifulSoup parsing** with **LLM validation** as a non-blocking enrichment layer.

## What Was Implemented

### 1. **Determinism Tests** (`tests/test_determinism.py`)
- Verifies HTML stability across fetches
- Checks for page markers (player/club URLs, tables, headers)
- Normalizes HTML (removes scripts, dynamic IDs, timestamps)
- Tests all 4 page types: PLAYER_PROFILE, PLAYER_TRANSFERS, CLUB_TRANSFERS, CLUB_PROFILE

**Usage:**
```bash
python tests/test_determinism.py
```

### 2. **Feature Flags** (added to `scraper/config.py`)
```python
# ScraperSettings
use_bs_extractors: bool = False  # Master switch
bs_fallback_to_llm: bool = True  # Fallback if BS fails
use_bs_extractors_for_raw: str = ""  # Comma-separated page types
enable_llm_validation: bool = True  # Run LLM validator
llm_validation_blocking: bool = False  # Validation never blocks
```

**Environment variables:**
```bash
USE_BS_EXTRACTORS=true
BS_FALLBACK_TO_LLM=true
USE_BS_EXTRACTORS_FOR="club_transfers,player_profile"
ENABLE_LLM_VALIDATION=true
```

### 3. **Utility Functions** (`scraper/extractors/utils.py`)
- `extract_id_from_url()` - Extract player/club/league IDs from URLs
- `parse_money()` - Parse fee strings (€15.5m → 15.5, EUR, True)
  - Handles: €15m, £500k, $10.5m, free transfer, loan, undisclosed
  - **Correct unit parsing** - no more heuristic division!
- `normalize_position()` - Map positions to standard codes (GK, CB, DM, etc.)
- `normalize_transfer_type()` - Map to permanent/loan/free/end_of_loan
- `parse_date()` - Parse various date formats to ISO (YYYY-MM-DD)
- `clean_text()` - Normalize whitespace and remove invisible chars

### 4. **BS Extractors** (`scraper/extractors/transfermarkt_bs.py`)

Deterministic parsers for each page type:

#### **`parse_player_profile(html, url)`**
Extracts:
- Player ID from URL (/spieler/ID)
- Name from h1.data-header__headline-wrapper
- Info table fields: DOB, height, position, foot, nationality, current club
- Market values (current value from chart if present)

#### **`parse_player_transfers(html, url)`**
Extracts:
- Player ID and name
- Transfer table rows (table.items)
- For each transfer: season, date, from/to clubs with IDs, market value, fee
- Transfer type detection (permanent/loan/free/end_of_loan)

#### **`parse_club_transfers(html, url)`**
Extracts:
- Club ID and name
- Season from selector
- Separate arrivals and departures boxes
- For each transfer: player with ID, other club with ID, fee, date

#### **`parse_club_profile(html, url)`**
Extracts:
- Club ID from URL
- Name from header
- Info table: country, league, division/tier

**All extractors:**
- Raise `ExtractionError` if markers missing or URL doesn't match
- Use stable CSS classes (table.items, info-table, data-header)
- Parse IDs from href attributes
- Return dicts matching existing Pydantic schemas

### 5. **LLM Validator** (`scraper/validators/transfermarkt_llm_validator.py`)

Non-blocking validator that:
- Detects anomalies (missing IDs, suspicious fees, invalid positions)
- Checks data consistency (currency, date formats, value ranges)
- Returns `ValidationReport` with warnings and suggested fixes
- **Never prevents extraction results from being saved**

Validation checks:
- Missing critical fields (IDs, names)
- Suspicious heights (< 150cm or > 220cm)
- Suspicious fees (> 500m - likely parsing error)
- Currency validation
- Position normalization failures

### 6. **Dual Backend Support** (updated `scraper/workers/extraction_worker.py`)

#### **Routing Logic:**
```python
async def extract_from_page(html, url, page_type):
    if is_transfermarkt(url) and should_use_bs(page_type):
        result = await extract_from_page_bs(...)
        if not result.success and fallback_enabled:
            result = await extract_from_page_llm(...)
            result.extraction_backend = "bs_fallback_llm"
    else:
        result = await extract_from_page_llm(...)
    return result
```

#### **Methods:**
- `extract_from_page_bs()` - Calls BS parsers, runs LLM validation if enabled
- `extract_from_page_llm()` - Original LLM extraction (renamed from extract_from_page)
- `extract_from_page()` - Router that selects backend based on config
- `_populate_typed_models()` - Converts BS dict to Pydantic models
- `_convert_llm_data_to_typed_models()` - Converts LLM dict with legacy fixes

### 7. **Updated Models** (`scraper/models.py`)

#### **ExtractionResult:**
```python
extraction_backend: str = "llm"  # "llm", "bs", or "bs_fallback_llm"
validation: Optional[Dict[str, Any]] = None  # ValidationReport dict
```

#### **ValidationReport:**
```python
warnings: List[str]
suggested_fixes: List[Dict[str, Any]]
fixes_applied: List[str]
needs_review: bool
confidence: float
validation_notes: Optional[str]
validated_at: datetime
```

## Migration Plan

### Phase 1: Testing (Current)
```bash
# Default: LLM only (backwards compatible)
USE_BS_EXTRACTORS=false
```

### Phase 2: Per-Page-Type Rollout
```bash
# Enable for club transfers only
USE_BS_EXTRACTORS=true
USE_BS_EXTRACTORS_FOR="club_transfers"
BS_FALLBACK_TO_LLM=true
ENABLE_LLM_VALIDATION=true
```

### Phase 3: Expand Coverage
```bash
# Add more page types
USE_BS_EXTRACTORS_FOR="club_transfers,player_profile,club_profile"
```

### Phase 4: Full Rollout
```bash
# All Transfermarkt pages
USE_BS_EXTRACTORS=true
USE_BS_EXTRACTORS_FOR=""  # Empty = all page types
BS_FALLBACK_TO_LLM=true  # Keep safety net
```

### Phase 5: LLM Validation Only
```bash
# BS extraction proven reliable
USE_BS_EXTRACTORS=true
BS_FALLBACK_TO_LLM=false  # Disable fallback
ENABLE_LLM_VALIDATION=true  # Keep validation
```

## Testing

### 1. Run Determinism Tests
```bash
cd /home/galo/all_fb/fb
python tests/test_determinism.py
```

### 2. Compare BS vs LLM Output
```bash
# Enable BS for one type
export USE_BS_EXTRACTORS=true
export USE_BS_EXTRACTORS_FOR="club_transfers"

# Run extraction
python -m scraper.workers.extraction_worker

# Check output files
ls -lh data/extracted/club_transfers_*.jsonl

# Compare fields (manual or scripted)
```

### 3. Verify Validation
```bash
# Check that validation reports are present
jq '.validation' data/extracted/club_transfers_*.jsonl | head
```

## Key Benefits

### ✅ Deterministic Extraction
- Same HTML → same output (no LLM variability)
- Faster (no LLM inference)
- Cheaper (no API calls for extraction)
- Debuggable (traceable parsing logic)

### ✅ Correct Fee Parsing
- **Before:** €2.87m → 2870000 (LLM error + heuristic fix)
- **After:** €2.87m → 2.87 (correct unit parsing)
- Handles: €15.5m, £500k, free, loan, undisclosed

### ✅ Stable IDs
- Extract canonical IDs from URLs
- No reliance on LLM to find IDs in text
- Player: /spieler/418560 → "418560"
- Club: /verein/281 → "281"

### ✅ Non-Blocking Validation
- LLM validator runs but never prevents save
- Warnings logged for review
- Suggested fixes can be applied mechanically
- Production data flow never blocked

### ✅ Safe Migration
- Feature flag control (global + per-page-type)
- Fallback to LLM if BS fails
- Track extraction_backend in every result
- No breaking changes to existing pipeline

## File Structure

```
scraper/
├── config.py                    # Added BS feature flags
├── models.py                    # Added extraction_backend, ValidationReport
├── extractors/
│   ├── __init__.py
│   ├── utils.py                # Parsing utilities
│   └── transfermarkt_bs.py     # BS extractors
├── validators/
│   ├── __init__.py
│   └── transfermarkt_llm_validator.py  # LLM validator
└── workers/
    └── extraction_worker.py    # Updated with dual backend

tests/
└── test_determinism.py         # HTML stability tests
```

## Next Steps

1. **Run determinism tests** to verify HTML stability
2. **Enable BS for one page type** (e.g., CLUB_TRANSFERS)
3. **Compare outputs** - BS vs LLM on same fixtures
4. **Validate key fields** match (IDs, transfer counts, fees)
5. **Gradually expand** to other page types
6. **Monitor validation reports** for edge cases
7. **Add fixtures/tests** for regression coverage

## Notes

- **Backwards compatible**: Default is LLM-only (USE_BS_EXTRACTORS=false)
- **Feature flagged**: Control per page type
- **Fallback-safe**: LLM fallback if BS hard-fails
- **Validation optional**: Can disable LLM validator to save costs
- **Data tracked**: Every result records extraction_backend
- **Type errors**: BS extractor has type hints that may show linter errors (BeautifulSoup types) but code is functional
