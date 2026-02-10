# Player Valuation Dashboard Integration

This document describes the new player valuation features integrated into the Streamlit dashboard.

## Overview

The dashboard now includes player valuation projections based on stratum-specific regime parameters derived from historical transfer data. It operates in two modes:

1. **Individual Player Projections** - Real-time simulations for specific players
2. **Batch EDA** - Pre-computed analysis across all strata

## Features

### 1. Individual Player Valuation (Player Search Tab)

When viewing a player's profile, you can now:

- View their stratum classification (age band + position group)
- See their current market value (extracted from transfer history)
- Run Monte Carlo simulations with customizable parameters:
  - Time horizon (3-12 months)
  - Number of simulation paths (100-5000)
  - Initial valuation (manual override available)

**Scenarios simulated:**
- **Stay**: Player remains at current club
- **Move immediately**: Player transfers immediately
- **Move after N months**: Hybrid scenario

**Outputs:**
- Summary statistics table (mean, median, percentiles, probability of decline)
- Interactive histogram showing distribution of final valuations
- Stratum parameters (μ, σ, sample size) for transparency

### 2. Batch Valuation EDA Tab

Loads pre-computed valuation projections for all player strata.

**Features:**
- Filter by age band, position, and scenario
- Summary statistics by scenario
- Box plots showing distribution across strata
- Heatmap: Position × Age Band mean returns
- Risk analysis: Top performers and riskiest scenarios
- CSV export functionality

## Setup & Usage

### Step 1: Ensure Stratum Statistics Exist

First, make sure you have up-to-date stratum statistics:

```bash
# Run from the football/ directory
python scripts/compute_stratum_stats.py
```

This will create `data/extracted/stratum_stats_<date>.jsonl`

### Step 2: Generate Batch Valuations (for Batch EDA)

Run the batch valuation processing script:

```bash
python scripts/run_batch_valuations.py --V0 2.0 --months 6 --N 1000
```

**Arguments:**
- `--V0`: Initial valuation in millions (default: 2.0)
- `--months`: Simulation horizon in months (default: 6)
- `--N`: Number of Monte Carlo paths per scenario (default: 1000)
- `--seed`: Random seed for reproducibility (default: 42)
- `--min-sample-size`: Minimum stratum sample size to include (default: 10)

This will create `data/summary/batch_valuations_<date>/` containing:
- `batch_results.csv` - Full simulation results
- `summary.json` - Metadata and parameters

**Example output:**
```
=== Batch Valuation Processing ===

Total strata: 32
V0: 2.00M, Horizon: 6 months, Paths: 1000

Complete stratum groups (with stay & moved): 16
Skipped 0 strata (incomplete or low-n)

[1/16] Processing 21-24_DEF...
  Stay:  n=  1562, μ=-0.0276, σ=0.0593
  Moved: n=   340, μ=0.2172, σ=0.4407
...

✓ Completed 16 strata
Results saved to data/summary/batch_valuations_2026-02-10/batch_results.csv
```

### Step 3: Launch Dashboard

```bash
streamlit run dashboard.py
```

## Technical Details

### Data Flow

```
Player Profile
    ↓
Extract: age, position, market value
    ↓
Map to Stratum: age_band + position_group
    ↓
Load Stratum Stats: μ_stay, σ_stay, μ_moved, σ_moved
    ↓
Create Regime Parameters
    ↓
Run Monte Carlo Simulation (RegimeSwitchingLogModel)
    ↓
Display Results
```

### Model

The valuation simulation uses a **regime-switching log-value dynamics** model:

```
log V_{t+1} = log V_t + μ_{s_t} + σ_{s_t} * ε_t
```

Where:
- `V_t` is valuation at time t (millions €)
- `s_t` is the regime at time t ("stay" or "moved")
- `μ_{s_t}` is the regime-specific monthly log-drift
- `σ_{s_t}` is the regime-specific monthly log-volatility
- `ε_t ~ N(0, 1)` is standard normal noise

### Stratum Mapping

**Age Bands:**
- U21: < 21 years
- 21-24: 21-24 years
- 25-28: 25-28 years
- 29+: ≥ 29 years

**Position Groups:**
- GK: Goalkeeper
- DEF: CB, LB, RB, LWB, RWB
- MID: DM, CM, AM, LM, RM
- FWD: LW, RW, CF, ST

**Move Labels:**
- stay: Player remained at same club
- moved: Player transferred to different club

### Feature Flags

Located in `dashboard.py`:

```python
FEATURE_FLAGS = {
    "use_enriched_profiles": True,  # If True, try enriched profiles; else use transfer edges
}
```

## File Structure

```
football/
├── dashboard.py                          # Main dashboard (updated)
├── scripts/
│   ├── compute_stratum_stats.py         # Generate stratum statistics
│   └── run_batch_valuations.py          # NEW: Batch valuation processing
├── data/
│   ├── extracted/
│   │   ├── stratum_stats_*.jsonl        # Stratum statistics
│   │   └── mv_transitions_*.jsonl       # Transition data
│   └── summary/
│       └── batch_valuations_*/          # NEW: Batch results
│           ├── batch_results.csv
│           └── summary.json
├── graph_builder/
│   └── transition_stats_loader.py       # Updated: Added mu/sigma_rate_per_30day
└── player_valuations/
    └── valuation_pathways/              # Valuation simulation engine
        ├── model/
        ├── engine/
        └── report/
```

## Example Queries

### Individual Player

1. Go to "Player Search" tab
2. Select a player (e.g., a 23-year-old defender)
3. Scroll to "📈 Valuation Projection" section
4. Adjust parameters if needed
5. Click "Run Valuation Projection"

Expected output:
- Classification: 21-24_DEF
- Scenarios: Stay 6m, Move immediately, Move after 3m
- Results: Summary stats + histogram

### Batch Analysis

1. Run batch processing (if not already done):
   ```bash
   python scripts/run_batch_valuations.py
   ```

2. Go to "Batch Valuation EDA" tab
3. Apply filters (e.g., only FWD positions, age 21-24)
4. Explore visualizations:
   - Box plots: Compare scenarios
   - Heatmap: Position × Age patterns
   - Risk tables: Top performers vs riskiest

## Troubleshooting

**Problem:** "No stratum data available for X_Y"

**Solution:** The player's stratum may have insufficient sample size (n < 10). Check:
```bash
python scripts/compute_stratum_stats.py | grep "X_Y"
```

---

**Problem:** "No batch valuation results found"

**Solution:** Run batch processing first:
```bash
python scripts/run_batch_valuations.py
```

---

**Problem:** Player's market value shows "N/A"

**Solution:** Use the "Override market value" checkbox to manually input an initial valuation.

## Future Enhancements

Potential improvements:

1. **Custom Scenarios**: Allow users to define custom regime sequences
2. **Multi-player Comparison**: Side-by-side comparison of multiple players
3. **Time Series View**: Show valuation evolution paths over time
4. **Enriched Profile Integration**: Pull market values from enriched player profiles
5. **Export Individual Results**: Download player-specific simulation data

## References

- Valuation CLI: `player_valuations/valuation_pathways/cli.py`
- Simulation Engine: `player_valuations/valuation_pathways/engine/simulator.py`
- Model: `player_valuations/valuation_pathways/model/dynamics.py`
- Transition Analyzer: `graph_builder/transition_analyzer.py`
