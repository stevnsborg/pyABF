"""Tests for pyabf.loan module."""

import pytest
from pyabf.loan import Loan


def _annuity_loan(**kw):
    defaults = dict(
        name="L", principal=1_000_000, interest_rate=0.03,
        contribution_rate=0.005, term_years=20, payments_per_year=4,
    )
    defaults.update(kw)
    return Loan(**defaults)


class TestAnnuity:
    def test_constant_payment_and_full_amortization(self):
        loan = _annuity_loan()
        s = loan.payment_schedule()
        assert len(s) == 80
        assert s["total_payment"].round(6).nunique() == 1
        assert s["total_payment"].iloc[0] == pytest.approx(loan.annuity_payment)
        assert s["closing_balance"].iloc[-1] == pytest.approx(0.0, abs=1e-6)
        assert s["principal_payment"].sum() == pytest.approx(loan.principal)

    def test_principal_part_increases(self):
        s = _annuity_loan().payment_schedule()
        assert s["principal_payment"].is_monotonic_increasing

    def test_balance_matches_closed_form(self):
        loan = _annuity_loan()
        r, n, k = loan.effective_period_rate, 80, 40
        expected = loan.principal * ((1 + r) ** n - (1 + r) ** k) / ((1 + r) ** n - 1)
        assert loan.balance_after_years(10) == pytest.approx(expected)

    def test_zero_rate(self):
        loan = _annuity_loan(interest_rate=0.0, contribution_rate=0.0)
        assert loan.annuity_payment == pytest.approx(1_000_000 / 80)
        assert loan.balance_after_years(20) == pytest.approx(0.0, abs=1e-6)


class TestInterestOnly:
    def test_fully_interest_only(self):
        loan = _annuity_loan(interest_only_years=20)
        s = loan.payment_schedule()
        assert (s["principal_payment"] == 0).all()
        assert s["closing_balance"].iloc[-1] == loan.principal
        assert loan.annuity_payment == 0.0

    def test_partial_interest_only(self):
        loan = _annuity_loan(term_years=30, interest_only_years=10)
        s = loan.payment_schedule()
        assert (s["principal_payment"].iloc[:40] == 0).all()
        assert s["total_payment"].iloc[40:].round(6).nunique() == 1
        assert loan.balance_after_years(10) == loan.principal
        assert loan.balance_after_years(30) == pytest.approx(0.0, abs=1e-6)


class TestValidationAndHelpers:
    def test_interest_only_longer_than_term(self):
        with pytest.raises(ValueError):
            Loan("L", term_years=10, interest_only_years=11)

    def test_balance_outside_term(self):
        with pytest.raises(ValueError):
            _annuity_loan().balance_after_years(21)

    def test_market_value(self):
        loan = _annuity_loan(bond_price=80)
        assert loan.market_value == 800_000
        assert loan.market_value_after_years(10) == pytest.approx(
            loan.balance_after_years(10) * 0.8
        )

    def test_annual_schedule(self):
        loan = _annuity_loan()
        annual = loan.annual_schedule()
        assert len(annual) == 20
        assert annual["total_payment"].sum() == pytest.approx(loan.total_payments())
        assert annual["closing_balance"].iloc[9] == pytest.approx(
            loan.balance_after_years(10)
        )
