"""Smoke tests for pyabf.plotting (skipped without matplotlib)."""

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

from pyabf import CooperativeUnit, HousingCooperative, Loan  # noqa: E402
from pyabf.plotting import (  # noqa: E402
    andel_areas,
    plot_share_value_cdf,
    plot_share_value_ranges,
)
from tests.test_monte_carlo import _assumptions  # noqa: E402


@pytest.fixture(scope="module")
def coop_and_mc():
    coop = HousingCooperative(
        name="Test",
        units=[CooperativeUnit("A", area=60, rooms=2), CooperativeUnit("B", area=80, rooms=3)],
        loans=[Loan("L", principal=1_000_000, bond_price=90)],
        valuation_assumptions=_assumptions(),
        share_price_buffer=500_000,
    )
    return coop, coop.run_monte_carlo(n_samples=100, seed=0)


def test_andel_areas(coop_and_mc):
    coop, _ = coop_and_mc
    assert andel_areas(coop) == {"A": 60, "B": 80}
    assert andel_areas([62]) == {"62 m²": 62}
    assert andel_areas({"x": 1}) == {"x": 1}


def test_ranges(coop_and_mc):
    coop, mc = coop_and_mc
    ax = plot_share_value_ranges(mc, coop)
    assert len(ax.get_yticks()) == 2
    matplotlib.pyplot.close("all")


def test_cdf(coop_and_mc):
    _, mc = coop_and_mc
    ax = plot_share_value_cdf(mc, [62], threshold=1_000_000)
    assert len(ax.lines) >= 1
    plot_share_value_cdf(mc, [50, 75])
    with pytest.raises(ValueError):
        plot_share_value_cdf(mc, [1, 2, 3, 4, 5])
    matplotlib.pyplot.close("all")
