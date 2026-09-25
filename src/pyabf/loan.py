"""
loan.py — Mortgage loan modeling for Danish housing cooperatives.

Supports annuity loans with:
  - Interest-only periods (afdragsfrihed)
  - Contribution rates (bidragssats), charged on the outstanding balance
    together with the interest
  - Bond price valuation (kursværdi / market value of remaining debt)

The loan is modelled from "now": ``principal`` is the balance at the start
of the schedule and ``term_years`` / ``interest_only_years`` are the
*remaining* periods. For an existing loan, pass the current outstanding
balance and remaining term.

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
        loan_type: Free-text label (e.g. 'fixed', 'variable'). Informational
            only; it does not change the calculation.
        principal: Outstanding balance at the start of the schedule (DKK)
        interest_rate: Annual nominal interest rate (e.g. 0.015 = 1.5%)
        contribution_rate: Annual contribution rate to the mortgage lender (e.g. 0.004)
        term_years: Remaining term in years (may be fractional, e.g. 24.25)
        interest_only_years: Number of interest-only years at the start of
            the schedule (default 0). Equal to ``term_years`` for a loan
            that is interest-only for its whole life.
        payments_per_year: Number of payment periods per year (default 4 = quarterly)
        bond_price: Bond price in percent (e.g. 80.0 = price of 80)

    Note:
        The ``interest`` column of :meth:`payment_schedule` includes the
        contribution (bidrag), since both are charged on the balance.
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

    def __post_init__(self) -> None:
        if self.payments_per_year <= 0:
            raise ValueError("payments_per_year must be positive.")
        if self.term_years < 0 or self.interest_only_years < 0:
            raise ValueError("term_years and interest_only_years must be >= 0.")
        if self.interest_only_years > self.term_years:
            raise ValueError("interest_only_years cannot exceed term_years.")

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
        """Market value (kursværdi) of the current principal at ``bond_price``."""
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

    @property
    def amortizing_periods(self) -> int:
        """Number of periods in the amortizing (annuity) phase."""
        return max(0, self.total_periods - self.interest_only_periods)

    @property
    def annuity_payment(self) -> float:
        """Fixed payment per period (ydelse) during the amortizing phase.

        Includes interest, contribution and principal.  Since the balance
        is unchanged during the interest-only phase, the annuity is
        computed on the full principal.  Returns 0.0 for a loan that is
        interest-only for its whole term.
        """
        if self.amortizing_periods == 0:
            return 0.0
        return self._compute_annuity_payment(
            self.principal, self.effective_period_rate, self.amortizing_periods
        )

    def payment_schedule(self) -> pd.DataFrame:
        """Generate a detailed payment schedule for the full loan term.

        During the interest-only phase only interest (incl. contribution) is
        paid.  Afterwards the loan is repaid as an annuity: the total
        payment is constant (``annuity_payment``) and the principal part
        grows as the interest part shrinks, so the balance reaches zero at
        the end of the term.

        Returns:
            DataFrame with columns:
                loan, period, opening_balance, interest, principal_payment,
                total_payment, closing_balance, bond_price, market_value
        """
        balance = self.principal
        annuity = self.annuity_payment
        rate = self.effective_period_rate

        schedule = []

        for period in range(1, self.total_periods + 1):
            opening_balance = balance
            interest = opening_balance * rate

            if period <= self.interest_only_periods:
                period_principal = 0.0
                total_payment = interest
            else:
                # Last period clears any rounding residue
                if period == self.total_periods:
                    period_principal = balance
                else:
                    period_principal = min(annuity - interest, balance)
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

    def annual_schedule(self) -> pd.DataFrame:
        """Payment schedule aggregated per year.

        Year 1 covers periods 1..payments_per_year, and so on. A final
        partial year (fractional ``term_years``) is included as its own row.

        Returns:
            DataFrame with columns:
                loan, year, interest, principal_payment, total_payment,
                closing_balance, market_value
        """
        schedule = self.payment_schedule()
        if schedule.empty:
            return schedule
        schedule["year"] = (schedule["period"] - 1) // self.payments_per_year + 1
        annual = schedule.groupby("year", as_index=False).agg(
            interest=("interest", "sum"),
            principal_payment=("principal_payment", "sum"),
            total_payment=("total_payment", "sum"),
            closing_balance=("closing_balance", "last"),
            market_value=("market_value", "last"),
        )
        annual.insert(0, "loan", self.name)
        return annual

    def balance_after_years(self, years: int) -> float:
        """Remaining balance after a given number of years.

        Args:
            years: Number of years from loan start

        Returns:
            Remaining balance in DKK

        Raises:
            ValueError: If years is negative or outside the loan term
        """
        if years < 0:
            raise ValueError("years must be >= 0.")
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
        """Total interest (including contribution) paid over the full loan term."""
        return float(self.payment_schedule()["interest"].sum())

    def total_payments(self) -> float:
        """Total payments (interest + principal) over the full loan term."""
        return float(self.payment_schedule()["total_payment"].sum())
