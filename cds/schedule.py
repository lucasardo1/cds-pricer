"""
cds/schedule.py

Payment schedule generation for CDS contracts.

Conventions:
    - Payment dates: IMM dates (Mar/Jun/Sep/Dec 20th)
    - Day count:     ACT/360 (ISDA standard for CDS)
    - Frequency:     Quarterly
"""

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Tuple


# ─────────────────────────────────────────────
# IMM DATE LOGIC
# ─────────────────────────────────────────────

IMM_MONTHS = [3, 6, 9, 12]  # Mar, Jun, Sep, Dec


def next_imm_date(reference_date: date) -> date:
    """
    Return the next IMM date strictly after reference_date.

    IMM dates are the 20th of March, June, September, December.

    Args:
        reference_date: The date to search forward from.

    Returns:
        The next IMM date after reference_date.

    Example:
        >>> next_imm_date(date(2026, 6, 13))
        date(2026, 9, 20)
    """
    year = reference_date.year

    for month in IMM_MONTHS:
        candidate = date(year, month, 20)
        if candidate > reference_date:
            return candidate

    # No IMM date found this year — return first IMM of next year
    return date(year + 1, 3, 20)


def imm_dates_between(start: date, end: date) -> List[date]:
    """
    Return all IMM dates strictly after start and up to and including end.

    Args:
        start: Start date (exclusive) — typically trade date.
        end:   End date (inclusive)   — typically maturity date.

    Returns:
        List of IMM dates in chronological order.

    Example:
        >>> imm_dates_between(date(2026, 6, 13), date(2027, 6, 20))
        [date(2026, 9, 20), date(2026, 12, 20), date(2027, 3, 20), date(2027, 6, 20)]
    """
    dates = []
    current = next_imm_date(start)

    while current <= end:
        dates.append(current)
        current = _next_imm_after(current)

    return dates


def _next_imm_after(imm_date: date) -> date:
    """
    Given an IMM date, return the following IMM date.
    Internal helper — use next_imm_date() for external calls.
    """
    month_idx = IMM_MONTHS.index(imm_date.month)

    if month_idx < len(IMM_MONTHS) - 1:
        # Next IMM is later in the same year
        return date(imm_date.year, IMM_MONTHS[month_idx + 1], 20)
    else:
        # December — wrap to March next year
        return date(imm_date.year + 1, 3, 20)


# ─────────────────────────────────────────────
# PAYMENT SCHEDULE
# ─────────────────────────────────────────────

def build_schedule(
    trade_date: date,
    maturity: date,
) -> List[Tuple[date, date, float, float]]:
    """
    Build the full payment schedule for a CDS contract.

    Each row represents one coupon period:
        (period_start, period_end, dcf, year_frac)

    Where:
        dcf       = ACT/360 day count fraction for the coupon period
        year_frac = time in years from trade_date to period_end
                    used to look up survival probability and discount factor

    Args:
        trade_date: Date the trade is entered into.
        maturity:   Maturity date of the CDS (should be an IMM date).

    Returns:
        List of tuples: (period_start, period_end, dcf, year_frac)

    Example:
        >>> schedule = build_schedule(date(2026, 6, 13), date(2027, 6, 20))
        >>> schedule[0]
        (date(2026, 6, 13), date(2026, 9, 20), 0.2722, 0.2694)
    """
    payment_dates = imm_dates_between(trade_date, maturity)

    schedule = []
    period_start = trade_date

    for period_end in payment_dates:
        dcf = act360(period_start, period_end)
        yf  = year_frac(trade_date, period_end)
        schedule.append((period_start, period_end, dcf, yf))
        period_start = period_end

    return schedule


# ─────────────────────────────────────────────
# DAY COUNT
# ─────────────────────────────────────────────

def act360(start: date, end: date) -> float:
    """
    ACT/360 day count fraction.

    Used for CDS coupon accrual (ISDA standard).
    Counts actual calendar days, divides by 360.

    Args:
        start: Period start date (inclusive).
        end:   Period end date (exclusive in market convention,
               but we use end - start for day count).

    Returns:
        Day count fraction as a float.

    Example:
        >>> act360(date(2026, 6, 20), date(2026, 9, 20))
        0.25  # 92 days / 360
    """
    return (end - start).days / 360.0


def year_frac(base_date: date, target_date: date) -> float:
    """
    Year fraction from base_date to target_date using ACT/365.

    Used to index into the discount and survival curves.
    Note: ACT/365 for year fractions (not ACT/360 — different use).

    Args:
        base_date:   Reference start (typically trade date).
        target_date: The date we want the year fraction to.

    Returns:
        Year fraction as a float.
    """
    return (target_date - base_date).days / 365.0