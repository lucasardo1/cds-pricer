"""
cds/pricer.py

CDS pricing functions.

Takes a payment schedule, survival curve, and discount curve
and computes the value of each leg, par spread, and upfront payment.

All functions are stateless — they take curves and schedules as inputs
and return floats. No classes needed here.

Conventions:
    - Spreads:   input/output in basis points
    - Upfront:   output in currency units (e.g. GBP)
    - Notional:  input in currency units
    - Position:  +1 = protection buyer, -1 = protection seller
"""

from datetime import date
from typing import List, Tuple

from cds.curves import DiscountCurve, SurvivalCurve
from cds.schedule import build_schedule


# ─────────────────────────────────────────────────────────────
# CORE BUILDING BLOCKS
# ─────────────────────────────────────────────────────────────

def risky_annuity(
    schedule:        List[Tuple],
    survival_curve:  SurvivalCurve,
    discount_curve:  DiscountCurve,
) -> float:
    """
    Risky annuity (RPV01) — PV of receiving 1bp per year,
    weighted by survival probability.

    Risky Annuity = Σ [S(tᵢ) × DF(tᵢ) × Δtᵢ]

    This is the key scaling factor in CDS pricing:
        Par Spread = Protection Leg / Risky Annuity
        Upfront    = (Par Spread − Coupon) × Risky Annuity × Notional
        CS01       ≈ Risky Annuity / 10,000

    Args:
        schedule:        Output of build_schedule().
        survival_curve:  Bootstrapped SurvivalCurve instance.
        discount_curve:  DiscountCurve instance.

    Returns:
        Risky annuity as a float (in years, survival-weighted).
    """
    ra = 0.0
    for (t_start, t_end, dcf, yf) in schedule:
        s  = survival_curve.survival_prob(yf)
        df = discount_curve.discount_factor(yf)
        ra += s * df * dcf
    return ra


def premium_leg(
    schedule:        List[Tuple],
    survival_curve:  SurvivalCurve,
    discount_curve:  DiscountCurve,
    coupon_bps:      float,
) -> float:
    """
    Present value of the premium leg.

    The protection buyer pays a fixed coupon each quarter,
    but only while the reference entity is still alive.

    PV(Premium) = Coupon × Σ [S(tᵢ) × DF(tᵢ) × Δtᵢ]
                = Coupon × Risky Annuity

    Args:
        schedule:        Output of build_schedule().
        survival_curve:  Bootstrapped SurvivalCurve instance.
        discount_curve:  DiscountCurve instance.
        coupon_bps:      Fixed coupon in basis points (e.g. 100).

    Returns:
        PV of premium leg per unit notional.
    """
    coupon = coupon_bps / 10_000
    return coupon * risky_annuity(schedule, survival_curve, discount_curve)


def protection_leg(
    schedule:        List[Tuple],
    survival_curve:  SurvivalCurve,
    discount_curve:  DiscountCurve,
    recovery:        float = 0.40,
) -> float:
    """
    Present value of the protection leg.

    The protection seller pays (1 − R) × Notional if a default occurs.
    The expected PV sums over each period's marginal default probability.

    PV(Protection) = (1−R) × Σ [PD(tᵢ) × DF(tᵢ)]

    Where:
        PD(tᵢ) = S(tᵢ₋₁) − S(tᵢ)   (marginal default prob in period i)

    Args:
        schedule:        Output of build_schedule().
        survival_curve:  Bootstrapped SurvivalCurve instance.
        discount_curve:  DiscountCurve instance.
        recovery:        Recovery rate as decimal. Default 0.40.

    Returns:
        PV of protection leg per unit notional.
    """
    pv   = 0.0
    s_prev = 1.0

    for (t_start, t_end, dcf, yf) in schedule:
        s_end = survival_curve.survival_prob(yf)
        df    = discount_curve.discount_factor(yf)

        # Marginal default probability in this period
        pd    = s_prev - s_end
        pv   += (1 - recovery) * pd * df

        s_prev = s_end

    return pv


def par_spread(
    schedule:        List[Tuple],
    survival_curve:  SurvivalCurve,
    discount_curve:  DiscountCurve,
    recovery:        float = 0.40,
) -> float:
    """
    Par spread — the coupon that makes the CDS NPV = 0 at inception.

    Par Spread = PV(Protection Leg) / Risky Annuity

    Args:
        schedule:        Output of build_schedule().
        survival_curve:  Bootstrapped SurvivalCurve instance.
        discount_curve:  DiscountCurve instance.
        recovery:        Recovery rate as decimal. Default 0.40.

    Returns:
        Par spread in BASIS POINTS.
    """
    ra  = risky_annuity(schedule, survival_curve, discount_curve)
    pl  = protection_leg(schedule, survival_curve, discount_curve, recovery)
    return (pl / ra) * 10_000  # → basis points


def upfront(
    schedule:        List[Tuple],
    survival_curve:  SurvivalCurve,
    discount_curve:  DiscountCurve,
    coupon_bps:      float,
    notional:        float,
    recovery:        float = 0.40,
    position:        int   = 1,
) -> float:
    """
    Upfront payment (post-2009 Big Bang convention).

    Since 2009, CDS trade with standardised coupons (100bps IG,
    500bps HY). The upfront payment compensates for the difference
    between the fixed coupon and the fair par spread.

    Upfront = (Par Spread − Coupon) × Risky Annuity × Notional

    Sign convention:
        Positive → protection buyer pays upfront to seller
                   (par spread > coupon, e.g. risky entity)
        Negative → protection seller pays upfront to buyer
                   (par spread < coupon, e.g. very safe entity)

    Position:
        +1 = protection buyer  (pays upfront if positive)
        -1 = protection seller (receives upfront if positive)

    Args:
        schedule:        Output of build_schedule().
        survival_curve:  Bootstrapped SurvivalCurve instance.
        discount_curve:  DiscountCurve instance.
        coupon_bps:      Standardised contract coupon in bps.
        notional:        Trade notional in currency units.
        recovery:        Recovery rate as decimal. Default 0.40.
        position:        +1 buyer, -1 seller. Default +1.

    Returns:
        Upfront payment in currency units.
        Positive = buyer pays, Negative = seller pays.
    """
    ps  = par_spread(schedule, survival_curve, discount_curve, recovery)
    ra  = risky_annuity(schedule, survival_curve, discount_curve)

    # Convert to decimals for calculation
    spread_diff = (ps - coupon_bps) / 10_000

    return position * spread_diff * ra * notional


def npv(
    schedule:        List[Tuple],
    survival_curve:  SurvivalCurve,
    discount_curve:  DiscountCurve,
    coupon_bps:      float,
    notional:        float,
    recovery:        float = 0.40,
    position:        int   = 1,
) -> float:
    """
    Mark-to-market NPV of an existing CDS position.

    NPV = (Protection Leg − Premium Leg) × Notional × Position

    For a new trade at par spread, NPV = 0.
    For an existing trade, NPV reflects market movement since inception.

    Args:
        schedule:        Output of build_schedule().
        survival_curve:  Current market survival curve.
        discount_curve:  Current market discount curve.
        coupon_bps:      Contract coupon fixed at trade inception.
        notional:        Trade notional in currency units.
        recovery:        Recovery rate as decimal.
        position:        +1 buyer, -1 seller.

    Returns:
        NPV in currency units.
    """
    pl  = protection_leg(schedule, survival_curve, discount_curve, recovery)
    pml = premium_leg(schedule, survival_curve, discount_curve, coupon_bps)
    return position * (pl - pml) * notional