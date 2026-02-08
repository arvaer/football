# League Tier Scraper Implementation Plan

## Objective
Build a comprehensive league tier extraction system to scrape tier 1-5 league data from Transfermarkt's Europa and Amerika competition index pages, creating a firehose of league→club→tier mappings for downstream valuation analysis.

## Scope
- **Target URLs**: `/wettbewerbe/europa` and `/wettbewerbe/amerika` only
- **Tier Coverage**: Tiers 1-5 for all countries in these confederations
- **Output**: JSONL files with league metadata (name, country, tier, confederation, clubs)

## Challenge: JavaScript-Rendered Tables

Transfermarkt uses dynamic content loading for competition tables. Need strategy to handle:

### Option 1: LLM-Based Extraction (Recommended - Matches Current Pattern)
- Pros: Already working for club transfers, handles varied HTML structures
- Cons: Dependent on LLM accuracy, requires good HTML reduction
- Implementation: Pass rendered HTML snapshot to LLM with schema
- **Recommendation**: Use this - consistent with existing extraction_worker.py pattern

### Option 2: BeautifulSoup Parsing of Rendered HTML
- Pros: Faster, no LLM cost, deterministic
- Cons: Brittle to HTML structure changes, requires reverse-engineering tables
- Implementation: Find table classes/IDs, parse rows directly
- **Recommendation**: Use as fallback/validation

### Option 3: Selenium/Playwright for Dynamic Rendering
- Pros: Gets fully rendered JS content
- Cons: Adds heavy dependency, slower, more complex
- Implementation: Spin up headless browser, wait for table load, extract HTML
- **Recommendation**: Defer unless HTML snapshots insufficient

### Hybrid Strategy (Proposed)
1. Discovery worker fetches HTML with requests (current approach)
2. Extraction worker uses LLM to parse table content from HTML snapshot
3. LLM schema instructs model to extract league tables specifically
4. Post-processing validates tier assignments (GB1→tier 1, ES2→tier 2)

**Key Insight**: Transfermarkt serves SSR (server-side rendered) HTML for initial load, so static HTML should contain table data. Test this assumption first.

## Implementation Steps

### Step 1: Add League Model and Page Types

**File**: `football/scraper/models.py`

**Changes**:
1. Add `LEAGUE_DETAIL` to `PageType` enum
2. Create `League` model with fields:
   ```python
   class League(BaseModel):
       tm_id: Optional[str] = None        # e.g., "GB1", "ES1"
       name: Optional[str] = None         # e.g., "Premier League"
       country: Optional[str] = None      # e.g., "England"
       tier: Optional[int] = None         # 1-5 (1=top division)
       confederation: Optional[str] = None # "UEFA", "CONMEBOL"
       clubs: List[str] = Field(default_factory=list)
       scraped_at: datetime = Field(default_factory=datetime.utcnow)
   ```
3. Add `leagues: List[League]` to `ExtractionResult` model

**URL Patterns to Match**:
- Index: `https://www.transfermarkt.us/wettbewerbe/europa`
- Detail: `https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1`
- Detail: `https://www.transfermarkt.com/laliga/startseite/wettbewerb/ES1`

### Step 2: Update Discovery Worker

**File**: `football/scraper/workers/discovery_worker.py`

**Changes**:
1. Add `LEAGUE_DETAIL` regex pattern to `PATTERNS` dict:
   ```python
   PageType.LEAGUE_DETAIL: re.compile(r'/[a-z0-9\-]+/(startseite|gesamtspielplan)/wettbewerb/[A-Z0-9]+')
   ```

2. Update priority map to include `LEAGUE_DETAIL` at HIGH priority (8)

3. Update routing logic to send league pages to extraction queue:
   ```python
   if page_type in [
       PageType.CLUB_TRANSFERS,
       PageType.PLAYER_TRANSFERS,
       PageType.PLAYER_PROFILE,
       PageType.LEAGUE_DETAIL,    # NEW
       PageType.LEAGUE_INDEX,     # NEW
   ]:
       await publish_extraction_task(new_task)
   ```

4. Add seed URLs to configuration:
   - `https://www.transfermarkt.us/wettbewerbe/europa`
   - `https://www.transfermarkt.us/wettbewerbe/amerika`

**Priority Rationale**: League data is foundational for tier classification, so HIGH priority ensures it's scraped before dependent club/player data.

### Step 3: Extend Extraction Worker

**File**: `football/scraper/workers/extraction_worker.py`

**Changes**:

1. **Add HTML reduction logic** for league pages in `_reduce_html_for_llm()`:
   ```python
   elif page_type in [PageType.LEAGUE_INDEX, PageType.LEAGUE_DETAIL]:
       relevant_parts = []
       
       # Competition tables (main content)
       tables = soup.find_all('table', class_='items')
       for table in tables[:10]:  # Get up to 10 tables
           relevant_parts.append(str(table))
       
       # League info boxes
       info_boxes = soup.find_all('div', class_='box')
       for box in info_boxes[:5]:
           relevant_parts.append(str(box))
       
       if relevant_parts:
           return '\n'.join(relevant_parts)[:40000]  # 40KB limit
   ```

