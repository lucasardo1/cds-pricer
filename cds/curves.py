"""
cds/curves.py

Discount curve and survival curve construction for CDS pricing.

DiscountCurve:
    Builds discount factors from continuously compounded swap rates.
    Interpolates linearly on rates between tenor nodes.

SurvivalCurve:
    Bootstraps piecewise constant hazard rates from CDS par spreads.
    Each tenor is solved independently using scipy.optimize.brentq,
    holding all previously solved hazard rates fixed.

Conventions:
    - Rates:     continuously compounded
    - Hazard:    piecewise constant between tenor nodes
    - Spreads:   input in basis points, converted to decimals internally
    - Recovery:  decimal (0.40 = 40%)
"""

import numpy as np
from scipy.optimize import brentq
from datetime import date
from typing import Dict, List, Tuple

from cds.schedule import build_schedule, act360, year_frac


# ─────────────────────────────────────────────────────────────
# DISCOUNT CURVE
# ─────────────────────────────────────────────────────────────

class DiscountCurve:
    """
    Discount curve built from continuously compounded swap rates.

    Interpolates linearly on rates between tenor nodes.
    Extrapolates flat beyond the last tenor.

    Args:
        swap_rates: Dict mapping tenor in years (float) to
                    continuously compounded rate (decimal).
                    e.g. {1: 0.0432, 2: 0.0418, 5: 0.0385}

    Example:
        >>> dc = DiscountCurve({1: 0.043, 2: 0.042, 5: 0.039})
        >>> dc.discount_factor(2.5)
        0.9014...
    """

    def __init__(self, swap_rates: Dict[float, float]):
        # Sort by tenor so interpolation works correctly
        sorted_items  = sorted(swap_rates.items())
        self._tenors  = np.array([t for t, r in sorted_items])
        self._rates   = np.array([r for t, r in sorted_items])

    def rate(self, t: float) -> float:
        """
        Interpolated continuously compounded rate at time t.

        Linear interpolation between nodes.
        Flat extrapolation beyond the last tenor.

        Args:
            t: Time in years.

        Returns:
            Continuously compounded rate as a decimal.
        """
        return float(np.interp(t, self._tenors, self._rates))

    def discount_factor(self, t: float) -> float:
        """
        Discount factor at time t.

        DF(t) = exp(−r(t) × t)

        Args:
            t: Time in years.

        Returns:
            Discount factor between 0 and 1.
        """
        if t <= 0:
            return 1.0
        r = self.rate(t)
        return float(np.exp(-r * t))


# ─────────────────────────────────────────────────────────────
# SURVIVAL CURVE
# ─────────────────────────────────────────────────────────────

