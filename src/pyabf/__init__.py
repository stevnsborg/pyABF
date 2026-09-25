"""
pyABF — Tools for computing and modeling the finances
of Danish housing cooperatives (andelsboligforeninger).

Everything is generic: property-specific data (units, loans, account
mappings, valuation assumptions) is supplied by the caller, so the same
package works for any andelsboligforening.

Modules:
    units       — Unit, CooperativeUnit, CommercialUnit, Improvement
    loan        — Loan (mortgage loans and payment schedules)
    accounting  — AccountEntry, AnnualReport
    valuation   — DCF property valuation (subpackage)
    tax         — Property tax (grundskyld) computation (2024+ rules)
    budget      — Budget tracking and balance-sheet import
    cooperative — HousingCooperative (the main class)
"""

from .units import Unit, CooperativeUnit, CommercialUnit, Improvement
from .loan import Loan
from .accounting import AccountEntry, AnnualReport, DEFAULT_NOTES
from .valuation import (
    PropertyDescription,
    RentAssumptions,
    ModernizationPlan,
    OperatingCostAssumptions,
    CapitalReturnAssumptions,
    ImprovementAllowance,
    EconomicAssumptions,
    ValuationAssumptions,
    DCFModel,
    ValuationResult,
    ValuationReport,
    CashFlowProjection,
    SensitivityGrid,
    run_sensitivity,
)
from .tax import compute_property_tax
from .cooperative import HousingCooperative
from .budget import (
    BudgetLineItem,
    BudgetCategory,
    Budget,
    BudgetTracker,
    AccountMapping,
    BalanceSheetRow,
    CategoryType,
    load_balance_sheet_csv,
    parse_danish_number,
)

__version__ = "0.1.0"

__all__ = [
    # Cooperative (the main entry point)
    "HousingCooperative",
    # Units
    "Unit",
    "CooperativeUnit",
    "CommercialUnit",
    "Improvement",
    # Loan
    "Loan",
    # Accounting
    "AccountEntry",
    "AnnualReport",
    "DEFAULT_NOTES",
    # Valuation
    "PropertyDescription",
    "RentAssumptions",
    "ModernizationPlan",
    "OperatingCostAssumptions",
    "CapitalReturnAssumptions",
    "ImprovementAllowance",
    "EconomicAssumptions",
    "ValuationAssumptions",
    "DCFModel",
    "ValuationResult",
    "ValuationReport",
    "CashFlowProjection",
    "SensitivityGrid",
    "run_sensitivity",
    # Tax
    "compute_property_tax",
    # Budget
    "BudgetLineItem",
    "BudgetCategory",
    "Budget",
    "BudgetTracker",
    "AccountMapping",
    "BalanceSheetRow",
    "CategoryType",
    "load_balance_sheet_csv",
    "parse_danish_number",
]
