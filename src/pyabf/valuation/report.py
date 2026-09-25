"""
report.py — Human-readable report generation for the DCF valuation.

Produces a structured text report that mirrors the presentation
format of a professional valuarvurdering.

Contains:
    ValuationReport  — Generates formatted text reports from a ValuationResult
"""

from __future__ import annotations

from textwrap import dedent

import pandas as pd

from .assumptions import ValuationAssumptions
from .dcf_model import DCFModel, ValuationResult
from .sensitivity import SensitivityGrid, run_sensitivity


class ValuationReport:
    """Generate human-readable reports from a DCF valuation.

    Combines the valuation result, assumptions summary, cash-flow
    projection table, and sensitivity analysis into a single
    formatted report.

    Example:
        >>> from pyabf.valuation import DCFModel, ValuationReport
        >>> model = DCFModel(assumptions)  # a populated ValuationAssumptions
        >>> result = model.compute()
        >>> report = ValuationReport(result, model.assumptions)
        >>> print(report.to_text())

    Attributes:
        result: The computed valuation result.
        assumptions: The assumptions used for the valuation.
        sensitivity: Optional pre-computed sensitivity grid.
    """

    def __init__(
        self,
        result: ValuationResult,
        assumptions: ValuationAssumptions,
        sensitivity: SensitivityGrid | None = None,
    ) -> None:
        self.result = result
        self.assumptions = assumptions
        self.sensitivity = sensitivity

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _section_header(self) -> str:
        """Valuation header and key result."""
        val = self.result.total_value_rounded
        per_sqm = self.result.total_value_per_sqm
        return dedent(f"""\
            ════════════════════════════════════════════════════════════════
             DCF PROPERTY VALUATION (Valuarvurdering)
            ════════════════════════════════════════════════════════════════

             Estimated market value:   {val:>15,.0f} DKK
             Per m² building area:     {per_sqm:>15,.0f} DKK/m²
            ────────────────────────────────────────────────────────────────
        """)

    def _section_assumptions(self) -> str:
        """Formatted assumptions summary."""
        a = self.assumptions
        lines = [
            "ASSUMPTIONS",
            "───────────────────────────────────────────────────────────────",
            "",
            "Property",
            f"  Total building area:       {a.property_desc.total_building_area:>10,.0f} m²",
            f"  Residential area:          {a.property_desc.residential_area:>10,.0f} m²",
            f"  Commercial area:           {a.property_desc.commercial_area:>10,.0f} m²",
            f"  Land area:                 {a.property_desc.land_area:>10,.0f} m²",
            "",
            "Rent levels",
            f"  Base residential rent:     {a.rent.base_rent_per_sqm:>10,.0f} DKK/m²/yr",
            f"  Modernized rent:           {a.rent.modernized_rent_per_sqm:>10,.0f} DKK/m²/yr",
            f"  Commercial rent:           {a.rent.commercial_rent_per_sqm:>10,.0f} DKK/m²/yr",
            f"  Total base residential:    {a.rent.total_base_residential_rent:>10,.0f} DKK/yr",
            f"  Total commercial:          {a.rent.total_commercial_rent:>10,.0f} DKK/yr",
            "",
            "Modernization",
            f"  Area to modernize:         {a.modernization.total_area_sqm:>10,.0f} m²",
            f"  Cost per m²:               {a.modernization.cost_per_sqm:>10,.0f} DKK/m²",
            f"  Duration:                  {a.modernization.duration_years:>10d} years",
            f"  Area per year:             {a.modernization.area_per_year:>10,.1f} m²/yr",
            f"  Annual cost (base year):   {a.modernization.annual_cost_base:>10,.0f} DKK/yr",
            "",
            "Operating costs (base year)",
            f"  Total:                     {a.total_operating_cost:>10,.0f} DKK/yr",
            "",
            "Improvement allowances (informational, included in base rent)",
        ]

        for imp in a.improvements:
            lines.append(
                f"  {imp.name:<40s} {imp.annual_allowance:>10,.0f} DKK/yr"
            )
        lines.append(
            f"  {'TOTAL':<40s} {a.total_improvement_allowance:>10,.0f} DKK/yr"
        )

        lines += [
            "",
            "Economic parameters",
            f"  Inflation rate:            {a.economic.inflation_rate * 100:>10.2f}%",
            f"  Required real return:      {a.economic.required_real_return * 100:>10.2f}%",
            f"  Discount rate (nominal):   {a.economic.discount_rate * 100:>10.2f}%",
            f"  Evaluation period:         {a.economic.evaluation_period:>10d} years",
            "",
        ]
        return "\n".join(lines)

    def _section_valuation(self) -> str:
        """NPV decomposition."""
        r = self.result
        lines = [
            "VALUATION BREAKDOWN",
            "───────────────────────────────────────────────────────────────",
            "",
            f"  PV of budget-period cash flows:  {r.pv_budget_period:>15,.0f} DKK",
            f"  Stabilised NOI (year {len(r.pv_cash_flows)} prices):  {r.terminal_noi:>15,.0f} DKK",
            f"  Terminal value (undiscounted):    {r.terminal_value:>15,.0f} DKK",
            f"  PV of terminal value:            {r.pv_terminal_value:>15,.0f} DKK",
            "",
            f"  ─────────────────────────────────────────────────",
            f"  TOTAL PROPERTY VALUE:            {r.total_value:>15,.0f} DKK",
            f"  Rounded:                         {r.total_value_rounded:>15,.0f} DKK",
            "",
        ]
        return "\n".join(lines)

    def _section_cash_flow_table(self) -> str:
        """Formatted cash-flow projection table."""
        df = self.result.projection.to_dataframe()

        # Select key columns for the report
        cols = [
            "Base residential rent",
            "Modernized residential rent",
            "Commercial rent",
            "Improvement allowances",
            "Capital return",
            "Total rental income",
            "Operating expenses",
            "Modernization cost",
            "Net operating income",
        ]
        df_display = df[cols].copy()

        # Format numbers
        for col in df_display.columns:
            df_display[col] = df_display[col].apply(lambda x: f"{x:,.0f}")

        lines = [
            "CASH FLOW PROJECTION",
            "───────────────────────────────────────────────────────────────",
            "",
            df_display.to_string(),
            "",
        ]
        return "\n".join(lines)

    def _section_sensitivity(self) -> str:
        """Formatted sensitivity analysis table."""
        if self.sensitivity is None:
            return ""

        df = self.sensitivity.to_dataframe()

        # Format values as thousands
        df_formatted = df.map(lambda x: f"{x:,.0f}")

        lines = [
            "SENSITIVITY ANALYSIS",
            "───────────────────────────────────────────────────────────────",
            "  Rows: Required real return (afkastkrav)",
            "  Cols: Modernized rent level (boliglejeniveau)",
            "",
            df_formatted.to_string(),
            "",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def to_text(self, include_sensitivity: bool = True) -> str:
        """Generate the full text report.

        Args:
            include_sensitivity: If True and no sensitivity grid was
                provided at init, compute one with default parameters.

        Returns:
            Multi-line string with the formatted report.
        """
        if include_sensitivity and self.sensitivity is None:
            self.sensitivity = run_sensitivity(self.assumptions)

        sections = [
            self._section_header(),
            self._section_assumptions(),
            self._section_valuation(),
            self._section_cash_flow_table(),
        ]

        if self.sensitivity is not None:
            sections.append(self._section_sensitivity())

        return "\n".join(sections)

    def to_dataframe(self) -> pd.DataFrame:
        """Return the cash-flow projection as a DataFrame.

        This is a convenience pass-through to the projection's
        ``to_dataframe()`` method.
        """
        return self.result.projection.to_dataframe()
