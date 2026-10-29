import hashlib
import math

from app.core.errors import BadRequestError

# Earth radius in meters
EARTH_RADIUS_M = 6371008.8


def validate_coordinates(lat: float, lon: float) -> None:
    """Validate latitude and longitude ranges."""
    if not (-90.0 <= lat <= 90.0):
        raise BadRequestError(
            message=f"Latitude {lat} out of range [-90, 90]",
            code="invalid_coordinates",
            details={"lat": lat, "lon": lon},
        )
    if not (-180.0 <= lon <= 180.0):
        raise BadRequestError(
            message=f"Longitude {lon} out of range [-180, 180]",
            code="invalid_coordinates",
            details={"lat": lat, "lon": lon},
        )


def validate_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> None:
    """Validate bounding box coordinates."""
    validate_coordinates(min_lat, min_lon)
    validate_coordinates(max_lat, max_lon)
    if min_lat > max_lat:
        raise BadRequestError(
            message=f"min_lat ({min_lat}) cannot be greater than max_lat ({max_lat})",
            code="invalid_bbox",
        )
    if min_lon > max_lon:
        # Note: Bounding box wrapping across antimeridian can be checked, but for standard bbox min_lon <= max_lon
        pass


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Great Circle distance in meters between two lat/lon pairs."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def fuzz_coordinates(
    lat: float,
    lon: float,
    seed: str,
    fuzz_distance_m: float = 200.0,
) -> tuple[float, float]:
    """
    Deterministically fuzz coordinates by approximately `fuzz_distance_m` (default 200m).
    Uses a SHA-256 hash of the seed to generate deterministic angle and distance factor,
    ensuring that repeated requests for the same incident return the exact same public point,
    preventing reverse-engineering through averaging.
    """
    validate_coordinates(lat, lon)

    # Hash seed to generate 2 pseudo-random integers
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    int_angle = int.from_bytes(h[:4], "big")
    int_dist = int.from_bytes(h[4:8], "big")

    # Angle in radians [0, 2*pi)
    bearing = (int_angle / 0xFFFFFFFF) * 2 * math.pi
    # Distance: between 0.85 and 1.15 of fuzz_distance_m
    dist_factor = 0.85 + (int_dist / 0xFFFFFFFF) * 0.30
    distance = fuzz_distance_m * dist_factor

    # Angular distance in radians
    delta = distance / EARTH_RADIUS_M

    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(delta)
        + math.cos(lat_rad) * math.sin(delta) * math.cos(bearing)
    )
    new_lon_rad = lon_rad + math.atan2(
        math.sin(bearing) * math.sin(delta) * math.cos(lat_rad),
        math.cos(delta) - math.sin(lat_rad) * math.sin(new_lat_rad),
    )

    fuzzed_lat = math.degrees(new_lat_rad)
    fuzzed_lon = (math.degrees(new_lon_rad) + 540.0) % 360.0 - 180.0

    return round(fuzzed_lat, 6), round(fuzzed_lon, 6)
