# Valuation Pathway Simulator

A stochastic simulation framework for quantifying how exposure regime transitions affect player valuation distributions.

## Overview

This tool demonstrates that **moving a player through higher-premium exposure regimes shifts the distribution of future valuation upward**.

Given a starting valuation, time horizon, and pathway scenario (regime sequence), the simulator generates Monte Carlo paths using discrete-time regime-switching log-value dynamics and produces distributional summaries.

## Model

**Discrete-time regime-switching log-value dynamics:**

```
log V_{t+1} = log V_t + μ_{s_t} + σ_{s_t} * ε_t
```

where:
- `V_t` is the valuation at time t (in millions)
- `s_t` is the regime at time t (e.g., "ecuador", "brazil", "europe")
- `μ_{s_t}` is the regime-specific monthly log-drift
- `σ_{s_t}` is the regime-specific monthly log-volatility
- `ε_t ~ N(0, 1)` is standard normal noise

## Quick Start

Install dependencies:
```bash
uv sync
```

Run simulation with default parameters:
```bash
python main.py
```

This generates an `out/` directory containing:
- `results.csv`: Full simulation data (scenario, path_id, V_T)
- `summary.json`: Summary statistics (mean, p10, p50, p90, prob_down)
- `hist.png`: Overlaid histograms of final valuations
- `report.md`: Markdown report with model description and results

## CLI Usage

```bash
python main.py [OPTIONS]
```

**Options:**
- `--V0 FLOAT`: Initial valuation in millions (default: 2.0)
- `--months INT`: Simulation horizon in months (default: 6)
- `--N INT`: Number of Monte Carlo paths per scenario (default: 1000)
- `--seed INT`: Random seed for reproducibility (default: 0)
- `--config PATH`: Path to YAML config file (default: config.yaml)
- `--outdir PATH`: Output directory (default: out)

**Example:**
```bash
python main.py --V0 5.0 --N 2000 --seed 42 --outdir results
```

## Configuration

Edit `config.yaml` to define:

1. **Regimes**: Each regime has `mu` (monthly log-drift) and `sigma` (monthly log-volatility)
2. **Scenarios**: Pathway definitions using compact segment notation
3. **Model**: Dynamics model name (currently `regime_switching_log`)
4. **Defaults**: Default simulation parameters

**Example scenario:**
```yaml
scenarios:
  ecuador_2m_brazil_4m:
    segments:
      - regime: ecuador
        months: 2
      - regime: brazil
        months: 4
```

## Architecture

The codebase follows a strict **pure core + I/O at edges** pattern:

```
valuation_pathways/
├── config/          # Configuration schema and loading
├── data/            # Data provider interfaces and implementations
├── model/           # Dynamics models (swappable via protocol)
├── engine/          # Pure simulation core (deterministic)
├── report/          # Artifact generation (I/O)
└── cli.py           # Command-line interface
```

### Swappable Models

The simulator supports multiple dynamics models through the `DynamicsModel` protocol:
- Current: `regime_switching_log` (regime-switching log-normal)
- Future: HMM-based regime inference, GBM, etc.

Add new models in `valuation_pathways/model/` and register in `MODEL_REGISTRY`.

## Project Structure

```
player_valuations/
├── valuation_pathways/      # Main package
│   ├── config/              # Config schemas and loading
│   ├── data/                # Data provider interfaces
│   │   └── sources/         # Concrete implementations
│   ├── model/               # Dynamics models and regime definitions
│   ├── engine/              # Pure simulation engine
│   └── report/              # Artifact generation
├── config.yaml              # Simulation configuration
├── main.py                  # CLI entry point
├── pyproject.toml           # Package metadata and dependencies
└── README.md
```

## Dependencies

- **numpy**: Numerical simulation
- **pandas**: Data manipulation
- **matplotlib**: Visualization
- **pydantic**: Configuration validation
- **pyyaml**: Config file parsing

## Next Steps

To extend the simulator:

1. **Add new regimes**: Edit `config.yaml` with new regime parameters
2. **Define new scenarios**: Add scenario segments in config
3. **Implement new models**: Create class implementing `DynamicsModel` protocol
4. **Swap data sources**: Implement data provider protocols (CSV, API, database)
5. **Add HMM inference**: Build regime inference model and register in `MODEL_REGISTRY`