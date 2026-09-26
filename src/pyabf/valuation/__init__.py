"""
valuation — DCF property valuation for Danish housing cooperatives.

A modular, transparent DCF model built from configurable assumption
dataclasses.  All assumptions default to zero/empty, so every valuation
is driven entirely by the property-specific values you pass in.

Modules:
    assumptions  — All configurable parameters (ValuationAssumptions)
    cash_flow    — Year-by-year income/expense projection
    dcf_model    — NPV engine with Gordon Growth terminal value
    sensitivity  — Two-dimensional what-if analysis grid
    report       — Human-readable report generation
    monte_carlo  — Monte Carlo simulation of the valuation

Quick start:
    >>> from pyabf.valuation import (
    ...     ValuationAssumptions, PropertyDescription, RentAssumptions,
    ...     OperatingCostAssumptions, DCFModel,
    ... )
    >>> assumptions = ValuationAssumptions(
    ...     property_desc=PropertyDescription(
    ...         total_building_area=5_000, residential_area=4_500),
    ...     rent=RentAssumptions(total_base_residential_rent=3_600_000),
    ...     operating=OperatingCostAssumptions(total_operating_cost=1_200_000),
    ... )
    >>> result = DCFModel(assumptions).compute()
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
from .monte_carlo import (
    ParameterDistribution,
    MonteCarloResult,
    run_monte_carlo,
    DEFAULT_PARAMETERS,
    DEFAULT_N_SAMPLES,
    DEFAULT_REL_STD,
    DEFAULT_RATE_ABS_STD,
)

# Deprecated: the original monolithic function is kept in _legacy.py so
# that ``from pyabf.valuation import compute_net_present_value`` keeps
# working.  It emits a DeprecationWarning; use DCFModel instead.
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
    # Monte Carlo
    "ParameterDistribution",
    "MonteCarloResult",
    "run_monte_carlo",
    "DEFAULT_PARAMETERS",
    "DEFAULT_N_SAMPLES",
    "DEFAULT_REL_STD",
    "DEFAULT_RATE_ABS_STD",
]
