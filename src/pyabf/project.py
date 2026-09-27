"""
project.py — Building projects with a budget paid over a period.

A project (e.g. new windows, a roof or a courtyard) has a total budget and
a duration in months. The cost is paid linearly: the same amount each
month from the start month until the project ends.

A given fraction of the cost counts as an improvement (forbedring). That
part is added to the improvement allowances (forbedringstillæg) in the
valuation, one :class:`~pyabf.valuation.ImprovementAllowance` per calendar
year with the amount paid that year.

Contains:
    ProjectPlan — A project's budget, duration and improvement fraction
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .valuation import ImprovementAllowance, ValuationAssumptions


@dataclass
class ProjectPlan:
    """A project with a budget paid in equal monthly amounts.

    Example:
        >>> plan = ProjectPlan("Windows", budget=1_200_000, duration_months=12,
        ...                    start_year=2026, start_month=7,
        ...                    improvement_fraction=0.4, yield_rate=0.05)
        >>> plan.monthly_payment
        100000.0
        >>> [(a.year, a.cost) for a in plan.improvement_allowances()]
        [(2026, 600000.0), (2027, 600000.0)]

    Attributes:
        name: Description of the project.
        budget: Total cost of the project (DKK).
        duration_months: Number of months the cost is paid over.
        start_year: Calendar year of the first payment.
        start_month: Month of the first payment (1–12, default January).
        improvement_fraction: Fraction of the cost that counts as an
            improvement in the valuation (``0.4`` = 40 %). Range 0.0–1.0.
        yield_rate: Annual yield rate on the improvement cost, passed on to
            the :class:`~pyabf.valuation.ImprovementAllowance` entries.
    """

    name: str
    budget: float
    duration_months: int
    start_year: int
    start_month: int = 1
    improvement_fraction: float = 0.0
    yield_rate: float = 0.0

    def __post_init__(self) -> None:
        if self.budget < 0:
            raise ValueError("budget must not be negative.")
        if self.duration_months <= 0:
            raise ValueError("duration_months must be positive.")
        if not 1 <= self.start_month <= 12:
            raise ValueError("start_month must be between 1 and 12.")
        if not 0.0 <= self.improvement_fraction <= 1.0:
            raise ValueError("improvement_fraction must be between 0 and 1.")

    @property
    def monthly_payment(self) -> float:
        """Amount paid each month (DKK)."""
        return self.budget / self.duration_months

    @property
    def improvement_value(self) -> float:
        """Part of the budget that counts as an improvement (DKK)."""
        return self.budget * self.improvement_fraction

    @property
    def end_year(self) -> int:
        """Calendar year of the last payment."""
        return self.start_year + (self.start_month - 1 + self.duration_months - 1) // 12

    @property
    def end_month(self) -> int:
        """Month (1–12) of the last payment."""
        return (self.start_month - 1 + self.duration_months - 1) % 12 + 1

    def payment_schedule(self) -> pd.DataFrame:
        """Monthly payment schedule.

        Returns:
            DataFrame with one row per month and the columns ``year``,
            ``month``, ``payment``, ``improvement`` (the improvement part of
            the payment) and ``cumulative_paid``.
        """
        rows = []
        for i in range(self.duration_months):
            offset = self.start_month - 1 + i
            rows.append({
                "year": self.start_year + offset // 12,
                "month": offset % 12 + 1,
                "payment": self.monthly_payment,
                "improvement": self.monthly_payment * self.improvement_fraction,
                "cumulative_paid": self.monthly_payment * (i + 1),
            })
        return pd.DataFrame(rows)

    def annual_payments(self) -> pd.DataFrame:
        """Payments summed per calendar year.

        Returns:
            DataFrame indexed by ``year`` with the columns ``months``,
            ``payment`` and ``improvement``.
        """
        schedule = self.payment_schedule()
        return schedule.groupby("year").agg(
            months=("month", "size"),
            payment=("payment", "sum"),
            improvement=("improvement", "sum"),
        )

    def improvement_allowances(self) -> list[ImprovementAllowance]:
        """Improvement allowances for the valuation, one per calendar year.

        Each entry's ``cost`` is the amount paid that year and its
        ``improvement_fraction`` is the project's, so the improvement part
        is ``cost × improvement_fraction``.

        Returns:
            List of :class:`~pyabf.valuation.ImprovementAllowance`.
        """
        return [
            ImprovementAllowance(
                name=f"{self.name} ({year})",
                year=int(year),
                cost=float(row.payment),
                improvement_fraction=self.improvement_fraction,
                yield_rate=self.yield_rate,
            )
            for year, row in self.annual_payments().iterrows()
        ]

    def add_to_valuation(self, assumptions: ValuationAssumptions) -> None:
        """Append the project's improvement allowances to ``assumptions``.

        Args:
            assumptions: The valuation inputs to update in place.
        """
        assumptions.improvements.extend(self.improvement_allowances())
