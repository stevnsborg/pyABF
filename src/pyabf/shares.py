"""
shares.py — From property value to share price (andelsværdiberegning).

The share price is the cooperative's equity divided by the area of the
owner-occupied residential units (the andele):

    Assets       = Property value + Liquid assets + Other assets
    Liabilities  = Mortgage debt + Other liabilities
    Equity       = Assets − Liabilities
    Share price  = Equity / Owner-occupied residential area   (DKK/m²)
    Share value  = Share price × unit area                     (DKK)

The mortgage debt is taken either at market value (kursværdi, principal ×
bond price) or at principal (nominal value); see
:attr:`pyabf.cooperative.HousingCooperative.debt_basis`.

Contains:
    DebtBasis        — "market" or "principal"
    ShareCalculation — The balance and resulting share price
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

DebtBasis = Literal["market", "principal"]
DEBT_BASES: tuple[DebtBasis, ...] = ("market", "principal")


@dataclass(frozen=True)
class ShareCalculation:
    """The balance behind a share price (andelsværdiberegning).

    All amounts in DKK.

    Attributes:
        property_value: Value of the property (e.g. the valuarvurdering).
        liquid_assets: Cash and bank holdings (likvide beholdninger).
        other_assets: Other assets (receivables, prepayments, ...).
        mortgage_debt: The loans, valued per ``debt_basis``.
        other_liabilities: Other debt (creditors, deposits, ...).
        owned_residential_area: Area of the owner-occupied residential
            units (m²), the denominator of the share price.
        debt_basis: How ``mortgage_debt`` was valued.
    """

    property_value: float
    liquid_assets: float
    other_assets: float
    mortgage_debt: float
    other_liabilities: float
    owned_residential_area: float
    debt_basis: DebtBasis = "market"

    @property
    def total_assets(self) -> float:
        """Property value + liquid assets + other assets."""
        return self.property_value + self.liquid_assets + self.other_assets

    @property
    def total_liabilities(self) -> float:
        """Mortgage debt + other liabilities."""
        return self.mortgage_debt + self.other_liabilities

    @property
    def equity(self) -> float:
        """Total assets − total liabilities (egenkapital)."""
        return self.total_assets - self.total_liabilities

    @property
    def price_per_sqm(self) -> float:
        """Share price in DKK/m²; 0.0 when there is no owned area."""
        if self.owned_residential_area == 0:
            return 0.0
        return self.equity / self.owned_residential_area

    def share_value(self, area: float) -> float:
        """Share value of a unit of ``area`` m² (DKK)."""
        return self.price_per_sqm * area

    def to_series(self) -> pd.Series:
        """The calculation as a labelled Series, top to bottom."""
        return pd.Series({
            "Property value": self.property_value,
            "Liquid assets": self.liquid_assets,
            "Other assets": self.other_assets,
            "Total assets": self.total_assets,
            f"Mortgage debt ({self.debt_basis})": self.mortgage_debt,
            "Other liabilities": self.other_liabilities,
            "Total liabilities": self.total_liabilities,
            "Equity": self.equity,
            "Owned residential area (m²)": self.owned_residential_area,
            "Share price (DKK/m²)": self.price_per_sqm,
        })
