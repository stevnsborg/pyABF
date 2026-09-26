"""Tests for pyabf.valuation.monte_carlo and HousingCooperative.run_monte_carlo."""

import numpy as np
import pytest

from pyabf import CooperativeUnit, HousingCooperative, Loan
from pyabf.valuation import (
    DCFModel,
    DEFAULT_PARAMETERS,
    EconomicAssumptions,
    ModernizationPlan,
    OperatingCostAssumptions,
    ParameterDistribution,
    PropertyDescription,
    RentAssumptions,
    ValuationAssumptions,
    run_monte_carlo,
)


def _assumptions(**operating):
    return ValuationAssumptions(
        property_desc=PropertyDescription(total_building_area=1_000, residential_area=1_000),
        rent=RentAssumptions(
            base_rent_per_sqm=1_000,
            modernized_rent_per_sqm=1_500,
            total_base_residential_rent=1_000_000,
        ),
        modernization=ModernizationPlan(total_area_sqm=1_000, cost_per_sqm=10_000, duration_years=10),
        operating=OperatingCostAssumptions(**(operating or {"total_operating_cost": 300_000})),
        economic=EconomicAssumptions(inflation_rate=0.02, required_real_return=0.03, evaluation_period=10),
    )


def _coop(**kw):
    return HousingCooperative(
        name="Test",
        units=[CooperativeUnit("A", area=500, rooms=2),
               CooperativeUnit("B", area=500, rooms=2, is_rental=True)],
        loans=[Loan("L1", principal=2_000_000, bond_price=90),
               Loan("L2", principal=1_000_000, bond_price=100)],
        valuation_assumptions=_assumptions(),
        **kw,
    )


class TestDefaults:
    def test_default_spreads(self):
        mc = run_monte_carlo(_assumptions(), n_samples=10, seed=0)
        table = mc.parameter_table()
        assert list(table.index) == list(DEFAULT_PARAMETERS)
        assert table.loc["economic.required_real_return", "std"] == pytest.approx(0.0025)
        assert table.loc["economic.inflation_rate", "std"] == pytest.approx(0.0025)
        assert table.loc["rent.modernized_rent_per_sqm", "std"] == pytest.approx(0.025 * 1_500)
        assert table.loc["operating.total_operating_cost", "std"] == pytest.approx(0.025 * 300_000)
        assert mc.n_samples == 10 and len(mc.samples) == 10

    def test_default_sample_count(self):
        mc = run_monte_carlo(_assumptions(), parameters="economic.inflation_rate", seed=0)
        assert mc.n_samples == 1000

    def test_operating_total_from_breakdown(self):
        mc = run_monte_carlo(_assumptions(insurance=200_000), parameters=[
            "operating.total_operating_cost"], n_samples=5, seed=0)
        assert mc.parameters[0].mean == 200_000


class TestSampling:
    def test_reproducible_with_seed(self):
        a = run_monte_carlo(_assumptions(), n_samples=20, seed=42)
        b = run_monte_carlo(_assumptions(), n_samples=20, seed=42)
        assert a.samples.equals(b.samples)

    def test_zero_std_reproduces_base_case(self):
        mc = run_monte_carlo(_assumptions(), parameters={"rent.modernized_rent_per_sqm": 0.0},
                             n_samples=5, seed=0)
        assert np.allclose(mc.values, DCFModel(_assumptions()).compute().total_value)
        assert mc.base_value == pytest.approx(mc.values[0])

    def test_each_draw_matches_dcf(self):
        mc = run_monte_carlo(_assumptions(), parameters=["economic.required_real_return"],
                             n_samples=3, seed=1)
        for r in mc.samples.itertuples():
            a = _assumptions()
            a.economic.required_real_return = r[1]
            assert r.total_value == pytest.approx(DCFModel(a).compute().total_value)

    def test_sample_statistics(self):
        mc = run_monte_carlo(_assumptions(), n_samples=4000, seed=3)
        assert mc.samples["economic.required_real_return"].std() == pytest.approx(0.0025, rel=0.05)
        assert mc.samples["rent.modernized_rent_per_sqm"].mean() == pytest.approx(1_500, rel=0.01)

    def test_input_not_modified(self):
        a = _assumptions()
        run_monte_carlo(a, n_samples=5, seed=0)
        assert a.operating.total_operating_cost == 300_000
        assert a.economic.required_real_return == 0.03

    def test_custom_distribution(self):
        dist = ParameterDistribution("economic.required_real_return", mean=0.04, std=0.001)
        mc = run_monte_carlo(_assumptions(), parameters=[dist], n_samples=5, seed=0)
        assert mc.parameters[0].mean == 0.04 and mc.parameters[0].std == 0.001

    def test_is_rate_override(self):
        dist = ParameterDistribution("rent.modernized_rent_per_sqm", is_rate=True)
        mc = run_monte_carlo(_assumptions(), parameters=[dist], n_samples=5, seed=0,
                             rate_abs_std=0.01)
        assert mc.parameters[0].std == 0.01

    def test_unknown_parameter(self):
        with pytest.raises(AttributeError):
            run_monte_carlo(_assumptions(), parameters=["rent.nope"], n_samples=2)

    def test_duplicate_parameter(self):
        with pytest.raises(ValueError):
            run_monte_carlo(_assumptions(), parameters=["rent.modernized_rent_per_sqm"] * 2)


