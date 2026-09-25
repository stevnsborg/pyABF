"""
cash_flow.py — Year-by-year cash-flow projection for the DCF valuation model.

Projects rental income, operating expenses, modernization costs, and net
operating income (NOI) over the budget period.  Each year's cash flow is
represented as an ``AnnualCashFlow`` dataclass; the full projection is
assembled by ``CashFlowProjection``.

The projection follows the structure of the DCF budget used in a typical
Danish valuarvurdering:

    Lejeindtægter (rental income)
      – Boliger, nuværende         (base residential rent)
      – Boliger, moderniserede     (modernized residential rent)
      – Erhverv                    (commercial rent)
    = Lejeindtægter i alt

    (Forbedringstillæg and kapitalafkast are assumed to be part of the
    existing rent roll; the corresponding columns are kept for reporting
    but are always 0 in the projection.)

    Driftsudgifter i alt           (operating expenses)

    Moderniseringsomkostninger     (modernization costs)
    Øvrige byggeudgifter           (other construction costs)
    Energimærke                    (energy label, year 1 only)

    = Netto Cash Flow              (net operating income)

All amounts are nominal (inflated from their base-year level).

Contains:
    AnnualCashFlow      — One year's income and expense breakdown
    CashFlowProjection  — Full projection over the budget period
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .assumptions import ValuationAssumptions


@dataclass
class AnnualCashFlow:
    """Cash-flow breakdown for a single year.

    All amounts are in nominal DKK (i.e. base-year values × cumulative
    inflation up to that year).

    Attributes:
        year_index: Year number within the budget period (1-based).
        base_residential_rent: Rent from un-modernized residential units.
        modernized_residential_rent: Rent from modernized residential units.
        commercial_rent: Rent from commercial units.
        improvement_allowances: Reserved; always 0 (included in base rent).
        capital_return: Reserved; always 0 (included in base rent).
        total_rental_income: Sum of all rental income components.
        operating_expenses: Total operating expenses for the year.
        modernization_cost: One-time modernization investment for the year.
        other_construction_costs: Other construction/building costs.
        energy_label_cost: Energy label upgrade cost (year 1 only).
        net_operating_income: Total income minus all costs.
        inflation_factor: Cumulative inflation factor for this year
            relative to base year (year 0).  Year 1 = (1 + r)¹.
        cumulative_modernized_area: Total area modernized by end of year (m²).
    """

    year_index: int
    base_residential_rent: float = 0.0
    modernized_residential_rent: float = 0.0
    commercial_rent: float = 0.0
    improvement_allowances: float = 0.0
    capital_return: float = 0.0
    total_rental_income: float = 0.0
    operating_expenses: float = 0.0
    modernization_cost: float = 0.0
    other_construction_costs: float = 0.0
    energy_label_cost: float = 0.0
    net_operating_income: float = 0.0
    inflation_factor: float = 1.0
    cumulative_modernized_area: float = 0.0

    def to_dict(self) -> dict[str, float | int]:
        """Flat dictionary representation for DataFrame construction."""
        return {
            "Year": self.year_index,
            "Base residential rent": self.base_residential_rent,
            "Modernized residential rent": self.modernized_residential_rent,
            "Commercial rent": self.commercial_rent,
            "Improvement allowances": self.improvement_allowances,
            "Capital return": self.capital_return,
            "Total rental income": self.total_rental_income,
            "Operating expenses": self.operating_expenses,
            "Modernization cost": self.modernization_cost,
            "Other construction costs": self.other_construction_costs,
            "Energy label cost": self.energy_label_cost,
            "Net operating income": self.net_operating_income,
            "Inflation factor": self.inflation_factor,
            "Cumulative modernized area (m²)": self.cumulative_modernized_area,
        }


@dataclass
class CashFlowProjection:
    """Complete cash-flow projection over the DCF budget period.

    Given a set of ``ValuationAssumptions``, this class computes the
    year-by-year cash-flow breakdown and provides both a list of
    ``AnnualCashFlow`` objects and a pandas DataFrame for export.

    The projection runs for ``evaluation_period`` years (typically 15).
    Year indices are 1-based: year 1 is the first future year.

    Additionally, a *terminal year* (year ``evaluation_period + 1``) is
    computed to represent the fully-stabilised cash flow used for the
    Gordon Growth terminal value.

    Attributes:
        assumptions: The input assumptions driving the projection.
        cash_flows: List of AnnualCashFlow for years 1 through
            evaluation_period + 1 (the terminal year).
    """

    assumptions: ValuationAssumptions
    cash_flows: list[AnnualCashFlow] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.cash_flows:
            self.cash_flows = self._project()

    # ------------------------------------------------------------------
    # Core projection logic
    # ------------------------------------------------------------------

    def _project(self) -> list[AnnualCashFlow]:
        """Build the year-by-year cash-flow projection.

        Returns:
            List of AnnualCashFlow for years 1 .. evaluation_period + 1.
        """
        a = self.assumptions
        n = a.economic.evaluation_period
        r = a.economic.inflation_rate

        # Pre-compute base-year totals (year 0 values, before inflation).
        #
        # The model uses an "uplift" approach:
        #   - The base residential rent (total_base_residential_rent) is the
        #     full rent roll for ALL existing residential tenancies.  This
        #     already includes improvement allowances and capital return as
        #     components of the cost-determined rent.
        #   - As units are modernized, the ADDITIONAL income is the
        #     difference (modernized_rent - base_rent) × newly modernized m².
        #   - The base rent total stays fixed (before inflation) because the
        #     entire existing rent roll continues; modernization adds uplift.
        base_residential = a.rent.total_base_residential_rent
        commercial = a.rent.total_commercial_rent
        operating = a.total_operating_cost

        # Modernization schedule
        area_per_year = a.modernization.area_per_year
        mod_cost_base = a.modernization.annual_cost_base

        # Rent uplift per m² of modernized area (DKK/m²/year, base year)
        rent_uplift_per_sqm = (
            a.rent.modernized_rent_per_sqm - a.rent.base_rent_per_sqm
        )

        flows: list[AnnualCashFlow] = []

        for year in range(1, n + 2):  # years 1 through n+1 (terminal)
            # Cumulative inflation factor: year i → (1 + r)^i
            infl = (1 + r) ** year

            # Cumulative modernized area generating rent this year.
            #
            # Modernization carried out in year t only produces the higher
            # rent from year t+1 onwards (the tenant moves out, the work
            # is done, the next tenant moves in at the new rent).  So the
            # rent-producing area lags the investment by one year:
            #   year 1: 0 m² (no prior modernization)
            #   year 2: area_per_year (year 1's work is now rented)
            #   ...
            #   year n: (n-1) × area_per_year
            #   year n+1 (terminal): fully modernized
            if year <= n:
                cum_mod_area = min(
                    area_per_year * (year - 1), a.modernization.total_area_sqm
                )
            else:
                cum_mod_area = a.modernization.total_area_sqm

            # --- Income (all nominal = base × inflation) ---

            # Base residential rent: the full existing rent roll, inflated.
            base_rent = base_residential * infl

            # Modernization rent uplift: only the INCREASE over base rent
            # for the cumulative modernized area.
            mod_rent = cum_mod_area * rent_uplift_per_sqm * infl

            # Commercial rent
            comm_rent = commercial * infl

            total_income = base_rent + mod_rent + comm_rent

            # --- Expenses (all nominal) ---

            # Operating expenses
            op_exp = operating * infl

            # Modernization cost: incurred only during the budget period,
            # and only for area that has not already been modernized
            # (relevant when duration_years < evaluation_period).
            if year <= n and area_per_year > 0:
                remaining = max(
                    0.0,
                    a.modernization.total_area_sqm - area_per_year * (year - 1),
                )
                fraction = min(1.0, remaining / area_per_year)
                mod_cost = mod_cost_base * fraction * infl
            else:
                mod_cost = 0.0

            # Other construction costs: during budget period only
            if year <= n:
                other_constr = a.other_construction_costs_per_year * infl
            else:
                other_constr = 0.0

            # Energy label: year 1 only
            energy = a.energy_label_cost * infl if year == 1 else 0.0

            # --- Net operating income ---
            noi = total_income - op_exp - mod_cost - other_constr - energy

            flows.append(AnnualCashFlow(
                year_index=year,
                base_residential_rent=base_rent,
                modernized_residential_rent=mod_rent,
                commercial_rent=comm_rent,
                improvement_allowances=0.0,
                capital_return=0.0,
                total_rental_income=total_income,
                operating_expenses=op_exp,
                modernization_cost=mod_cost,
                other_construction_costs=other_constr,
                energy_label_cost=energy,
                net_operating_income=noi,
                inflation_factor=infl,
                cumulative_modernized_area=cum_mod_area,
            ))

        return flows

    # ------------------------------------------------------------------
    # Access helpers
    # ------------------------------------------------------------------

    @property
    def budget_period_flows(self) -> list[AnnualCashFlow]:
        """Cash flows for years 1 through evaluation_period (excl. terminal)."""
        n = self.assumptions.economic.evaluation_period
        return [cf for cf in self.cash_flows if cf.year_index <= n]

    @property
    def terminal_year_flow(self) -> AnnualCashFlow:
        """The terminal-year (year n+1) stabilised cash flow."""
        return self.cash_flows[-1]

    @property
    def noi_array(self) -> np.ndarray:
        """Net operating income for years 1..n as a numpy array.

        Does *not* include the terminal year.
        """
        return np.array([cf.net_operating_income for cf in self.budget_period_flows])

    def to_dataframe(self) -> pd.DataFrame:
        """Convert the projection to a pandas DataFrame.

        Includes all years (1 through n+1).  The terminal year is
        labelled as year n+1 with a note in the index.

        Returns:
            DataFrame with one row per year and columns for each
            income/expense component.
        """
        records = [cf.to_dict() for cf in self.cash_flows]
        df = pd.DataFrame(records)
        df = df.set_index("Year")
        return df
