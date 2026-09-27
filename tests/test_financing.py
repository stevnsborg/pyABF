"""Tests for pyabf.financing."""

import pytest

from pyabf import Loan, ProjectFinancing, ProjectPlan


def _plan(**kw):
    args = dict(name="Roof", budget=1_200_000, duration_months=12,
                start_year=2026, start_month=1)
    args.update(kw)
    return ProjectPlan(**args)


LOAN = Loan("Loan", interest_rate=0.04, term_years=30, payments_per_year=4)


class TestLiquidOnly:
    def test_paid_from_bank_without_interest(self):
        fin = ProjectFinancing(_plan(), liquid_assets=2_000_000)
        df = fin.schedule()
        assert df["bank_balance"].iloc[-1] == pytest.approx(800_000)
        assert (df["credit_draw"] == 0).all()
        assert fin.loans() == []
        assert fin.shortfall == 0

    def test_deposit_interest(self):
        fin = ProjectFinancing(_plan(budget=0), liquid_assets=1_200_000,
                               deposit_rate=0.012)
        # 0.1 % per month, compounded
        assert fin.schedule()["bank_balance"].iloc[-1] == pytest.approx(
            1_200_000 * 1.001 ** 12)

    def test_shortfall(self):
        fin = ProjectFinancing(_plan(), liquid_assets=1_000_000)
        assert fin.shortfall == pytest.approx(200_000)
        assert fin.summary()["min_bank_balance"] == pytest.approx(-200_000)


class TestCredit:
    def test_capitalised_interest(self):
        fin = ProjectFinancing(_plan(), credit_fraction=1.0,
                               credit_interest_rate=0.12,
                               credit_settlement="liquid",
                               liquid_assets=2_000_000)
        df = fin.schedule()
        # Month k's interest is 1 % of the balance after k-1 draws
        expected = 0.0
        for _ in range(12):
            expected = expected * 1.01 + 100_000
        assert fin.credit_balance_at_end == pytest.approx(expected)
        assert df["credit_balance"].iloc[-1] == 0
        assert df["bank_balance"].iloc[-1] == pytest.approx(2_000_000 - expected)
        assert fin.loans() == []

    def test_interest_paid_from_bank(self):
        fin = ProjectFinancing(_plan(), credit_fraction=1.0,
                               credit_interest_rate=0.12,
                               capitalize_credit_interest=False,
                               credit_settlement="liquid",
                               liquid_assets=2_000_000)
        interest = sum(100_000 * k * 0.01 for k in range(12))
        assert fin.credit_balance_at_end == pytest.approx(1_200_000)
        assert fin.schedule()["bank_balance"].iloc[-1] == pytest.approx(
            2_000_000 - interest - 1_200_000)

    def test_settled_by_loan(self):
        terms = Loan("Settle", interest_rate=0.05, term_years=20, bond_price=96)
        fin = ProjectFinancing(_plan(), credit_fraction=1.0,
                               credit_settlement="loan", settlement_loan=terms)
        (loan,) = fin.loans()
        assert loan.name == "Settle (credit)"
        assert loan.principal == pytest.approx(1_200_000 / 0.96)
        assert loan.interest_rate == 0.05
        assert fin.summary()["debt_at_end"] == pytest.approx(loan.principal)
        assert fin.schedule()["bank_balance"].iloc[-1] == pytest.approx(0)


class TestLoan:
    def test_proceeds_and_payments(self):
        fin = ProjectFinancing(_plan(), loan_fraction=1.0,
                               loan=Loan("L", interest_rate=0.04, term_years=10,
                                         interest_only_years=10,
                                         payments_per_year=4, bond_price=100))
        df = fin.schedule()
        # Interest-only: 1 % per quarter on 1.2M, paid in months 3, 6, 9, 12
        assert list(df.loc[df["loan_payment"] > 0, "month"]) == [3, 6, 9, 12]
        assert df["loan_payment"].sum() == pytest.approx(48_000)
        assert df["bank_balance"].iloc[-1] == pytest.approx(-48_000)
        assert df["loan_balance"].iloc[-1] == pytest.approx(1_200_000)

    def test_bond_price(self):
        fin = ProjectFinancing(_plan(), loan_fraction=0.5,
                               loan=Loan("L", bond_price=80, term_years=20))
        assert fin.project_loan().principal == pytest.approx(600_000 / 0.8)

    def test_deposit_interest_on_proceeds(self):
        base = ProjectFinancing(_plan(), loan_fraction=1.0, loan=LOAN)
        earning = ProjectFinancing(_plan(), loan_fraction=1.0, loan=LOAN,
                                   deposit_rate=0.03)
        assert earning.summary()["deposit_interest"] > 0
        assert (earning.summary()["bank_balance_at_end"]
                > base.summary()["bank_balance_at_end"])


class TestMix:
    def test_split_and_loans(self):
        fin = ProjectFinancing(_plan(), loan_fraction=0.5, credit_fraction=0.3,
                               loan=LOAN, liquid_assets=500_000,
                               credit_interest_rate=0.05)
        s = fin.summary()
        assert s["financed_by_loan"] == pytest.approx(600_000)
        assert s["financed_by_credit"] == pytest.approx(360_000)
        assert s["financed_by_liquid_assets"] == pytest.approx(240_000)
        assert [loan.name for loan in fin.loans()] == ["Loan", "Loan (credit)"]
        annual = fin.annual_schedule()
        assert annual.loc[2026, "project_payment"] == pytest.approx(1_200_000)

    def test_schedule_spans_years(self):
        fin = ProjectFinancing(_plan(start_month=7), liquid_assets=1_200_000)
        assert list(fin.annual_schedule().index) == [2026, 2027]


@pytest.mark.parametrize("kw", [
    {"loan_fraction": 1.2},
    {"loan_fraction": 0.6, "credit_fraction": 0.6, "loan": LOAN},
    {"loan_fraction": 0.5},                                  # no loan terms
    {"credit_fraction": 0.5},                                # no settlement terms
    {"credit_settlement": "bond"},
    {"loan_fraction": 0.5, "loan": Loan("L", payments_per_year=5)},
])
def test_invalid(kw):
    with pytest.raises(ValueError):
        ProjectFinancing(_plan(), **kw)
