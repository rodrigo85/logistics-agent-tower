"""Tests for the Google Maps traffic service and its endpoints.

Pure-function tests always run. Tests that hit the real Routes API are marked
`integration` and are skipped unless GOOGLE_MAPS_API_KEY is configured.
"""

import pytest
from fastapi.testclient import TestClient

from logistics_tower.api.main import app
from logistics_tower.config import settings
from logistics_tower.services.traffic_service import GoogleMapsTrafficService, decode_polyline, get_traffic_service

client = TestClient(app)

_HAS_KEY = bool(settings.google_maps_api_key and settings.google_maps_api_key.get_secret_value())
requires_google_maps = pytest.mark.skipif(not _HAS_KEY, reason="GOOGLE_MAPS_API_KEY not configured")


def test_decode_polyline():
    # Reference example from Google's Encoded Polyline Algorithm documentation
    poly = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    coords = decode_polyline(poly)
    assert len(coords) == 3
    assert coords[0] == [38.5, -120.2]
    assert coords[1] == [40.7, -120.95]


def test_traffic_service_reports_availability_consistently():
    svc = get_traffic_service()
    assert svc.is_available() is _HAS_KEY


def test_traffic_service_returns_none_without_key(monkeypatch):
    monkeypatch.setattr(settings, "google_maps_api_key", None)
    svc = GoogleMapsTrafficService()
    assert svc.is_available() is False
    assert svc.get_route_with_traffic(-26.94, -48.70, -26.91, -48.64) is None


def test_api_traffic_status():
    res = client.get("/api/traffic/status")
    assert res.status_code == 200
    data = res.json()
    assert data["provider"] == "google_maps_routes_v2"
    assert data["live_traffic_enabled"] is _HAS_KEY


def test_api_traffic_route_rejects_invalid_coordinates():
    res = client.get("/api/traffic/route?origin_lat=999&origin_lng=0&dest_lat=0&dest_lng=0")
    assert res.status_code == 422


@pytest.mark.integration
@requires_google_maps
def test_api_traffic_route_live():
    # CD Itajaí -> Supermercado Bistek (Fazenda)
    res = client.get("/api/traffic/route?origin_lat=-26.9418&origin_lng=-48.7094&dest_lat=-26.9185&dest_lng=-48.6492")
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "google_maps_routes_v2"
    assert data["distance_km"] > 0
    assert data["duration_minutes"] > 0
    assert len(data["coordinates"]) > 0