class SurvivalCurve:
    """
    Survival curve bootstrapped from CDS par spreads.

    Assumes piecewise constant hazard rates between tenor nodes
    (the ISDA standard model assumption).

    Bootstraps iteratively: solves for each hazard rate segment
    by finding the value that makes the corresponding CDS NPV = 0,
    holding all previously solved segments fixed.

    Args:
        spread_curve:    Dict mapping tenor in years (float) to
                         CDS par spread in BASIS POINTS.
                         e.g. {1: 80, 2: 110, 3: 150, 5: 200}
        discount_curve:  A DiscountCurve instance.
        recovery:        Recovery rate as decimal. Default 0.40.
        trade_date:      Reference date. Defaults to today.

    Example:
        >>> dc = DiscountCurve({1: 0.043, 5: 0.039})
        >>> sc = SurvivalCurve({1: 80, 5: 200}, dc)
        >>> sc.survival_prob(5.0)
        0.8821...
    """

    def __init__(
        self,
        spread_curve:   Dict[float, float],
        discount_curve: DiscountCurve,
        recovery:       float = 0.40,
        trade_date:     date  = None,
    ):
        self._dc        = discount_curve
        self._recovery  = recovery
        self._trade_date = trade_date or date.today()

        # Bootstrap: solve hazard rates tenor by tenor
        sorted_items     = sorted(spread_curve.items())
        self._tenors     = [t for t, s in sorted_items]
        self._spreads    = [s / 10_000 for t, s in sorted_items]  # bps → decimal
        self._hazards    = self._bootstrap()

    # ── Public interface ──────────────────────────────────────

    def survival_prob(self, t: float) -> float:
        """
        Survival probability to time t.

        S(t) = exp(−∫₀ᵗ λ(s) ds)

        With piecewise constant hazard rates, this becomes:
        S(t) = exp(−Σ λᵢ × Δtᵢ)

        where the sum accumulates hazard over each segment up to t.

        Args:
            t: Time in years.

        Returns:
            Survival probability between 0 and 1.
        """
        if t <= 0:
            return 1.0
        return float(np.exp(-self._cumulative_hazard(t)))

    def hazard_rate(self, t: float) -> float:
        """
        Instantaneous hazard rate at time t.

        Returns the piecewise constant hazard rate for the
        segment containing t.

        Args:
            t: Time in years.

        Returns:
            Hazard rate as a decimal (e.g. 0.0133 = 1.33% per year).
        """
        for i, tenor in enumerate(self._tenors):
            if t <= tenor:
                return self._hazards[i]
        # Beyond last tenor — flat extrapolation
        return self._hazards[-1]

    # ── Bootstrapper ─────────────────────────────────────────

    def _bootstrap(self) -> List[float]:
        """
        Solve for piecewise constant hazard rates by iterating
        through tenors and finding the root of NPV = 0 at each.

        Returns:
            List of hazard rates, one per tenor segment.
        """
        hazards = []

        for i, (tenor, spread) in enumerate(
            zip(self._tenors, self._spreads)
        ):
            # Tenors solved so far (needed to price this CDS)
            solved_tenors  = self._tenors[:i]
            solved_hazards = hazards[:i]

            def npv(lam: float) -> float:
                """NPV of CDS at this tenor given candidate hazard rate lam."""
                trial_hazards = solved_hazards + [lam]
                trial_tenors  = solved_tenors  + [tenor]
                return self._price_cds(
                    tenor, spread, trial_tenors, trial_hazards
                )

            # Brentq: find lam in [1e-6, 10.0] where npv(lam) = 0
            try:
                lam = brentq(npv, 1e-6, 10.0, xtol=1e-10, rtol=1e-10)
            except ValueError:
                # Fallback: use flat hazard rate approximation
                lam = self._spreads[i] / (1 - self._recovery)
            hazards.append(lam)

        return hazards

    def _cumulative_hazard(self, t: float) -> float:
        """
        Cumulative hazard integral ∫₀ᵗ λ(s) ds.

        With piecewise constant hazard rates, this is a sum
        of λᵢ × (segment length) up to time t.

        Args:
            t: Time in years.

        Returns:
            Cumulative hazard (non-negative float).
        """
        cumulative = 0.0
        prev       = 0.0

        for tenor, lam in zip(self._tenors, self._hazards):
            if t <= tenor:
                cumulative += lam * (t - prev)
                return cumulative
            cumulative += lam * (tenor - prev)
            prev = tenor

        # Beyond last tenor — flat extrapolation
        cumulative += self._hazards[-1] * (t - prev)
        return cumulative

    def _survival_from_segments(
        self,
        t:        float,
        tenors:   List[float],
        hazards:  List[float],
    ) -> float:
        """
        Survival probability using a trial set of hazard rate segments.

        Used during bootstrapping before self._hazards is finalised.

        Args:
            t:       Time in years.
            tenors:  Tenor nodes (partially built during bootstrap).
            hazards: Hazard rates (partially built during bootstrap).

        Returns:
            Survival probability.
        """
        cumulative = 0.0
        prev       = 0.0

        for tenor, lam in zip(tenors, hazards):
            if t <= tenor:
                cumulative += lam * (t - prev)
                return float(np.exp(-cumulative))
            cumulative += lam * (tenor - prev)
            prev = tenor

        cumulative += hazards[-1] * (t - prev)
        return float(np.exp(-cumulative))

    def _price_cds(
        self,
        tenor:   float,
        spread:  float,
        tenors:  List[float],
        hazards: List[float],
    ) -> float:
        """
        Price a CDS (compute NPV) given trial hazard rate segments.

        NPV = PV(Protection Leg) − PV(Premium Leg)

        Used during bootstrapping to find the hazard rate that
        sets NPV = 0.

        Args:
            tenor:   Maturity in years.
            spread:  Par spread as decimal (e.g. 0.0200 = 200bps).
            tenors:  Trial tenor nodes.
            hazards: Trial hazard rates.

        Returns:
            NPV of the CDS. Zero when correctly priced.
        """
        # Build a payment schedule for this tenor
        from dateutil.relativedelta import relativedelta
        maturity = self._imm_from_years(tenor)
        schedule = build_schedule(self._trade_date, maturity)

        R  = self._recovery
        pv_protection = 0.0
        pv_premium    = 0.0

        s_prev = 1.0  # survival prob at start of first period

        for (t_start, t_end, dcf, yf) in schedule:
            s_end = self._survival_from_segments(yf, tenors, hazards)
            df    = self._dc.discount_factor(yf)

            # Protection leg: (1−R) × marginal default prob × DF
            pd            = s_prev - s_end
            pv_protection += (1 - R) * pd * df

            # Premium leg: spread × survival × DF × day count fraction
            pv_premium    += spread * s_end * df * dcf

            s_prev = s_end

        return pv_protection - pv_premium

    def _imm_from_years(self, years: float) -> date:
        """
        Convert a tenor in years to the nearest IMM maturity date.

        Adds the year offset to the trade date and finds
        the nearest March/June/September/December 20th.

        Args:
            years: Tenor as a float (e.g. 5.0 for 5Y).

        Returns:
            IMM maturity date.
        """
        from dateutil.relativedelta import relativedelta
        from cds.schedule import next_imm_date

        approx = self._trade_date + relativedelta(years=int(years))
        return next_imm_date(approx - relativedelta(days=1))