"""
budget_inputs.py — Take DCF valuation inputs from a budget.

Instead of typing the operating costs and the commercial rent into
:class:`~pyabf.valuation.ValuationAssumptions`, they can be computed from
the cooperative's :class:`~pyabf.budget.Budget`. A
:class:`BudgetValuationMapping` says which budget lines feed which
valuation parameters, and which amounts to use:

    - ``"budgeted"``: the budgeted amounts (default)
    - ``"actual"``: the actuals as they stand
    - ``"extrapolated"``: the year-to-date actuals scaled to a full year
      (``actual × 12 / months_elapsed``)

Parameters the mapping does not cover keep the values already in the
assumptions, and explicit overrides always win over the budget.

Budget amounts follow the bookkeeping sign convention (expenses positive,
income negative); the valuation parameters are positive amounts.

Contains:
    BudgetValuationMapping — Budget lines → valuation parameters
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from typing import Literal

from ..budget import Budget, BudgetTracker, CategoryType
from .assumptions import OperatingCostAssumptions, ValuationAssumptions

BudgetBasis = Literal["budgeted", "actual", "extrapolated"]
BUDGET_BASES: tuple[str, ...] = ("budgeted", "actual", "extrapolated")

#: Operating-cost fields that are annual DKK amounts and can be taken from
#: budget lines (the per-m² fields, ``other`` and the total cannot).
OPERATING_AMOUNT_FIELDS: tuple[str, ...] = tuple(
    f.name for f in fields(OperatingCostAssumptions)
    if f.name not in ("exterior_maintenance_per_sqm",
                      "interior_maintenance_per_sqm",
                      "other", "total_operating_cost")
)


@dataclass
class BudgetValuationMapping:
    """Which budget lines feed which valuation parameters.

    Example:
        >>> mapping = BudgetValuationMapping(
        ...     operating={"insurance": "insurance",    # a named field
        ...                "grundskyld": "property_tax",
        ...                "repairs": "Maintenance"},   # → operating.other
        ...     commercial_rent=["shop_rent"],
        ... )

    Attributes:
        operating: Budget item key → operating-cost target. A target that
            is one of :data:`OPERATING_AMOUNT_FIELDS` (e.g. ``"insurance"``)
            sets that field; any other name becomes a line in
            ``OperatingCostAssumptions.other``. Several items may share a
            target; their amounts are summed. When empty, the operating
            costs are not taken from the budget.
        commercial_rent: Budget item keys (income lines) whose total is
            the commercial rent (``rent.total_commercial_rent``). When
            empty, the commercial rent is not taken from the budget.
        include_unmapped_expenses: Also put every expense line not in
            ``operating`` into ``other`` (under its name). Off by default,
            since a cooperative's budget holds items such as mortgage
            interest that are not operating costs in a valuation.
        basis: Which amounts to use: ``"budgeted"``, ``"actual"`` or
            ``"extrapolated"``.
        months_elapsed: Months of the fiscal year the actuals cover, used
            by ``basis="extrapolated"``.
    """

    operating: dict[str, str] = field(default_factory=dict)
    commercial_rent: list[str] = field(default_factory=list)
    include_unmapped_expenses: bool = False
    basis: BudgetBasis = "budgeted"
    months_elapsed: int = 12

    def __post_init__(self) -> None:
        if self.basis not in BUDGET_BASES:
            raise ValueError(
                f"basis must be one of {BUDGET_BASES}, got {self.basis!r}.")
        if not 1 <= self.months_elapsed <= 12:
            raise ValueError("months_elapsed must be between 1 and 12.")
        for target in self.operating.values():
            if target in ("exterior_maintenance_per_sqm",
                          "interior_maintenance_per_sqm",
                          "other", "total_operating_cost"):
                raise ValueError(
                    f"{target!r} cannot be taken from a budget line; pass it "
                    "as an override instead.")

    # ------------------------------------------------------------------

    def amount(self, budget: Budget, item_key: str) -> float:
        """A budget line's amount on the chosen basis (budget sign).

        Raises:
            KeyError: If the budget has no line with this key.
        """
        item = budget.find_item(item_key)
        if item is None:
            raise KeyError(
                f"Budget {budget.fiscal_year} has no line {item_key!r}.")
        if self.basis == "budgeted":
            return item.budgeted
        if self.basis == "actual":
            return item.actual
        return BudgetTracker._extrapolate_annual(item.actual, self.months_elapsed)

    def operating_costs(
        self, budget: Budget, **overrides: float | dict[str, float] | None
    ) -> OperatingCostAssumptions:
        """Operating costs computed from the budget.

        Args:
            budget: The budget to read.
            **overrides: ``OperatingCostAssumptions`` fields to set
                explicitly (e.g. ``caretaker=180_000`` or
                ``exterior_maintenance_per_sqm=40``). They replace the
                amounts from the budget.

        Returns:
            The operating costs, with ``total_operating_cost=None`` so the
            total is the sum of the lines (unless overridden).
        """
        values: dict[str, float] = {}
        other: dict[str, float] = {}
        for item_key, target in self.operating.items():
            amount = self.amount(budget, item_key)
            if target in OPERATING_AMOUNT_FIELDS:
                values[target] = values.get(target, 0.0) + amount
            else:
                other[target] = other.get(target, 0.0) + amount

        if self.include_unmapped_expenses:
            for cat in budget.categories.values():
                if cat.category_type is not CategoryType.EXPENSE:
                    continue
                for item in cat.items.values():
                    if item.key not in self.operating:
                        name = item.name or item.key
                        other[name] = (other.get(name, 0.0)
                                       + self.amount(budget, item.key))

        unknown = set(overrides) - {f.name for f in fields(OperatingCostAssumptions)}
        if unknown:
            raise TypeError(f"Unknown operating-cost fields: {sorted(unknown)}")
        return OperatingCostAssumptions(**{"other": other, **values, **overrides})

    def commercial_rent_amount(self, budget: Budget) -> float:
        """Commercial rent from the budget (positive DKK)."""
        return -sum(self.amount(budget, key) for key in self.commercial_rent)

    def apply(
        self,
        assumptions: ValuationAssumptions,
        budget: Budget,
        **operating_overrides: float | dict[str, float] | None,
    ) -> ValuationAssumptions:
        """A copy of ``assumptions`` with the mapped parameters from the budget.

        ``assumptions`` itself is not changed. The operating costs are
        replaced as a whole when ``operating`` is set (so a
        ``total_operating_cost`` in ``assumptions`` does not hide the
        budget lines); pass per-m² maintenance and other fixed values as
        ``operating_overrides``.

        Args:
            assumptions: The valuation inputs to start from.
            budget: The budget to read.
            **operating_overrides: See :meth:`operating_costs`.

        Returns:
            New ``ValuationAssumptions``.
        """
        if operating_overrides and not self.operating:
            raise ValueError(
                "operating overrides need an operating mapping; set the "
                "fields on assumptions.operating instead.")
        result = copy.deepcopy(assumptions)
        if self.operating:
            result.operating = self.operating_costs(budget, **operating_overrides)
        if self.commercial_rent:
            result.rent.total_commercial_rent = self.commercial_rent_amount(budget)
        return result
