# CLAUDE.md — Project Context & Guidelines

This file gives context to anyone (or any AI assistant) working on this codebase.
Read this before touching any file.

---

## What This Project Is

A from-scratch CDS pricing library. The goal is to understand and implement the
ISDA standard model methodology without relying on black-box libraries.

Built by Luca Sardo — credit risk analyst at TwentyFour Asset Management —
as a systematic quant finance portfolio project.

---

## What This Project Is NOT

- Not a production trading system
- Not a Bloomberg wrapper
- Not a copy of the `isda` Python package

The point is to build every component from first principles, then validate
against market-standard tools.

---

## Core Design Principles

### 1. Dummy data first, real data later
Every module is built against `data/dummy/`. Real Bloomberg data slots in
via a loader swap — the pricing engine never changes.

### 2. Build order is strict
Do not skip ahead. Each module depends on the previous:
```
schedule.py → curves.py → pricer.py → risk.py → notebooks
```

### 3. Validate at every step
Each module has corresponding tests in `tests/`. Run them before moving on.
The survival curve must reprice all input spreads to NPV < 1e-6.

### 4. No magic numbers
All constants (recovery rate, coupon, day count convention) are explicit
parameters. Nothing hardcoded inside functions.

### 5. Everything is documented
Every function has a docstring explaining:
- What it does
- Parameters and types
- What it returns
- The mathematical formula it implements

---

## Module Responsibilities

### schedule.py
- Generate IMM dates (Mar/Jun/Sep/Dec 20th)
- Build payment schedule from trade date to maturity
- Calculate ACT/360 day count fractions
- Calculate year fractions from settlement date

### curves.py
- Build discount curve from swap rates (linear interp on cont. comp. rates)
- Bootstrap survival curve from CDS par spreads (piecewise constant hazard)
- Expose `discount_factor(t)` and `survival_prob(t)` methods
- Validate: reprice all input spreads → NPV must be < 1e-6

### pricer.py
- Price premium leg (survival-weighted coupon PV)
- Price protection leg (default-weighted recovery PV)
- Solve for par spread (protection leg / risky annuity)
- Calculate upfront payment (post-2009 Big Bang convention)
- Calculate risky annuity

### risk.py
- CS01: bump spread curve +1bp → rebuild survival curve → reprice → delta
- IR01: bump swap curve +1bp → rebuild discount curve → reprice → delta
- All risk by bump-and-reprice, not analytical

### utils.py
- Date arithmetic helpers
- ACT/360 and ACT/365 day count
- Any shared helper functions

---

## Data Structures

### Trade (dict)
```python
trade = {
    "trade_date":       "2026-06-13",
    "maturity":         "2031-06-20",   # IMM date
    "notional":         10_000_000,
    "coupon_bps":       100,            # 100 = IG standard, 500 = HY
    "recovery_rate":    0.40,
    "spread_bps":       250,            # flat spread (for single tenor)
}
```

### Spread Curve (dict)
```python
spread_curve = {
    "1Y":  80,
    "2Y":  110,
    "3Y":  150,
    "5Y":  200,
    "7Y":  230,
    "10Y": 260,
}  # all values in basis points
```

### Swap Curve (dict)
```python
swap_curve = {
    "1Y":  0.045,
    "2Y":  0.044,
    "3Y":  0.043,
    "5Y":  0.042,
    "7Y":  0.041,
    "10Y": 0.040,
}  # all values as decimals (not percent)
```

---

## Key Conventions

| Convention | Choice | Reason |
|---|---|---|
| Day count | ACT/360 | ISDA standard for CDS |
| Payment frequency | Quarterly | ISDA standard |
| Hazard rate interpolation | Piecewise constant | ISDA standard |
| Rate interpolation | Linear on cont. comp. | Simple, sufficient |
| Spread units | Basis points in data, decimals in calculations | Convert at boundary |
| Dates | Python `datetime.date` objects throughout | No strings inside functions |

---

## Validation Targets

| Check | Target |
|---|---|
| Survival curve reprice | NPV < 1e-6 for all input tenors |
| Survival monotonicity | Strictly decreasing |
| Par spread (IG example) | Within 0.5bp of Bloomberg CDSW |
| CS01 (5Y IG) | ~£450-500 per £10mm notional |
| Upfront sign | Positive if par spread > coupon (buyer pays up) |

---

## Build Status

- [ ] schedule.py
- [ ] curves.py
- [ ] pricer.py
- [ ] risk.py
- [ ] utils.py
- [ ] tests/test_schedule.py
- [ ] tests/test_curves.py
- [ ] tests/test_pricer.py
- [ ] notebooks/01_curve_construction.ipynb
- [ ] notebooks/02_single_name_pricer.ipynb
- [ ] notebooks/03_portfolio_risk.ipynb
- [ ] notebooks/04_bloomberg_validation.ipynb

---

## Future Extensions (do not build yet)

- Index CDS (iTraxx XOVER, CDX HY)
- CDS options
- Bloomberg `blpapi` data loader
- Streamlit dashboard
- SQL Server integration for portfolio risk storage