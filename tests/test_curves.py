"""
tests/test_curves.py

Unit tests for cds/curves.py
Run with: pytest tests/test_curves.py -v
"""

import pytest
import json
import os
from datetime import date
from cds.curves import DiscountCurve, SurvivalCurve


# ── Fixtures ─────────────────────────────────────────────────

TRADE_DATE = date(2026, 6, 13)

SWAP_RATES = {
    1:  0.0432,
    2:  0.0418,
    3:  0.0401,
    5:  0.0385,
    7:  0.0379,
    10: 0.0371,
}

SPREAD_CURVE_IG = {   # Vodafone-like BBB-
    1:  45,
    2:  65,
    3:  90,
    5:  120,
    7:  145,
    10: 170,
}

SPREAD_CURVE_HY = {   # iTraxx XOVER-like
    1:  180,
    2:  230,
    3:  265,
    5:  310,
    7:  340,
    10: 375,
}


# ── DiscountCurve Tests ───────────────────────────────────────

def test_discount_factor_at_zero():
    """DF(0) must be exactly 1."""
    dc = DiscountCurve(SWAP_RATES)
    assert dc.discount_factor(0) == 1.0

def test_discount_factor_at_node():
    """DF at a tenor node should match exp(−r×t)."""
    dc  = DiscountCurve(SWAP_RATES)
    r1  = SWAP_RATES[1]
    expected = pytest.approx(__import__('math').exp(-r1 * 1), rel=1e-6)
    assert dc.discount_factor(1) == expected

def test_discount_factors_decreasing():
    """Discount factors must be strictly decreasing."""
    dc = DiscountCurve(SWAP_RATES)
    dfs = [dc.discount_factor(t) for t in [1, 2, 3, 5, 7, 10]]
    assert all(dfs[i] > dfs[i+1] for i in range(len(dfs)-1))

def test_discount_factor_between_zero_and_one():
    """All discount factors must be between 0 and 1."""
    dc = DiscountCurve(SWAP_RATES)
    for t in [0.5, 1, 2, 5, 10]:
        assert 0 < dc.discount_factor(t) <= 1.0

def test_discount_factor_interpolation():
    """Interpolated rate should be between the bracketing nodes."""
    dc   = DiscountCurve(SWAP_RATES)
    r25  = dc.rate(2.5)
    assert SWAP_RATES[2] >= r25 >= SWAP_RATES[3]


# ── SurvivalCurve Tests ───────────────────────────────────────

def test_survival_at_zero():
    """S(0) must be exactly 1 — alive today with certainty."""
    dc = DiscountCurve(SWAP_RATES)
    sc = SurvivalCurve(SPREAD_CURVE_IG, dc, trade_date=TRADE_DATE)
    assert sc.survival_prob(0) == 1.0

def test_survival_between_zero_and_one():
    """All survival probs must be valid probabilities."""
    dc = DiscountCurve(SWAP_RATES)
    sc = SurvivalCurve(SPREAD_CURVE_IG, dc, trade_date=TRADE_DATE)
    for t in [1, 2, 3, 5, 7, 10]:
        sp = sc.survival_prob(t)
        assert 0 < sp < 1.0

def test_survival_strictly_decreasing():
    """Survival probabilities must be strictly decreasing."""
    dc  = DiscountCurve(SWAP_RATES)
    sc  = SurvivalCurve(SPREAD_CURVE_IG, dc, trade_date=TRADE_DATE)
    sps = [sc.survival_prob(t) for t in [1, 2, 3, 5, 7, 10]]
    assert all(sps[i] > sps[i+1] for i in range(len(sps)-1))

def test_hy_survival_lower_than_ig():
    """HY entity should have lower survival prob than IG at same tenor."""
    dc   = DiscountCurve(SWAP_RATES)
    sc_ig = SurvivalCurve(SPREAD_CURVE_IG, dc, trade_date=TRADE_DATE)
    sc_hy = SurvivalCurve(SPREAD_CURVE_HY, dc, trade_date=TRADE_DATE)
    assert sc_hy.survival_prob(5) < sc_ig.survival_prob(5)

def test_hazard_rate_positive():
    """All hazard rates must be positive."""
    dc = DiscountCurve(SWAP_RATES)
    sc = SurvivalCurve(SPREAD_CURVE_IG, dc, trade_date=TRADE_DATE)
    for t in [1, 2, 3, 5, 7, 10]:
        assert sc.hazard_rate(t) > 0

def test_hazard_rate_approximation():
    """
    Hazard rate should be approximately spread / (1 − recovery).
    This is the flat hazard rate approximation — a useful sanity check.
    Tests that bootstrapped rate is within 60% of the approximation.
    """
    dc       = DiscountCurve(SWAP_RATES)
    sc       = SurvivalCurve(SPREAD_CURVE_IG, dc, trade_date=TRADE_DATE)
    spread_5y = SPREAD_CURVE_IG[5] / 10_000  # bps → decimal
    approx   = spread_5y / (1 - 0.40)
    actual   = sc.hazard_rate(5)
    assert abs(actual - approx) / approx < 0.60  # within 60%


# ── Reprice Validation ────────────────────────────────────────
# THIS IS THE CRITICAL TEST
# Bootstrap from spreads, reprice each CDS — must come back to zero

def test_reprice_ig_to_par():
    """
    Core validation: bootstrap from IG spreads, reprice all tenors.
    Every CDS must reprice to NPV < 1e-4.
    """
    dc = DiscountCurve(SWAP_RATES)
    sc = SurvivalCurve(SPREAD_CURVE_IG, dc, trade_date=TRADE_DATE)

    tenors  = sorted(SPREAD_CURVE_IG.keys())
    hazards = sc._hazards

    for tenor, spread in SPREAD_CURVE_IG.items():
        npv = sc._price_cds(
            tenor,
            spread / 10_000,
            [t for t in tenors if t <= tenor],
            hazards[:len([t for t in tenors if t <= tenor])]
        )
        assert abs(npv) < 1e-4, (
            f"Reprice failed at {tenor}Y: NPV = {npv:.6f}"
        )

def test_reprice_hy_to_par():
    """Same reprice validation for HY spread curve."""
    dc = DiscountCurve(SWAP_RATES)
    sc = SurvivalCurve(SPREAD_CURVE_HY, dc, trade_date=TRADE_DATE)

    tenors  = sorted(SPREAD_CURVE_HY.keys())
    hazards = sc._hazards

    for tenor, spread in SPREAD_CURVE_HY.items():
        npv = sc._price_cds(
            tenor,
            spread / 10_000,
            [t for t in tenors if t <= tenor],
            hazards[:len([t for t in tenors if t <= tenor])]
        )
        assert abs(npv) < 1e-4, (
            f"Reprice failed at {tenor}Y: NPV = {npv:.6f}"
        )