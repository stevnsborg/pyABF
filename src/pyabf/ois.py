"""
ois.py — Fetch unit data for a property from OIS.dk by BFE number.

OIS (Den Offentlige Informationsserver, https://www.ois.dk) exposes BBR
data for every Danish property.  Given a BFE number (the unique id of a
fast ejendom) this module fetches the property's BBR units (enheder) and
converts them into pyABF :class:`~pyabf.units.Unit` objects.

The endpoint used is the JSON API behind the OIS.dk web front end
(``/api/property/GetPropertyFromBFE``).  It is not an officially
documented API, so its shape may change without notice.  No login is
required.

Mapping from BBR to pyABF:
    address   ← ``adressebetegnelse``
    area      ← ``enh026EnhedensSamledeAreal`` (total unit area, m²)
    rooms     ← ``enh031AntalVærelser``
    bathrooms ← ``enh066AntalBadeværelser``
    type      ← ``enh020EnhedensAnvendelse``: codes 1xx (housing) become
                :class:`CooperativeUnit`, everything else
                :class:`CommercialUnit`.

BBR does not record whether a unit is let out by the cooperative, so all
units are created as owner-occupied (``is_rental=False``).  Adjust
``is_rental`` afterwards and call ``HousingCooperative.refresh_rates()``.

Example (requires network access)::

    >>> from pyabf import HousingCooperative
    >>> coop = HousingCooperative.from_ois("A/B Example", [6018310])  # doctest: +SKIP
    >>> len(coop.units)  # doctest: +SKIP
    17

Basements and roof floors (tagetager) are not units in BBR; fetch them
with :func:`fetch_floors` and filter on ``OISFloor.kind``.

Contains:
    OISUnit      — A BBR unit as fetched from OIS
    OISFloor     — A BBR floor (basement, roof floor, ...) as fetched from OIS
    OISClient    — Minimal HTTP client for the OIS API
    OISError     — Raised when a lookup fails
    fetch_units  — Fetch the units for one or more BFE numbers
    fetch_floors — Fetch the floors for one or more BFE numbers
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from .units import Unit, CooperativeUnit, CommercialUnit


DEFAULT_BASE_URL = "https://www.ois.dk"

# BBR lifecycle status codes for units that no longer exist
# (afsluttet, historisk, fejlregistreret, midlertidig afsluttet, henlagt).
INACTIVE_STATUSES = frozenset({"9", "10", "11", "12", "14"})


class OISError(RuntimeError):
    """Raised when a property cannot be fetched from OIS."""


def _to_int(value: Any, default: int = 0) -> int:
    """Convert a BBR value (int, numeric string, ``None`` or ``""``) to int."""
    if value is None or value == "":
        return default
    return int(value)


@dataclass
class OISUnit:
    """A BBR unit (enhed) as fetched from OIS.

    Attributes:
        bfe: The BFE number the unit was fetched under.
        bbr_id: The unit's BBR id (unique and stable).
        address: Full address, e.g. ``"Blågårdsgade 10, 3., 2200 København N"``.
        floor: Floor designation (``"st"``, ``"1"``, ``"kl"``, ...).
        door: Door designation (``"th"``, ``"tv"``, ``""``, ...).
        area: Total unit area in m².
        residential_area: Area used for housing in m².
        commercial_area: Area used for business in m².
        rooms: Number of rooms.
        bathrooms: Number of bathrooms.
        usage_code: BBR usage code (enhedens anvendelse), e.g. ``"140"``.
        status: BBR lifecycle status code.
        raw: The full unit record as returned by OIS.
    """

    bfe: int
    bbr_id: str
    address: str
    floor: str
    door: str
    area: float
    residential_area: float
    commercial_area: float
    rooms: int
    bathrooms: int
    usage_code: str
    status: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_residential(self) -> bool:
        """True if the BBR usage code is a housing code (1xx)."""
        return self.usage_code.startswith("1")

    @property
    def is_active(self) -> bool:
        """False if BBR marks the unit as closed, historic or erroneous."""
        return self.status not in INACTIVE_STATUSES

    @classmethod
    def from_record(cls, bfe: int, record: dict[str, Any]) -> OISUnit:
        """Build an OISUnit from one ``enhed`` record of the OIS response."""
        return cls(
            bfe=bfe,
            bbr_id=record["Id"],
            address=record.get("adressebetegnelse") or "",
            floor=record.get("etagebetegnelse") or "",
            door=record.get("dørbetegnelse") or "",
            area=float(record.get("enh026EnhedensSamledeAreal") or 0),
            residential_area=float(record.get("enh027ArealTilBeboelse") or 0),
            commercial_area=float(record.get("enh028ArealTilErhverv") or 0),
            rooms=_to_int(record.get("enh031AntalVærelser")),
            bathrooms=_to_int(record.get("enh066AntalBadeværelser")),
            usage_code=str(record.get("enh020EnhedensAnvendelse") or ""),
            status=str(record.get("Status") or ""),
            raw=record,
        )

    def to_unit(self) -> Unit:
        """Convert to a pyABF unit.

        Returns:
            A :class:`CooperativeUnit` for housing units, otherwise a
            :class:`CommercialUnit`.  The unit is owner-occupied and has
            ``bfe`` and ``bbr_id`` set.
        """
        unit_cls = CooperativeUnit if self.is_residential else CommercialUnit
        return unit_cls(
            address=self.address,
            area=self.area,
            rooms=self.rooms,
            bathrooms=self.bathrooms,
            bfe=self.bfe,
            bbr_id=self.bbr_id,
        )


FloorKind = Literal["basement", "roof", "floor"]

# BBR floor type codes (eta025Etagetype)
_FLOOR_KINDS: dict[str, FloorKind] = {"0": "floor", "1": "roof", "2": "basement"}


@dataclass
class OISFloor:
    """A BBR floor (etage) of a building, e.g. a basement or roof floor.

    Basements and roof floors (tagetager) are not units in BBR, so they
    are not covered by :class:`OISUnit`.

    Attributes:
        bfe: The BFE number the floor was fetched under.
        bbr_id: The floor's BBR id.
        building_id: BBR id of the building the floor belongs to.
        building_number: The building's number on the property.
        address: Street address of the building, e.g. ``"Tagensvej 64"``.
        floor: Floor designation (``"kl"``, ``"st"``, ``"5"``, ...).
        kind: ``"basement"``, ``"roof"`` or ``"floor"``.
        area: Total floor area in m².
        basement_area: Basement area in m² (0 for other floors).
        utilized_roof_area: Area of the roof floor in use, in m².
        basement_residential_area: Area approved for housing in the
            basement, in m².
        basement_commercial_area: Area used for business in the
            basement, in m².
        status: BBR lifecycle status code.
        raw: The full floor record as returned by OIS.
    """

    bfe: int
    bbr_id: str
    building_id: str
    building_number: int | None
    address: str
    floor: str
    kind: FloorKind
    area: float
    basement_area: float
    utilized_roof_area: float
    basement_residential_area: float
    basement_commercial_area: float
    status: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_active(self) -> bool:
        """False if BBR marks the floor as closed, historic or erroneous."""
        return self.status not in INACTIVE_STATUSES

    @classmethod
    def from_record(
        cls, bfe: int, record: dict[str, Any], building: dict[str, Any] | None
    ) -> OISFloor:
        """Build an OISFloor from one ``etage`` record and its ``bygning``."""
        building = building or {}
        access = building.get("Adgangsadresse") or {}
        address = " ".join(
            part for part in (access.get("Vejnavn"), access.get("Husnummertekst"))
            if part
        )
        return cls(
            bfe=bfe,
            bbr_id=record["ETAGE_id_lokalId"],
            building_id=record.get("BYG_id_lokalId") or "",
            building_number=building.get("byg007Bygningsnummer"),
            address=address,
            floor=record.get("eta006BygningensEtagebetegnelse") or "",
            kind=_FLOOR_KINDS.get(str(record.get("eta025Etagetype")), "floor"),
            area=float(record.get("eta020SamletArealAfEtage") or 0),
            basement_area=float(record.get("eta022Kælderareal") or 0),
            utilized_roof_area=float(
                record.get("eta021ArealAfUdnyttetDelAfTagetage") or 0
            ),
            basement_residential_area=float(
                record.get("eta023ArealAfLovligBeboelseIKælder") or 0
            ),
            basement_commercial_area=float(record.get("eta026ErhvervIKælder") or 0),
            status=str(record.get("Status") or ""),
            raw=record,
        )


class OISClient:
    """Minimal HTTP client for the OIS.dk property API.

    Property records are cached per BFE, so fetching both units and
    floors of a property costs a single request.  OIS rate-limits
    requests; on HTTP 429 the client waits and retries.

    Args:
        base_url: Root URL of the OIS site.
        timeout: Request timeout in seconds.
        user_agent: User-Agent header sent with each request.
        max_retries: How many times to retry after HTTP 429.
        retry_delay: Seconds to wait before the first retry (doubled on
            each further retry) when OIS sends no ``Retry-After`` header.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        user_agent: str = "pyABF",
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._cache: dict[int, dict[str, Any]] = {}

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < self.max_retries:
                    retry_after = exc.headers.get("Retry-After", "")
                    delay = (
                        float(retry_after) if retry_after.isdigit()
                        else self.retry_delay * 2**attempt
                    )
                    time.sleep(delay)
                    continue
                raise OISError(f"OIS request failed ({exc.code}): {url}") from exc
            except urllib.error.URLError as exc:
                raise OISError(f"Could not reach OIS: {exc.reason}") from exc

    def get_property(self, bfe: int) -> dict[str, Any]:
        """Fetch the raw property record (grund, bygning, enhed, ...) for a BFE.

        Args:
            bfe: The BFE number.

        Returns:
            The decoded JSON response.

        Raises:
            OISError: If the request fails or the BFE is unknown (OIS
                answers unknown BFE numbers with HTTP 500).
        """
        bfe = int(bfe)
        if bfe not in self._cache:
            self._cache[bfe] = self._get_json(
                "/api/property/GetPropertyFromBFE", {"bfe": bfe}
            )
        return self._cache[bfe]

    def get_units(self, bfe: int, include_inactive: bool = False) -> list[OISUnit]:
        """Fetch the BBR units registered on a BFE.

        Args:
            bfe: The BFE number.
            include_inactive: If True, also return units BBR marks as
                closed, historic or erroneous.

        Returns:
            List of OISUnit, sorted by address.
        """
        data = self.get_property(bfe)
        units = [OISUnit.from_record(int(bfe), r) for r in data.get("enhed") or []]
        if not include_inactive:
            units = [u for u in units if u.is_active]
        return sorted(units, key=lambda u: u.address)

    def get_floors(self, bfe: int, include_inactive: bool = False) -> list[OISFloor]:
        """Fetch the BBR floors (incl. basements and roof floors) on a BFE.

        OIS lists a floor once per staircase (opgang) that reaches it;
        each floor is returned only once.

        Args:
            bfe: The BFE number.
            include_inactive: If True, also return floors BBR marks as
                closed, historic or erroneous.

        Returns:
            List of OISFloor, sorted by building number and floor.
        """
        data = self.get_property(bfe)
        buildings = {b["Id"]: b for b in data.get("bygning") or []}
        floors: dict[str, OISFloor] = {}
        for record in data.get("etage") or []:
            floor = OISFloor.from_record(
                int(bfe), record, buildings.get(record.get("BYG_id_lokalId"))
            )
            floors.setdefault(floor.bbr_id, floor)
        result = list(floors.values())
        if not include_inactive:
            result = [f for f in result if f.is_active]
        return sorted(result, key=lambda f: (f.building_number or 0, f.floor))


