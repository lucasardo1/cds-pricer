"""
tests/test_pricer.py

Unit tests for cds/pricer.py
Run with: pytest tests/test_pricer.py -v
"""

import pytest
from datetime import date
from cds.curves import DiscountCurve, SurvivalCurve
from cds.schedule import build_schedule
from cds.pricer import (
    risky_annuity,
    premium_leg,
    protection_leg,
    par_spread,
    upfront,
    npv,
)

# ── Fixtures ─────────────────────────────────────────────────

TRADE_DATE = date(2026, 6, 13)
MATURITY   = date(2031, 6, 20)  # 5Y

SWAP_RATES = {
    1: 0.0432, 2: 0.0418, 3: 0.0401,
    5: 0.0385, 7: 0.0379, 10: 0.0371,
}

SPREAD_IG = {1: 45, 2: 65, 3: 90, 5: 120, 7: 145, 10: 170}
SPREAD_HY = {1: 180, 2: 230, 3: 265, 5: 310, 7: 340, 10: 375}


@pytest.fixture
def ig_setup():
    dc  = DiscountCurve(SWAP_RATES)
    sc  = SurvivalCurve(SPREAD_IG, dc, trade_date=TRADE_DATE)
    sch = build_schedule(TRADE_DATE, MATURITY)
    return sch, sc, dc


@pytest.fixture
def hy_setup():
    dc  = DiscountCurve(SWAP_RATES)
    sc  = SurvivalCurve(SPREAD_HY, dc, trade_date=TRADE_DATE)
    sch = build_schedule(TRADE_DATE, MATURITY)
    return sch, sc, dc


# ── Risky Annuity Tests ───────────────────────────────────────

def test_risky_annuity_positive(ig_setup):
    """Risky annuity must be positive."""
    sch, sc, dc = ig_setup
    assert risky_annuity(sch, sc, dc) > 0

def test_risky_annuity_less_than_regular(ig_setup):
    """
    Risky annuity must be less than regular annuity.
    Survival weighting always reduces the value.
    """
    sch, sc, dc = ig_setup
    ra      = risky_annuity(sch, sc, dc)
    reg_ann = sum(dcf for (_, _, dcf, _) in sch)
    assert ra < reg_ann

def test_risky_annuity_hy_less_than_ig(ig_setup, hy_setup):
    """HY risky annuity should be lower than IG — higher default risk."""
    sch_ig, sc_ig, dc_ig = ig_setup
    sch_hy, sc_hy, dc_hy = hy_setup
    assert risky_annuity(sch_hy, sc_hy, dc_hy) < risky_annuity(sch_ig, sc_ig, dc_ig)


# ── Premium Leg Tests ─────────────────────────────────────────

def test_premium_leg_positive(ig_setup):
    """Premium leg PV must be positive."""
    sch, sc, dc = ig_setup
    assert premium_leg(sch, sc, dc, coupon_bps=100) > 0

def test_premium_leg_scales_with_coupon(ig_setup):
    """Doubling the coupon should double the premium leg."""
    sch, sc, dc = ig_setup
    pl_100 = premium_leg(sch, sc, dc, coupon_bps=100)
    pl_200 = premium_leg(sch, sc, dc, coupon_bps=200)
    assert abs(pl_200 / pl_100 - 2.0) < 1e-6


# ── Protection Leg Tests ──────────────────────────────────────

def test_protection_leg_positive(ig_setup):
    """Protection leg PV must be positive."""
    sch, sc, dc = ig_setup
    assert protection_leg(sch, sc, dc) > 0

def test_protection_leg_less_than_one(ig_setup):
    """Protection leg per unit notional must be less than (1−R)."""
    sch, sc, dc = ig_setup
    pl = protection_leg(sch, sc, dc, recovery=0.40)
    assert pl < 0.60  # can't exceed (1 − recovery)

def test_protection_leg_hy_greater_than_ig(ig_setup, hy_setup):
    """HY protection leg should be greater — higher default probability."""
    sch_ig, sc_ig, dc_ig = ig_setup
    sch_hy, sc_hy, dc_hy = hy_setup
    assert (protection_leg(sch_hy, sc_hy, dc_hy) >
            protection_leg(sch_ig, sc_ig, dc_ig))


# ── Par Spread Tests ──────────────────────────────────────────

def test_par_spread_positive(ig_setup):
    """Par spread must be positive."""
    sch, sc, dc = ig_setup
    assert par_spread(sch, sc, dc) > 0

def test_par_spread_ig_near_input(ig_setup):
    """
    Par spread should be close to the 5Y input spread.
    The 5Y schedule prices off the full curve so won't be exact,
    but should be in the right ballpark.
    """
    sch, sc, dc = ig_setup
    ps = par_spread(sch, sc, dc)
    assert 80 < ps < 160  # reasonable range around 120bps input

def test_par_spread_hy_greater_than_ig(ig_setup, hy_setup):
    """HY par spread must exceed IG par spread."""
    sch_ig, sc_ig, dc_ig = ig_setup
    sch_hy, sc_hy, dc_hy = hy_setup
    assert (par_spread(sch_hy, sc_hy, dc_hy) >
            par_spread(sch_ig, sc_ig, dc_ig))


# ── Upfront Tests ─────────────────────────────────────────────

def test_upfront_hy_buyer_pays(hy_setup):
    """
    HY entity with 500bps coupon but ~310bps par spread:
    par spread < coupon → seller pays upfront to buyer.
    """
    sch, sc, dc = hy_setup
    uf = upfront(sch, sc, dc, coupon_bps=500,
                 notional=10_000_000, recovery=0.40)
    assert uf < 0  # seller pays — par spread < 500bps coupon

def test_upfront_ig_buyer_pays(ig_setup):
    """
    IG entity with 100bps coupon but ~120bps par spread:
    par spread > coupon → buyer pays upfront to seller.
    """
    sch, sc, dc = ig_setup
    uf = upfront(sch, sc, dc, coupon_bps=100,
                 notional=10_000_000, recovery=0.40)
    assert uf > 0  # buyer pays — par spread > 100bps coupon

def test_upfront_seller_opposite_sign(ig_setup):
    """Protection seller upfront should be opposite sign to buyer."""
    sch, sc, dc = ig_setup
    uf_buyer  = upfront(sch, sc, dc, coupon_bps=100,
                        notional=10_000_000, position=1)
    uf_seller = upfront(sch, sc, dc, coupon_bps=100,
                        notional=10_000_000, position=-1)
    assert abs(uf_buyer + uf_seller) < 1e-6

def test_upfront_scales_with_notional(ig_setup):
    """Doubling notional should double the upfront."""
    sch, sc, dc = ig_setup
    uf_10mm = upfront(sch, sc, dc, coupon_bps=100, notional=10_000_000)
    uf_20mm = upfront(sch, sc, dc, coupon_bps=100, notional=20_000_000)
    assert abs(uf_20mm / uf_10mm - 2.0) < 1e-6


# ── NPV Tests ────────────────────────────────────────────────

def test_npv_at_par_spread_zero(ig_setup):
    """
    If coupon = par spread, NPV should be zero.
    This is the definition of par spread.
    """
    sch, sc, dc = ig_setup
    ps  = par_spread(sch, sc, dc)
    pnl = npv(sch, sc, dc, coupon_bps=ps,
              notional=10_000_000)
    assert abs(pnl) < 1.0  # within £1 on £10mm notional