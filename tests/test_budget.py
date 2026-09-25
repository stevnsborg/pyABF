"""Tests for pyabf.budget module."""

import io
import pytest
from pyabf.budget import (
    BudgetLineItem,
    BudgetCategory,
    Budget,
    BudgetTracker,
    AccountMapping,
    BalanceSheetRow,
    CategoryType,
    load_balance_sheet_csv,
    parse_danish_number,
    _round_to,
    _increment_fiscal_year,
)


class TestParseDanishNumber:
    def test_positive_integer(self):
        assert parse_danish_number("1.573.500,00") == 1_573_500.0

    def test_negative(self):
        assert parse_danish_number("-20.477,27") == -20_477.27

    def test_zero(self):
        assert parse_danish_number("0,00") == 0.0

    def test_empty(self):
        assert parse_danish_number("") == 0.0

    def test_whitespace(self):
        assert parse_danish_number("  ") == 0.0

    def test_small_number(self):
        assert parse_danish_number("149,85") == 149.85

    def test_large_negative(self):
        assert parse_danish_number("-4.385.000,00") == -4_385_000.0


class TestBudgetLineItem:
    def test_variance(self):
        item = BudgetLineItem("rent", "Rent", budgeted=100_000, actual=105_000)
        assert item.variance == 5_000

    def test_utilisation(self):
        item = BudgetLineItem("ins", "Insurance", budgeted=200_000, actual=180_000)
        assert item.utilisation == pytest.approx(0.9)

    def test_utilisation_zero_budget(self):
        item = BudgetLineItem("misc", "Misc", budgeted=0, actual=500)
        assert item.utilisation is None


class TestBudgetCategory:
    def test_totals(self):
        cat = BudgetCategory("ops", "Operations", CategoryType.EXPENSE)
        cat.add_item(BudgetLineItem("a", "A", budgeted=100, actual=90))
        cat.add_item(BudgetLineItem("b", "B", budgeted=200, actual=250))
        assert cat.total_budgeted == 300
        assert cat.total_actual == 340
        assert cat.total_variance == 40


class TestBudget:
    @staticmethod
    def _make_budget():
        b = Budget(fiscal_year="2025/2026")
        inc = BudgetCategory("income", "Income", CategoryType.INCOME)
        inc.add_item(BudgetLineItem("rent", "Rent", budgeted=-4_385_000))
        inc.add_item(BudgetLineItem("lease", "Lease", budgeted=-240_000))
        b.add_category(inc)
        exp = BudgetCategory("ops", "Operations", CategoryType.EXPENSE)
        exp.add_item(BudgetLineItem("tax", "Tax", budgeted=380_000))
        exp.add_item(BudgetLineItem("ins", "Insurance", budgeted=290_000))
        b.add_category(exp)
        b.rent_amount = 4_385_000
        b.mortgage_principal = 708_000
        return b

    def test_operating_result(self):
        b = self._make_budget()
        assert b.operating_result_budgeted == 3_955_000

    def test_find_item(self):
        b = self._make_budget()
        assert b.find_item("tax") is not None
        assert b.find_item("nonexistent") is None


class TestLoadBalanceSheetCsv:
    SAMPLE_CSV = "Fin.;Konto;Tekst;D/S;Bem.;Bev. per.;Saldo pr.;Budget året\n1341;;Indtaegter;;;;\n1341;11100;Erhvervsleje, opkraevet;Dr;;-20.477,27;-221.801,53;-240.000,00\n1341;11310;Boligafgift, opkraevet;Dr;;-371.736,00;-4.013.356,00;-4.385.000,00\n1341;;Indtaegter i alt;;;-392.213,27;-4.235.157,53;-4.625.000,00\n1341;13010;Ejendomsskatter/grundskyld;Dr;;-91.197,58;415.202,43;380.000,00\n"

    def test_parses_rows_with_account_numbers(self):
        rows = load_balance_sheet_csv(io.StringIO(self.SAMPLE_CSV))
        assert len(rows) == 3
        assert rows[0].account_number == "11100"
        assert rows[0].ytd_balance == pytest.approx(-221_801.53)

    def test_skips_section_headers(self):
        rows = load_balance_sheet_csv(io.StringIO(self.SAMPLE_CSV))
        account_numbers = [r.account_number for r in rows]
        assert "" not in account_numbers

    def test_budget_column_parsed(self):
        rows = load_balance_sheet_csv(io.StringIO(self.SAMPLE_CSV))
        assert rows[1].annual_budget == pytest.approx(-4_385_000.0)


class TestAccountMapping:
    def test_lookup(self):
        m = AccountMapping()
        m.add("11100", "commercial_lease")
        m.add("11310", "rent")
        assert m.lookup("11100") == "commercial_lease"
        assert m.lookup("99999") is None

    def test_add_many(self):
        m = AccountMapping()
        m.add_many({"11100": "lease", "11310": "rent"})
        assert m.lookup("11100") == "lease"


