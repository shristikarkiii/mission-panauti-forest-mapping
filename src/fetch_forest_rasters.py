"""Step 2 - clip the Hansen Global Forest Change layers to Panauti.

The Hansen tiles are 40000x40000 px (~250 MB each) and live on public HTTPS.
Rather than downloading them, this reads only the window covering Panauti
straight out of the remote GeoTIFFs via GDAL's /vsicurl driver and writes
small local clips into ``data/raster/``.

    python src/fetch_forest_rasters.py [--force]
"""

from __future__ import annotations

import argparse
import time

import rasterio
from rasterio.windows import from_bounds

import config
import geo

# Only the needed byte ranges are pulled, and consecutive strips are merged
# into single requests - without this the read is hundreds of round trips.
GDAL_ENV = dict(
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    GDAL_HTTP_MULTIPLEX="YES",
    GDAL_HTTP_VERSION="2",
    VSI_CACHE="TRUE",
    VSI_CACHE_SIZE=100_000_000,
    CPL_VSIL_CURL_CACHE_SIZE=200_000_000,
)


def clip_layer(layer: str, bounds, force: bool) -> None:
    dest = config.raster_path(layer)
    if dest.exists() and not force:
        print(f"[skip] {dest.name} already present")
        return

    url = "/vsicurl/" + config.gfc_url(layer)
    started = time.time()
    with rasterio.open(url) as src:
        window = from_bounds(*bounds, src.transform).round_lengths().round_offsets()
        data = src.read(1, window=window)
        profile = src.profile | {
            "height": data.shape[0],
            "width": data.shape[1],
            "transform": src.window_transform(window),
            "compress": "deflate",
            "predictor": 2,
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
            "driver": "GTiff",
        }

    with rasterio.open(dest, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(
            source=config.gfc_url(layer),
            dataset=f"Hansen Global Forest Change {config.GFC_VERSION}",
            citation="Hansen et al. (2013), Science 342:850-853",
        )
    mb = dest.stat().st_size / 1e6
    print(
        f"[ok  ] {dest.name}  {data.shape[1]}x{data.shape[0]} px  "
        f"{mb:.2f} MB  {time.time() - started:.0f}s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download existing clips")
    args = parser.parse_args()

    bounds = geo.padded_bounds(geo.load_boundary())
    print(f"[info] window W{bounds[0]:.4f} S{bounds[1]:.4f} E{bounds[2]:.4f} N{bounds[3]:.4f}")

    with rasterio.Env(**GDAL_ENV):
        for layer in config.GFC_LAYERS:
            clip_layer(layer, bounds, args.force)


if __name__ == "__main__":
    main()
