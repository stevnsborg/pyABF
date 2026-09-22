"""
loan.py — Mortgage loan modeling for Danish housing cooperatives.

Supports annuity loans with:
  - Interest-only periods
  - Contribution rates (bidragssats)
  - Bond price valuation (market value of remaining debt)

Contains:
    Loan — Class for modeling a mortgage loan
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Loan:
    """A mortgage loan held by a housing cooperative.

    Attributes:
        name: Descriptive name for the loan (e.g. 'Loan 15')
        loan_type: Type of loan (e.g. 'fixed', 'variable')
        principal: The original loan amount (DKK)
        interest_rate: Annual nominal interest rate (e.g. 0.015 = 1.5%)
        contribution_rate: Annual contribution rate to the mortgage lender (e.g. 0.004)
        term_years: Total term in years
        interest_only_years: Number of interest-only years (default 0)
        payments_per_year: Number of payment periods per year (default 4 = quarterly)
        bond_price: Bond price in percent (e.g. 80.0 = price of 80)
    """

    name: str
    loan_type: str = "annuity"
    principal: float = 0.0
    interest_rate: float = 0.0
    contribution_rate: float = 0.0
    term_years: float = 25.0
    interest_only_years: float = 0.0
    payments_per_year: int = 4
    bond_price: float = 100.0

    @property
    def effective_period_rate(self) -> float:
        """Effective interest rate per period (interest + contribution divided by periods)."""
        return (self.interest_rate + self.contribution_rate) / self.payments_per_year

    @property
    def total_periods(self) -> int:
        """Total number of payment periods."""
        return round(self.term_years * self.payments_per_year)

    @property
    def interest_only_periods(self) -> int:
        """Number of periods in the interest-only phase."""
        return round(self.interest_only_years * self.payments_per_year)

    @property
    def market_value(self) -> float:
        """Market value of the full principal based on the bond price."""
        return self.principal * self.bond_price / 100

    @staticmethod
    def _compute_annuity_payment(amount: float, rate: float, periods: int) -> float:
        """Compute the fixed annuity payment.

        Args:
            amount: Outstanding balance / principal
            rate: Interest rate per period
            periods: Number of remaining periods

        Returns:
            The fixed period payment (DKK)
        """
        if rate == 0:
            return amount / periods if periods > 0 else 0.0
        return amount * (rate * (1 + rate) ** periods) / ((1 + rate) ** periods - 1)

    def _compute_principal_payment(self, balance: float) -> float:
        """Compute the principal payment per period for the amortizing phase.

        Args:
            balance: The current outstanding balance

        Returns:
            Principal payment per period (DKK)
        """
        amortizing_years = self.term_years - self.interest_only_years
        amortizing_periods = round(amortizing_years * self.payments_per_year)
        if amortizing_periods <= 0:
            return 0.0
        annuity = self._compute_annuity_payment(
            balance, self.effective_period_rate, amortizing_periods
        )
        return annuity - (balance * self.effective_period_rate)

    def payment_schedule(self) -> pd.DataFrame:
        """Generate a detailed payment schedule for the full loan term.

        Returns:
            DataFrame with columns:
                loan, period, opening_balance, interest, principal_payment,
                total_payment, closing_balance, bond_price, market_value
        """
        balance = self.principal
        principal_pmt = self._compute_principal_payment(balance)
        rate = self.effective_period_rate

        schedule = []

        for period in range(1, self.total_periods + 1):
            opening_balance = balance
            interest = opening_balance * rate

            if period <= self.interest_only_periods:
                period_principal = 0.0
                total_payment = interest
            else:
                period_principal = min(principal_pmt, balance)
                total_payment = interest + period_principal

            balance -= period_principal
            balance = max(balance, 0.0)

            mv = balance * self.bond_price / 100

            schedule.append({
                "loan": self.name,
                "period": period,
                "opening_balance": opening_balance,
                "interest": interest,
                "principal_payment": period_principal,
                "total_payment": total_payment,
                "closing_balance": balance,
                "bond_price": self.bond_price,
                "market_value": mv,
            })

        return pd.DataFrame(schedule)

    def balance_after_years(self, years: int) -> float:
        """Remaining balance after a given number of years.

        Args:
            years: Number of years from loan start

        Returns:
            Remaining balance in DKK

        Raises:
            ValueError: If years is outside the loan term
        """
        if years == 0:
            return self.principal

        schedule = self.payment_schedule()
        target_period = years * self.payments_per_year
        if target_period > len(schedule):
            raise ValueError(
                f"Year {years} is outside the loan term ({self.term_years} years)."
            )
        return float(schedule.iloc[target_period - 1]["closing_balance"])

    def market_value_after_years(self, years: int) -> float:
        """Market value of the remaining debt after a given number of years.

        Args:
            years: Number of years from loan start

        Returns:
            Market value in DKK
        """
        return self.balance_after_years(years) * self.bond_price / 100

    def total_interest(self) -> float:
        """Total interest paid over the full loan term."""
        return float(self.payment_schedule()["interest"].sum())

    def total_payments(self) -> float:
        """Total payments (interest + principal) over the full loan term."""
        return float(self.payment_schedule()["total_payment"].sum())
