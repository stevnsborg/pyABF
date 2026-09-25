"""
cooperative.py — The main class representing a Danish housing cooperative.

Brings together all components: units, loans, accounting, budgets,
valuation, and tax — providing a single entry point for managing
the cooperative's complete financial picture.

The cooperative sets two annual rates (DKK/m²/year):
  - owned_rate_per_sqm: the charge for owner-occupied units (boligafgift)
  - rental_rate_per_sqm: the charge for rented-out units

These are propagated to each unit and scaled by the unit's area.
Rental units with a fixed_rent override the rate-based calculation.

Example:
    >>> from pyabf import HousingCooperative, CooperativeUnit, Loan
    >>> coop = HousingCooperative(
    ...     name="A/B Example",
    ...     units=[CooperativeUnit("Street 1, st.", area=70, rooms=3)],
    ...     owned_rate_per_sqm=650,
    ...     loans=[Loan("Loan 1", principal=10_000_000, interest_rate=0.02)],
    ... )
    >>> coop.total_annual_income
    45500.0

Contains:
    HousingCooperative — The main class
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .units import Unit, CooperativeUnit, CommercialUnit
from .loan import Loan
from .accounting import AnnualReport
from .budget import Budget, BudgetTracker, AccountMapping
from .tax import compute_property_tax
from .ois import OISClient, fetch_units
from .valuation import (
    ValuationAssumptions,
    DCFModel,
    ValuationResult,
    ValuationReport,
    run_sensitivity,
)


@dataclass
class HousingCooperative:
    """A Danish housing cooperative (andelsboligforening).

    This is the primary entry point for pyABF.  Instantiate it with the
    cooperative's units, loans, and rates, then use its methods to manage
    budgets, annual reports, valuations, and share-price computations.

    All units — residential and commercial, owned and rented — are stored
    in a single list.  Use the filtering properties to break them down
    by type and ownership.

    Note:
        Rates are pushed to the units when the cooperative is created and
        whenever ``set_owned_rate`` / ``set_rental_rate`` is called.  If
        you append units to ``units`` or change a unit's ``is_rental``
        afterwards, call :meth:`refresh_rates` to update them.

    Attributes:
        name: Name of the cooperative.
        units: List of all units in the property.
        owned_rate_per_sqm: Annual charge per m² for owned units (DKK/m²/year).
        rental_rate_per_sqm: Annual charge per m² for rental units (DKK/m²/year).
        loans: List of the cooperative's mortgage loans.
        annual_reports: Dict of {year: AnnualReport}.
        budgets: Dict of {fiscal_year_label: Budget}.
        account_mapping: Mapping from bookkeeping account numbers to
            budget line-item keys.  Shared across all budgets.
        bfe_numbers: BFE numbers of the properties the cooperative owns.
            Used by :meth:`add_units_from_ois` to load units from OIS.dk.
    """

    name: str
    units: list[Unit] = field(default_factory=list)
    owned_rate_per_sqm: float = 0.0
    rental_rate_per_sqm: float = 0.0
    loans: list[Loan] = field(default_factory=list)
    annual_reports: dict[int, AnnualReport] = field(default_factory=dict)
    budgets: dict[str, Budget] = field(default_factory=dict)
    account_mapping: AccountMapping = field(default_factory=AccountMapping)
    bfe_numbers: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Propagate rates to all units after initialization."""
        self._propagate_rates()

    @classmethod
    def from_ois(
        cls,
        name: str,
        bfe_numbers: list[int],
        client: OISClient | None = None,
        **kwargs: Any,
    ) -> HousingCooperative:
        """Create a cooperative with its units loaded from OIS.dk.

        Args:
            name: Name of the cooperative.
            bfe_numbers: BFE numbers of the cooperative's properties.
            client: OIS client to use; a default one if omitted.
            **kwargs: Other ``HousingCooperative`` fields (rates, loans, ...).

        Returns:
            The new cooperative.
        """
        coop = cls(name=name, bfe_numbers=list(bfe_numbers), **kwargs)
        coop.add_units_from_ois(client=client)
        return coop

    def add_units_from_ois(
        self,
        bfe_numbers: list[int] | None = None,
        client: OISClient | None = None,
        include_inactive: bool = False,
    ) -> list[Unit]:
        """Fetch units from OIS.dk and add them to the cooperative.

        Housing units become :class:`CooperativeUnit`, all others
        :class:`CommercialUnit`; every unit is added as owner-occupied
        (see :mod:`pyabf.ois`).  Units whose BBR id is already present in
        ``units`` are skipped, so calling this again does not create
        duplicates.  BFE numbers passed here are appended to
        ``bfe_numbers``.

        Args:
            bfe_numbers: BFE numbers to fetch.  Defaults to
                ``self.bfe_numbers``.
            client: OIS client to use; a default one if omitted.
            include_inactive: Also add units BBR marks as closed,
                historic or erroneous.

        Returns:
            The units that were added.

        Raises:
            OISError: If a BFE number cannot be fetched.
        """
        if bfe_numbers is None:
            bfe_numbers = self.bfe_numbers
        else:
            self.bfe_numbers.extend(
                b for b in bfe_numbers if b not in self.bfe_numbers
            )
        existing = {u.bbr_id for u in self.units if u.bbr_id is not None}
        added = [
            ois_unit.to_unit()
            for ois_unit in fetch_units(
                bfe_numbers, client=client, include_inactive=include_inactive
            )
            if ois_unit.bbr_id not in existing
        ]
        self.units.extend(added)
        self._propagate_rates()
        return added

    def refresh_rates(self) -> None:
        """Re-apply the cooperative's rates to all units.

        Call this after adding units or changing a unit's ``is_rental``.
        """
        self._propagate_rates()

    def add_unit(self, unit: Unit) -> None:
        """Add a unit and apply the cooperative's rate to it.

        Args:
            unit: The unit to add.
        """
        self.units.append(unit)
        self._propagate_rates()

    def _propagate_rates(self) -> None:
        """Set the per-m² rate on each unit based on its ownership status."""
        for unit in self.units:
            if unit.is_rental:
                unit._rate_per_sqm = self.rental_rate_per_sqm
            else:
                unit._rate_per_sqm = self.owned_rate_per_sqm

    def set_owned_rate(self, rate: float) -> None:
        """Update the annual rate for owned units and propagate.

        Args:
            rate: New rate in DKK/m²/year.
        """
        self.owned_rate_per_sqm = rate
        self._propagate_rates()

    def set_rental_rate(self, rate: float) -> None:
        """Update the annual rate for rental units and propagate.

        Args:
            rate: New rate in DKK/m²/year.
        """
        self.rental_rate_per_sqm = rate
        self._propagate_rates()

    # ═══════════════════════════════════════════════════════════════════
    # Unit filtering
    # ═══════════════════════════════════════════════════════════════════

    @property
    def residential_units(self) -> list[Unit]:
        """All residential units (anything that is not a CommercialUnit)."""
        return [u for u in self.units if not isinstance(u, CommercialUnit)]

    @property
    def commercial_units(self) -> list[CommercialUnit]:
        """All commercial/business units."""
        return [u for u in self.units if isinstance(u, CommercialUnit)]

    @property
    def owned_units(self) -> list[Unit]:
        """All owner-occupied units (not rented out)."""
        return [u for u in self.units if not u.is_rental]

    @property
    def rental_units(self) -> list[Unit]:
        """All units that are rented out."""
        return [u for u in self.units if u.is_rental]

    @property
    def owned_residential(self) -> list[Unit]:
        """Residential units that are owner-occupied (the actual andele)."""
        return [u for u in self.residential_units if not u.is_rental]

    @property
    def rental_residential(self) -> list[Unit]:
        """Residential units that are rented out."""
        return [u for u in self.residential_units if u.is_rental]

    @property
    def owned_commercial(self) -> list[CommercialUnit]:
        """Commercial units owned/operated by the cooperative."""
        return [u for u in self.commercial_units if not u.is_rental]

    @property
    def rental_commercial(self) -> list[CommercialUnit]:
        """Commercial units that are rented out."""
        return [u for u in self.commercial_units if u.is_rental]

    # ═══════════════════════════════════════════════════════════════════
    # Area calculations
    # ═══════════════════════════════════════════════════════════════════

    @property
    def total_area(self) -> float:
        """Total area of all units (m²)."""
        return sum(u.area for u in self.units)

    @property
    def residential_area(self) -> float:
        """Total area of all residential units (m²)."""
        return sum(u.area for u in self.residential_units)

    @property
    def commercial_area(self) -> float:
        """Total area of all commercial units (m²)."""
        return sum(u.area for u in self.commercial_units)

    @property
    def owned_area(self) -> float:
        """Total area of all owner-occupied units (m²)."""
        return sum(u.area for u in self.owned_units)

    @property
    def rental_area(self) -> float:
        """Total area of all rented-out units (m²)."""
        return sum(u.area for u in self.rental_units)

    @property
    def owned_residential_area(self) -> float:
        """Total area of owner-occupied residential units (m²)."""
        return sum(u.area for u in self.owned_residential)

    @property
    def rental_residential_area(self) -> float:
        """Total area of rented residential units (m²)."""
        return sum(u.area for u in self.rental_residential)

    @property
    def owned_commercial_area(self) -> float:
        """Total area of owned commercial units (m²)."""
        return sum(u.area for u in self.owned_commercial)

    @property
    def rental_commercial_area(self) -> float:
        """Total area of rented commercial units (m²)."""
        return sum(u.area for u in self.rental_commercial)

    # ═══════════════════════════════════════════════════════════════════
    # Income
    # ═══════════════════════════════════════════════════════════════════

    @property
    def total_annual_income(self) -> float:
        """Total annual income from all units (DKK)."""
        return sum(u.annual_charge for u in self.units)

    @property
    def owned_annual_income(self) -> float:
        """Total annual income from owned units (DKK)."""
        return sum(u.annual_charge for u in self.owned_units)

    @property
    def rental_annual_income(self) -> float:
        """Total annual income from rental units (DKK)."""
        return sum(u.annual_charge for u in self.rental_units)

    # ═══════════════════════════════════════════════════════════════════
    # Debt (loans)
    # ═══════════════════════════════════════════════════════════════════

    @property
    def total_debt(self) -> float:
        """Total outstanding debt across all loans (DKK)."""
        return sum(loan.principal for loan in self.loans)

    @property
    def total_debt_market_value(self) -> float:
        """Total market value of all loans (DKK)."""
        return sum(loan.market_value for loan in self.loans)

    def debt_after_years(self, years: int) -> float:
        """Total remaining debt after a given number of years.

        Args:
            years: Number of years from now.

        Returns:
            Total remaining debt in DKK.
        """
        return sum(loan.balance_after_years(years) for loan in self.loans)

    @property
    def total_annual_debt_service(self) -> float:
        """Total annual debt service (first year payments) across all loans (DKK).

        Sums the first period's total_payment × payments_per_year for each
        loan, i.e. the ydelse (interest, contribution and principal).
        """
        total = 0.0
        for loan in self.loans:
            schedule = loan.payment_schedule()
            if not schedule.empty:
                first_payment = float(schedule.iloc[0]["total_payment"])
                total += first_payment * loan.payments_per_year
        return total

    @property
    def total_annual_principal(self) -> float:
        """Total annual principal repayment (first year) across all loans (DKK).

        Useful for budget planning — this is the 'afdrag' that affects
        liquidity but is not an operating expense.
        """
        total = 0.0
        for loan in self.loans:
            schedule = loan.payment_schedule()
            if not schedule.empty:
                first_principal = float(schedule.iloc[0]["principal_payment"])
                total += first_principal * loan.payments_per_year
        return total

    # ═══════════════════════════════════════════════════════════════════
    # Annual reports
    # ═══════════════════════════════════════════════════════════════════

    def create_annual_report(
        self,
        year: int,
        from_defaults: bool = True,
        notes: dict[str, tuple[str, bool]] | None = None,
    ) -> AnnualReport:
        """Create an annual report for a given year and store it.

        Replaces any existing report for the same year.

        Args:
            year: The fiscal year.
            from_defaults: If True, pre-populate with empty notes.
            notes: Custom note layout ``{note_id: (name, is_expense)}``
                used when ``from_defaults`` is True.  Defaults to
                :data:`pyabf.accounting.DEFAULT_NOTES`.

        Returns:
            The newly created AnnualReport.
        """
        if from_defaults:
            report = AnnualReport.from_defaults(year, notes=notes)
        else:
            report = AnnualReport(year=year)
        self.annual_reports[year] = report
        return report

    def get_annual_report(self, year: int) -> AnnualReport | None:
        """Retrieve a stored annual report.

        Args:
            year: The fiscal year.

        Returns:
            The AnnualReport if it exists, otherwise None.
        """
        return self.annual_reports.get(year)

    # ═══════════════════════════════════════════════════════════════════
    # Budget management
    # ═══════════════════════════════════════════════════════════════════

    def add_budget(self, budget: Budget) -> None:
        """Store a budget, keyed by its fiscal_year label.

        Args:
            budget: The Budget to store.
        """
        self.budgets[budget.fiscal_year] = budget

    def get_budget(self, fiscal_year: str) -> Budget | None:
        """Retrieve a stored budget.

        Args:
            fiscal_year: The fiscal year label (e.g. '2025/2026').

        Returns:
            The Budget if it exists, otherwise None.
        """
        return self.budgets.get(fiscal_year)

    def create_budget_tracker(self, fiscal_year: str) -> BudgetTracker:
        """Create a BudgetTracker for a stored budget.

        Uses the cooperative's shared account_mapping.

        Args:
            fiscal_year: The fiscal year label of the budget to track.

        Returns:
            A BudgetTracker linked to the budget and account mapping.

        Raises:
            KeyError: If no budget exists for the given fiscal year.
        """
        budget = self.budgets.get(fiscal_year)
        if budget is None:
            raise KeyError(f"No budget found for fiscal year '{fiscal_year}'.")
        return BudgetTracker(budget=budget, mapping=self.account_mapping)

    def update_budget_actuals_from_file(
        self,
        fiscal_year: str,
        path: str | Path,
        **csv_kwargs: Any,
    ) -> dict[str, float]:
        """Load a balance-sheet CSV and update a budget's actuals.

        Convenience method that creates a tracker, loads the CSV,
        and updates the budget in one step.

        Args:
            fiscal_year: The fiscal year label of the budget.
            path: Path to the balance-sheet CSV.
            **csv_kwargs: Forwarded to ``load_balance_sheet_csv``.

        Returns:
            Dict of unmapped account numbers and their YTD balances.
        """
        tracker = self.create_budget_tracker(fiscal_year)
        return tracker.update_actuals_from_file(path, **csv_kwargs)

    def suggest_next_budget(
        self,
        fiscal_year: str,
        **kwargs: Any,
    ) -> Budget:
        """Suggest a budget for the next fiscal year.

        Creates a tracker for the given budget, runs the suggestion
        engine, and returns (but does not store) the suggested budget.

        Args:
            fiscal_year: The fiscal year label of the current budget.
            **kwargs: Forwarded to ``BudgetTracker.suggest_next_year_budget``.

        Returns:
            A new Budget with suggested amounts for next year.
        """
        tracker = self.create_budget_tracker(fiscal_year)
        return tracker.suggest_next_year_budget(**kwargs)

    # ═══════════════════════════════════════════════════════════════════
    # Valuation
    # ═══════════════════════════════════════════════════════════════════

    def run_valuation(
        self,
        assumptions: ValuationAssumptions,
    ) -> ValuationResult:
        """Run a DCF property valuation.

        Args:
            assumptions: Complete set of valuation inputs.

        Returns:
            A ValuationResult with the computed property value.
        """
        model = DCFModel(assumptions=assumptions)
        return model.compute()

    def run_valuation_with_report(
        self,
        assumptions: ValuationAssumptions,
        include_sensitivity: bool = True,
    ) -> tuple[ValuationResult, ValuationReport]:
        """Run a valuation and generate a formatted report.

        Args:
            assumptions: Complete set of valuation inputs.
            include_sensitivity: If True, include a sensitivity analysis.

        Returns:
            Tuple of (ValuationResult, ValuationReport).
        """
        model = DCFModel(assumptions=assumptions)
        result = model.compute()
        sensitivity = (
            run_sensitivity(assumptions) if include_sensitivity else None
        )
        report = ValuationReport(result, assumptions, sensitivity)
        return result, report

    # ═══════════════════════════════════════════════════════════════════
    # Tax
    # ═══════════════════════════════════════════════════════════════════

    def compute_property_tax(
        self,
        new_property_value: float,
        old_property_value: float,
        tax_rate: float,
        tax_year: int,
        **tax_rules: Any,
    ) -> tuple[float, float]:
        """Compute property tax for a given year (2024+ Danish rules).

        Delegates to :func:`pyabf.tax.compute_property_tax`; see there for
        the exact meaning of each argument.

        Args:
            new_property_value: The new official land assessment (DKK).
            old_property_value: The pre-reform tax level (DKK).
            tax_rate: The land tax rate (e.g. 0.026).
            tax_year: The year to compute tax for (>= 2024).
            **tax_rules: Optional rule overrides forwarded to
                ``compute_property_tax`` (e.g. ``max_annual_increase_rate``).

        Returns:
            Tuple of (tax, increase) in DKK.
        """
        return compute_property_tax(
            new_property_value=new_property_value,
            old_property_value=old_property_value,
            tax_rate=tax_rate,
            tax_year=tax_year,
            **tax_rules,
        )

    def project_property_tax(
        self,
        new_property_value: float,
        old_property_value: float,
        tax_rate: float,
        start_year: int = 2024,
        end_year: int = 2040,
        **tax_rules: Any,
    ) -> list[dict[str, float | int]]:
        """Project property tax over a range of years.

        Args:
            new_property_value: The new official land assessment (DKK).
            old_property_value: The pre-reform tax level (DKK).
            tax_rate: The land tax rate.
            start_year: First year to project (>= 2024).
            end_year: Last year to project (inclusive).
            **tax_rules: Optional rule overrides forwarded to
                :func:`pyabf.tax.compute_property_tax`.

        Returns:
            List of dicts with keys: year, tax, increase.  Pass to
            ``pandas.DataFrame`` for a tabular view.
        """
        rows = []
        for year in range(start_year, end_year + 1):
            tax, increase = compute_property_tax(
                new_property_value, old_property_value, tax_rate, year,
                **tax_rules,
            )
            rows.append({"year": year, "tax": tax, "increase": increase})
        return rows

    # ═══════════════════════════════════════════════════════════════════
    # Share value
    # ═══════════════════════════════════════════════════════════════════

    def compute_share_price(
        self,
        property_value: float,
        other_assets: float = 0.0,
        other_liabilities: float = 0.0,
    ) -> float:
        """Compute the share price per square meter.

        The share price is based on the owner-occupied residential area,
        since only those units carry a cooperative share.

        Formula:
            Equity = Property value + Other assets
                   - Debt (market value) - Other liabilities
            Share price = Equity / Owner-occupied residential area

        Debt is taken at market value (``Loan.market_value``, i.e.
        principal × bond price).  Returns 0.0 when there is no
        owner-occupied residential area.

        Args:
            property_value: The assessed property value (DKK).
            other_assets: Other assets besides the property (DKK).
            other_liabilities: Other liabilities besides mortgage debt (DKK).

        Returns:
            Share price in DKK/m².
        """
        equity = (
            property_value
            + other_assets
            - self.total_debt_market_value
            - other_liabilities
        )
        if self.owned_residential_area == 0:
            return 0.0
        return equity / self.owned_residential_area

    def update_share_values(self, share_price: float) -> None:
        """Update share values for all owner-occupied residential units.

        Only :class:`CooperativeUnit` instances are updated; plain
        :class:`Unit` objects have no share value.

        Args:
            share_price: Share price in DKK/m².
        """
        for unit in self.owned_residential:
            if isinstance(unit, CooperativeUnit):
                unit.compute_share_value(share_price)

    def compute_and_update_shares(
        self,
        property_value: float,
        other_assets: float = 0.0,
        other_liabilities: float = 0.0,
    ) -> float:
        """Compute the share price and update all cooperative units.

        Convenience method that calls ``compute_share_price`` and then
        ``update_share_values``.

        Args:
            property_value: The assessed property value (DKK).
            other_assets: Other assets besides the property (DKK).
            other_liabilities: Other liabilities besides mortgage debt (DKK).

        Returns:
            The computed share price in DKK/m².
        """
        price = self.compute_share_price(
            property_value, other_assets, other_liabilities
        )
        self.update_share_values(price)
        return price

    # ═══════════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════════

    def summary(self) -> dict[str, Any]:
        """Return a summary dict of the cooperative's key metrics.

        Returns:
            Dict with unit counts, areas, income, debt, and budget info.
        """
        return {
            "name": self.name,
            "total_units": len(self.units),
            "residential_units": len(self.residential_units),
            "commercial_units": len(self.commercial_units),
            "owned_units": len(self.owned_units),
            "rental_units": len(self.rental_units),
            "total_area_sqm": self.total_area,
            "residential_area_sqm": self.residential_area,
            "commercial_area_sqm": self.commercial_area,
            "owned_rate_per_sqm": self.owned_rate_per_sqm,
            "rental_rate_per_sqm": self.rental_rate_per_sqm,
            "total_annual_income": self.total_annual_income,
            "total_debt": self.total_debt,
            "total_debt_market_value": self.total_debt_market_value,
            "num_loans": len(self.loans),
            "num_annual_reports": len(self.annual_reports),
            "num_budgets": len(self.budgets),
        }
