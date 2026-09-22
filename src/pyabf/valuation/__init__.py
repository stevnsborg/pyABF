"""
valuation — DCF property valuation for Danish housing cooperatives.

This subpackage replaces the monolithic ``compute_net_present_value()``
function with a modular, transparent model built from configurable
assumption dataclasses.

Modules:
    assumptions  — All configurable parameters (ValuationAssumptions)
    cash_flow    — Year-by-year income/expense projection
    dcf_model    — NPV engine with Gordon Growth terminal value
    sensitivity  — Two-dimensional what-if analysis grid
    report       — Human-readable report generation

Quick start:
    >>> from pyabf.valuation import ValuationAssumptions, DCFModel
    >>> model = DCFModel(ValuationAssumptions())  # Wiborg TR 1976 defaults
    >>> result = model.compute()
    >>> print(f"Property value: {result.total_value_rounded:,.0f} DKK")
"""

from .assumptions import (
    PropertyDescription,
    RentAssumptions,
    ModernizationPlan,
    OperatingCostAssumptions,
    CapitalReturnAssumptions,
    ImprovementAllowance,
    EconomicAssumptions,
    ValuationAssumptions,
    DEFAULT_IMPROVEMENT_ALLOWANCES,
)
from .cash_flow import AnnualCashFlow, CashFlowProjection
from .dcf_model import DCFModel, ValuationResult
from .sensitivity import SensitivityGrid, run_sensitivity
from .report import ValuationReport

# Backward compatibility: the original monolithic function is preserved
# in _legacy.py and re-exported here so that existing code using
#   from pyabf.valuation import compute_net_present_value
# continues to work.
from ._legacy import compute_net_present_value  # noqa: F401

__all__ = [
    # Assumptions
    "PropertyDescription",
    "RentAssumptions",
    "ModernizationPlan",
    "OperatingCostAssumptions",
    "CapitalReturnAssumptions",
    "ImprovementAllowance",
    "EconomicAssumptions",
    "ValuationAssumptions",
    "DEFAULT_IMPROVEMENT_ALLOWANCES",
    # Cash flow
    "AnnualCashFlow",
    "CashFlowProjection",
    # DCF model
    "DCFModel",
    "ValuationResult",
    # Sensitivity
    "SensitivityGrid",
    "run_sensitivity",
    # Report
    "ValuationReport",
]
