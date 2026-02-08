"""Tests for regime definitions and parameter validation."""

import pytest
from valuation_pathways.model.regimes import RegimeParameters


def test_regime_parameters_valid():
    """Test valid regime parameter creation."""
    params = RegimeParameters(mu=0.01, sigma=0.1)
    assert params.mu == 0.01
    assert params.sigma == 0.1


def test_regime_parameters_negative_sigma_raises():
    """Test that negative sigma raises ValueError."""
    with pytest.raises(ValueError, match="sigma must be non-negative"):
        RegimeParameters(mu=0.01, sigma=-0.1)
