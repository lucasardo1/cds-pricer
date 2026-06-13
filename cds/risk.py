"""
cds/risk.py

Risk sensitivities for CDS positions, computed by bump-and-reprice.

CS01:  Change in upfront for a 1bp parallel shift in the spread curve.
IR01:  Change in upfront for a 1bp parallel shift in the swap curve.

Both are computed by:
    1. Price the trade at current market inputs
    2. Bump the relevant curve by 1bp
    3. Reprice
    4. Return the difference

Sign convention (protection buyer):
    CS01 is positive — spreads widen → protection worth more → gain
    IR01 is negative — rates rise → discount factors fall → loss

CS01 by tenor:
    Bumps each tenor node independently to show which part
    of the spread curve the trade is most sensitive to.
"""

from datetime import date
from typing import Dict, Tuple

from cds.curves import DiscountCurve, SurvivalCurve
from cds.schedule import build_schedule
from cds.pricer import upfront


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _build_and_price(
    trade_date:   date,
    maturity:     date,
    swap_rates:   Dict[float, float],
    spread_curve: Dict[float, float],
    coupon_bps:   float,
    notional:     float,
    recovery:     float,
    position:     int,
) -> float:
    """
    Build curves and return upfront for a given set of market inputs.
    Internal helper used by all risk functions.
    """
    dc  = DiscountCurve(swap_rates)
    sc  = SurvivalCurve(
        spread_curve, dc,
        recovery=recovery,
        trade_date=trade_date
    )
    sch = build_schedule(trade_date, maturity)
    return upfront(sch, sc, dc, coupon_bps, notional, recovery, position)


def _bump_spreads(
    spread_curve: Dict[float, float],
    bump_bps:     float = 1.0,
) -> Dict[float, float]:
    """
    Return a new spread curve with all tenors shifted by bump_bps.

    Args:
        spread_curve: Original spread curve (bps).
        bump_bps:     Size of bump in basis points. Default 1bp.

    Returns:
        New spread curve with bump applied.
    """
    return {t: s + bump_bps for t, s in spread_curve.items()}


def _bump_rates(
    swap_rates: Dict[float, float],
    bump_bps:   float = 1.0,
) -> Dict[float, float]:
    """
    Return a new swap curve with all tenors shifted by bump_bps.

    Args:
        swap_rates: Original swap curve (decimals).
        bump_bps:   Size of bump in basis points. Default 1bp.

    Returns:
        New swap curve with bump applied (still in decimals).
    """
    bump = bump_bps / 10_000
    return {t: r + bump for t, r in swap_rates.items()}


# ─────────────────────────────────────────────────────────────
# CS01
# ─────────────────────────────────────────────────────────────

def cs01(
    trade_date:   date,
    maturity:     date,
    swap_rates:   Dict[float, float],
    spread_curve: Dict[float, float],
    coupon_bps:   float,
    notional:     float,
    recovery:     float = 0.40,
    position:     int   = 1,
    bump_bps:     float = 1.0,
) -> float:
    """
    CS01 — sensitivity to a 1bp parallel shift in the spread curve.

    CS01 = Upfront(spread + 1bp) − Upfront(spread)

    For a protection buyer, CS01 is positive:
    wider spreads → protection worth more → upfront received increases.

    Approximately equal to:
        CS01 ≈ Risky Annuity × Notional / 10,000

    Args:
        trade_date:   Trade date.
        maturity:     CDS maturity date.
        swap_rates:   Swap curve as {tenor: rate}.
        spread_curve: CDS spread curve as {tenor: spread_bps}.
        coupon_bps:   Contract coupon in bps.
        notional:     Trade notional in currency units.
        recovery:     Recovery rate. Default 0.40.
        position:     +1 buyer, -1 seller. Default +1.
        bump_bps:     Bump size in bps. Default 1.0.

    Returns:
        CS01 in currency units per 1bp move.
    """
    base   = _build_and_price(
        trade_date, maturity, swap_rates, spread_curve,
        coupon_bps, notional, recovery, position
    )
    bumped = _build_and_price(
        trade_date, maturity, swap_rates,
        _bump_spreads(spread_curve, bump_bps),
        coupon_bps, notional, recovery, position
    )
    return bumped - base


def cs01_by_tenor(
    trade_date:   date,
    maturity:     date,
    swap_rates:   Dict[float, float],
    spread_curve: Dict[float, float],
    coupon_bps:   float,
    notional:     float,
    recovery:     float = 0.40,
    position:     int   = 1,
    bump_bps:     float = 1.0,
) -> Dict[float, float]:
    """
    CS01 bucketed by tenor — bumps each spread node independently.

    Shows which part of the spread curve the trade is most
    sensitive to. Useful for hedging — tells you which tenor
    CDS to buy/sell to flatten the risk.

    Args:
        Same as cs01(), no additional arguments.

    Returns:
        Dict mapping tenor to CS01 contribution in currency units.

    Example:
        {1: 45.2, 2: 89.1, 3: 134.0, 5: 220.5, 7: 0.0, 10: 0.0}
        (zeros for tenors beyond the trade maturity)
    """
    base = _build_and_price(
        trade_date, maturity, swap_rates, spread_curve,
        coupon_bps, notional, recovery, position
    )

    result = {}
    for tenor in spread_curve:
        # Bump only this tenor node
        bumped_curve = dict(spread_curve)
        bumped_curve[tenor] = spread_curve[tenor] + bump_bps

        bumped = _build_and_price(
            trade_date, maturity, swap_rates, bumped_curve,
            coupon_bps, notional, recovery, position
        )
        result[tenor] = bumped - base

    return result


# ─────────────────────────────────────────────────────────────
# IR01
# ─────────────────────────────────────────────────────────────

def ir01(
    trade_date:   date,
    maturity:     date,
    swap_rates:   Dict[float, float],
    spread_curve: Dict[float, float],
    coupon_bps:   float,
    notional:     float,
    recovery:     float = 0.40,
    position:     int   = 1,
    bump_bps:     float = 1.0,
) -> float:
    """
    IR01 — sensitivity to a 1bp parallel shift in the swap curve.

    IR01 = Upfront(swap + 1bp) − Upfront(swap)

    For a protection buyer, IR01 is typically small and negative:
    higher rates → lower discount factors → protection leg worth less.

    Much smaller than CS01 in absolute terms for most CDS.

    Args:
        trade_date:   Trade date.
        maturity:     CDS maturity date.
        swap_rates:   Swap curve as {tenor: rate}.
        spread_curve: CDS spread curve as {tenor: spread_bps}.
        coupon_bps:   Contract coupon in bps.
        notional:     Trade notional in currency units.
        recovery:     Recovery rate. Default 0.40.
        position:     +1 buyer, -1 seller. Default +1.
        bump_bps:     Bump size in bps. Default 1.0.

    Returns:
        IR01 in currency units per 1bp move.
    """
    base   = _build_and_price(
        trade_date, maturity, swap_rates, spread_curve,
        coupon_bps, notional, recovery, position
    )
    bumped = _build_and_price(
        trade_date, maturity,
        _bump_rates(swap_rates, bump_bps),
        spread_curve,
        coupon_bps, notional, recovery, position
    )
    return bumped - base