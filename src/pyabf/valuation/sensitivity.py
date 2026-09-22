"""
sensitivity.py — Sensitivity analysis for the DCF valuation model.

Generates a grid of property values varying two key parameters:

    1. **Required real return** (afkastkrav) — varies ±0.75% in steps of 0.25%
    2. **Rent level** (boliglejeniveau) — varies ±2% in steps of 1%

This mirrors the sensitivity table on page 29 of the Wiborg report
(7 rows × 5 columns).

The default grid dimensions and step sizes are configurable.

Contains:
    SensitivityGrid   — Computed grid of valuations
    run_sensitivity    — Convenience function to build the grid
"""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy

import numpy as np
import pandas as pd

from .assumptions import ValuationAssumptions
from .dcf_model import DCFModel


@dataclass(frozen=True)
class SensitivityGrid:
    """Result of a two-dimensional sensitivity analysis.

    Attributes:
        yield_offsets: Array of yield offsets (percentage points)
            relative to the base required real return.
            E.g. [-0.0075, -0.005, ..., 0.005, 0.0075].
        rent_offsets: Array of rent-level offsets (percentage change)
            relative to the base modernized rent level.
            E.g. [-0.02, -0.01, 0.0, 0.01, 0.02].
        values: 2D array of total property values (DKK).
            Shape: (len(yield_offsets), len(rent_offsets)).
        base_yield: The base required real return (before offsets).
        base_rent: The base modernized rent per m² (before offsets).
    """

    yield_offsets: np.ndarray
    rent_offsets: np.ndarray
    values: np.ndarray
    base_yield: float
    base_rent: float

    def to_dataframe(self) -> pd.DataFrame:
        """Convert the grid to a pandas DataFrame.

        Rows are labelled with the absolute yield (e.g. "2.50%", "2.75%").
        Columns are labelled with the absolute rent level (DKK/m²).

        The base-case cell is at the intersection of the un-offset
        yield and rent level.

        Returns:
            DataFrame with formatted labels and values rounded to
            the nearest integer.
        """
        row_labels = [
            f"{(self.base_yield + offset) * 100:.2f}%"
            for offset in self.yield_offsets
        ]
        col_labels = [
            f"{self.base_rent * (1 + offset):,.0f} DKK/m²"
            for offset in self.rent_offsets
        ]

        df = pd.DataFrame(
            np.round(self.values).astype(int),
            index=row_labels,
            columns=col_labels,
        )
        df.index.name = "Required real return"
        df.columns.name = "Modernized rent (DKK/m²)"
        return df


def run_sensitivity(
    assumptions: ValuationAssumptions,
    yield_steps: int = 3,
    yield_step_size: float = 0.0025,
    rent_steps: int = 2,
    rent_step_size: float = 0.01,
) -> SensitivityGrid:
    """Run a two-dimensional sensitivity analysis.

    Varies the required real return and the modernized rent level
    symmetrically around the base case, computes a DCF valuation for
    each combination, and returns the grid.

    Args:
        assumptions: Base-case assumptions.
        yield_steps: Number of steps above and below the base yield.
            Default 3 → offsets -0.75%, -0.50%, -0.25%, 0, +0.25%,
            +0.50%, +0.75% (7 rows).
        yield_step_size: Size of each yield step (percentage points).
            Default 0.0025 = 0.25%.
        rent_steps: Number of steps above and below the base rent.
            Default 2 → offsets -2%, -1%, 0, +1%, +2% (5 columns).
        rent_step_size: Size of each rent step (percentage change).
            Default 0.01 = 1%.

    Returns:
        A ``SensitivityGrid`` with the computed values.
    """
    base_yield = assumptions.economic.required_real_return
    base_rent = assumptions.rent.modernized_rent_per_sqm
    base_residential = assumptions.rent.total_base_residential_rent

    # Build offset arrays
    yield_offsets = np.arange(
        -yield_steps * yield_step_size,
        (yield_steps + 1) * yield_step_size,
        yield_step_size,
    )
    rent_offsets = np.arange(
        -rent_steps * rent_step_size,
        (rent_steps + 1) * rent_step_size,
        rent_step_size,
    )

    # Round to avoid floating-point drift
    yield_offsets = np.round(yield_offsets, 6)
    rent_offsets = np.round(rent_offsets, 6)

    values = np.zeros((len(yield_offsets), len(rent_offsets)))

    for i, y_offset in enumerate(yield_offsets):
        for j, r_offset in enumerate(rent_offsets):
            # Deep-copy to avoid mutating the original
            a = deepcopy(assumptions)

            # Adjust required real return
            a.economic.required_real_return = base_yield + y_offset

            # Adjust rent level: both the per-m² rate and the base total
            # (the base total is also scaled so the un-modernized rent
            # tracks the same percentage change)
            a.rent.modernized_rent_per_sqm = base_rent * (1 + r_offset)
            a.rent.total_base_residential_rent = base_residential * (1 + r_offset)

            model = DCFModel(a)
            result = model.compute()
            values[i, j] = result.total_value

    return SensitivityGrid(
        yield_offsets=yield_offsets,
        rent_offsets=rent_offsets,
        values=values,
        base_yield=base_yield,
        base_rent=base_rent,
    )
