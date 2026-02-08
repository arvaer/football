"""Tests for Pydantic configuration schemas."""

import pytest
from pydantic import ValidationError
from valuation_pathways.config.schema import (
    RegimeConfig,
    ScenarioSegment,
    ScenarioConfig,
    SimulationConfig,
)


def test_regime_config_validation():
    """Test that RegimeConfig validates sigma >= 0."""
    # Valid config
    regime = RegimeConfig(mu=0.01, sigma=0.1)
    assert regime.mu == 0.01
    assert regime.sigma == 0.1
    
    # Invalid sigma
    with pytest.raises(ValidationError):
        RegimeConfig(mu=0.01, sigma=-0.1)


def test_scenario_config_expand_to_sequence():
    """Test that scenario segments expand correctly to regime sequence."""
    scenario = ScenarioConfig(
        segments=[
            ScenarioSegment(regime="ecuador", months=2),
            ScenarioSegment(regime="brazil", months=3),
        ]
    )
    
    sequence = scenario.expand_to_sequence(total_months=5)
    assert sequence == ["ecuador", "ecuador", "brazil", "brazil", "brazil"]
    
    # Wrong total should raise
    with pytest.raises(ValueError, match="sum to 5 months"):
        scenario.expand_to_sequence(total_months=6)
