"""
tax.py — Property tax computation for Danish housing cooperatives.

From 2024, new rules apply for land tax (grundskyld): the annual
increase is capped at 4.75% of the new assessment (2.8% in the first year).

Source: https://www.vurderingsportalen.dk/erhverv/andelsbolig/beskatning/eksempler-grundskyld

Contains:
    compute_property_tax — Compute property tax for a given year
"""

from __future__ import annotations

import math


def compute_property_tax(
    new_property_value: float,
    old_property_value: float,
    tax_rate: float,
    tax_year: int,
) -> tuple[float, float]:
    """Compute property tax for a housing cooperative (2024 onwards).

    The new rules (from 2024) cap the annual increase in land tax:
      - 2024: Increase of 2.8% of the old property value
      - 2025+: Max 4.75% increase per year until the new tax level is reached

    Args:
        new_property_value: The new official property assessment (DKK)
        old_property_value: The old property assessment (DKK)
        tax_rate: The land tax rate (e.g. 0.026)
        tax_year: The year to compute tax for (>= 2024)

    Returns:
        Tuple of:
            tax: The computed property tax for the year (DKK)
            increase: The year's increase in tax (DKK)

    Raises:
        ValueError: If tax_year < 2024
    """
    if tax_year < 2024:
        raise ValueError("This model only applies from 2024 onwards.")

    # First year increase (2.8% of old value)
    increase_2024 = old_property_value * 0.028
    tax_2024 = old_property_value + increase_2024

    # Target tax (80% discount in the transition scheme)
    target_tax = new_property_value * tax_rate * 0.8

    # Number of years to reach target tax
    if target_tax * 0.0475 > 0:
        terminal_year = int(math.floor(
            (target_tax - tax_2024) / (target_tax * 0.0475)
        ))
    else:
        terminal_year = 0

    if tax_year == 2024:
        return tax_2024, increase_2024

    elif tax_year < 2024 + terminal_year:
        annual_increase = target_tax * 0.0475
        tax = tax_2024 + annual_increase * (tax_year - 2024)
        return tax, annual_increase

    elif tax_year == 2024 + terminal_year:
        remaining_increase = target_tax - target_tax * 0.0475 * terminal_year
        return target_tax, remaining_increase

    else:
        # Target tax reached — no further increase
        return target_tax, 0.0
