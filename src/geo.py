"""Small geometry helpers shared by the analysis and mapping steps.

Kept deliberately light: rasterio (which bundles GDAL) covers everything the
project needs, so there is no geopandas/shapely dependency to install.
"""

from __future__ import annotations

import json
import math

import numpy as np
import rasterio.features

import config

# Mean Earth radius used by the WGS84 authalic sphere, in metres.
EARTH_RADIUS_M = 6_371_007.181


def load_boundary() -> dict:
    """The Panauti polygon as a GeoJSON geometry dict (EPSG:4326)."""
    with config.BOUNDARY.open(encoding="utf-8") as fh:
        return json.load(fh)["features"][0]["geometry"]


def geometry_bounds(geometry: dict) -> tuple[float, float, float, float]:
    """(west, south, east, north) of a GeoJSON geometry."""
    xs: list[float] = []
    ys: list[float] = []

    def walk(node) -> None:
        if isinstance(node[0], (int, float)):
            xs.append(node[0])
            ys.append(node[1])
        else:
            for child in node:
                walk(child)

    walk(geometry["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def padded_bounds(geometry: dict, pad: float = config.BBOX_PAD):
    west, south, east, north = geometry_bounds(geometry)
    return west - pad, south - pad, east + pad, north + pad


def boundary_mask(geometry: dict, shape, transform) -> np.ndarray:
    """Boolean array, True for pixels whose centre falls inside the polygon."""
    return rasterio.features.geometry_mask(
        [geometry], out_shape=shape, transform=transform, invert=True
    )


def pixel_area_ha(transform, shape) -> np.ndarray:
    """Per-row pixel area in hectares for a geographic (lat/lon) raster.

    Pixels in a lat/lon grid shrink towards the poles, so a single scalar
    area would bias the totals. This integrates the exact spherical area of
    one cell for every raster row and broadcasts it across the columns.
    """
    rows = shape[0]
    lon_res = abs(transform.a)
    lat_res = abs(transform.e)
    top = transform.f

    north = np.deg2rad(top - lat_res * np.arange(rows))
    south = np.deg2rad(top - lat_res * np.arange(1, rows + 1))
    # Area of a spherical quadrilateral: R^2 * dlon * (sin(lat_n) - sin(lat_s))
    area_m2 = (EARTH_RADIUS_M**2) * math.radians(lon_res) * (np.sin(north) - np.sin(south))
    return (area_m2 / 10_000.0).reshape(rows, 1)
