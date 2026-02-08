"""Tests for configuration loader."""

import pytest
import tempfile
from pathlib import Path
from valuation_pathways.config.loader import load_config


def test_load_config_valid():
    """Test loading a valid config file."""
    config_yaml = """
model: regime_switching_log
regimes:
  ecuador:
    mu: 0.01
    sigma: 0.1
scenarios:
  test_scenario:
    segments:
      - regime: ecuador
        months: 6
defaults:
  V0: 2.0
  months: 6
  N: 100
  seed: 0
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(config_yaml)
        f.flush()
        
        config = load_config(f.name)
        assert config.model == "regime_switching_log"
        assert "ecuador" in config.regimes
        assert config.regimes["ecuador"].mu == 0.01
        
        Path(f.name).unlink()


def test_load_config_file_not_found():
    """Test that missing config file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_config("nonexistent.yaml")
