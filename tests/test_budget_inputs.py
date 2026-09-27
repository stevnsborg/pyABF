"""Tests for pyabf.valuation.budget_inputs."""

import pytest

from pyabf import (Budget, BudgetCategory, BudgetLineItem, CategoryType,
                   CooperativeUnit, HousingCooperative)
from pyabf.valuation import (BudgetValuationMapping, DCFModel,
                             OperatingCostAssumptions, RentAssumptions,
                             ValuationAssumptions)


def _budget():
    budget = Budget(fiscal_year="2025/2026")
    income = BudgetCategory("income", "Indtægter", CategoryType.INCOME)
    income.add_item(BudgetLineItem("rent", "Boligafgift", budgeted=-2_000_000))
    income.add_item(BudgetLineItem("shop", "Erhvervsleje", budgeted=-300_000,
                                   actual=-160_000))
    ops = BudgetCategory("ops", "Driftsudgifter", CategoryType.EXPENSE)
    ops.add_item(BudgetLineItem("insurance", "Forsikringer", budgeted=200_000,
                                actual=90_000))
    ops.add_item(BudgetLineItem("tax", "Grundskyld", budgeted=150_000,
                                actual=75_000))
    ops.add_item(BudgetLineItem("repairs", "Reparationer", budgeted=100_000))
    ops.add_item(BudgetLineItem("interest", "Renter", budgeted=400_000))
    budget.add_category(income)
    budget.add_category(ops)
    return budget


MAPPING = {"insurance": "insurance", "tax": "property_tax",
           "repairs": "Maintenance"}


class TestOperatingCosts:
    def test_fields_and_other(self):
        op = BudgetValuationMapping(operating=MAPPING).operating_costs(_budget())
        assert op.insurance == 200_000
        assert op.property_tax == 150_000
        assert op.other == {"Maintenance": 100_000}
        assert op.total_operating_cost is None
        assert op.compute_total(_empty_property()) == 450_000

    def test_items_sharing_a_target_are_summed(self):
        op = BudgetValuationMapping(
            operating={"insurance": "Fixed", "tax": "Fixed"}
        ).operating_costs(_budget())
        assert op.other == {"Fixed": 350_000}

    def test_overrides_win(self):
        op = BudgetValuationMapping(operating=MAPPING).operating_costs(
            _budget(), insurance=1, exterior_maintenance_per_sqm=40)
        assert op.insurance == 1
        assert op.exterior_maintenance_per_sqm == 40

    def test_unknown_override(self):
        with pytest.raises(TypeError):
            BudgetValuationMapping(operating=MAPPING).operating_costs(
                _budget(), insurence=1)

    def test_include_unmapped_expenses(self):
        op = BudgetValuationMapping(
            operating={"insurance": "insurance"}, include_unmapped_expenses=True
        ).operating_costs(_budget())
        assert op.other == {"Grundskyld": 150_000, "Reparationer": 100_000,
                            "Renter": 400_000}

    def test_actual_and_extrapolated(self):
        actual = BudgetValuationMapping(operating=MAPPING, basis="actual")
        assert actual.operating_costs(_budget()).insurance == 90_000
        extra = BudgetValuationMapping(operating=MAPPING, basis="extrapolated",
                                       months_elapsed=6)
        assert extra.operating_costs(_budget()).insurance == 180_000

    def test_missing_item(self):
        with pytest.raises(KeyError):
            BudgetValuationMapping(operating={"nope": "insurance"}).operating_costs(
                _budget())

    @pytest.mark.parametrize("kw", [
        {"basis": "forecast"},
        {"months_elapsed": 0},
        {"operating": {"insurance": "total_operating_cost"}},
        {"operating": {"insurance": "exterior_maintenance_per_sqm"}},
    ])
    def test_invalid(self, kw):
        with pytest.raises(ValueError):
            BudgetValuationMapping(**kw)


def _empty_property():
    from pyabf.valuation import PropertyDescription
    return PropertyDescription()


class TestApply:
    def _assumptions(self):
        return ValuationAssumptions(
            rent=RentAssumptions(total_base_residential_rent=3_000_000,
                                 total_commercial_rent=999),
            operating=OperatingCostAssumptions(total_operating_cost=1_000_000),
        )

    def test_commercial_rent_is_positive(self):
        mapping = BudgetValuationMapping(commercial_rent=["shop"])
        assert mapping.commercial_rent_amount(_budget()) == 300_000

    def test_apply_copies_and_replaces_mapped_parameters(self):
        base = self._assumptions()
        mapping = BudgetValuationMapping(operating=MAPPING,
                                         commercial_rent=["shop"])
        new = mapping.apply(base, _budget())
        assert new.total_operating_cost == 450_000
        assert new.rent.total_commercial_rent == 300_000
        assert new.rent.total_base_residential_rent == 3_000_000
        # The original is untouched
        assert base.total_operating_cost == 1_000_000
        assert base.rent.total_commercial_rent == 999
        assert DCFModel(new).compute().total_value != DCFModel(base).compute().total_value

    def test_unmapped_parameters_are_kept(self):
        base = self._assumptions()
        new = BudgetValuationMapping(commercial_rent=["shop"]).apply(base, _budget())
        assert new.total_operating_cost == 1_000_000

    def test_overrides_need_operating_mapping(self):
        with pytest.raises(ValueError):
            BudgetValuationMapping(commercial_rent=["shop"]).apply(
                self._assumptions(), _budget(), insurance=1)


class TestCooperative:
    def test_valuation_assumptions_from_budget(self):
        coop = HousingCooperative(
            name="A/B Test",
            units=[CooperativeUnit("Street 1", area=100, rooms=3)],
            valuation_assumptions=TestApply()._assumptions(),
        )
        coop.add_budget(_budget())
        mapping = BudgetValuationMapping(operating=MAPPING)
        new = coop.valuation_assumptions_from_budget(
            "2025/2026", mapping, caretaker=50_000)
        assert new.total_operating_cost == 500_000
        assert coop.valuation_assumptions.total_operating_cost == 1_000_000
        assert coop.run_valuation(new).total_value > coop.run_valuation().total_value

    def test_missing_budget(self):
        coop = HousingCooperative(name="A/B Test",
                                  valuation_assumptions=ValuationAssumptions())
        with pytest.raises(ValueError):
            coop.valuation_assumptions_from_budget(
                "2030/2031", BudgetValuationMapping())
