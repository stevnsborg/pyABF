"""Tests for pyabf.valuation subpackage."""

import pytest
from pyabf.valuation import (
    ValuationAssumptions,
    PropertyDescription,
    RentAssumptions,
    ModernizationPlan,
    OperatingCostAssumptions,
    EconomicAssumptions,
    DCFModel,
    ValuationReport,
    run_sensitivity,
    compute_net_present_value,
)


def _assumptions(**kw):
    a = ValuationAssumptions(
        property_desc=PropertyDescription(total_building_area=1_000, residential_area=1_000),
        rent=RentAssumptions(
            base_rent_per_sqm=1_000,
            modernized_rent_per_sqm=1_500,
            total_base_residential_rent=1_000_000,
        ),
        modernization=ModernizationPlan(total_area_sqm=1_000, cost_per_sqm=10_000, duration_years=10),
        operating=OperatingCostAssumptions(total_operating_cost=300_000),
        economic=EconomicAssumptions(inflation_rate=0.02, required_real_return=0.03, evaluation_period=10),
    )
    for k, v in kw.items():
        setattr(a, k, v)
    return a


class TestAssumptions:
    def test_operating_total_from_breakdown(self):
        op = OperatingCostAssumptions(
            insurance=100, other={"misc": 50}, exterior_maintenance_per_sqm=2
        )
        assert op.compute_total(PropertyDescription(total_building_area=10)) == 170

    def test_stabilised_yield_is_real_return(self):
        econ = EconomicAssumptions(inflation_rate=0.02, required_real_return=0.03)
        assert econ.discount_rate == pytest.approx(0.05)
        assert econ.stabilised_yield == pytest.approx(0.03)


class TestDCF:
    def test_no_modernization_is_perpetuity(self):
        # Without modernization, NOI grows with inflation from year 1, so
        # PV = NOI_0 × (1+g) / (d − g) — up to the model's terminal convention.
        a = _assumptions(modernization=ModernizationPlan())
        result = DCFModel(a).compute()
        noi0 = 1_000_000 - 300_000
        assert result.total_value == pytest.approx(noi0 / 0.03, rel=0.03)

    def test_modernization_cost_stops_when_area_done(self):
        a = _assumptions(modernization=ModernizationPlan(
            total_area_sqm=1_000, cost_per_sqm=10_000, duration_years=5))
        flows = DCFModel(a).compute().projection.budget_period_flows
        assert flows[4].modernization_cost > 0
        assert all(cf.modernization_cost == 0 for cf in flows[5:])
        base_cost = sum(cf.modernization_cost / cf.inflation_factor for cf in flows)
        assert base_cost == pytest.approx(1_000 * 10_000)

    def test_higher_return_lowers_value(self):
        low = DCFModel(_assumptions()).compute().total_value
        a = _assumptions()
        a.economic.required_real_return = 0.04
        assert DCFModel(a).compute().total_value < low


class TestSensitivityAndReport:
    def test_grid_shape_and_center(self):
        a = _assumptions()
        grid = run_sensitivity(a)
        assert grid.values.shape == (7, 5)
        assert grid.values[3, 2] == pytest.approx(DCFModel(a).compute().total_value)

    def test_report_renders(self):
        a = _assumptions()
        result = DCFModel(a).compute()
        text = ValuationReport(result, a).to_text(include_sensitivity=False)
        assert "TOTAL PROPERTY VALUE" in text


def test_legacy_function_warns():
    with pytest.warns(DeprecationWarning):
        compute_net_present_value(1, 1, 1, 1, 15)
