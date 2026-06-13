# Build Plan

## Phase 1 — Schedule (schedule.py)

The foundation. Everything else depends on correct payment dates.

- [ ] `next_imm_date(date)` — next IMM date from any given date
- [ ] `imm_dates_between(start, end)` — all IMM dates in a range
- [ ] `payment_schedule(trade_date, maturity)` — full list of payment dates
- [ ] `day_count_fraction(start, end)` — ACT/360 fraction for each period
- [ ] `year_fraction(start, end)` — time in years from settlement to each date

**Done when:** `tests/test_schedule.py` all pass

---

## Phase 2 — Curves (curves.py)

The core model. Survival curve is the heart of CDS pricing.

- [ ] `DiscountCurve` class
  - [ ] Takes swap curve dict as input
  - [ ] Interpolates continuously compounded rates
  - [ ] `discount_factor(t)` method
- [ ] `SurvivalCurve` class
  - [ ] Takes spread curve dict + DiscountCurve as input
  - [ ] Bootstraps piecewise constant hazard rates
  - [ ] `survival_prob(t)` method
  - [ ] `hazard_rate(t)` method
- [ ] Validation: reprice all input spreads → NPV < 1e-6

**Done when:** `tests/test_curves.py` all pass + reprice validation clean

---

## Phase 3 — Pricer (pricer.py)

- [ ] `premium_leg(schedule, survival_curve, discount_curve, coupon)`
- [ ] `protection_leg(schedule, survival_curve, discount_curve, recovery)`
- [ ] `risky_annuity(schedule, survival_curve, discount_curve)`
- [ ] `par_spread(trade, survival_curve, discount_curve)` 
- [ ] `upfront(trade, survival_curve, discount_curve)`
- [ ] `npv(trade, survival_curve, discount_curve)`

**Done when:** `tests/test_pricer.py` all pass

---

## Phase 4 — Risk (risk.py)

- [ ] `cs01(trade, spread_curve, swap_curve)` — bump spread +1bp, reprice
- [ ] `ir01(trade, spread_curve, swap_curve)` — bump swap +1bp, reprice
- [ ] `cs01_by_tenor(trade, spread_curve, swap_curve)` — bucket CS01 by tenor

**Done when:** CS01 on 5Y IG trade ≈ £450-500 per £10mm notional

---

## Phase 5 — Dummy Data (data/dummy/)

- [ ] `trades.json` — 5 sample trades (IG, HY, short dated, long dated, distressed)
- [ ] `market_data.json` — realistic spread curves and swap curve

---

## Phase 6 — Notebooks

- [ ] `01_curve_construction.ipynb` — visual walkthrough of bootstrapping
- [ ] `02_single_name_pricer.ipynb` — price a trade step by step
- [ ] `03_portfolio_risk.ipynb` — aggregate CS01 across a book
- [ ] `04_bloomberg_validation.ipynb` — compare outputs vs Bloomberg CDSW

---

## Phase 7 — Polish

- [ ] Clean up all docstrings
- [ ] Final README review
- [ ] All tests green
- [ ] Push clean final version to GitHub