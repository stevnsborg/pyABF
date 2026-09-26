"""
monte_carlo_example.py — Monte Carlo simulation of the TR76 valuarvurdering.

Walks through the general cases:

    1. Default parameters on the valuation alone
    2. A chosen subset of parameters, default spreads
    3. Custom spreads ({path: std} and ParameterDistribution)
    4. The share price: the Forening's balance (property value + liquid
       holdings − debt − buffer) per m² of andel, and the value of each
       andel, with and without the 40M buffer
    5. Through the Forening: the Monte Carlo of the property value, debt
       (bond prices), share price and value per andel together
    6. Which parameters drive the spread (input for a tornado chart)
    7. Plots: range bars per andel and the cumulative curve for a 62 m²
       andel, saved to ABTR1976/figures/ (needs matplotlib)

Defaults: 1000 samples; std 2.5 % of the value for amounts and 0.25
percentage points for rates.

Run from the repository root:
    python ABTR1976/monte_carlo_example.py
"""

from __future__ import annotations

import pandas as pd

from pathlib import Path

from pyabf import HousingCooperative, ParameterDistribution, run_monte_carlo

from tr76 import build_tr76

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", None)
pd.set_option("display.float_format", lambda v: f"{v:,.4g}" if abs(v) < 10 else f"{v:,.0f}")

MILLION = 1_000_000
FIGURES = Path(__file__).parent / "figures"


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

    # 4. From property value to share price (base case): the balance
    #    and the value of each andel
    calc = forening.share_calculation(base)
    print("4) Andelsværdi, base case")
    print(calc.to_series().to_string(float_format=lambda v: f"{v:,.0f}"), "\n")
    print(forening.share_values(base), "\n")
    no_buffer = forening.share_calculation(base, buffer=0).price_per_sqm
    print(f"   Without the buffer: {no_buffer:,.0f} DKK/m² "
          f"(the {calc.buffer / MILLION:.0f}M buffer is "
          f"{no_buffer - calc.price_per_sqm:,.0f} DKK/m²)\n")

    # 5. Monte Carlo through the Forening: valuation + loan bond prices,
    #    then the same balance for every draw
    mc = forening.run_monte_carlo(seed=seed)
    print("5) Forening Monte Carlo: property value, debt and share price")
    print(mc.summary(["total_value", "mortgage_debt", "equity",
                      "share_price"]), "\n")
    print("   Value per andel (DKK)")
    print(forening.share_value_distribution(mc), "\n")

    # 6. What drives the spread
    print("6) Contribution to the spread of the share price")
    print(mc.sensitivity("share_price"), "\n")

    # All draws, one row each — the input for any plot
    print("Samples:", mc.samples.shape, "\n", mc.samples.head(3).T, "\n")

    plot(mc)


def plot(mc) -> None:
    """7. Save the range and cumulative charts to ABTR1976/figures/."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print('7) Skipping plots: pip install "pyABF[plot]"')
        return
    from pyabf.plotting import plot_share_value_cdf, plot_share_value_ranges

    FIGURES.mkdir(exist_ok=True)
    # Typical apartment sizes; pass the Forening itself to show every andel
    sizes = [50, 62, 75, 90, 110]
    ax = plot_share_value_ranges(
        mc, sizes, title="TR76 — share value per andel (40M buffer withheld)")
    ax.figure.savefig(FIGURES / "share_value_ranges.png", dpi=150,
                      bbox_inches="tight")
    ax = plot_share_value_cdf(
        mc, [62], threshold=1_000_000,
        title="TR76 — 62 m² andel: chance the value is below a given amount")
    ax.figure.savefig(FIGURES / "share_value_cdf_62m2.png", dpi=150,
                      bbox_inches="tight")
    ax = plot_share_value_cdf(mc, [50, 75, 110], title="TR76 — by andel size")
    ax.figure.savefig(FIGURES / "share_value_cdf_sizes.png", dpi=150,
                      bbox_inches="tight")
    plt.close("all")
    print(f"7) Plots saved to {FIGURES}")


if __name__ == "__main__":
    main()
