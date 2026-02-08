"""Tests for regime-switching log dynamics model."""

import numpy as np
import pytest
from valuation_pathways.model.regimes import RegimeParameters
from valuation_pathways.model.dynamics import RegimeSwitchingLogModel


def test_simulate_path_deterministic():
    """Test that simulation is deterministic given a fixed seed."""
    params = {
        "ecuador": RegimeParameters(mu=0.01, sigma=0.1),
        "brazil": RegimeParameters(mu=0.02, sigma=0.08),
    }
    model = RegimeSwitchingLogModel(params)
    
    regime_seq = ["ecuador", "ecuador", "brazil", "brazil"]
    
    # Run twice with same seed
    path1 = model.simulate_path(V0=2.0, regime_sequence=regime_seq, months=4, seed=42)
    path2 = model.simulate_path(V0=2.0, regime_sequence=regime_seq, months=4, seed=42)
    
    np.testing.assert_array_equal(path1, path2)


def test_simulate_path_unknown_regime_raises():
    """Test that unknown regime raises KeyError."""
    params = {"ecuador": RegimeParameters(mu=0.01, sigma=0.1)}
    model = RegimeSwitchingLogModel(params)
    
    with pytest.raises(KeyError, match="Unknown regime 'unknown'"):
        model.simulate_path(V0=2.0, regime_sequence=["unknown"], months=1, seed=0)
