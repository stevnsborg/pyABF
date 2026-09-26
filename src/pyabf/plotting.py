"""
plotting.py — Charts of the Monte Carlo share values (matplotlib).

Requires matplotlib (``pip install "pyABF[plot]"``).

Both charts take a :class:`~pyabf.valuation.MonteCarloResult` from
:meth:`HousingCooperative.run_monte_carlo` and the andele to show, given
as a cooperative (its owner-occupied residential units), a
``{label: area}`` mapping, or a list of areas in m².

    plot_share_value_ranges — Range bars per andel: 90 % and 50 %
                              intervals, median and base case
    plot_share_value_cdf    — Cumulative curve: the chance that an
                              andel's value is below a given amount

Contains:
    andel_areas, plot_share_value_ranges, plot_share_value_cdf
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from .cooperative import HousingCooperative
    from .valuation import MonteCarloResult

# Colors: one blue ramp for the single-series range chart, categorical
# slots in fixed order for the cumulative curves, and ink for text.
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
BLUE_LIGHT = "#9ec5f4"   # 90 % interval
BLUE = "#2a78d6"         # 50 % interval
BLUE_DARK = "#104281"    # median
CATEGORICAL = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")

MAX_CDF_SERIES = len(CATEGORICAL)

Areas = "HousingCooperative | Mapping[str, float] | Iterable[float]"


def _pyplot():
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - depends on the env
        raise ImportError(
            'Plotting needs matplotlib: pip install "pyABF[plot]"'
        ) from exc
    return plt


def andel_areas(areas: Any) -> dict[str, float]:
    """Normalise the accepted ``areas`` forms to ``{label: area}``.

    Args:
        areas: A cooperative (its owner-occupied residential units,
            labelled by address), a ``{label: area}`` mapping, or a list
            of areas (labelled ``"62 m²"``).
    """
    if hasattr(areas, "owned_residential"):
        return {u.address: float(u.area) for u in areas.owned_residential}
    if isinstance(areas, Mapping):
        return {str(k): float(v) for k, v in areas.items()}
    return {f"{a:g} m²": float(a) for a in areas}


def _money_formatter(scale: float, unit: str):
    from matplotlib.ticker import FuncFormatter

    def fmt(v, _pos):
        return f"{v / scale:,.2f}".rstrip("0").rstrip(".") + unit
    return FuncFormatter(fmt)


def _scale_for(values: np.ndarray) -> tuple[float, str]:
    top = float(np.nanmax(np.abs(values))) if len(values) else 0.0
    if top >= 1e6:
        return 1e6, "M"
    if top >= 1e3:
        return 1e3, "k"
    return 1.0, ""


def _style_axes(ax: Axes, value_axis: str) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.set_facecolor(SURFACE)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9, length=0)
    ax.grid(axis=value_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _new_axes(ax: Axes | None, height: float):
    plt = _pyplot()
    if ax is None:
        fig, ax = plt.subplots(figsize=(9, height))
        fig.patch.set_facecolor(SURFACE)
    return ax


def plot_share_value_ranges(
    mc: MonteCarloResult,
    areas: Any,
    ax: Axes | None = None,
    title: str | None = "Share value per andel",
    xlabel: str = "Share value (DKK)",
    label_median: bool = True,
) -> Axes:
    """Range bars of the simulated share value per andel.

    Each row shows the 90 % interval (p5–p95, thin light bar), the 50 %
    interval (p25–p75, thick bar), the median (dark tick) and the base
    case (open diamond).  Rows are ordered by area, smallest at the top.

    Args:
        mc: Result of ``HousingCooperative.run_monte_carlo``.
        areas: The andele to show (see :func:`andel_areas`).
        ax: Axes to draw on; a new figure if omitted.
        title: Chart title (``None`` for none).
        xlabel: Value-axis label.
        label_median: Write the median value at the end of each row.

    Returns:
        The matplotlib Axes.
    """
    rows = sorted(andel_areas(areas).items(), key=lambda kv: kv[1])
    if not rows:
        raise ValueError("No andele to plot.")
    price = mc.samples["share_price"].to_numpy()
    q = np.quantile(price, [0.05, 0.25, 0.5, 0.75, 0.95])
    base = mc.base_values["share_price"]

    ax = _new_axes(ax, height=1.2 + 0.55 * len(rows))
    y = np.arange(len(rows))[::-1]
    area = np.array([a for _, a in rows])
    p5, p25, p50, p75, p95 = (q[i] * area for i in range(5))

    ax.hlines(y, p5, p95, color=BLUE_LIGHT, linewidth=5,
              label="90 % of simulations")
    ax.hlines(y, p25, p75, color=BLUE, linewidth=11,
              label="50 % of simulations")
    ax.scatter(p50, y, marker="|", s=260, linewidths=2.5, color=BLUE_DARK,
               zorder=3, label="Median")
    ax.scatter(base * area, y, marker="D", s=46, facecolor=SURFACE,
               edgecolor=INK, linewidths=1.4, zorder=4, label="Base case")

    scale, unit = _scale_for(p95)
    if label_median:
        for yi, hi, med in zip(y, p95, p50):
            ax.annotate(
                f"median {med / scale:,.2f}{unit}", (hi, yi),
                xytext=(8, 0), textcoords="offset points", va="center",
                fontsize=9, color=INK_SECONDARY,
            )
    ax.set_yticks(y, [f"{label}  ({a:g} m²)" if not label.endswith("m²")
                      else label for label, a in rows])
    ax.xaxis.set_major_formatter(_money_formatter(scale, unit))
    ax.set_xlabel(xlabel, color=INK_SECONDARY, fontsize=10)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.margins(x=0.12)
    _style_axes(ax, "x")
    ax.spines["left"].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12 - 0.3 / len(rows)),
              ncol=4, frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    if title:
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold",
                     color=INK, pad=10)
    return ax


def plot_share_value_cdf(
    mc: MonteCarloResult,
    areas: Any,
    ax: Axes | None = None,
    threshold: float | None = None,
    title: str | None = "Chance the share value is below a given amount",
    xlabel: str = "Share value (DKK)",
) -> Axes:
    """Cumulative distribution of the simulated share value.

    One curve per andel (at most four).  Read it as: at value *x* on the
    horizontal axis, the curve gives the share of simulations where the
    andel is worth less than *x*.  The base case is marked with a dot;
    dashed guides mark 5 %, 50 % and 95 %.  With a single andel the
    5 / 50 / 95 % values are labelled on the curve.

    Args:
        mc: Result of ``HousingCooperative.run_monte_carlo``.
        areas: The andele to show (see :func:`andel_areas`).  Use a
            single typical andel, or compare a few sizes.
        ax: Axes to draw on; a new figure if omitted.
        threshold: Optional value (DKK) to mark, labelled with the
            chance of being below it (first andel only).
        title: Chart title (``None`` for none).
        xlabel: Value-axis label.

    Returns:
        The matplotlib Axes.
    """
    from matplotlib.ticker import PercentFormatter

    rows = sorted(andel_areas(areas).items(), key=lambda kv: kv[1])
    if not rows:
        raise ValueError("No andele to plot.")
    if len(rows) > MAX_CDF_SERIES:
        raise ValueError(
            f"At most {MAX_CDF_SERIES} andele per cumulative chart; "
            "pick representative sizes."
        )
    price = np.sort(mc.samples["share_price"].to_numpy())
    prob = np.arange(1, len(price) + 1) / len(price)
    base = mc.base_values["share_price"]
    scale, unit = _scale_for(price * rows[-1][1])

    ax = _new_axes(ax, height=4.8)
    for level in (0.05, 0.5, 0.95):
        ax.axhline(level, color=INK_MUTED, linewidth=0.8, linestyle=(0, (4, 3)),
                   zorder=1)
        ax.annotate(f"{level:.0%}", (1, level), xycoords=("axes fraction", "data"),
                    xytext=(4, 0), textcoords="offset points", va="center",
                    fontsize=8, color=INK_MUTED)

    for (label, area), color in zip(rows, CATEGORICAL):
        values = price * area
        ax.plot(values, prob, color=color, linewidth=2, label=label, zorder=2)
        base_prob = float(np.mean(price <= base))
        ax.scatter([base * area], [base_prob], s=64, color=color,
                   edgecolor=SURFACE, linewidths=2, zorder=3)
        if len(rows) > 1:
            med = np.quantile(values, 0.5)
            ax.annotate(label, (med, 0.5), xytext=(6, -12),
                        textcoords="offset points", fontsize=9,
                        color=INK_SECONDARY)

    if len(rows) == 1:
        label, area = rows[0]
        # Percentile values left of the curve, base case to the right
        for level in (0.05, 0.5, 0.95):
            v = np.quantile(price, level) * area
            ax.annotate(f"{level:.0%}: {v / scale:,.2f}{unit}", (v, level),
                        xytext=(-10, 4), textcoords="offset points",
                        ha="right", va="bottom", fontsize=9,
                        color=INK_SECONDARY)
        ax.annotate(f"base case {base * area / scale:,.2f}{unit}",
                    (base * area, float(np.mean(price <= base))),
                    xytext=(10, -4), textcoords="offset points", ha="left",
                    va="top", fontsize=9, color=INK_SECONDARY)

    if threshold is not None:
        area = rows[0][1]
        p_below = float(np.mean(price * area < threshold))
        ax.axvline(threshold, color=INK, linewidth=1, zorder=1)
        ax.annotate(f"{p_below:.0%} below {threshold / scale:,.2f}{unit}",
                    (threshold, 0.02), xytext=(6, 0), textcoords="offset points",
                    fontsize=9, color=INK)

    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.xaxis.set_major_formatter(_money_formatter(scale, unit))
    ax.set_xlabel(xlabel, color=INK_SECONDARY, fontsize=10)
    ax.set_ylabel("Share of simulations below", color=INK_SECONDARY, fontsize=10)
    _style_axes(ax, "both")
    if len(rows) > 1:
        ax.legend(loc="upper left", frameon=False, fontsize=9,
                  labelcolor=INK_SECONDARY)
    if title:
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold",
                     color=INK, pad=10)
    return ax
