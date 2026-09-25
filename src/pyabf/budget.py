"""
budget.py — Budget tracking, balance-sheet import, and next-year budget
suggestions for a housing cooperative.

The module is generic: account-number-to-budget-category mappings and the
chart of accounts are supplied at instantiation time so the same code works
for any Danish andelsboligforening regardless of bookkeeping layout.

Contains:
    BudgetLineItem     — One budget line (name + budgeted amount)
    BudgetCategory     — A named group of line items (income or expense)
    Budget             — A complete annual budget with categories
    AccountMapping     — Maps bookkeeping account numbers to budget lines
    BalanceSheetRow    — One row from an imported balance/trial-balance CSV
    BudgetTracker      — Compares budget vs. actuals and suggests next year

Helper functions:
    parse_danish_number     — Parse '1.234,56' style numbers
    load_balance_sheet_csv  — Read a trial-balance CSV export

Sign convention:
    Amounts follow the bookkeeping convention used in most Danish
    trial-balance exports: expenses are positive and income is negative.
    Budget line items should be entered the same way (e.g. rent income
    as ``budgeted=-4_385_000``) so that actuals from the balance sheet
    can be compared directly.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import IO


# ---------------------------------------------------------------------------
# Core budget data structures
# ---------------------------------------------------------------------------

class CategoryType(Enum):
    """Whether a budget category is income or expense."""
    INCOME = "income"
    EXPENSE = "expense"


@dataclass
class BudgetLineItem:
    """A single named line in the budget.

    Attributes:
        key: Machine-readable identifier (e.g. 'property_tax')
        name: Human-readable label (e.g. 'Ejendomsskatter')
        budgeted: The budgeted amount for the year (positive = expense,
                  negative = income — sign follows accounting convention)
        actual: The year-to-date actual amount (updated from a balance sheet)
    """

    key: str
    name: str
    budgeted: float = 0.0
    actual: float = 0.0

    @property
    def variance(self) -> float:
        """Actual minus budgeted.  Positive = over budget for expenses."""
        return self.actual - self.budgeted

    @property
    def utilisation(self) -> float | None:
        """Actual as a fraction of budget.  None when budget is zero."""
        if self.budgeted == 0.0:
            return None
        return self.actual / self.budgeted


@dataclass
class BudgetCategory:
    """A named group of budget lines (e.g. 'Driftsudgifter').

    Attributes:
        key: Machine-readable identifier
        name: Human-readable label
        category_type: Whether this is income or expense
        items: Ordered dict of line items keyed by their ``key``
    """

    key: str
    name: str
    category_type: CategoryType
    items: dict[str, BudgetLineItem] = field(default_factory=dict)

    def add_item(self, item: BudgetLineItem) -> None:
        """Add (or replace) a line item, keyed by ``item.key``."""
        self.items[item.key] = item

    @property
    def total_budgeted(self) -> float:
        """Sum of budgeted amounts for all items in the category."""
        return sum(i.budgeted for i in self.items.values())

    @property
    def total_actual(self) -> float:
        """Sum of actual amounts for all items in the category."""
        return sum(i.actual for i in self.items.values())

    @property
    def total_variance(self) -> float:
        """Actual minus budgeted for the whole category."""
        return self.total_actual - self.total_budgeted


@dataclass
class Budget:
    """A complete annual budget composed of categories.

    Attributes:
        fiscal_year: Label for the fiscal year (e.g. '2025/2026')
        categories: Ordered dict of categories keyed by their ``key``
        rent_amount: Current annual total rent collected from cooperative
                     units (boligafgift), as a positive number. Used by the
                     suggestion engine to size a rent increase.
        mortgage_principal: Annual mortgage principal repayment (afdrag).
                           Not an operating cost but affects liquidity.
        depreciation: Annual depreciation (afskrivninger).
    """

    fiscal_year: str
    categories: dict[str, BudgetCategory] = field(default_factory=dict)
    rent_amount: float = 0.0
    mortgage_principal: float = 0.0
    depreciation: float = 0.0

    # -- helpers -------------------------------------------------------------

    def add_category(self, cat: BudgetCategory) -> None:
        """Add (or replace) a category, keyed by ``cat.key``."""
        self.categories[cat.key] = cat

    def find_item(self, item_key: str) -> BudgetLineItem | None:
        """Find a line item by key across all categories (None if absent)."""
        for cat in self.categories.values():
            if item_key in cat.items:
                return cat.items[item_key]
        return None

    # -- aggregates ----------------------------------------------------------

    @property
    def total_income_budgeted(self) -> float:
        """Budgeted income (negative under the accounting sign convention)."""
        return sum(
            c.total_budgeted
            for c in self.categories.values()
            if c.category_type is CategoryType.INCOME
        )

    @property
    def total_income_actual(self) -> float:
        """Actual income (negative under the accounting sign convention)."""
        return sum(
            c.total_actual
            for c in self.categories.values()
            if c.category_type is CategoryType.INCOME
        )

    @property
    def total_expense_budgeted(self) -> float:
        """Budgeted expenses (positive)."""
        return sum(
            c.total_budgeted
            for c in self.categories.values()
            if c.category_type is CategoryType.EXPENSE
        )

    @property
    def total_expense_actual(self) -> float:
        """Actual expenses (positive)."""
        return sum(
            c.total_actual
            for c in self.categories.values()
            if c.category_type is CategoryType.EXPENSE
        )

    @property
    def operating_result_budgeted(self) -> float:
        """Budgeted operating result (income - expenses).
        Positive = surplus.  Income is stored as negative (accounting sign)."""
        return -(self.total_income_budgeted + self.total_expense_budgeted)

    @property
    def operating_result_actual(self) -> float:
        """Actual operating result (income - expenses). Positive = surplus."""
        return -(self.total_income_actual + self.total_expense_actual)

    @property
    def liquidity_result_budgeted(self) -> float:
        """Operating result minus mortgage principal and depreciation."""
        return (
            self.operating_result_budgeted
            - self.mortgage_principal
            - self.depreciation
        )


# ---------------------------------------------------------------------------
# Account mapping — links bookkeeping account numbers to budget lines
# ---------------------------------------------------------------------------

@dataclass
class AccountMapping:
    """Maps bookkeeping account numbers to budget line-item keys.

    The balance sheet exported from an administrator's system contains
    account numbers (e.g. '13010') and amounts. This mapping tells the
    tracker which budget line each account number belongs to.

    Attributes:
        account_to_item: Dict mapping account number (str) → budget item key.
            Several accounts may map to the same item; their balances are
            summed.
        unmapped_category: Key of a budget category that should collect
            accounts which don't match any mapping.  Each such account is
            added to that category as its own line item (key
            ``"account:<number>"``, named after the account description).
            When None (the default), unmapped accounts are only reported
            in the return value of ``BudgetTracker.update_actuals``.
    """

    account_to_item: dict[str, str] = field(default_factory=dict)
    unmapped_category: str | None = None

    def add(self, account_number: str, item_key: str) -> None:
        """Map one account number to a budget item key."""
        self.account_to_item[account_number] = item_key

    def add_many(self, mappings: dict[str, str]) -> None:
        """Add multiple account → item mappings at once."""
        self.account_to_item.update(mappings)

    def lookup(self, account_number: str) -> str | None:
        """Return the budget item key for an account number, or None."""
        return self.account_to_item.get(account_number)


# ---------------------------------------------------------------------------
# Balance sheet row — one row from the imported CSV / Excel
# ---------------------------------------------------------------------------

@dataclass
class BalanceSheetRow:
    """A single row from a balance / trial-balance export.

    Attributes:
        account_number: The bookkeeping account number (Konto)
        description: The account description (Tekst)
        period_movement: Movement in the most recent period
        ytd_balance: Year-to-date balance (Saldo)
        annual_budget: The full-year budget from the bookkeeping system
    """

    account_number: str
    description: str
    period_movement: float = 0.0
    ytd_balance: float = 0.0
    annual_budget: float = 0.0


def parse_danish_number(value: str) -> float:
    """Parse a Danish-formatted number string to float.

    Danish format uses period as thousands separator and comma as decimal:
        '-20.477,27' → -20477.27
        '1.573.500,00' → 1573500.00
        '0,00' → 0.0

    Args:
        value: A string with Danish number formatting.

    Returns:
        The parsed float value.  Empty or unparseable strings return 0.0
        (balance exports often leave cells blank for zero).
    """
    if not value or not value.strip():
        return 0.0
    s = value.strip()
    # Remove thousands separator (period)
    s = s.replace(".", "")
    # Replace decimal comma with dot
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_balance_sheet_csv(
    source: str | Path | IO[str],
    *,
    account_col: int = 1,
    description_col: int = 2,
    period_col: int = 5,
    ytd_col: int = 6,
    budget_col: int = 7,
    delimiter: str = ";",
    skip_rows: int = 1,
    encoding: str = "utf-8-sig",
) -> list[BalanceSheetRow]:
    """Load a balance sheet from a CSV file.

    The default column indices match a common administrator export format:
        Col 0: Fin.  (company id)
        Col 1: Konto (account number)
        Col 2: Tekst (description)
        Col 3: D/S   (debit/credit marker)
        Col 4: Bem.  (remark)
        Col 5: Bev. per. (period movement)
        Col 6: Saldo pr. (YTD balance)
        Col 7: Budget året (annual budget)

    All column indices and the delimiter are configurable so the parser
    works with different administrator exports.

    Args:
        source: File path or file-like object.
        account_col: Column index for account number.
        description_col: Column index for description.
        period_col: Column index for period movement.
        ytd_col: Column index for YTD balance.
        budget_col: Column index for annual budget.
        delimiter: CSV delimiter character.
        skip_rows: Number of header rows to skip.
        encoding: File encoding (used only when *source* is a path).

    Returns:
        A list of BalanceSheetRow objects for rows that have an account
        number (section headers and subtotals are skipped).
    """

    def _parse_rows(reader):
        rows: list[BalanceSheetRow] = []
        for _ in range(skip_rows):
            try:
                next(reader)
            except StopIteration:
                break
        for raw in reader:
            if len(raw) <= max(account_col, description_col):
                continue
            acct = raw[account_col].strip() if account_col < len(raw) else ""
            # Skip rows without a numeric account number (headers/subtotals)
            if not acct or not re.match(r"^\d+$", acct):
                continue
            desc = raw[description_col].strip() if description_col < len(raw) else ""
            period = parse_danish_number(raw[period_col]) if period_col < len(raw) else 0.0
            ytd = parse_danish_number(raw[ytd_col]) if ytd_col < len(raw) else 0.0
            budget = parse_danish_number(raw[budget_col]) if budget_col < len(raw) else 0.0
            rows.append(BalanceSheetRow(
                account_number=acct,
                description=desc,
                period_movement=period,
                ytd_balance=ytd,
                annual_budget=budget,
            ))
        return rows

    if isinstance(source, (str, Path)):
        with open(source, newline="", encoding=encoding) as f:
            reader = csv.reader(f, delimiter=delimiter)
            return _parse_rows(reader)
    else:
        reader = csv.reader(source, delimiter=delimiter)
        return _parse_rows(reader)


# ---------------------------------------------------------------------------
# BudgetTracker — the main orchestrator
# ---------------------------------------------------------------------------

@dataclass
class BudgetTracker:
    """Tracks a budget against actuals and suggests next year's budget.

    Workflow:
        1. Create a Budget with categories and line items.
        2. Set up an AccountMapping to link account numbers → item keys.
        3. Call ``update_actuals_from_balance_sheet`` with a CSV/Excel path.
        4. Inspect variances via the Budget's properties.
        5. Call ``suggest_next_year_budget`` to get a proposed budget.

    Attributes:
        budget: The budget being tracked.
        mapping: The account-to-item mapping.
        balance_rows: The most recently loaded balance sheet rows.
    """

    budget: Budget
    mapping: AccountMapping
    balance_rows: list[BalanceSheetRow] = field(default_factory=list)

    def update_actuals(self, rows: list[BalanceSheetRow]) -> dict[str, float]:
        """Update actual amounts on budget line items from balance rows.

        All actuals are first reset to zero.  Each row's YTD balance is
        then added to the budget line item that its account number maps
        to.  Accounts that appear in multiple rows with the same item key
        are summed.

        If ``mapping.unmapped_category`` names an existing category, each
        unmapped account with a non-zero balance is added to it as a line
        item (see :class:`AccountMapping`).

        Args:
            rows: Parsed balance sheet rows.

        Returns:
            Dict of unmapped account numbers and their YTD balances.
            This includes accounts mapped to an item key that doesn't
            exist in the budget.
        """
        self.balance_rows = rows

        # Reset all actuals to zero first
        for cat in self.budget.categories.values():
            for item in cat.items.values():
                item.actual = 0.0

        catch_all = (
            self.budget.categories.get(self.mapping.unmapped_category)
            if self.mapping.unmapped_category is not None
            else None
        )

        unmapped: dict[str, float] = {}
        for row in rows:
            item_key = self.mapping.lookup(row.account_number)
            budget_item = (
                self.budget.find_item(item_key) if item_key is not None else None
            )
            if budget_item is not None:
                budget_item.actual += row.ytd_balance
                continue

            # Unmapped account (or mapped to a non-existent item)
            if item_key is None and row.ytd_balance == 0.0:
                continue
            unmapped[row.account_number] = (
                unmapped.get(row.account_number, 0.0) + row.ytd_balance
            )
            if catch_all is not None:
                key = f"account:{row.account_number}"
                if key not in catch_all.items:
                    catch_all.add_item(BudgetLineItem(
                        key=key,
                        name=row.description or row.account_number,
                    ))
                catch_all.items[key].actual += row.ytd_balance

        return unmapped

    def update_actuals_from_file(
        self,
        path: str | Path,
        **csv_kwargs,
    ) -> dict[str, float]:
        """Load a balance-sheet CSV and update actuals in one step.

        Args:
            path: Path to the CSV file.
            **csv_kwargs: Forwarded to ``load_balance_sheet_csv``.

        Returns:
            Dict of unmapped account numbers and their YTD balances.
        """
        rows = load_balance_sheet_csv(path, **csv_kwargs)
        return self.update_actuals(rows)

    # -- Extrapolation -------------------------------------------------------

    @staticmethod
    def _extrapolate_annual(
        ytd: float,
        months_elapsed: int,
        total_months: int = 12,
    ) -> float:
        """Linearly extrapolate a YTD figure to a full year.

        Args:
            ytd: Year-to-date amount.
            months_elapsed: How many months of the fiscal year have passed.
            total_months: Total months in the fiscal year (default 12).

        Returns:
            Extrapolated annual amount.
        """
        if months_elapsed <= 0:
            return ytd
        if months_elapsed >= total_months:
            return ytd
        return ytd * total_months / months_elapsed

    # -- Next-year budget suggestion -----------------------------------------

    def suggest_next_year_budget(
        self,
        *,
        months_elapsed: int = 12,
        inflation_rate: float = 0.0,
        max_rent_increase_pct: float = 0.05,
        prior_year_actuals: dict[str, float] | None = None,
        overrides: dict[str, float] | None = None,
        current_year_weight: float = 0.6,
        rounding: int = 500,
        rent_rounding: int = 1000,
        min_rent_increase_pct: float = 0.005,
    ) -> Budget:
        """Suggest a budget for the next fiscal year.

        The suggestion logic:
          1. For each expense line, take the higher of (a) this year's
             budget and (b) the extrapolated actual, then apply inflation.
          2. For income lines, carry forward the current budget.
          3. Round every line to the nearest ``rounding``.
          4. If the resulting liquidity result is a deficit, compute the
             rent increase needed and cap it at ``max_rent_increase_pct``.
             Increases below ``min_rent_increase_pct`` are not suggested.
          5. Rent (boligafgift) is never decreased.

        The suggested rent is returned in ``Budget.rent_amount`` only; the
        income line items are *not* adjusted, so the returned budget's
        operating result shows the result before any rent increase.

        When ``prior_year_actuals`` is given (item_key → actual amount),
        the engine blends the extrapolated current-year actual with the
        prior-year actual using ``current_year_weight`` (default 60 %
        current, 40 % prior) for smoother projections.

        Any entry in ``overrides`` replaces the computed suggestion for
        that item key (it is still rounded).

        Args:
            months_elapsed: Months elapsed in the current fiscal year
                            (used to extrapolate YTD to annual).
            inflation_rate: General inflation adjustment (e.g. 0.02 = 2 %).
            max_rent_increase_pct: Maximum allowed rent increase as a
                                   fraction (e.g. 0.05 = 5 %).
            prior_year_actuals: Optional prior-year actuals for smoothing.
            overrides: Dict of item_key → forced budgeted amount.
            current_year_weight: Weight of the current year when blending
                with ``prior_year_actuals`` (0–1).
            rounding: Round each suggested line to this multiple (DKK).
                Use 0 or 1 to disable.
            rent_rounding: Round the suggested rent to this multiple (DKK).
            min_rent_increase_pct: Smallest rent increase worth suggesting
                as a fraction (e.g. 0.005 = 0.5 %).

        Returns:
            A new Budget object with suggested amounts for next year.
        """
        overrides = overrides or {}
        prior = prior_year_actuals or {}

        # Determine next fiscal year label
        next_year = _increment_fiscal_year(self.budget.fiscal_year)

        new_budget = Budget(fiscal_year=next_year)
        new_budget.mortgage_principal = self.budget.mortgage_principal
        new_budget.depreciation = self.budget.depreciation

        for cat in self.budget.categories.values():
            new_cat = BudgetCategory(
                key=cat.key,
                name=cat.name,
                category_type=cat.category_type,
            )
            for item in cat.items.values():
                if item.key in overrides:
                    suggested = overrides[item.key]
                elif cat.category_type is CategoryType.INCOME:
                    # Income: carry forward current budget (don't reduce)
                    suggested = item.budgeted
                else:
                    # Expense: use the higher of budget or extrapolated actual
                    extrapolated = self._extrapolate_annual(
                        item.actual, months_elapsed
                    )
                    # Blend with prior year if available
                    if item.key in prior:
                        blended = (
                            current_year_weight * extrapolated
                            + (1 - current_year_weight) * prior[item.key]
                        )
                    else:
                        blended = extrapolated

                    # Take the higher of current budget or blended actual
                    base = max(abs(item.budgeted), abs(blended))
                    # Preserve the sign of the original budget
                    if item.budgeted < 0:
                        suggested = -base
                    else:
                        suggested = base

                    # Apply inflation
                    suggested *= 1 + inflation_rate

                # Round for cleaner budget numbers
                suggested = _round_to(suggested, rounding)

                new_cat.add_item(BudgetLineItem(
                    key=item.key,
                    name=item.name,
                    budgeted=suggested,
                ))
            new_budget.add_category(new_cat)

        # --- Rent adjustment suggestion ---
        new_budget.rent_amount = self.budget.rent_amount
        deficit = -new_budget.liquidity_result_budgeted

        if deficit > 0 and new_budget.rent_amount > 0:
            increase_needed = deficit / new_budget.rent_amount
            capped_increase = min(increase_needed, max_rent_increase_pct)
            if capped_increase > min_rent_increase_pct:
                new_budget.rent_amount *= 1 + capped_increase
                new_budget.rent_amount = _round_to(
                    new_budget.rent_amount, rent_rounding
                )

        return new_budget

    # -- Variance report -----------------------------------------------------

    def variance_report(self) -> list[dict]:
        """Generate a list of variance records for all budget items.

        Returns:
            List of dicts with keys: category, item, key, budgeted,
            actual, variance, utilisation_pct.  Pass the result to
            ``pandas.DataFrame`` for a tabular view.
        """
        rows = []
        for cat in self.budget.categories.values():
            for item in cat.items.values():
                util = item.utilisation
                rows.append({
                    "category": cat.name,
                    "item": item.name,
                    "key": item.key,
                    "budgeted": item.budgeted,
                    "actual": item.actual,
                    "variance": item.variance,
                    "utilisation_pct": round(util * 100, 1) if util is not None else None,
                })
        return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _round_to(value: float, nearest: int) -> float:
    """Round *value* to the nearest multiple of *nearest*."""
    if nearest <= 0:
        return value
    return round(value / nearest) * nearest


def _increment_fiscal_year(label: str) -> str:
    """Increment a fiscal-year label like '2025/2026' → '2026/2027'.

    Also handles single-year labels like '2025' → '2026'.
    """
    parts = label.split("/")
    if len(parts) == 2:
        try:
            a, b = int(parts[0]), int(parts[1])
            return f"{a + 1}/{b + 1}"
        except ValueError:
            pass
    try:
        return str(int(label) + 1)
    except ValueError:
        return label + "+1"
