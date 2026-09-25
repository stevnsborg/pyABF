"""
_legacy.py — Deprecated monolithic DCF valuation function.

Kept only for backward compatibility.  New code should use
:class:`pyabf.valuation.DCFModel` with :class:`ValuationAssumptions`,
which is documented, configurable and tested.

Contains:
    compute_net_present_value — Deprecated DCF valuation function
"""

from __future__ import annotations

import warnings

import numpy as np
from numpy.typing import NDArray


def compute_net_present_value(
    average_rent: float,
    modernized_rent: float,
    modernization_cost: float,
    operating_cost: float,
    modernization_area: float,
    commercial_rent: float = 0.0,
    deduction: float = 0.0,
    evaluation_period: int = 15,
    inflation_rate: float = 0.02,
    required_return: float = 0.035,
    extra_allowance: float = 0.0,
) -> tuple[float, float, NDArray]:
    """Compute the property's net present value using a DCF model.

    .. deprecated::
        Use :class:`pyabf.valuation.DCFModel` instead.

    The model calculates the present value of expected cash flows
    over the evaluation period, plus a terminal value (exit value)
    for the remaining economic life using the Gordon Growth model.

    Args:
        average_rent: Average annual rental income (DKK)
        modernized_rent: Rent increase per m² after modernization (DKK/m²)
        modernization_cost: Annual modernization cost (DKK)
        operating_cost: Annual operating expenses (DKK)
        modernization_area: Total area to be modernized (m²)
        commercial_rent: Annual commercial rental income (DKK)
        deduction: Annual deduction (DKK)
        evaluation_period: Number of years in the DCF model (default 15)
        inflation_rate: Annual inflation rate (default 0.02 = 2%)
        required_return: Real required return above inflation (default 0.035 = 3.5%)
        extra_allowance: Extra annual allowance during modernization (DKK)

    Returns:
        Tuple of:
            npv_cash_flow: NPV of the periodic cash flows
            npv_terminal: NPV of the terminal value
            balance: 8×(N+1) matrix with individual cash flow components
                Rows: [0] avg_rent, [1] mod_rent, [2] commercial,
                      [3] (reserved), [4] operating, [5] modernization,
                      [6] extra_allowance, [7] deduction
    """
    warnings.warn(
        "compute_net_present_value is deprecated; use pyabf.valuation.DCFModel.",
        DeprecationWarning,
        stacklevel=2,
    )
    discount_rate = inflation_rate + required_return
    n = evaluation_period

    # Time axis (year 1 to N+1; last year is used for terminal value)
    years = np.arange(1, n + 2, dtype=int)
    balance = np.zeros((8, n + 1))

    # Annual modernized area
    area_per_year = modernization_area / n

    for i in range(n + 1):
        inflation_adj = (1 + inflation_rate) ** i

        # Income
        balance[0, i] = average_rent * inflation_adj
        balance[1, i] = (
            modernized_rent * inflation_adj * area_per_year * i
            if i != modernization_area + 1 or i == 0
            else area_per_year * n
        )
        balance[2, i] = commercial_rent * inflation_adj

        # Expenses (negative)
        balance[4, i] = -operating_cost * inflation_adj
        balance[5, i] = (
            -modernization_cost * inflation_adj * area_per_year
            if area_per_year * (i + 1) <= modernization_area
            else 0
        )
        balance[6, i] = (
            -extra_allowance * inflation_adj
            if area_per_year * (i + 1) <= modernization_area
            else 0
        )
        balance[7, i] = -deduction * inflation_adj

    # Total cash flow
    cash_flow = balance.sum(axis=0)

    # NPV of periodic cash flows (excluding terminal year)
    npv_cash_flow = float(
        np.sum((cash_flow / ((1 + discount_rate) ** years))[:-1])
    )

    # Terminal value (Gordon Growth model on the last year's cash flow)
    npv_terminal = float(
        cash_flow[-1]
        / (discount_rate - inflation_rate)
        / ((1 + discount_rate) ** n)
    )

    return npv_cash_flow, npv_terminal, balance
