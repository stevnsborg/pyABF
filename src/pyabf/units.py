"""
units.py — Classes for the physical units in a housing cooperative.

Contains:
    Unit            — Base class for a residential or commercial unit
    CooperativeUnit — A cooperative housing unit (andel)
    CommercialUnit  — A commercial lease unit
    Improvement     — An individual improvement made to a unit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Unit:
    """Base class for a physical unit (residential or commercial).

    The annual charge for each unit is computed from a per-m² rate
    set at the cooperative level and scaled by the unit's area.
    Rental units can override this with a fixed rent.

    A unit on its own has a rate of 0; the rate is assigned when the unit
    is added to a :class:`~pyabf.cooperative.HousingCooperative` (or when
    the cooperative's rates change).

    Attributes:
        address: Street address of the unit
        area: Floor area in m²
        rooms: Number of rooms
        bathrooms: Number of bathrooms
        is_rental: True if the unit is rented out, False if owner-occupied
        fixed_rent: Fixed annual rent for rental units (DKK). If set (> 0)
            this overrides the rate-based calculation for rental units.
        rate_per_sqm: Annual rate (DKK/m²/year) assigned by the owning
            cooperative. Read-only; not an ``__init__`` argument.
    """

    address: str
    area: float          # m²
    rooms: int
    bathrooms: int = 1
    is_rental: bool = False
    fixed_rent: float = 0.0
    _rate_per_sqm: float = field(default=0.0, init=False, repr=False)

    @property
    def rate_per_sqm(self) -> float:
        """Annual rate per m² (DKK/m²/year) assigned by the cooperative."""
        return self._rate_per_sqm

    @property
    def annual_charge(self) -> float:
        """The annual charge for this unit (DKK).

        For rental units with a fixed_rent > 0, returns the fixed rent.
        Otherwise, computed as rate_per_sqm × area, where the rate
        is propagated from the cooperative.
        """
        if self.is_rental and self.fixed_rent > 0:
            return self.fixed_rent
        return self._rate_per_sqm * self.area


@dataclass
class CooperativeUnit(Unit):
    """A cooperative housing unit (andelsbolig).

    Attributes:
        improvements: List of improvements made to this unit
            (forbedringer), which are added on top of the share value when
            computing the maximum sale price.
        share_value: The computed value of the cooperative share (DKK),
            i.e. ``price_per_sqm × area``. ``None`` until computed.
        price_per_sqm: Share price per m² used to compute ``share_value``.
    """

    improvements: list["Improvement"] = field(default_factory=list)
    share_value: float | None = None
    price_per_sqm: float | None = None

    def compute_share_value(self, new_price_per_sqm: float) -> float:
        """Compute the share value from a new price per square meter.

        Args:
            new_price_per_sqm: Price per m² (DKK/m²)

        Returns:
            The updated share value in DKK.
        """
        self.price_per_sqm = new_price_per_sqm
        self.share_value = new_price_per_sqm * self.area
        return self.share_value

    def improvements_value(self, current_year: int) -> float:
        """Total remaining (depreciated) value of all improvements.

        Args:
            current_year: The year to evaluate the improvements at.

        Returns:
            Sum of :meth:`Improvement.remaining_value` in DKK.
        """
        return sum(imp.remaining_value(current_year) for imp in self.improvements)

    def max_sale_price(self, current_year: int) -> float:
        """Maximum sale price: share value plus remaining improvement value.

        Args:
            current_year: The year to evaluate the improvements at.

        Returns:
            Maximum sale price in DKK.

        Raises:
            ValueError: If the share value has not been computed yet.
        """
        if self.share_value is None:
            raise ValueError(
                "share_value is not set; call compute_share_value() first."
            )
        return self.share_value + self.improvements_value(current_year)


@dataclass
class CommercialUnit(Unit):
    """A commercial/business unit in the cooperative.

    Can be either rented out (is_rental=True) or owned/operated
    by the cooperative (is_rental=False).
    """

    pass


DepreciationModel = Literal["linear", "none"]


@dataclass
class Improvement:
    """An individual improvement made to a cooperative unit.

    The remaining value depends on the depreciation model:
      - "linear": value decreases linearly over the lifespan,
        reaching zero at (year + lifespan). Computed as:
            remaining = cost × max(0, 1 - age / lifespan)
      - "none": no depreciation; value stays equal to cost.

    Attributes:
        id: Unique identifier for the improvement
        year: The year the improvement was made
        cost: The original cost of the improvement (DKK)
        depreciation: Depreciation model ("linear" or "none")
        lifespan: Depreciation period in years (default 10). Must be
            positive when ``depreciation="linear"``.
    """

    id: str
    year: int
    cost: float
    depreciation: DepreciationModel = "linear"
    lifespan: int = 10

    def remaining_value(self, current_year: int) -> float:
        """Compute the remaining value of the improvement at a given year.

        Args:
            current_year: The year to evaluate the value at

        Returns:
            Remaining value in DKK (never negative). Improvements dated in
            the future are returned at full cost.

        Raises:
            ValueError: If the depreciation model is unknown or the
                lifespan is not positive for linear depreciation.
        """
        if self.depreciation == "none":
            return self.cost

        if self.depreciation != "linear":
            raise ValueError(f"Unknown depreciation model: {self.depreciation!r}")
        if self.lifespan <= 0:
            raise ValueError("lifespan must be positive for linear depreciation.")

        age = current_year - self.year
        if age < 0:
            return self.cost
        fraction_remaining = max(0.0, 1.0 - age / self.lifespan)
        return self.cost * fraction_remaining
