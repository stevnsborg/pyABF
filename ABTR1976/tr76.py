"""
tr76.py — A/B TR 1976 set up as a pyabf ``HousingCooperative`` (Forening).

Sources:
    - Valuation: Wiborg + Partnere valuarvurdering (case 600688), base
      case 182,004,331 DKK.  The inputs are reconstructed from that base
      case (15-year budget period, 2 % inflation, 3.25 % real return):
      they reproduce its property value, PV of the budget period, terminal
      NOI and yearly NOI.
    - Loans 15, 16 and 17: docs/loan.ipynb.

Placeholders — replace with the real figures:
    - Units: one aggregated unit holding the whole residential area.  Use
      ``forening.add_units_from_ois([...BFE...])`` or the real unit list
      to get per-apartment share values.
    - base_rent_per_sqm / modernized_rent_per_sqm: only their difference
      (850 DKK/m², the rent uplift) is known from the valuation.
    - other_assets / other_liabilities: from the scenario analysis.
"""

from __future__ import annotations

from pyabf import CooperativeUnit, HousingCooperative, Loan
from pyabf.valuation import (
    EconomicAssumptions,
    ModernizationPlan,
    OperatingCostAssumptions,
    PropertyDescription,
    RentAssumptions,
    ValuationAssumptions,
)

RESIDENTIAL_AREA = 6_572  # m², the area to be modernized


def tr76_valuation_assumptions() -> ValuationAssumptions:
    """The Wiborg base-case valuation inputs (reconstructed)."""
    return ValuationAssumptions(
        property_desc=PropertyDescription(
            total_building_area=RESIDENTIAL_AREA,
            residential_area=RESIDENTIAL_AREA,
        ),
        rent=RentAssumptions(
            base_rent_per_sqm=832,          # placeholder, see module doc
            modernized_rent_per_sqm=1_682,  # base + 850 DKK/m² uplift
            total_base_residential_rent=5_464_327,
            total_commercial_rent=532_400,
        ),
        modernization=ModernizationPlan(
            total_area_sqm=RESIDENTIAL_AREA,
            cost_per_sqm=5_220,
            duration_years=15,
        ),
        operating=OperatingCostAssumptions(total_operating_cost=3_628_333),
        economic=EconomicAssumptions(
            inflation_rate=0.02,
            required_real_return=0.0325,
            evaluation_period=15,
        ),
    )


def tr76_loans() -> list[Loan]:
    """Loans 15, 16 and 17 (outstanding balance and remaining term)."""
    return [
        Loan("Loan 15", principal=5_493_000, interest_rate=0.0100,
             contribution_rate=0.003889, term_years=24.25,
             interest_only_years=24.25, bond_price=80.938),
        Loan("Loan 16", principal=12_274_139.55, interest_rate=0.015,
             term_years=24, bond_price=77.43),
        Loan("Loan 17", principal=8_795_398.91, interest_rate=0.02116,
             term_years=24.5, bond_price=80.80),
    ]


def build_tr76() -> HousingCooperative:
    """A/B TR 1976 with loans, valuation and balance-sheet items."""
    return HousingCooperative(
        name="A/B TR 1976",
        units=[
            CooperativeUnit("Andele i alt (pladsholder)",
                            area=RESIDENTIAL_AREA, rooms=0),
        ],
        loans=tr76_loans(),
        valuation_assumptions=tr76_valuation_assumptions(),
        other_assets=2_500_000,
        other_liabilities=500_000,
    )
