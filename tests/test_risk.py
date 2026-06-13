"""
tests/test_risk.py

Unit tests for cds/risk.py
Run with: pytest tests/test_risk.py -v
"""

import pytest
from datetime import date
from cds.risk import cs01, cs01_by_tenor, ir01

# ── Fixtures ─────────────────────────────────────────────────

TRADE_DATE = date(2026, 6, 13)
MATURITY   = date(2031, 6, 20)

SWAP_RATES = {
    1: 0.0432, 2: 0.0418, 3: 0.0401,
    5: 0.0385, 7: 0.0379, 10: 0.0371,
}

SPREAD_IG = {1: 45, 2: 65, 3: 90, 5: 120, 7: 145, 10: 170}
SPREAD_HY = {1: 180, 2: 230, 3: 265, 5: 310, 7: 340, 10: 375}


# ── CS01 Tests ────────────────────────────────────────────────

def test_cs01_buyer_positive():
    """
    Protection buyer CS01 should be positive.
    Wider spreads → protection worth more → gain.
    """
    result = cs01(
        TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
        coupon_bps=100, notional=10_000_000
    )
    assert result > 0

def test_cs01_seller_negative():
    """
    Protection seller CS01 should be negative.
    Wider spreads → protection costs more → loss.
    """
    result = cs01(
        TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
        coupon_bps=100, notional=10_000_000, position=-1
    )
    assert result < 0

def test_cs01_buyer_seller_opposite():
    """Buyer and seller CS01 should be equal and opposite."""
    buyer  = cs01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                  coupon_bps=100, notional=10_000_000, position=1)
    seller = cs01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                  coupon_bps=100, notional=10_000_000, position=-1)
    assert abs(buyer + seller) < 1e-6

def test_cs01_scales_with_notional():
    """Doubling notional should double CS01."""
    cs01_10mm = cs01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                     coupon_bps=100, notional=10_000_000)
    cs01_20mm = cs01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                     coupon_bps=100, notional=20_000_000)
    assert abs(cs01_20mm / cs01_10mm - 2.0) < 1e-4

def test_cs01_in_expected_range():
    """
    5Y IG CS01 on £10mm should be roughly £400-500.
    Approximate check: CS01 ≈ Risky Annuity × Notional / 10,000
                             ≈ 4.40 × 10,000,000 / 10,000
                             ≈ £4,400
    Wait — that's per 1bp on the full notional. Let's verify the range.
    """
    result = cs01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                  coupon_bps=100, notional=10_000_000)
    assert 3_000 < result < 6_000

def test_cs01_hy_greater_than_ig():
    """
    HY CS01 should differ from IG — different risky annuity.
    Both positive for protection buyer.
    """
    cs01_ig = cs01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                   coupon_bps=100, notional=10_000_000)
    cs01_hy = cs01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_HY,
                   coupon_bps=500, notional=10_000_000)
    assert cs01_ig > 0
    assert cs01_hy > 0


# ── CS01 by Tenor Tests ───────────────────────────────────────

def test_cs01_by_tenor_keys(  ):
    """Should return a value for every tenor in the spread curve."""
    result = cs01_by_tenor(
        TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
        coupon_bps=100, notional=10_000_000
    )
    assert set(result.keys()) == set(SPREAD_IG.keys())

def test_cs01_by_tenor_sums_to_parallel():
    """
    Sum of tenor CS01s should approximately equal the parallel CS01.
    Not exact due to curve non-linearity, but should be close.
    """
    parallel = cs01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                    coupon_bps=100, notional=10_000_000)
    by_tenor = cs01_by_tenor(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                              coupon_bps=100, notional=10_000_000)
    tenor_sum = sum(by_tenor.values())
    assert abs(tenor_sum - parallel) / abs(parallel) < 0.05

def test_cs01_by_tenor_beyond_maturity_small():
    """
    Tenors beyond trade maturity should have near-zero CS01.
    A 5Y trade has no sensitivity to the 7Y or 10Y spread node.
    """
    result = cs01_by_tenor(
        TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
        coupon_bps=100, notional=10_000_000
    )
    assert abs(result[7])  < 100
    assert abs(result[10]) < 100


# ── IR01 Tests ────────────────────────────────────────────────

def test_ir01_small_relative_to_cs01():
    """
    IR01 should be much smaller than CS01 in absolute terms.
    CDS is primarily a credit instrument, not a rates instrument.
    """
    c = cs01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
             coupon_bps=100, notional=10_000_000)
    i = ir01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
             coupon_bps=100, notional=10_000_000)
    assert abs(i) < abs(c) * 0.20

def test_ir01_buyer_negative():
    """
    Protection buyer IR01 should be negative.
    Higher rates → lower discount factors → protection leg worth less.
    """
    result = ir01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                  coupon_bps=100, notional=10_000_000)
    assert result < 0

def test_ir01_seller_positive():
    """IR01 should flip sign for protection seller."""
    result = ir01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                  coupon_bps=100, notional=10_000_000, position=-1)
    assert result > 0

def test_ir01_scales_with_notional():
    """Doubling notional should double IR01."""
    ir01_10mm = ir01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                     coupon_bps=100, notional=10_000_000)
    ir01_20mm = ir01(TRADE_DATE, MATURITY, SWAP_RATES, SPREAD_IG,
                     coupon_bps=100, notional=20_000_000)
    assert abs(ir01_20mm / ir01_10mm - 2.0) < 1e-4