2. **Add LLM schemas** to `get_schema_for_page_type()`:

   **For LEAGUE_INDEX** (continental overview):
   ```json
   {
     "confederation": "string (UEFA, CONMEBOL, etc.)",
     "leagues": [
       {
         "tm_id": "string (extract from URL - e.g., 'GB1', 'ES1', 'IT1')",
         "name": "string (e.g., 'Premier League', 'La Liga')",
         "country": "string",
         "tier": "integer (1-5) - Extract from:
                  1) League name patterns (e.g., 'Premier League'=1, 'Championship'=2, 'League One'=3)
                  2) URL code last digit (GB1=1, GB2=2, ES1=1, ES2=2)
                  3) Division indicators in description
                  Common tier 1 names: Premier League, La Liga, Serie A, Bundesliga, Ligue 1
                  Common tier 2 names: Championship, La Liga 2, Serie B, 2. Bundesliga"
       }
     ]
   }
   ```

   **For LEAGUE_DETAIL** (individual league page):
   ```json
   {
     "league": {
       "tm_id": "string (from URL)",
       "name": "string",
       "country": "string",
       "tier": "integer (1-5) - same extraction logic as above",
       "confederation": "string (UEFA, CONMEBOL, etc.)"
     },
     "clubs": [
       {
         "name": "string (full club name)",
         "tm_id": "string or null (extract from club profile link if available)"
       }
     ]
   }
   ```

3. **Add model parsing logic** in `_convert_to_models()`:
   ```python
   elif page_type == PageType.LEAGUE_INDEX:
       if "leagues" in data:
           for league_data in data["leagues"]:
               league_data["confederation"] = data.get("confederation")
               league = League(**league_data)
               result.leagues.append(league)
   
   elif page_type == PageType.LEAGUE_DETAIL:
       if "league" in data:
           league_data = data["league"]
           club_names = [c["name"] for c in data.get("clubs", [])]
           league_data["clubs"] = club_names
           league = League(**league_data)
           result.leagues.append(league)
   ```

4. **Add tier validation helper**:
   ```python
   def _infer_tier_from_tm_id(tm_id: str) -> Optional[int]:
       """Extract tier from Transfermarkt competition code.
       Examples: GB1→1, ES2→2, IT1→1, BR2→2
       """
       match = re.search(r'([A-Z]+)(\d+)$', tm_id)
       if match and match.group(2).isdigit():
           return int(match.group(2))
       return None
   ```

## Output Format

### league_index_YYYY-MM-DD.jsonl
```json
{
  "success": true,
  "page_type": "league_index",
  "url": "https://www.transfermarkt.us/wettbewerbe/europa",
  "leagues": [
    {
      "tm_id": "GB1",
      "name": "Premier League",
      "country": "England",
      "tier": 1,
      "confederation": "UEFA",
      "clubs": [],
      "scraped_at": "2026-02-08T10:30:00.000000"
    },
    {
      "tm_id": "ES1",
      "name": "La Liga",
      "country": "Spain",
      "tier": 1,
      "confederation": "UEFA",
      "clubs": [],
      "scraped_at": "2026-02-08T10:30:00.000000"
    }
  ]
}
```

### league_detail_YYYY-MM-DD.jsonl
```json
{
  "success": true,
  "page_type": "league_detail",
  "url": "https://www.transfermarkt.com/premier-league/startseite/wettbewerb/GB1",
  "leagues": [
    {
      "tm_id": "GB1",
      "name": "Premier League",
      "country": "England",
      "tier": 1,
      "confederation": "UEFA",
      "clubs": ["Liverpool FC", "Manchester City", "Arsenal FC", "..."],
      "scraped_at": "2026-02-08T10:30:00.000000"
    }
  ]
}
```

## Testing Strategy

1. **Unit Tests**: Tier inference from tm_id, URL pattern matching
2. **Integration Test**: Scrape `/wettbewerbe/europa`, verify league extraction
3. **Smoke Test**: Check if tables are in static HTML (curl page, grep for league names)
4. **Validation**: Cross-reference tier assignments (GB1 should always be tier 1)

## Success Metrics

- **Coverage**: Extract 100+ leagues from Europa + Amerika (tiers 1-3 minimum)
- **Accuracy**: Tier assignments match URL codes (GB1→tier 1, ES2→tier 2, etc.)
- **Completeness**: Each league has country, tier, and club list populated
- **Performance**: Process both continental indexes in < 10 minutes

## Next Steps (Post-Implementation)

1. Create `football/processing/tier_classifier.py` to map scraped leagues→tiers
2. Build `league_tiers.yaml` config from extracted data
3. Connect to player transfer data to build career tier pathways
4. Compute empirical μ̂ₛ, σ̂ₛ per tier for player_valuations simulator

## Open Questions

1. **HTML Content Verification**: Do we need to manually inspect `/wettbewerbe/europa` to confirm tables are in static HTML, or are they AJAX-loaded?
2. **Tier Boundaries**: Should tier 5+ leagues be scraped, or stop at tier 3-4 for quality/relevance?
3. **Country Mapping**: Some clubs have ambiguous countries (e.g., Welsh clubs in English leagues) - how to handle?
4. **Update Frequency**: Should this be a one-time scrape or periodic refresh to catch league promotions/relegations?
