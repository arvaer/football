"""Tests for summary metrics computation."""

import pytest
import numpy as np
from valuation_pathways.engine.metrics import compute_summary_metrics


def test_compute_summary_metrics_basic():
    """Test basic summary statistics computation."""
    # Simple deterministic test data
    final_values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    V0 = 3.0
    
    summary = compute_summary_metrics(final_values, V0)
    
    assert summary["mean"] == 3.0
    assert summary["p50"] == 3.0  # Median
    assert summary["prob_down"] == 0.4  # 2 out of 5 are < 3.0


def test_compute_summary_metrics_percentiles():
    """Test percentile calculations are correct."""
    # 100 values from 0 to 99
    final_values = np.arange(100, dtype=float)
    V0 = 50.0
    
    summary = compute_summary_metrics(final_values, V0)
    
    assert summary["p10"] == pytest.approx(9.9, rel=0.1)
    assert summary["p50"] == pytest.approx(49.5, rel=0.1)
    assert summary["p90"] == pytest.approx(89.1, rel=0.1)
    assert summary["prob_down"] == 0.5