class TestResult:
    def test_summary_and_sensitivity(self):
        mc = run_monte_carlo(_assumptions(), n_samples=500, seed=0)
        summary = mc.summary()
        assert {"base", "mean", "std", "p5", "p50", "p95"} <= set(summary.columns)
        assert summary.loc["total_value", "p5"] < summary.loc["total_value", "p95"]
        sens = mc.sensitivity()
        assert sens.index[0] == "economic.required_real_return"
        assert sens["contribution"].sum() == pytest.approx(1)
        assert 0 <= mc.probability_below(mc.base_value) <= 1


class TestCooperative:
    def test_stored_assumptions_used(self):
        coop = _coop()
        assert coop.run_valuation().total_value == DCFModel(_assumptions()).compute().total_value
        with pytest.raises(ValueError):
            HousingCooperative(name="X").run_valuation()

    def test_share_price_from_result_and_defaults(self):
        coop = _coop(other_assets=100_000, other_liabilities=50_000)
        result = coop.run_valuation()
        expected = (result.total_value + 100_000 - 2_800_000 - 50_000) / 500
        assert coop.compute_share_price(result) == pytest.approx(expected)

    def test_property_description(self):
        coop = _coop()
        desc = coop.property_description(land_area=300)
        assert desc.total_building_area == 1_000 and desc.land_area == 300

    def test_monte_carlo_share_price(self):
        coop = _coop(other_assets=100_000)
        mc = coop.run_monte_carlo(n_samples=200, seed=0)
        s = mc.samples
        assert {"loans.L1.bond_price", "loans.L2.bond_price", "share_price"} <= set(s.columns)
        debt = s["loans.L1.bond_price"] * 20_000 + s["loans.L2.bond_price"] * 10_000
        assert np.allclose(s["mortgage_debt"], debt)
        assert np.allclose(s["share_price"], (s["total_value"] + 100_000 - debt) / 500)
        assert mc.base_values["share_price"] == pytest.approx(
            coop.compute_share_price(coop.run_valuation()))
        assert mc.parameter_table().loc["loans.L1.bond_price", "std"] == pytest.approx(0.025 * 90)

    def test_monte_carlo_fixed_loans(self):
        mc = _coop().run_monte_carlo(n_samples=10, seed=0, loan_parameters=[])
        assert np.allclose(mc.samples["mortgage_debt"], 2_800_000)

    def test_monte_carlo_rejects_irrelevant_loan_parameter(self):
        with pytest.raises(ValueError):
            _coop().run_monte_carlo(n_samples=2, loan_parameters=["interest_rate"])


class TestShareCalculation:
    def test_balance_with_liquid_assets(self):
        coop = _coop(liquid_assets=300_000, other_assets=100_000, other_liabilities=50_000)
        calc = coop.share_calculation(10_000_000)
        assert calc.total_assets == 10_400_000
        assert calc.mortgage_debt == 2_800_000
        assert calc.equity == 10_400_000 - 2_850_000
        assert calc.price_per_sqm == pytest.approx(calc.equity / 500)
        assert calc.to_series()["Equity"] == calc.equity
        assert coop.compute_share_price(10_000_000) == calc.price_per_sqm

    def test_principal_debt_basis(self):
        coop = _coop(debt_basis="principal")
        assert coop.share_calculation(10_000_000).mortgage_debt == 3_000_000
        mc = coop.run_monte_carlo(n_samples=10, seed=0)
        assert not any(c.startswith("loans.") for c in mc.samples)
        assert np.allclose(mc.samples["mortgage_debt"], 3_000_000)
        with pytest.raises(ValueError):
            coop.run_monte_carlo(n_samples=2, loan_parameters=["bond_price"])
        with pytest.raises(ValueError):
            _coop(debt_basis="nominal")

    def test_share_values_per_andel(self):
        coop = _coop(liquid_assets=1_000_000)
        table = coop.share_values()
        assert list(table.index) == ["A"]  # the rental unit has no andel
        price = coop.compute_share_price(coop.run_valuation())
        assert table.loc["A", "share_value"] == pytest.approx(price * 500)

    def test_monte_carlo_includes_liquid_assets(self):
        coop = _coop(liquid_assets=1_000_000)
        mc = coop.run_monte_carlo(n_samples=50, seed=0)
        s = mc.samples
        assert np.allclose(s["equity"], s["total_value"] + 1_000_000 - s["mortgage_debt"])
        dist = coop.share_value_distribution(mc)
        assert dist.loc["A", "base"] == pytest.approx(mc.base_values["share_price"] * 500)
        assert dist.loc["A", "p5"] < dist.loc["A", "p95"]
