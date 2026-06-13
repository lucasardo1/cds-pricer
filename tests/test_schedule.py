"""
tests/test_schedule.py

Unit tests for cds/schedule.py
Run with: pytest tests/test_schedule.py -v
"""

import pytest
from datetime import date
from cds.schedule import (
    next_imm_date,
    imm_dates_between,
    build_schedule,
    act360,
    year_frac,
)


# ─────────────────────────────────────────────
# IMM DATE TESTS
# ─────────────────────────────────────────────

def test_next_imm_date_before_march():
    """From January, next IMM should be March 20."""
    assert next_imm_date(date(2026, 1, 1)) == date(2026, 3, 20)

def test_next_imm_date_on_imm():
    """From exactly an IMM date, next should be the following IMM."""
    assert next_imm_date(date(2026, 6, 20)) == date(2026, 9, 20)

def test_next_imm_date_after_december():
    """From December 21, next IMM should wrap to March next year."""
    assert next_imm_date(date(2026, 12, 21)) == date(2027, 3, 20)

def test_next_imm_date_mid_year():
    """From June 13, next IMM is June 20 — a short stub is valid."""
    assert next_imm_date(date(2026, 6, 13)) == date(2026, 6, 20)

def test_imm_dates_between_one_year():
    """One year from Jun 13 2026 includes the Jun 20 stub."""
    result = imm_dates_between(date(2026, 6, 13), date(2027, 6, 20))
    expected = [
        date(2026, 6, 20),   # short stub
        date(2026, 9, 20),
        date(2026, 12, 20),
        date(2027, 3, 20),
        date(2027, 6, 20),
    ]
    assert result == expected

def test_imm_dates_between_five_years():
    """5Y CDS from Jun 13 has 21 periods including the front stub."""
    result = imm_dates_between(date(2026, 6, 13), date(2031, 6, 20))
    assert len(result) == 21

def test_imm_dates_end_inclusive():
    """Maturity date itself should be included."""
    result = imm_dates_between(date(2026, 6, 13), date(2026, 9, 20))
    assert date(2026, 9, 20) in result


# ─────────────────────────────────────────────
# DAY COUNT TESTS
# ─────────────────────────────────────────────

def test_act360_quarter():
    """Jun 20 to Sep 20 = 92 days / 360."""
    result = act360(date(2026, 6, 20), date(2026, 9, 20))
    assert abs(result - 92 / 360) < 1e-10

def test_act360_positive():
    """Day count fraction should always be positive."""
    result = act360(date(2026, 1, 1), date(2026, 12, 31))
    assert result > 0

def test_year_frac_one_year():
    """Exactly one year should return ~1.0."""
    result = year_frac(date(2026, 6, 13), date(2027, 6, 13))
    assert abs(result - 1.0) < 0.01


# ─────────────────────────────────────────────
# SCHEDULE TESTS
# ─────────────────────────────────────────────

def test_schedule_structure():
    """Each row should be a 4-tuple."""
    schedule = build_schedule(date(2026, 6, 13), date(2031, 6, 20))
    for row in schedule:
        assert len(row) == 4

def test_schedule_length_5y():
    """5Y CDS from Jun 13 should have 21 periods including front stub."""
    schedule = build_schedule(date(2026, 6, 13), date(2031, 6, 20))
    assert len(schedule) == 21

def test_schedule_year_fracs_increasing():
    """Year fractions must be strictly increasing."""
    schedule = build_schedule(date(2026, 6, 13), date(2031, 6, 20))
    yfracs = [row[3] for row in schedule]
    assert all(yfracs[i] < yfracs[i+1] for i in range(len(yfracs)-1))

def test_schedule_dcf_positive():
    """All day count fractions must be positive."""
    schedule = build_schedule(date(2026, 6, 13), date(2031, 6, 20))
    assert all(row[2] > 0 for row in schedule)

def test_schedule_periods_contiguous():
    """End of one period should be start of the next."""
    schedule = build_schedule(date(2026, 6, 13), date(2031, 6, 20))
    for i in range(len(schedule) - 1):
        assert schedule[i][1] == schedule[i+1][0]