def fetch_floors(
    bfe_numbers: Iterable[int],
    client: OISClient | None = None,
    include_inactive: bool = False,
) -> list[OISFloor]:
    """Fetch the BBR floors for one or more BFE numbers.

    Filter on :attr:`OISFloor.kind` to get e.g. only basements and roof
    floors.

    Args:
        bfe_numbers: BFE numbers to look up.
        client: Client to use; a default :class:`OISClient` if omitted.
        include_inactive: Forwarded to :meth:`OISClient.get_floors`.

    Returns:
        List of OISFloor in the order the BFE numbers were given.
    """
    client = client or OISClient()
    seen: set[str] = set()
    result: list[OISFloor] = []
    for bfe in bfe_numbers:
        for floor in client.get_floors(bfe, include_inactive=include_inactive):
            if floor.bbr_id not in seen:
                seen.add(floor.bbr_id)
                result.append(floor)
    return result


def fetch_units(
    bfe_numbers: Iterable[int],
    client: OISClient | None = None,
    include_inactive: bool = False,
) -> list[OISUnit]:
    """Fetch the BBR units for one or more BFE numbers.

    Units that appear under more than one BFE (e.g. a samlet fast ejendom
    and one of its ejerlejligheder) are returned only once.

    Args:
        bfe_numbers: BFE numbers to look up.
        client: Client to use; a default :class:`OISClient` if omitted.
        include_inactive: Forwarded to :meth:`OISClient.get_units`.

    Returns:
        List of OISUnit in the order the BFE numbers were given.
    """
    client = client or OISClient()
    seen: set[str] = set()
    result: list[OISUnit] = []
    for bfe in bfe_numbers:
        for unit in client.get_units(bfe, include_inactive=include_inactive):
            if unit.bbr_id not in seen:
                seen.add(unit.bbr_id)
                result.append(unit)
    return result