class TestBudgetTracker:
    @staticmethod
    def _make_tracker():
        b = Budget(fiscal_year="2025/2026")
        inc = BudgetCategory("income", "Income", CategoryType.INCOME)
        inc.add_item(BudgetLineItem("rent", "Rent", budgeted=-4_385_000))
        inc.add_item(BudgetLineItem("lease", "Lease", budgeted=-240_000))
        b.add_category(inc)
        exp = BudgetCategory("ops", "Operations", CategoryType.EXPENSE)
        exp.add_item(BudgetLineItem("tax", "Tax", budgeted=380_000))
        exp.add_item(BudgetLineItem("ins", "Insurance", budgeted=290_000))
        exp.add_item(BudgetLineItem("maint", "Maintenance", budgeted=700_000))
        b.add_category(exp)
        b.rent_amount = 4_385_000
        b.mortgage_principal = 708_000
        m = AccountMapping()
        m.add_many({
            "11100": "lease",
            "11310": "rent",
            "13010": "tax",
            "13100": "ins",
            "15500": "maint",
        })
        return BudgetTracker(budget=b, mapping=m)

    def test_update_actuals(self):
        tracker = self._make_tracker()
        rows = [
            BalanceSheetRow("11100", "Lease", ytd_balance=-221_801.53),
            BalanceSheetRow("11310", "Rent", ytd_balance=-4_013_356.0),
            BalanceSheetRow("13010", "Tax", ytd_balance=415_202.43),
            BalanceSheetRow("13100", "Insurance", ytd_balance=279_497.51),
        ]
        unmapped = tracker.update_actuals(rows)
        assert len(unmapped) == 0
        assert tracker.budget.find_item("lease").actual == pytest.approx(-221_801.53)
        assert tracker.budget.find_item("tax").actual == pytest.approx(415_202.43)

    def test_unmapped_accounts_returned(self):
        tracker = self._make_tracker()
        rows = [BalanceSheetRow("99999", "Unknown", ytd_balance=1_234.56)]
        unmapped = tracker.update_actuals(rows)
        assert "99999" in unmapped

    def test_variance_report(self):
        tracker = self._make_tracker()
        rows = [BalanceSheetRow("13010", "Tax", ytd_balance=415_202.43)]
        tracker.update_actuals(rows)
        report = tracker.variance_report()
        tax_row = [r for r in report if r["key"] == "tax"][0]
        assert tax_row["budgeted"] == 380_000
        assert tax_row["actual"] == pytest.approx(415_202.43)
        assert tax_row["variance"] == pytest.approx(35_202.43)

    def test_suggest_next_year_basic(self):
        tracker = self._make_tracker()
        rows = [
            BalanceSheetRow("11100", "Lease", ytd_balance=-221_801.53),
            BalanceSheetRow("11310", "Rent", ytd_balance=-4_013_356.0),
            BalanceSheetRow("13010", "Tax", ytd_balance=415_202.43),
            BalanceSheetRow("13100", "Insurance", ytd_balance=279_497.51),
            BalanceSheetRow("15500", "Maintenance", ytd_balance=246_426.24),
        ]
        tracker.update_actuals(rows)
        suggestion = tracker.suggest_next_year_budget(months_elapsed=11, inflation_rate=0.02)
        assert suggestion.fiscal_year == "2026/2027"
        tax_item = suggestion.find_item("tax")
        assert tax_item is not None
        assert tax_item.budgeted >= 415_000

    def test_rent_never_decreases(self):
        tracker = self._make_tracker()
        rows = [
            BalanceSheetRow("11100", "Lease", ytd_balance=-240_000),
            BalanceSheetRow("11310", "Rent", ytd_balance=-4_385_000),
            BalanceSheetRow("13010", "Tax", ytd_balance=100_000),
            BalanceSheetRow("13100", "Insurance", ytd_balance=100_000),
            BalanceSheetRow("15500", "Maintenance", ytd_balance=100_000),
        ]
        tracker.update_actuals(rows)
        suggestion = tracker.suggest_next_year_budget(months_elapsed=12)
        assert suggestion.rent_amount >= tracker.budget.rent_amount


class TestHelpers:
    def test_round_to(self):
        assert _round_to(1_573_123, 500) == 1_573_000
        assert _round_to(1_573_400, 500) == 1_573_500
        assert _round_to(-280_100, 500) == -280_000

    def test_increment_fiscal_year(self):
        assert _increment_fiscal_year("2025/2026") == "2026/2027"
        assert _increment_fiscal_year("2025") == "2026"

    def test_extrapolate(self):
        result = BudgetTracker._extrapolate_annual(100_000, 6, 12)
        assert result == pytest.approx(200_000)

    def test_extrapolate_full_year(self):
        result = BudgetTracker._extrapolate_annual(100_000, 12, 12)
        assert result == pytest.approx(100_000)


class TestGeneralisedOptions:
    def _tracker(self, **mapping_kw):
        budget = Budget(fiscal_year="2025")
        ops = BudgetCategory("ops", "Ops", CategoryType.EXPENSE)
        ops.add_item(BudgetLineItem("ins", "Insurance", budgeted=1_000))
        other = BudgetCategory("other", "Other", CategoryType.EXPENSE)
        budget.add_category(ops)
        budget.add_category(other)
        mapping = AccountMapping({"100": "ins"}, **mapping_kw)
        return BudgetTracker(budget, mapping)

    def test_unmapped_category_collects_accounts(self):
        tracker = self._tracker(unmapped_category="other")
        rows = [
            BalanceSheetRow("100", "Insurance", ytd_balance=900),
            BalanceSheetRow("200", "Misc", ytd_balance=50),
        ]
        assert tracker.update_actuals(rows) == {"200": 50}
        item = tracker.budget.find_item("account:200")
        assert item.name == "Misc" and item.actual == 50

    def test_suggestion_parameters(self):
        tracker = self._tracker()
        tracker.update_actuals([BalanceSheetRow("100", "Insurance", ytd_balance=1_234)])
        nxt = tracker.suggest_next_year_budget(
            prior_year_actuals={"ins": 1_000}, current_year_weight=0.5, rounding=1,
        )
        assert nxt.find_item("ins").budgeted == 1_117
