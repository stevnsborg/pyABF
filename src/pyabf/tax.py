"""
tax.py — Property tax (grundskyld) computation for Danish housing cooperatives.

From 2024, new rules apply for land tax (grundskyld): the tax moves from
its old level towards a new target level (based on the new public
assessment) with a capped annual increase.

The model implemented here:

    tax(first_year)  = old_tax × (1 + first_year_increase_rate)
    target_tax       = new_property_value × tax_rate × (1 − target_discount)
    annual_increase  = target_tax × max_annual_increase_rate
    tax(year)        = min(target_tax,
                           tax(first_year) + annual_increase × (year − first_year))

i.e. the tax rises by at most ``annual_increase`` per year until it reaches
the target, after which it stays flat. If the first-year tax already
exceeds the target it is held at the first-year level.

The default rule parameters (2.8 %, 4.75 %, 20 % discount, first year 2024)
are exposed as keyword arguments so they can be adjusted if the rules or
your municipality's transition scheme differ.

Source: https://www.vurderingsportalen.dk/erhverv/andelsbolig/beskatning/eksempler-grundskyld

Contains:
    compute_property_tax — Compute property tax for a given year
"""

from __future__ import annotations

#: First year the new rules apply.
FIRST_TAX_YEAR = 2024
#: Increase applied to the old tax level in the first year (2.8 %).
FIRST_YEAR_INCREASE_RATE = 0.028
#: Maximum yearly increase as a fraction of the target tax (4.75 %).
MAX_ANNUAL_INCREASE_RATE = 0.0475
#: Discount on the new assessment in the transition scheme (20 %).
TARGET_DISCOUNT = 0.20


def compute_property_tax(
    new_property_value: float,
    old_property_value: float,
    tax_rate: float,
    tax_year: int,
    *,
    first_tax_year: int = FIRST_TAX_YEAR,
    first_year_increase_rate: float = FIRST_YEAR_INCREASE_RATE,
    max_annual_increase_rate: float = MAX_ANNUAL_INCREASE_RATE,
    target_discount: float = TARGET_DISCOUNT,
) -> tuple[float, float]:
    """Compute property tax (grundskyld) for a housing cooperative.

    Args:
        new_property_value: The new official land assessment (DKK).
        old_property_value: The old tax level the transition starts from
            (DKK). Note that this is used directly as the pre-reform
            annual *tax amount*: the first-year tax is
            ``old_property_value × (1 + first_year_increase_rate)``.
        tax_rate: The municipal land tax rate as a fraction
            (e.g. 0.026 for 26 ‰).
        tax_year: The year to compute tax for (>= ``first_tax_year``).
        first_tax_year: First year the new rules apply (default 2024).
        first_year_increase_rate: Increase in the first year (default 2.8 %).
        max_annual_increase_rate: Maximum yearly increase as a fraction of
            the target tax (default 4.75 %).
        target_discount: Discount applied to the new assessment when
            computing the target tax (default 20 %).

    Returns:
        Tuple of:
            tax: The computed property tax for the year (DKK)
            increase: The year's increase in tax (DKK)

    Raises:
        ValueError: If ``tax_year`` is before ``first_tax_year``.
    """
    if tax_year < first_tax_year:
        raise ValueError(f"This model only applies from {first_tax_year} onwards.")

    # First year: fixed increase on the old level
    first_increase = old_property_value * first_year_increase_rate
    first_tax = old_property_value + first_increase

    # Target tax after the transition
    target_tax = new_property_value * tax_rate * (1 - target_discount)
    annual_increase = target_tax * max_annual_increase_rate

    years_since_start = tax_year - first_tax_year
    if years_since_start == 0:
        return first_tax, first_increase

    def _tax_after(years: int) -> float:
        # Capped linear increase from first_tax, never exceeding the target.
        # If the first-year tax is already above target it is kept flat.
        return max(first_tax, min(target_tax, first_tax + annual_increase * years))

    tax = _tax_after(years_since_start)
    return tax, tax - _tax_after(years_since_start - 1)
