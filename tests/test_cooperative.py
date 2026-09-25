"""Tests for pyabf.cooperative and pyabf.accounting modules."""

import pytest
from pyabf import (
    HousingCooperative,
    CooperativeUnit,
    CommercialUnit,
    Loan,
    AccountEntry,
    AnnualReport,
    Budget,
)


@pytest.fixture
def coop():
    return HousingCooperative(
        name="Test",
        units=[
            CooperativeUnit("A", area=60, rooms=2),
            CooperativeUnit("B", area=40, rooms=1, is_rental=True),
            CommercialUnit("C", area=100, rooms=1, is_rental=True, fixed_rent=50_000),
        ],
        owned_rate_per_sqm=600,
        rental_rate_per_sqm=900,
        loans=[Loan("L", principal=1_000_000, interest_rate=0.02, bond_price=90)],
    )


class TestHousingCooperative:
    def test_areas_and_income(self, coop):
        assert coop.total_area == 200
        assert coop.owned_residential_area == 60
        assert coop.total_annual_income == 60 * 600 + 40 * 900 + 50_000

    def test_rate_changes_propagate(self, coop):
        coop.set_owned_rate(700)
        assert coop.owned_annual_income == 60 * 700

    def test_add_unit_gets_rate(self, coop):
        unit = CooperativeUnit("D", area=10, rooms=1)
        coop.add_unit(unit)
        assert unit.annual_charge == 6_000

    def test_share_price(self, coop):
        price = coop.compute_and_update_shares(property_value=2_000_000)
        assert price == pytest.approx((2_000_000 - 900_000) / 60)
        assert coop.units[0].share_value == pytest.approx(price * 60)
        # Rental units do not get a share value
        assert coop.units[1].share_value is None

    def test_debt_service(self, coop):
        loan = coop.loans[0]
        assert coop.total_annual_debt_service == pytest.approx(loan.annuity_payment * 4)

    def test_budget_tracker_missing_year(self, coop):
        with pytest.raises(KeyError):
            coop.create_budget_tracker("1999")
        coop.add_budget(Budget("2025"))
        assert coop.create_budget_tracker("2025").budget.fiscal_year == "2025"

    def test_property_tax_projection(self, coop):
        rows = coop.project_property_tax(20_000_000, 200_000, 0.026, 2024, 2026)
        assert [r["year"] for r in rows] == [2024, 2025, 2026]


class TestAnnualReport:
    def test_default_layout(self):
        report = AnnualReport.from_defaults(2025)
        assert len(report.notes) == 10
        report.find_note("01").add_item("rent", 1_000)
        report.find_note("06").add_item("roof", 300)
        assert report.result == 700

    def test_custom_layout(self):
        report = AnnualReport.from_defaults(2025, notes={"1": ("Income", False)})
        assert [n.name for n in report.notes] == ["Income"]

    def test_add_duplicate_note(self):
        report = AnnualReport(2025, notes=[AccountEntry("01")])
        with pytest.raises(ValueError):
            report.add_note(AccountEntry("01"))
