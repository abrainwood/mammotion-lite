"""Device tracker coordinate extraction for Mammotion Lite."""

from __future__ import annotations

import json
import logging
import math

from .runtime_data import MammotionLiteData

_LOGGER = logging.getLogger(__name__)

# Coordinates where both abs(lat) and abs(lon) are below this threshold
# (in radians) are treated as uninitialised GPS. 0.01 rad ~ 0.57 deg ~ 63km.
NEAR_ZERO_THRESHOLD_RAD = 0.01

# Snapshot coordinates below this threshold in degrees are likely uninitialised
# or raw radian values not yet converted by CoordinateConverter.
# Valid lat must be > ~1 degree from equator for any real mower location.
MIN_PLAUSIBLE_DEGREES = 1.0


def _coords_from_snapshot(data: MammotionLiteData) -> tuple[float, float] | None:
    """Extract coordinates from snapshot (RPT report data).

    Only valid when pymammotion's CoordinateConverter has run with a proper
    RTK base station reference. Before that, values may be raw ENU or radian
    values that look like tiny degree values (e.g. -0.586 instead of -33.58).

    We check position_type > 0 (meaning GPS/RTK fix) and that the coordinates
    are plausible degree values (not radian-scale garbage).
    """
    if not data.snapshot:
        return None
    try:
        raw = data.snapshot.raw
        lat = raw.location.device.latitude
        _LOGGER.debug(
            "Snapshot coords: lat=%s, lon=%s, position_type=%s",
            lat, raw.location.device.longitude, raw.location.position_type,
        )
        lon = raw.location.device.longitude

        # position_type 0 = uninitialised, no GPS fix
        if raw.location.position_type == 0:
            return None

        # Either coordinate near zero = likely uninitialised or unconverted radians
        if abs(lat) < MIN_PLAUSIBLE_DEGREES or abs(lon) < MIN_PLAUSIBLE_DEGREES:
            return None

        # Sanity: valid WGS84 degrees have lat in [-90, 90], lon in [-180, 180]
        # Values like -0.586 (radian for Sydney lat) would fail the MIN_PLAUSIBLE check above
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None

        return (lat, lon)
    except AttributeError:
        return None


def extract_coordinates(data: MammotionLiteData) -> tuple[float, float] | None:
    """Extract GPS coordinates from snapshot (preferred) or properties push (fallback).

    Snapshot coordinates come from RPT reports via pymammotion's coordinate
    converter - already in WGS84 degrees. Properties coordinates are from
    30-min passive pushes in radians, requiring conversion.

    Returns (lat_degrees, lon_degrees) tuple or None.
    """
    # Preferred: snapshot from RPT reports (degrees, updated every 60s during mowing)
    result = _coords_from_snapshot(data)
    if result:
        return result

    # Fallback: properties push (radians, 30-min passive push)
    if not data.properties or not data.properties.params.items.coordinate:
        return None

    try:
        coord_value = data.properties.params.items.coordinate.value
        if isinstance(coord_value, str):
            coord = json.loads(coord_value)
        elif isinstance(coord_value, dict):
            coord = coord_value
        else:
            return None

        lat_rad = coord.get("lat")
        lon_rad = coord.get("lon")

        if lat_rad is None or lon_rad is None:
            return None

        # Filter out uninitialised GPS (both lat and lon near zero radians)
        if abs(lat_rad) < NEAR_ZERO_THRESHOLD_RAD and abs(lon_rad) < NEAR_ZERO_THRESHOLD_RAD:
            return None

        # Convert from radians to degrees
        lat_deg = lat_rad * 180.0 / math.pi
        lon_deg = lon_rad * 180.0 / math.pi

        return (lat_deg, lon_deg)

    except (json.JSONDecodeError, ValueError, TypeError):
        _LOGGER.debug("Failed to parse coordinate data")
        return None
