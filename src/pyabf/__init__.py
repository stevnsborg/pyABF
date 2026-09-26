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
    shares      — ShareCalculation (property value → share price)
    cooperative — HousingCooperative (the main class)
    ois         — Load units from OIS.dk by BFE number
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
    ParameterDistribution,
    MonteCarloResult,
    run_monte_carlo,
)
from .tax import compute_property_tax
from .shares import ShareCalculation
from .cooperative import HousingCooperative
from .ois import OISClient, OISUnit, OISFloor, OISError, fetch_units, fetch_floors
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
    "ShareCalculation",
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
    "ParameterDistribution",
    "MonteCarloResult",
    "run_monte_carlo",
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
    # OIS
    "OISClient",
    "OISUnit",
    "OISFloor",
    "OISError",
    "fetch_units",
    "fetch_floors",
]
