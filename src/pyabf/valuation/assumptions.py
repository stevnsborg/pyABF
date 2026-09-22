"""
assumptions.py — Configurable parameters for the DCF property valuation model.

A Danish housing cooperative's market value (valuarvurdering) is computed
using a Discounted Cash Flow (DCF) model.  The model projects rental income
and operating expenses over a budget period (typically 15 years), then
applies a Gordon Growth terminal value for the stabilised years beyond.

This module defines the *input* side of that model as a hierarchy of
dataclasses.  Every number that a board, a valuar, or a what-if analysis
might want to change is exposed as a named, documented field.

Hierarchy
---------
ValuationAssumptions          ← top-level container
├── PropertyDescription       ← physical areas (residential, commercial, …)
├── RentAssumptions           ← per-m² rent levels and total base rent
├── ModernizationPlan         ← area, cost, and timeline for §19.2 upgrades
├── OperatingCostAssumptions  ← annual operating expenses (driftsudgifter)
├── CapitalReturnAssumptions  ← capital return items (kapitalafkast)
├── ImprovementAllowance[]    ← individual improvement line items
└── EconomicAssumptions       ← inflation, required return, budget period

All fields default to zero / empty so the model is fully
general.  Pass property-specific values when constructing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Property description
# ---------------------------------------------------------------------------

@dataclass
class PropertyDescription:
    """Physical areas of the property (m²).

    These areas drive per-m² calculations throughout the model.

    Attributes:
        total_building_area: Total building area per BBR (m²).
            Used as the denominator for per-m² metrics when accounting
            for the full property including commercial space.
        residential_area: Total residential area (m²).
            The area eligible for residential rent and modernization.
        commercial_area: Commercial/business area (m²).
        basement_area: Total basement area (m²).
        roof_area: Total roof/attic area (m²).
        land_area: Total land area per title deed (m²).
    """

    total_building_area: float = 0.0   # samlet bygningsareal (m²)
    residential_area: float = 0.0      # boligareal (m²)
    commercial_area: float = 0.0         # erhvervsareal (m²)
    basement_area: float = 0.0         # kælderareal (m²)
    roof_area: float = 0.0             # tagetagens areal (m²)
    land_area: float = 0.0             # grundareal i alt (m²)


# ---------------------------------------------------------------------------
# Rent levels
# ---------------------------------------------------------------------------

@dataclass
class RentAssumptions:
    """Rental income parameters (DKK/m²/year unless noted).

    The model tracks three categories of rental income that each grow
    with inflation over the budget period:

    1. **Base residential rent** — the current cost-determined rent
       (omkostningsbestemt husleje) for existing tenancies.
    2. **Modernized rent** — the higher rent achievable after a
       comprehensive modernization (gennemgribende modernisering)
       under Lejelovens §19 stk. 2 (formerly Boligreguleringslovens
       §5 stk. 2).
    3. **Commercial rent** — the estimated market rent for commercial
       units.

    Attributes:
        base_rent_per_sqm: Current average residential rent (DKK/m²/year).
            From the Wiborg report this is the weighted average across
            all residential tenancies.
        modernized_rent_per_sqm: Rent per m² after §19.2 modernization
            (DKK/m²/year).  This is the *total* rent for a modernized
            unit, not the *increase*.
        commercial_rent_per_sqm: Estimated commercial rent (DKK/m²/year).
        total_base_residential_rent: Total annual base residential rent
            from all existing tenancies (DKK).  This is used directly
            rather than computed from base_rent_per_sqm × area, because
            the actual rent roll may include tenancies at different rates
            (e.g. converted commercial units already at 1,700 DKK/m²).
        total_commercial_rent: Total annual commercial rent (DKK).
    """

    base_rent_per_sqm: float = 0.0           # gennemsnitlig leje pr. m²
    modernized_rent_per_sqm: float = 0.0       # boliglejeniveau renoveret
    commercial_rent_per_sqm: float = 0.0       # erhvervslejeniveau
    total_base_residential_rent: float = 0.0   # total annual base rent (DKK)
    total_commercial_rent: float = 0.0         # erhvervslejemål (DKK)


# ---------------------------------------------------------------------------
# Modernization plan
# ---------------------------------------------------------------------------

@dataclass
class ModernizationPlan:
    """Parameters for the phased modernization of residential units.

    When a tenant vacates, the cooperative can carry out a comprehensive
    modernization (gennemgribende modernisering) and subsequently charge
    the higher §19.2 rent.  The model assumes a linear schedule: the
    same number of square meters are modernized each year over the
    budget period.

    Attributes:
        total_area_sqm: Total residential area to be modernized (m²).
            Typically equals the full residential area.
        cost_per_sqm: One-time modernization cost per m² (DKK/m²).
            Covers renovation of kitchens, bathrooms, surfaces, etc.
        duration_years: Number of years over which modernization is
            phased.  Usually equals the budget period (15 years).
        vacancy_rate: Assumed fraction of units vacating per year.
            Determines the area modernized each year.  When set to 0
            the model falls back to total_area / duration_years.
    """

    total_area_sqm: float = 0.0      # areal renovering (m²)
    cost_per_sqm: float = 0.0         # moderniseringsomkostninger pr. m²
    duration_years: int = 15           # budgetperiode
    vacancy_rate: float = 0.0         # fraflytterfrekvens (0 = linear)

    @property
    def area_per_year(self) -> float:
        """Area modernized each year (m²).

        If a vacancy rate is set, that drives the pace.
        Otherwise the total area is spread evenly across the duration.
        """
        if self.vacancy_rate > 0:
            return self.total_area_sqm * self.vacancy_rate
        if self.duration_years <= 0:
            return 0.0
        return self.total_area_sqm / self.duration_years

    @property
    def annual_cost_base(self) -> float:
        """Base-year modernization cost (DKK), before inflation.

        This is area_per_year × cost_per_sqm.
        """
        return self.area_per_year * self.cost_per_sqm


# ---------------------------------------------------------------------------
# Operating costs
# ---------------------------------------------------------------------------

@dataclass
class OperatingCostAssumptions:
    """Annual operating expenses (driftsudgifter) in DKK.

    The total is the sum of all individual cost lines.  These are the
    *base-year* amounts; the model inflates them year by year.

    The breakdown mirrors the line items in the Wiborg budget (Bilag 1).
    For a quick scenario analysis you can just set ``total_operating_cost``
    directly; the individual lines are informational / audit support.

    Attributes:
        property_tax: Grundskyld (land tax).
        pest_control: Rottebekæmpelsesgebyr.
        chimney_sweep: Skorstensfejning.
        sidewalk_cleaning: Renholdelse, fortov.
        waste_collection: Dagrenovation- & renholdelsesgebyr.
        water: Vand - fordeles i.h.t. vandregnskab.
        insurance: Forsikringer.
        electricity: Electricitet.
        caretaker: Vicevært / renholdelse / abonnementer mm.
        administration: Administration / Revision.
        exterior_maintenance_per_sqm: Løbende udvendig vedligeholdelse (DKK/m²).
        interior_maintenance_per_sqm: Løbende indvendig vedligeholdelse (DKK/m²).
        heating_accounts: Varme- & vandregnskab.
        total_operating_cost: Total annual operating cost (DKK).
            If set, this overrides the sum of the individual lines.
            If 0.0 or None, the total is computed from the breakdown.
    """

    property_tax: float = 0.0
    pest_control: float = 0.0
    chimney_sweep: float = 0.0
    sidewalk_cleaning: float = 0.0
    waste_collection: float = 0.0
    water: float = 0.0
    insurance: float = 0.0
    electricity: float = 0.0
    caretaker: float = 0.0
    administration: float = 0.0
    exterior_maintenance_per_sqm: float = 0.0
    interior_maintenance_per_sqm: float = 0.0
    heating_accounts: float = 0.0
    total_operating_cost: float | None = None

    def compute_total(self, property: PropertyDescription) -> float:
        """Compute total operating cost from the individual lines.

        Args:
            property: The property description (needed for area-based items).

        Returns:
            Total annual operating cost in DKK.
        """
        if self.total_operating_cost is not None:
            return self.total_operating_cost

        area_based = (
            self.exterior_maintenance_per_sqm * property.total_building_area
            + self.interior_maintenance_per_sqm * property.residential_area
        )
        fixed = (
            self.property_tax
            + self.pest_control
            + self.chimney_sweep
            + self.sidewalk_cleaning
            + self.waste_collection
            + self.water
            + self.insurance
            + self.electricity
            + self.caretaker
            + self.administration
            + self.heating_accounts
        )
        return fixed + area_based


# ---------------------------------------------------------------------------
# Capital return (kapitalafkast)
# ---------------------------------------------------------------------------

@dataclass
class CapitalReturnAssumptions:
    """Capital return on the property (kapitalafkast).

    Under Danish rules, part of the rent covers a capital return to
    the property owner.  This is based on the 15th general assessment
    (15. alm. vurdering) and a percentage of the assessed value.

    Attributes:
        assessment_per_sqm: 15th general assessment per m² (DKK/m²).
        assessment_pct: Percentage of the assessment used for return.
        technical_installations: Additional return for technical
            installations (number of years' worth).
    """

    assessment_per_sqm: float = 0.0     # 15. alm. Vurdering (skøn) pr. m²
    assessment_pct: float = 0.07          # 7% heraf
    technical_installations: float = 0.0  # tekniske installationer (years)


# ---------------------------------------------------------------------------
# Improvement allowances (forbedringstillæg)
# ---------------------------------------------------------------------------

@dataclass
class ImprovementAllowance:
    """A single improvement contributing to the rent level (forbedringstillæg).

    Under Danish tenancy law, the landlord can pass through the cost of
    specific improvements to the rent, as an annual yield on the
    investment (adjusted for the improvement fraction of the total cost).

    The annual rent increase from an improvement is:
        cost × improvement_fraction × yield_rate

    Attributes:
        name: Description of the improvement.
        year: Year the improvement was completed.
        cost: Total cost of the improvement (DKK).
        improvement_fraction: Fraction of the cost considered an
            improvement (vs. maintenance).  Range 0.0–1.0.
        yield_rate: Annual yield rate on the improvement cost.
    """

    name: str
    year: int
    cost: float
    improvement_fraction: float
    yield_rate: float

    @property
    def annual_allowance(self) -> float:
        """Annual rent increase from this improvement (DKK)."""
        return self.cost * self.improvement_fraction * self.yield_rate


# No default improvements — supply property-specific lists at instantiation.
DEFAULT_IMPROVEMENT_ALLOWANCES: list[ImprovementAllowance] = []


# ---------------------------------------------------------------------------
# Economic assumptions
# ---------------------------------------------------------------------------

@dataclass
class EconomicAssumptions:
    """Macro-economic and valuation parameters.

    These drive the discounting and the terminal value calculation.

    Attributes:
        inflation_rate: Annual inflation rate.
            The ECB targets 2%; the Wiborg report uses 2%.
        required_real_return: Required real return above inflation.
            Set by the valuar based on market conditions, property risk,
            and alternative investments.  3.25% in the Wiborg report.
        evaluation_period: Number of years in the DCF budget period.
            After this period the property is assumed to be fully
            modernized and the cash flow stabilises.  15 years is standard.
    """

    inflation_rate: float = 0.02    # 2% inflation
    required_real_return: float = 0.0325  # 3.25% real return
    evaluation_period: int = 15     # 15-year budget period

    @property
    def discount_rate(self) -> float:
        """Nominal discount rate (inflation + real return).

        In the Wiborg report: 2% + 3.25% = 5.25%.
        """
        return self.inflation_rate + self.required_real_return

    @property
    def stabilised_yield(self) -> float:
        """Stabilised yield used for the terminal value (= discount_rate).

        After the budget period, the property is assumed to generate
        a constant real cash flow growing at the inflation rate.
        The capitalisation rate for the Gordon Growth model equals
        the nominal discount rate.
        """
        return self.discount_rate


# ---------------------------------------------------------------------------
# Top-level container
# ---------------------------------------------------------------------------

@dataclass
class ValuationAssumptions:
    """Complete set of assumptions for a DCF property valuation.

    This is the single object you create and pass to ``DCFModel``.
    Change any field to run a scenario; the model recomputes everything
    from these inputs.

    Example:
        >>> from pyabf.valuation import ValuationAssumptions, DCFModel
        >>> assumptions = ValuationAssumptions(
        ...     property_desc=PropertyDescription(total_building_area=5000, ...),
        ...     rent=RentAssumptions(base_rent_per_sqm=800, ...),
        ...     ...
        ... )
        >>> model = DCFModel(assumptions)
        >>> result = model.compute()
        >>> print(f"Property value: {result.total_value:,.0f} DKK")

    Attributes:
        property_desc: Physical description of the property.
        rent: Rental income parameters.
        modernization: Modernization plan (area, cost, timeline).
        operating: Operating cost breakdown.
        capital_return: Capital return parameters.
        improvements: List of improvement allowances.
        economic: Inflation, return, and budget period.
        energy_label_cost: One-time cost to upgrade the energy label
            to category C (DKK).  Included in year-1 expenses when > 0.
            For properties already at A/B/C, set to 0.
        other_construction_costs_per_year: Additional annual construction/
            building-permit costs during the modernization period (DKK/year).
    """

    property_desc: PropertyDescription = field(default_factory=PropertyDescription)
    rent: RentAssumptions = field(default_factory=RentAssumptions)
    modernization: ModernizationPlan = field(default_factory=ModernizationPlan)
    operating: OperatingCostAssumptions = field(
        default_factory=OperatingCostAssumptions
    )
    capital_return: CapitalReturnAssumptions = field(
        default_factory=CapitalReturnAssumptions
    )
    improvements: list[ImprovementAllowance] = field(
        default_factory=lambda: list(DEFAULT_IMPROVEMENT_ALLOWANCES)
    )
    economic: EconomicAssumptions = field(default_factory=EconomicAssumptions)
    energy_label_cost: float = 0.0
    other_construction_costs_per_year: float = 0.0

    @property
    def total_improvement_allowance(self) -> float:
        """Sum of all annual improvement allowances (DKK)."""
        return sum(imp.annual_allowance for imp in self.improvements)

    @property
    def total_operating_cost(self) -> float:
        """Total annual base-year operating cost (DKK)."""
        return self.operating.compute_total(self.property_desc)

    def summary_dict(self) -> dict[str, float | int | str]:
        """Return a flat dictionary of key assumptions for display.

        Useful for logging, reports, and comparison tables.
        """
        return {
            "Residential area (m²)": self.property_desc.residential_area,
            "Commercial area (m²)": self.property_desc.commercial_area,
            "Total building area (m²)": self.property_desc.total_building_area,
            "Base rent (DKK/m²/yr)": self.rent.base_rent_per_sqm,
            "Modernized rent (DKK/m²/yr)": self.rent.modernized_rent_per_sqm,
            "Commercial rent (DKK/m²/yr)": self.rent.commercial_rent_per_sqm,
            "Total base residential rent (DKK)": self.rent.total_base_residential_rent,
            "Total commercial rent (DKK)": self.rent.total_commercial_rent,
            "Modernization area (m²)": self.modernization.total_area_sqm,
            "Modernization cost (DKK/m²)": self.modernization.cost_per_sqm,
            "Modernization duration (years)": self.modernization.duration_years,
            "Area per year (m²)": self.modernization.area_per_year,
            "Total operating cost (DKK)": self.total_operating_cost,
            "Total improvement allowance (DKK)": self.total_improvement_allowance,
            "Inflation rate": self.economic.inflation_rate,
            "Required real return": self.economic.required_real_return,
            "Discount rate (nominal)": self.economic.discount_rate,
            "Evaluation period (years)": self.economic.evaluation_period,
        }
