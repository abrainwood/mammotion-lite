"""Device tracker coordinate extraction for Mammotion Lite."""

from __future__ import annotations

import json
import logging
import math

from .runtime_data import MammotionLiteData

_LOGGER = logging.getLogger(__name__)

# Last logged rejection to deduplicate debug spam. Snapshot pushes arrive
# every ~30s with identical invalid coordinates (RTK base uninitialised);
# logging every rejection fills the buffer and hides useful messages.
_last_snapshot_rejection: str | None = None

# Coordinates where both abs(lat) and abs(lon) are below this threshold
# (in radians) are treated as uninitialised GPS. 0.01 rad ~ 0.57 deg ~ 63km.
NEAR_ZERO_THRESHOLD_RAD = 0.01

# Snapshot coordinates below this threshold in degrees are likely uninitialised
# or raw radian values not yet converted by CoordinateConverter.
# Valid lat must be > ~1 degree from equator for any real mower location.
MIN_PLAUSIBLE_DEGREES = 1.0


def _coords_from_rtk_base(raw) -> tuple[float, float] | None:
    """Extract coordinates from the RTK base station (radians).

    The RTK base is physically at the charger. When the CoordinateConverter
    hasn't been initialised (device coords near-zero), this gives a usable
    location. Returns None if RTK base coords are also zero.
    """
    try:
        rtk_lat = raw.location.RTK.latitude
        rtk_lon = raw.location.RTK.longitude
    except AttributeError:
        return None
    if abs(rtk_lat) < NEAR_ZERO_THRESHOLD_RAD and abs(rtk_lon) < NEAR_ZERO_THRESHOLD_RAD:
        return None
    lat_deg = rtk_lat * 180.0 / math.pi
    lon_deg = rtk_lon * 180.0 / math.pi
    if -90 <= lat_deg <= 90 and -180 <= lon_deg <= 180:
        _LOGGER.debug("Using RTK base coords: lat=%.4f, lon=%.4f", lat_deg, lon_deg)
        return (lat_deg, lon_deg)
    return None


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
        lon = raw.location.device.longitude
        pos_type = raw.location.position_type

        global _last_snapshot_rejection  # noqa: PLW0603

        # position_type 0 = uninitialised, no GPS fix
        if pos_type == 0:
            rejection = f"position_type=0 (lat={lat:.6f}, lon={lon:.6f})"
            if rejection != _last_snapshot_rejection:
                _LOGGER.debug("Snapshot coords rejected: %s", rejection)
                _last_snapshot_rejection = rejection
            return None

        # Either coordinate near zero = likely uninitialised or unconverted radians
        if abs(lat) < MIN_PLAUSIBLE_DEGREES or abs(lon) < MIN_PLAUSIBLE_DEGREES:
            # Try RTK base station coords as fallback (radians, near the charger)
            rtk_result = _coords_from_rtk_base(raw)
            if rtk_result:
                _last_snapshot_rejection = None
                return rtk_result
            rejection = f"implausible (lat={lat:.6f}, lon={lon:.6f}, position_type={pos_type})"
            if rejection != _last_snapshot_rejection:
                _LOGGER.debug("Snapshot coords rejected: %s", rejection)
                _last_snapshot_rejection = rejection
            return None

        # Sanity: valid WGS84 degrees have lat in [-90, 90], lon in [-180, 180]
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            rejection = f"out of WGS84 range (lat={lat:.6f}, lon={lon:.6f})"
            if rejection != _last_snapshot_rejection:
                _LOGGER.debug("Snapshot coords rejected: %s", rejection)
                _last_snapshot_rejection = rejection
            return None

        # Valid coordinates - clear rejection state
        _last_snapshot_rejection = None

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
