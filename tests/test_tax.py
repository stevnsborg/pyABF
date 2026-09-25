"""Tests for pyabf.tax module."""

import pytest
from pyabf.tax import compute_property_tax

# first = 200_000 × 1.028 = 205_600; target = 20M × 0.026 × 0.8 = 416_000;
# cap = 416_000 × 0.0475 = 19_760 per year
ARGS = dict(new_property_value=20_000_000, old_property_value=200_000, tax_rate=0.026)


def test_first_year():
    tax, inc = compute_property_tax(**ARGS, tax_year=2024)
    assert tax == pytest.approx(205_600)
    assert inc == pytest.approx(5_600)


def test_capped_increase():
    tax, inc = compute_property_tax(**ARGS, tax_year=2026)
    assert tax == pytest.approx(205_600 + 2 * 19_760)
    assert inc == pytest.approx(19_760)


def test_increase_never_exceeds_cap_and_reaches_target():
    prev = None
    for year in range(2024, 2045):
        tax, inc = compute_property_tax(**ARGS, tax_year=year)
        if prev is not None:
            assert inc == pytest.approx(tax - prev)
            assert inc <= 19_760 + 1e-6
        prev = tax
    assert prev == pytest.approx(416_000)


def test_before_first_year_raises():
    with pytest.raises(ValueError):
        compute_property_tax(**ARGS, tax_year=2023)


def test_rule_overrides():
    tax, _ = compute_property_tax(
        **ARGS, tax_year=2025, first_tax_year=2025, first_year_increase_rate=0.0
    )
    assert tax == pytest.approx(200_000)
