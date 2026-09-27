"""
financing.py — Financing a project with a loan, a construction credit,
liquid assets or a mix.

A :class:`ProjectFinancing` pays a :class:`~pyabf.project.ProjectPlan`'s
monthly payments from three sources:

    - **Loan** (``loan_fraction`` of the budget): a mortgage loan taken at
      the start of the project. The cash proceeds go into the bank and the
      project is paid from there; the loan's payments are paid from the
      bank as they fall due.
    - **Credit** (``credit_fraction``): a construction credit
      (byggekredit) drawn month by month as the project is paid. Interest
      is charged monthly on the drawn balance and either added to the
      credit or paid from the bank.
    - **Liquid assets** (the rest): paid directly from the bank.

The bank balance starts at ``liquid_assets`` and earns ``deposit_rate``
(credited monthly on a positive balance). A negative balance is not
funded; it is reported as a shortfall.

At the end of the project the credit (drawn amount plus capitalised
interest) is settled, either by a new loan (``credit_settlement="loan"``)
or from the bank (``credit_settlement="liquid"``).

Loans are raised at ``bond_price``: to get a cash amount ``C`` the
principal is ``C / (bond_price / 100)``.

Contains:
    ProjectFinancing — The financing of one project, simulated monthly
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import pandas as pd

from .loan import Loan
from .project import ProjectPlan

CreditSettlement = Literal["loan", "liquid"]
CREDIT_SETTLEMENTS: tuple[str, ...] = ("loan", "liquid")


@dataclass
class ProjectFinancing:
    """How a project is paid for, simulated month by month.

    Example:
        >>> from pyabf import Loan, ProjectPlan
        >>> plan = ProjectPlan("Roof", budget=1_200_000, duration_months=12,
        ...                    start_year=2026)
        >>> fin = ProjectFinancing(
        ...     plan, credit_fraction=1.0, credit_interest_rate=0.06,
        ...     credit_settlement="loan",
        ...     loan=Loan("Roof loan", interest_rate=0.04, term_years=30))
        >>> round(fin.credit_balance_at_end) > 1_200_000   # + interest
        True
        >>> [loan.name for loan in fin.loans()]
        ['Roof loan (credit)']

    Attributes:
        project: The project to finance.
        loan_fraction: Fraction of the budget financed by a loan taken at
            the start of the project.
        credit_fraction: Fraction of the budget drawn on the credit.
            ``1 − loan_fraction − credit_fraction`` is paid from liquid
            assets.
        loan: Terms of the loan (interest, contribution, term,
            interest-only years, payments per year, bond price). Its
            ``principal`` is ignored and set from the amount financed; its
            ``payments_per_year`` must divide 12. Required when
            ``loan_fraction > 0``.
        credit_interest_rate: Annual interest rate on the drawn credit.
        capitalize_credit_interest: Add the credit interest to the credit
            balance (default). If False it is paid monthly from the bank.
        liquid_assets: Bank balance at the start of the project (DKK).
        deposit_rate: Annual interest rate on a positive bank balance.
        credit_settlement: How the credit is settled at the end:
            ``"loan"`` (refinanced by a new loan) or ``"liquid"`` (paid
            from the bank).
        settlement_loan: Terms of the loan that replaces the credit.
            Defaults to ``loan``. Required when the credit is settled by a
            loan and ``loan`` is not given.
    """

    project: ProjectPlan
    loan_fraction: float = 0.0
    credit_fraction: float = 0.0
    loan: Loan | None = None
    credit_interest_rate: float = 0.0
    capitalize_credit_interest: bool = True
    liquid_assets: float = 0.0
    deposit_rate: float = 0.0
    credit_settlement: CreditSettlement = "loan"
    settlement_loan: Loan | None = None

    def __post_init__(self) -> None:
        for name in ("loan_fraction", "credit_fraction"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1.")
        if self.loan_fraction + self.credit_fraction > 1.0 + 1e-12:
            raise ValueError("loan_fraction + credit_fraction cannot exceed 1.")
        if self.credit_settlement not in CREDIT_SETTLEMENTS:
            raise ValueError(
                f"credit_settlement must be one of {CREDIT_SETTLEMENTS}, "
                f"got {self.credit_settlement!r}.")
        if self.loan_fraction > 0 and self.loan is None:
            raise ValueError("loan_fraction > 0 needs loan terms (loan=...).")
        if (self.credit_fraction > 0 and self.credit_settlement == "loan"
                and self._settlement_terms is None):
            raise ValueError(
                "Settling the credit by a loan needs settlement_loan or loan.")
        for terms in (self.loan, self.settlement_loan):
            if terms is not None and 12 % terms.payments_per_year:
                raise ValueError("A loan's payments_per_year must divide 12.")

    # ------------------------------------------------------------------
    # Amounts
    # ------------------------------------------------------------------

    @property
    def liquid_fraction(self) -> float:
        """Fraction of the budget paid from liquid assets."""
        return max(0.0, 1.0 - self.loan_fraction - self.credit_fraction)

    @property
    def loan_amount(self) -> float:
        """Cash raised by the project loan (DKK)."""
        return self.project.budget * self.loan_fraction

    @property
    def _settlement_terms(self) -> Loan | None:
        return self.settlement_loan if self.settlement_loan is not None else self.loan

    @staticmethod
    def _raise_loan(terms: Loan, cash: float, name: str) -> Loan:
        """A loan with the given terms that pays out ``cash``."""
        return replace(terms, name=name,
                       principal=cash / (terms.bond_price / 100))

    def project_loan(self) -> Loan | None:
        """The loan taken at the start of the project (None if no loan)."""
        if self.loan_fraction == 0 or self.loan is None:
            return None
        return self._raise_loan(self.loan, self.loan_amount, self.loan.name)

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def schedule(self) -> pd.DataFrame:
        """Month-by-month simulation of the financing.

        Each month, in order: deposit interest on the opening bank
        balance, credit interest on the opening credit balance, the
        project payment (split over credit and bank), and the loan payment
        if one falls due. The loan's proceeds are deposited before the
        first month's payments; the credit is settled after the last.

        Returns:
            DataFrame with one row per month and the columns ``year``,
            ``month``, ``project_payment``, ``credit_draw``,
            ``paid_from_bank``, ``credit_interest``, ``credit_balance``,
            ``loan_payment``, ``loan_interest``, ``loan_balance``,
            ``deposit_interest`` and ``bank_balance``. Balances are at the
            end of the month; the last row is after the credit has been
            settled.
        """
        loan = self.project_loan()
        loan_rows = loan.payment_schedule() if loan is not None else None
        months_per_period = 12 // loan.payments_per_year if loan else 0
        loan_balance = loan.principal if loan else 0.0

        bank = self.liquid_assets + self.loan_amount
        credit = 0.0
        pay_schedule = self.project.payment_schedule()
        rows = []
        for i, pay in enumerate(pay_schedule.itertuples()):
            deposit_interest = max(bank, 0.0) * self.deposit_rate / 12
            bank += deposit_interest

            credit_interest = credit * self.credit_interest_rate / 12
            if self.capitalize_credit_interest:
                credit += credit_interest
            else:
                bank -= credit_interest

            draw = pay.payment * self.credit_fraction
            from_bank = pay.payment - draw
            credit += draw
            bank -= from_bank

            loan_payment = loan_interest = 0.0
            if loan is not None and (i + 1) % months_per_period == 0:
                period = (i + 1) // months_per_period
                if period <= len(loan_rows):
                    row = loan_rows.iloc[period - 1]
                    loan_payment = float(row["total_payment"])
                    loan_interest = float(row["interest"])
                    loan_balance = float(row["closing_balance"])
                    bank -= loan_payment

            rows.append({
                "year": pay.year,
                "month": pay.month,
                "project_payment": pay.payment,
                "credit_draw": draw,
                "paid_from_bank": from_bank,
                "credit_interest": credit_interest,
                "credit_balance": credit,
                "loan_payment": loan_payment,
                "loan_interest": loan_interest,
                "loan_balance": loan_balance,
                "deposit_interest": deposit_interest,
                "bank_balance": bank,
            })

        df = pd.DataFrame(rows)
        # Settle the credit at the end of the project
        if self.credit_settlement == "liquid":
            df.loc[df.index[-1], "bank_balance"] -= credit
        df.loc[df.index[-1], "credit_balance"] = 0.0
        df.attrs["credit_at_end"] = credit
        return df

    def annual_schedule(self) -> pd.DataFrame:
        """The monthly schedule summed per calendar year (balances at year end)."""
        df = self.schedule()
        flows = ["project_payment", "credit_draw", "paid_from_bank",
                 "credit_interest", "loan_payment", "loan_interest",
                 "deposit_interest"]
        balances = ["credit_balance", "loan_balance", "bank_balance"]
        return df.groupby("year").agg(
            {**{c: "sum" for c in flows}, **{c: "last" for c in balances}})

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    @property
    def credit_balance_at_end(self) -> float:
        """Credit balance (draws + capitalised interest) before settlement."""
        return float(self.schedule().attrs["credit_at_end"])

    def settlement_loan_raised(self) -> Loan | None:
        """The loan that replaces the credit (None if not settled by a loan)."""
        credit = self.credit_balance_at_end
        terms = self._settlement_terms
        if self.credit_settlement != "loan" or credit <= 0 or terms is None:
            return None
        return self._raise_loan(terms, credit, f"{terms.name} (credit)")

    def loans(self) -> list[Loan]:
        """The loans the financing creates, at their original principal.

        The project loan starts at the project start; the loan replacing
        the credit starts at the project end.
        """
        return [loan for loan in (self.project_loan(),
                                  self.settlement_loan_raised())
                if loan is not None]

    def summary(self) -> dict[str, float]:
        """Key figures of the financing (DKK)."""
        df = self.schedule()
        credit = float(df.attrs["credit_at_end"])
        settlement = self.settlement_loan_raised()
        loan_balance = float(df["loan_balance"].iloc[-1])
        return {
            "budget": self.project.budget,
            "financed_by_loan": self.loan_amount,
            "financed_by_credit": float(df["credit_draw"].sum()),
            "financed_by_liquid_assets": self.project.budget * self.liquid_fraction,
            "credit_interest": float(df["credit_interest"].sum()),
            "loan_interest": float(df["loan_interest"].sum()),
            "deposit_interest": float(df["deposit_interest"].sum()),
            "credit_at_end": credit,
            "bank_balance_at_end": float(df["bank_balance"].iloc[-1]),
            "min_bank_balance": float(df["bank_balance"].min()),
            "debt_at_end": loan_balance + (settlement.principal if settlement else 0.0),
        }

    @property
    def shortfall(self) -> float:
        """How far the bank balance goes below zero at its lowest (DKK, ≥ 0)."""
        return max(0.0, -float(self.schedule()["bank_balance"].min()))
