"""Step 1 - build the study-area boundary.

Downloads the geoBoundaries ADM3 layer for Nepal (if it is not already on
disk) and writes the single Panauti Municipality polygon out as
``data/panauti.geojson``. Only the clipped polygon is committed to the repo;
the national file is large and stays local.

    python src/fetch_boundary.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

import config


def download_adm3() -> None:
    if config.ADM3_LOCAL.exists():
        print(f"[skip] {config.ADM3_LOCAL.name} already present")
        return
    print(f"[get ] {config.ADM3_SOURCE}")
    with urllib.request.urlopen(config.ADM3_SOURCE) as resp:
        config.ADM3_LOCAL.write_bytes(resp.read())
    mb = config.ADM3_LOCAL.stat().st_size / 1e6
    print(f"[ok  ] {config.ADM3_LOCAL.name} ({mb:.1f} MB)")


def extract_place() -> dict:
    with config.ADM3_LOCAL.open(encoding="utf-8") as fh:
        collection = json.load(fh)

    matches = [
        f
        for f in collection["features"]
        if f["properties"].get("shapeName", "").strip().lower() == config.PLACE.lower()
    ]
    if not matches:
        sys.exit(f"[fail] no {config.ADM_LEVEL} unit named {config.PLACE!r}")
    if len(matches) > 1:
        sys.exit(f"[fail] {len(matches)} units named {config.PLACE!r}; disambiguate by shapeID")
    return matches[0]


def main() -> None:
    download_adm3()
    feature = extract_place()
    out = {"type": "FeatureCollection", "features": [feature]}
    config.BOUNDARY.write_text(json.dumps(out), encoding="utf-8")
    print(f"[ok  ] {config.BOUNDARY.name} <- {feature['properties']['shapeName']}")


if __name__ == "__main__":
    main()
