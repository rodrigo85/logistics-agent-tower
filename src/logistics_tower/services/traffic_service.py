"""
Enterprise Traffic & Routes Service using Google Maps Platform.
Integrates real-time traffic queries via Google Routes API v2,
providing live congestion data, road distances, ETAs and polyline geometry.
"""

import logging
import time
from typing import Any

import httpx

from logistics_tower.config import settings

logger = logging.getLogger(__name__)


def decode_polyline(polyline_str: str) -> list[list[float]]:
    """Decodes Google's Encoded Polyline Algorithm Format into [[lat, lng], ...]."""
    index, lat, lng = 0, 0, 0
    coordinates: list[list[float]] = []
    length = len(polyline_str)

    while index < length:
        shift, result = 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift, result = 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coordinates.append([round(lat / 1e5, 6), round(lng / 1e5, 6)])

    return coordinates


class GoogleMapsTrafficService:
    """
    Client for Google Maps Routes API v2.
    Queries real-time traffic, travel duration with congestion, and route geometry.
    """

    def __init__(self, cache_ttl_seconds: int | None = None):
        self.cache_ttl = cache_ttl_seconds if cache_ttl_seconds is not None else settings.google_maps_cache_ttl_seconds
        self._cache: dict[tuple[float, float, float, float], tuple[float, dict[str, Any]]] = {}

    @property
    def api_key(self) -> str | None:
        if settings.google_maps_api_key:
            return settings.google_maps_api_key.get_secret_value()
        return None

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_route_with_traffic(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> dict[str, Any] | None:
        """
        Queries Google Routes API for real-time traffic, duration and geometry.
        Returns dict with distance_meters, duration_minutes, coordinates, and traffic_status.
        """
        api_key = self.api_key
        if not api_key:
            return None

        # Check cache (rounded to 4 decimals ~ 11 meters)
        cache_key = (
            round(origin_lat, 4),
            round(origin_lng, 4),
            round(dest_lat, 4),
            round(dest_lng, 4),
        )
        now = time.time()
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return data

        url = "https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": (
                "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,"
                "routes.description,routes.warnings"
            ),
        }
        payload = {
            "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
            "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
        }

        try:
            with httpx.Client(timeout=4.0) as client:
                response = client.post(url, json=payload, headers=headers)

            if response.status_code != 200:
                logger.warning(f"Google Routes API returned {response.status_code}: {response.text[:200]}")
                return None

            data = response.json()
            routes = data.get("routes", [])
            if not routes:
                return None

            route = routes[0]
            distance_meters = int(route.get("distanceMeters", 0))
            raw_duration = route.get("duration", "0s").rstrip("s")
            duration_seconds = int(raw_duration) if raw_duration.isdigit() else 0
            duration_minutes = max(1, round(duration_seconds / 60.0, 1))

            encoded_poly = route.get("polyline", {}).get("encodedPolyline", "")
            coordinates = decode_polyline(encoded_poly) if encoded_poly else []

            result = {
                "source": "google_maps_routes_v2",
                "distance_meters": distance_meters,
                "distance_km": round(distance_meters / 1000.0, 1),
                "duration_seconds": duration_seconds,
                "duration_minutes": duration_minutes,
                "coordinates": coordinates,
                "route_description": route.get("description", ""),
                "traffic_aware": True,
            }

            logger.info(
                f"[Google Maps API] Tráfego ao vivo consultado: "
                f"({origin_lat:.4f}, {origin_lng:.4f}) -> ({dest_lat:.4f}, {dest_lng:.4f}) | "
                f"{result['distance_km']} km em {result['duration_minutes']} min"
            )

            self._cache[cache_key] = (now, result)
            return result

        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning(f"Failed to fetch Google Maps traffic route: {e}")
            return None


_traffic_service_instance: GoogleMapsTrafficService | None = None


def get_traffic_service() -> GoogleMapsTrafficService:
    global _traffic_service_instance
    if _traffic_service_instance is None:
        _traffic_service_instance = GoogleMapsTrafficService()
    return _traffic_service_instance
