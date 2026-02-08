"""Tests for simulation engine."""

import numpy as np
import pytest
from valuation_pathways.model.regimes import RegimeParameters
from valuation_pathways.model.dynamics import RegimeSwitchingLogModel
from valuation_pathways.engine.simulator import run_simulation


def test_run_simulation_deterministic():
    """Test that run_simulation is deterministic with fixed seed."""
    params = {"ecuador": RegimeParameters(mu=0.01, sigma=0.1)}
    model = RegimeSwitchingLogModel(params)
    
    scenario_paths = {"test": ["ecuador", "ecuador", "ecuador"]}
    
    result1 = run_simulation(
        V0=2.0, scenario_paths=scenario_paths, model=model,
        months=3, n_paths=10, seed=42
    )
    result2 = run_simulation(
        V0=2.0, scenario_paths=scenario_paths, model=model,
        months=3, n_paths=10, seed=42
    )
    
    # Check final values are identical
    np.testing.assert_array_equal(
        result1.final_values["V_T"].values,
        result2.final_values["V_T"].values
    )
    
    # Check summaries match
    assert result1.summary == result2.summary


def test_run_simulation_multiple_scenarios():
    """Test simulation with multiple scenarios produces correct structure."""
    params = {
        "ecuador": RegimeParameters(mu=0.01, sigma=0.1),
        "brazil": RegimeParameters(mu=0.02, sigma=0.08),
    }
    model = RegimeSwitchingLogModel(params)
    
    scenario_paths = {
        "stay_ecuador": ["ecuador", "ecuador"],
        "move_to_brazil": ["ecuador", "brazil"],
    }
    
    result = run_simulation(
        V0=2.0, scenario_paths=scenario_paths, model=model,
        months=2, n_paths=5, seed=0
    )
    
    # Check we have results for both scenarios
    assert set(result.final_values["scenario"].unique()) == {"stay_ecuador", "move_to_brazil"}
    
    # Check we have 5 paths per scenario
    assert len(result.final_values) == 10
    assert len(result.summary) == 2
    assert "stay_ecuador" in result.summary
    assert "move_to_brazil" in result.summary
