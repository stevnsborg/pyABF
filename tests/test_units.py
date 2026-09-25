"""Tests for pyabf.units module."""

import pytest
from pyabf.units import Unit, CooperativeUnit, CommercialUnit, Improvement


class TestUnit:
    def test_charge_is_zero_without_cooperative(self):
        assert Unit("A", area=50, rooms=2).annual_charge == 0.0

    def test_fixed_rent_overrides_rate_for_rentals(self):
        unit = CommercialUnit("B", area=100, rooms=1, is_rental=True, fixed_rent=90_000)
        unit._rate_per_sqm = 500
        assert unit.annual_charge == 90_000

    def test_fixed_rent_ignored_for_owned(self):
        unit = Unit("C", area=100, rooms=1, fixed_rent=90_000)
        unit._rate_per_sqm = 500
        assert unit.annual_charge == 50_000

    def test_rate_is_not_an_init_argument(self):
        with pytest.raises(TypeError):
            Unit("D", area=1, rooms=1, _rate_per_sqm=5)


class TestImprovement:
    def test_linear_depreciation(self):
        imp = Improvement("k", year=2020, cost=100_000, lifespan=10)
        assert imp.remaining_value(2025) == pytest.approx(50_000)
        assert imp.remaining_value(2035) == 0.0

    def test_future_improvement_at_full_cost(self):
        assert Improvement("k", 2030, 1_000).remaining_value(2025) == 1_000

    def test_no_depreciation(self):
        imp = Improvement("k", 2000, 1_000, depreciation="none")
        assert imp.remaining_value(2050) == 1_000

    def test_invalid_lifespan(self):
        with pytest.raises(ValueError):
            Improvement("k", 2020, 1_000, lifespan=0).remaining_value(2021)


class TestCooperativeUnit:
    def test_share_value_and_max_price(self):
        unit = CooperativeUnit(
            "E", area=80, rooms=3,
            improvements=[Improvement("bath", 2020, 100_000, lifespan=10)],
        )
        assert unit.compute_share_value(10_000) == 800_000
        assert unit.improvements_value(2025) == pytest.approx(50_000)
        assert unit.max_sale_price(2025) == pytest.approx(850_000)

    def test_max_price_requires_share_value(self):
        with pytest.raises(ValueError):
            CooperativeUnit("F", area=50, rooms=2).max_sale_price(2025)
