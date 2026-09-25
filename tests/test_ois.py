"""Tests for pyabf.ois (offline, using a fake OIS client)."""

import pytest
from pyabf import (
    HousingCooperative,
    CooperativeUnit,
    CommercialUnit,
    OISClient,
    OISError,
    fetch_units,
    fetch_floors,
)


def enhed(id, address, usage="140", area=95, rooms=4, baths=1, status="6"):
    return {
        "Id": id,
        "adressebetegnelse": address,
        "etagebetegnelse": "1",
        "dørbetegnelse": "",
        "enh020EnhedensAnvendelse": usage,
        "enh026EnhedensSamledeAreal": area,
        "enh027ArealTilBeboelse": area if usage.startswith("1") else None,
        "enh028ArealTilErhverv": 0 if usage.startswith("1") else area,
        "enh031AntalVærelser": rooms,
        "enh066AntalBadeværelser": baths,
        "Status": status,
    }


def etage(id, opgang, type, name, area, basement=0, status="6"):
    return {
        "ETAGE_id_lokalId": id,
        "BYG_id_lokalId": "byg1",
        "ParentId": opgang,
        "eta025Etagetype": type,
        "eta006BygningensEtagebetegnelse": name,
        "eta020SamletArealAfEtage": area,
        "eta021ArealAfUdnyttetDelAfTagetage": 0,
        "eta022Kælderareal": basement,
        "eta023ArealAfLovligBeboelseIKælder": 0,
        "eta026ErhvervIKælder": 0,
        "Status": status,
    }


BUILDING = {
    "Id": "byg1",
    "byg007Bygningsnummer": 1,
    "Adgangsadresse": {"Vejnavn": "Vej", "Husnummertekst": "1"},
}

PROPERTIES = {
    100: {"bygning": [BUILDING], "etage": [
        # Floors are listed once per staircase (opgang)
        etage("kl", "opg1", "2", "kl", 245, basement=245),
        etage("kl", "opg2", "2", "kl", 245, basement=245),
        etage("st", "opg1", "0", "st", 245),
        etage("tag", "opg1", "1", "5", 245),
        etage("gone", "opg1", "1", "6", 100, status="10"),
    ], "enhed": [
        enhed("a", "Vej 1, 1., 2200 København N", area=95, rooms=4),
        enhed("b", "Vej 1, kl., 2200 København N", usage="322", area=40,
              rooms=2, baths=None),
        enhed("old", "Vej 1, 2., 2200 København N", status="10"),
    ]},
    # Overlaps with 100 (e.g. an ejerlejlighed under the same SFE)
    200: {"enhed": [
        enhed("a", "Vej 1, 1., 2200 København N"),
        enhed("c", "Vej 3, st., 2200 København N", area=60, rooms=2),
    ]},
}


class FakeClient(OISClient):
    def __init__(self):
        super().__init__()
        self.calls = []

    def get_property(self, bfe):
        self.calls.append(bfe)
        if bfe not in PROPERTIES:
            raise OISError(f"unknown BFE {bfe}")
        return PROPERTIES[bfe]


class TestFetchUnits:
    def test_maps_fields_and_skips_inactive(self):
        units = fetch_units([100], client=FakeClient())
        assert [u.bbr_id for u in units] == ["a", "b"]  # sorted by address
        flat, shop = units
        assert flat.area == 95 and flat.rooms == 4 and flat.bathrooms == 1
        assert flat.is_residential
        assert not shop.is_residential and shop.bathrooms == 0

    def test_include_inactive(self):
        units = fetch_units([100], client=FakeClient(), include_inactive=True)
        assert "old" in {u.bbr_id for u in units}

    def test_deduplicates_across_bfes(self):
        units = fetch_units([100, 200], client=FakeClient())
        assert sorted(u.bbr_id for u in units) == ["a", "b", "c"]

    def test_unknown_bfe(self):
        with pytest.raises(OISError):
            fetch_units([999], client=FakeClient())


class TestFetchFloors:
    def test_floors_deduplicated_and_classified(self):
        floors = fetch_floors([100], client=FakeClient())
        assert {f.bbr_id: f.kind for f in floors} == {
            "kl": "basement", "st": "floor", "tag": "roof"
        }
        basement = next(f for f in floors if f.kind == "basement")
        assert basement.basement_area == 245
        assert basement.address == "Vej 1" and basement.building_number == 1

    def test_include_inactive(self):
        floors = fetch_floors([100], client=FakeClient(), include_inactive=True)
        assert "gone" in {f.bbr_id for f in floors}

    def test_property_without_floors(self):
        assert fetch_floors([200], client=FakeClient()) == []


class TestOISClient:
    def test_property_is_cached(self, monkeypatch):
        client = OISClient()
        calls = []
        monkeypatch.setattr(
            client, "_get_json", lambda path, params: calls.append(params) or {}
        )
        client.get_property(100)
        client.get_property(100)
        assert len(calls) == 1

    def test_retries_on_rate_limit(self, monkeypatch):
        import io, urllib.error, urllib.request
        responses = [
            urllib.error.HTTPError("u", 429, "rate limited", {}, None),
            io.BytesIO(b'{"enhed": []}'),
        ]

        def fake_urlopen(request, timeout):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr("pyabf.ois.time.sleep", lambda s: None)
        assert OISClient().get_property(100) == {"enhed": []}


class TestCooperativeFromOIS:
    def test_from_ois(self):
        coop = HousingCooperative.from_ois(
            "Test", [100], client=FakeClient(), owned_rate_per_sqm=600
        )
        assert coop.bfe_numbers == [100]
        assert len(coop.units) == 2
        flat = next(u for u in coop.units if u.bbr_id == "a")
        assert isinstance(flat, CooperativeUnit)
        assert flat.bfe == 100
        assert isinstance(coop.commercial_units[0], CommercialUnit)
        assert coop.total_area == 135
        assert flat.annual_charge == 95 * 600

    def test_add_units_is_idempotent(self):
        coop = HousingCooperative("Test")
        client = FakeClient()
        assert len(coop.add_units_from_ois([100], client=client)) == 2
        added = coop.add_units_from_ois([100, 200], client=client)
        assert [u.bbr_id for u in added] == ["c"]
        assert coop.bfe_numbers == [100, 200]
        assert len(coop.units) == 3

    def test_uses_stored_bfe_numbers(self):
        coop = HousingCooperative("Test", bfe_numbers=[200])
        coop.add_units_from_ois(client=FakeClient())
        assert {u.bbr_id for u in coop.units} == {"a", "c"}
