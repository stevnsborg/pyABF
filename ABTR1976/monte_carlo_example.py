"""
monte_carlo_example.py — Monte Carlo simulation of the TR76 valuarvurdering.

Walks through the general cases:

    1. Default parameters on the valuation alone
    2. A chosen subset of parameters, default spreads
    3. Custom spreads ({path: std} and ParameterDistribution)
    4. Through the Forening: property value, debt (bond prices) and
       share price together
    5. Which parameters drive the spread (input for a tornado chart)

Defaults: 1000 samples; std 2.5 % of the value for amounts and 0.25
percentage points for rates.

Run from the repository root:
    python ABTR1976/monte_carlo_example.py
"""

from __future__ import annotations

import pandas as pd

from pyabf import HousingCooperative, ParameterDistribution, run_monte_carlo

from tr76 import build_tr76

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", None)
pd.set_option("display.float_format", lambda v: f"{v:,.4g}" if abs(v) < 10 else f"{v:,.0f}")

MILLION = 1_000_000


def main(forening: HousingCooperative | None = None, seed: int = 1976) -> None:
    forening = forening or build_tr76()
    assumptions = forening.valuation_assumptions
    base = forening.run_valuation()
    print(f"{forening.name}: base-case value {base.total_value:,.0f} DKK\n")

    # 1. Default parameters (see pyabf.valuation.DEFAULT_PARAMETERS)
    mc = run_monte_carlo(assumptions, seed=seed)
    print("1) Default parameters — input distributions")
    print(mc.parameter_table(), "\n")
    print(mc.summary(["total_value"]), "\n")
    lo, hi = mc.quantile([0.05, 0.95])
    print(f"   90 % interval: {lo / MILLION:.1f}M – {hi / MILLION:.1f}M DKK\n")

    # 2. Only the parameters you select, default spreads
    mc = run_monte_carlo(
        assumptions,
        parameters=["economic.required_real_return",
                    "rent.modernized_rent_per_sqm"],
        seed=seed,
    )
    print("2) Required return and modernized rent only")
    print(mc.summary(["total_value"]), "\n")

    # 3. Custom spreads: a mapping {path: std} (None = default), or
    #    ParameterDistribution for full control (mean, std, is_rate)
    mc = run_monte_carlo(
        assumptions,
        parameters=[
            ParameterDistribution("economic.required_real_return", std=0.005),
            ParameterDistribution("operating.total_operating_cost",
                                  std=0.05 * 3_628_333),
            "modernization.cost_per_sqm",
        ],
        n_samples=2000,
        seed=seed,
    )
    print("3) Custom spreads (return ±0.5 pp, operating cost ±5 %), 2000 draws")
    print(mc.parameter_table())
    print(mc.summary(["total_value"]), "\n")

    # 4. Through the Forening: valuation + loan bond prices -> share price
    mc = forening.run_monte_carlo(seed=seed)
    print("4) Forening: property value, debt and share price")
    print(mc.summary(["total_value", "debt_market_value", "equity",
                      "share_price"]), "\n")
    for area in (62, 75):
        p5, p50, p95 = mc.quantile([0.05, 0.5, 0.95], "share_price") * area
        print(f"   {area} m² andel: median {p50:,.0f} DKK "
              f"(90 %: {p5:,.0f} – {p95:,.0f})")
    print()

    # 5. What drives the spread
    print("5) Contribution to the spread of the share price")
    print(mc.sensitivity("share_price"), "\n")

    # All draws, one row each — the input for any plot
    print("Samples:", mc.samples.shape, "\n", mc.samples.head(3).T)


if __name__ == "__main__":
    main()
