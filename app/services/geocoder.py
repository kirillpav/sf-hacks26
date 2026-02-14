"""Geocode region names to bounding boxes using Nominatim (no API key)."""

from __future__ import annotations

from geopy.geocoders import Nominatim


_geocoder = Nominatim(user_agent="deforestation-alert-mvp", timeout=10)


def region_to_bbox(region_name: str) -> list[float] | None:
    """Convert a region name to a bounding box [west, south, east, north].

    Returns None if geocoding fails.
    """
    location = _geocoder.geocode(region_name, exactly_one=True, viewbox=None)
    if location is None:
        return None

    # Nominatim returns bounding box as [south, north, west, east]
    raw_bbox = location.raw.get("boundingbox", [])
    if len(raw_bbox) != 4:
        return None

    south, north, west, east = [float(x) for x in raw_bbox]
    return [west, south, east, north]
