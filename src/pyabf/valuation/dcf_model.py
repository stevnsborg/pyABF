"""
dcf_model.py — Discounted Cash Flow (DCF) valuation engine.

Computes the market value (handelsværdi) of a Danish housing cooperative
property using the DCF method:

    Property Value = PV(budget-period cash flows) + PV(terminal value)

The **terminal value** uses the Gordon Growth Model:
    TV = NOI_terminal / (yield − growth)

where yield = discount_rate and growth = inflation_rate, so
    TV = NOI_terminal / required_real_return

The terminal value is then discounted back to present value using the
same nominal discount rate.

Contains:
    ValuationResult  — Immutable container for the computed valuation
    DCFModel         — The valuation engine
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .assumptions import ValuationAssumptions
from .cash_flow import CashFlowProjection


@dataclass(frozen=True)
class ValuationResult:
    """Immutable result of a DCF property valuation.

    All monetary values are in DKK.

    Attributes:
        pv_budget_period: Present value of cash flows during the
            budget period (years 1..n).
        terminal_value: Undiscounted terminal value (Gordon Growth).
        pv_terminal_value: Present value of the terminal value
            (discounted from year n).
        total_value: Sum of PV budget-period + PV terminal value.
            This is the estimated market value of the property.
        total_value_per_sqm: Total value divided by total building area.
        discount_factors: Array of discount factors for years 1..n.
        pv_cash_flows: Array of discounted cash flows for years 1..n.
        terminal_noi: The stabilised NOI used for the terminal value.
        stabilised_yield: The cap rate used for the terminal value
            (required_real_return).
        projection: The underlying ``CashFlowProjection``.
    """

    pv_budget_period: float
    terminal_value: float
    pv_terminal_value: float
    total_value: float
    total_value_per_sqm: float
    discount_factors: np.ndarray
    pv_cash_flows: np.ndarray
    terminal_noi: float
    stabilised_yield: float
    projection: CashFlowProjection

    def summary_dict(self) -> dict[str, float | int | str]:
        """Return a flat summary of the valuation result for display."""
        return {
            "PV budget period (DKK)": round(self.pv_budget_period),
            "Terminal value (DKK)": round(self.terminal_value),
            "PV terminal value (DKK)": round(self.pv_terminal_value),
            "Total value (DKK)": round(self.total_value),
            "Total value (DKK/m²)": round(self.total_value_per_sqm),
            "Terminal NOI (DKK)": round(self.terminal_noi),
            "Stabilised yield": self.stabilised_yield,
            "Budget period (years)": len(self.pv_cash_flows),
        }

    @property
    def total_value_rounded(self) -> float:
        """Total value rounded to the nearest 1,000 DKK.

        This is the figure typically reported in a valuarvurdering.
        """
        return round(self.total_value / 1_000) * 1_000


@dataclass
class DCFModel:
    """Discounted Cash Flow valuation engine.

    Orchestrates the cash-flow projection and the NPV calculation.

    Example:
        >>> from pyabf.valuation import ValuationAssumptions, DCFModel
        >>> model = DCFModel(ValuationAssumptions())
        >>> result = model.compute()
        >>> print(f"Value: {result.total_value_rounded:,.0f} DKK")

    Attributes:
        assumptions: Complete set of valuation inputs.
    """

    assumptions: ValuationAssumptions

    def compute(self) -> ValuationResult:
        """Run the full DCF valuation.

        Steps:
            1. Build the year-by-year cash-flow projection.
            2. Compute discount factors for years 1..n.
            3. Discount each year's NOI to present value.
            4. Compute the Gordon Growth terminal value from year n+1 NOI.
            5. Discount the terminal value back from year n.
            6. Sum to get total property value.

        Returns:
            A ``ValuationResult`` with all computed values.
        """
        a = self.assumptions
        n = a.economic.evaluation_period
        discount_rate = a.economic.discount_rate
        real_return = a.economic.required_real_return

        # --- Step 1: Cash-flow projection ---
        projection = CashFlowProjection(assumptions=a)

        # --- Step 2: Discount factors ---
        # D(t) = 1 / (1 + discount_rate)^t  for t = 1, 2, ..., n
        years = np.arange(1, n + 1, dtype=float)
        discount_factors = 1.0 / (1 + discount_rate) ** years

        # --- Step 3: Discounted budget-period cash flows ---
        noi_array = projection.noi_array
        pv_cash_flows = noi_array * discount_factors
        pv_budget_period = float(np.sum(pv_cash_flows))

        # --- Step 4: Terminal value (Gordon Growth Model) ---
        #
        # The terminal value represents the property's value at the end
        # of the budget period, assuming the cash flow has stabilised
        # (full modernization, no more one-off costs).
        #
        # The stabilised NOI at year n is computed as:
        #   - Full rental income (all area modernized, at year-n inflation)
        #   - Minus operating expenses (at year-n inflation)
        #   - No modernization or construction costs
        #
        # TV = stabilised_NOI_n / required_real_return
        #
        # This is equivalent to the Gordon Growth formula where the
        # nominal discount rate and the growth rate (inflation) cancel,
        # leaving only the real return in the denominator.
        inflation_n = (1 + a.economic.inflation_rate) ** n
        full_mod_area = a.modernization.total_area_sqm
        rent_uplift = (
            a.rent.modernized_rent_per_sqm - a.rent.base_rent_per_sqm
        )
        stabilised_income = (
            (a.rent.total_base_residential_rent
             + full_mod_area * rent_uplift
             + a.rent.total_commercial_rent)
            * inflation_n
        )
        stabilised_opex = a.total_operating_cost * inflation_n
        terminal_noi = stabilised_income - stabilised_opex
        if real_return > 0:
            terminal_value = terminal_noi / real_return
        else:
            terminal_value = 0.0

        # --- Step 5: Discount terminal value back from year n ---
        pv_terminal = terminal_value / (1 + discount_rate) ** n

        # --- Step 6: Total property value ---
        total_value = pv_budget_period + pv_terminal

        total_per_sqm = (
            total_value / a.property_desc.total_building_area
            if a.property_desc.total_building_area > 0
            else 0.0
        )

        return ValuationResult(
            pv_budget_period=pv_budget_period,
            terminal_value=terminal_value,
            pv_terminal_value=pv_terminal,
            total_value=total_value,
            total_value_per_sqm=total_per_sqm,
            discount_factors=discount_factors,
            pv_cash_flows=pv_cash_flows,
            terminal_noi=terminal_noi,
            stabilised_yield=real_return,
            projection=projection,
        )
