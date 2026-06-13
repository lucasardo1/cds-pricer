# CDS Pricer

A from-scratch CDS pricing library in Python implementing the ISDA standard model methodology.

Built to understand the mechanics of single-name CDS pricing from first principles — survival curve bootstrapping, par spread solving, upfront calculation, and risk sensitivities (CS01, IR01).

---

## Motivation

Credit Default Swaps are the foundation of credit risk transfer and hedging in fixed income. Pricing them correctly requires:

- A bootstrapped **survival curve** implied from market spreads
- A **discount curve** from risk-free rates
- Careful handling of **payment schedules** (IMM dates, ACT/360 day count)
- **Risk metrics** computed by bump-and-reprice against the survival curve

Most implementations use black-box libraries. This project builds every component from scratch and validates against Bloomberg CDSW.

---

## Methodology

### Survival Curve

The survival probability to time *t* is:

```
Survival(t) = exp(−∫₀ᵗ λ(s) ds)
```

Where λ(s) is the hazard rate — the instantaneous conditional default probability.

We assume **piecewise constant hazard rates** between tenor nodes (the ISDA standard). Given market CDS spreads at tenors [1Y, 2Y, 3Y, 5Y, 7Y, 10Y], we bootstrap iteratively:

- Solve for λ₁ such that the 1Y CDS prices to par
- Hold λ₁ fixed, solve for λ₂ such that the 2Y CDS prices to par
- Repeat through all tenors

Each solve uses `scipy.optimize.brentq` (bracketed root finding).

### Discount Curve

Built from swap rates using linear interpolation on continuously compounded rates. Discount factors:

```
DF(t) = exp(−r(t) × t)
```

### CDS Legs

**Premium leg** — the fixed coupon payments, survival-weighted:
```
PV(Premium) = Coupon × Σ [Survival(tᵢ) × DF(tᵢ) × Δtᵢ]
```

**Protection leg** — the contingent default payment:
```
PV(Protection) = (1 − R) × Σ [PD(tᵢ) × DF(tᵢ)]

Where PD(tᵢ) = Survival(tᵢ₋₁) − Survival(tᵢ)
```

### Par Spread

The spread that sets NPV = 0:
```
Par Spread = PV(Protection) / Risky Annuity

Risky Annuity = Σ [Survival(tᵢ) × DF(tᵢ) × Δtᵢ]
```

### Upfront Payment (Post-2009 Big Bang)

Since 2009, CDS trade with standardised coupons (100bps IG, 500bps HY). An upfront payment compensates for the difference:
```
Upfront = (Par Spread − Coupon) × Risky Annuity × Notional
```

### Risk Metrics

Computed by bump-and-reprice:

- **CS01** — shift spread curve +1bp, rebuild survival curve, reprice. Δ upfront.
- **IR01** — shift swap curve +1bp, rebuild discount curve, reprice. Δ upfront.

---

## Project Structure

```
cds-pricer/
│
├── cds/
│   ├── schedule.py     # IMM dates, payment schedules, ACT/360 day count
│   ├── curves.py       # Discount curve + survival curve bootstrapper
│   ├── pricer.py       # Premium leg, protection leg, par spread, upfront
│   ├── risk.py         # CS01, IR01, DV01 by bump-and-reprice
│   └── utils.py        # Date helpers, day count fractions
│
├── data/
│   ├── dummy/          # Synthetic market data for development
│   └── real/           # Bloomberg data (not committed to git)
│
├── notebooks/
│   ├── 01_curve_construction.ipynb
│   ├── 02_single_name_pricer.ipynb
│   ├── 03_portfolio_risk.ipynb
│   └── 04_bloomberg_validation.ipynb
│
└── tests/              # Unit tests for each module
```

---

## Build Order

| Phase | Module | Description |
|---|---|---|
| 1 | `schedule.py` | IMM dates, payment schedule, day count |
| 2 | `curves.py` | Discount curve + survival curve bootstrap |
| 3 | `pricer.py` | Par spread, upfront, risky annuity |
| 4 | `risk.py` | CS01, IR01 bump-and-reprice |
| 5 | `notebooks/` | Walkthrough and visualisation |
| 6 | Validation | Benchmark vs Bloomberg CDSW |

---

## Data

### Dummy Data (Development)

Synthetic trades and market data in `data/dummy/`. Designed so the real data loader is a drop-in replacement.

### Real Data (Bloomberg)

- CDS par spreads: `CDSW` screen, or `CDS_SPREAD` field via `blpapi`
- Risk-free curve: YCSW0023 (USD OIS) or equivalent
- Recovery rates: ISDA standard (40% senior unsecured)
- IMM dates: calculated from schedule module

Real data files are excluded from version control via `.gitignore`.

---

## Validation

Each component is validated independently:

1. **Survival curve** — reprice all input spreads, check NPV < 1e-6
2. **Monotonicity** — survival probabilities strictly decreasing
3. **End-to-end** — par spread, upfront, CS01 benchmarked against Bloomberg CDSW

---

## Requirements

```
numpy
pandas
scipy
matplotlib
jupyter
```

Install:
```bash
pip install -r requirements.txt
```

---

## Roadmap

- [ ] Single-name CDS pricer (par spread, upfront, CS01, IR01)
- [ ] Portfolio aggregation (summed CS01 by tenor bucket)
- [ ] Index CDS (iTraxx XOVER, CDX HY)
- [ ] Bloomberg data integration via `blpapi`
- [ ] CDS option pricing (swaption on credit spread)
- [ ] Streamlit dashboard for live pricing

---

## Author

Luca Sardo — Fixed Income Credit Risk
