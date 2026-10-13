"""Shared paths, constants and study-area settings for the Panauti analysis."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RASTER = DATA / "raster"
OUTPUTS = ROOT / "outputs"
MAPS = OUTPUTS / "maps"
TABLES = OUTPUTS / "tables"

for _d in (RASTER, MAPS, TABLES):
    _d.mkdir(parents=True, exist_ok=True)

# Study area ---------------------------------------------------------------
# Panauti Municipality, Kavrepalanchok District, Bagmati Province, Nepal.
PLACE = "Panauti"
ADM_LEVEL = "ADM3"
BOUNDARY = DATA / "panauti.geojson"

# geoBoundaries ADM3 for Nepal. Large (~45 MB), so it is not committed -
# fetch_boundary.py downloads it on demand and clips Panauti out of it.
ADM3_SOURCE = (
    "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/"
    "NPL/ADM3/geoBoundaries-NPL-ADM3.geojson"
)
ADM3_LOCAL = DATA / "NPL_ADM3.geojson"

# Hansen Global Forest Change ---------------------------------------------
# Hansen, M. C. et al. (2013) "High-Resolution Global Maps of 21st-Century
# Forest Cover Change." Science 342: 850-853. Annual update v1.12 covers
# loss years 2001-2024 at 1 arc-second (~30 m).
GFC_VERSION = "GFC-2024-v1.12"
GFC_TILE = "30N_080E"  # 10x10 deg tile containing Panauti (85.5E, 27.6N)
GFC_BASE = "https://storage.googleapis.com/earthenginepartners-hansen"
GFC_LAYERS = ("treecover2000", "lossyear", "gain", "datamask")

LOSS_YEAR_START = 2001
LOSS_YEAR_END = 2024
GAIN_PERIOD = (2000, 2012)  # the Hansen gain layer is only defined for this window

# A pixel counts as forest in 2000 when its tree canopy cover is at or above
# this percentage. 30% is the threshold used by Global Forest Watch headline
# statistics, so results here are comparable to GFW's country dashboards.
CANOPY_THRESHOLD = 30

# Padding (degrees) around the municipality bounds when clipping rasters, so
# map frames are not flush against the boundary.
BBOX_PAD = 0.01


def gfc_url(layer: str) -> str:
    """Public HTTPS URL of one Hansen GFC layer for the study-area tile."""
    return f"{GFC_BASE}/{GFC_VERSION}/Hansen_{GFC_VERSION}_{layer}_{GFC_TILE}.tif"


def raster_path(layer: str) -> Path:
    """Local path of the Panauti-sized clip of one Hansen layer."""
    return RASTER / f"panauti_{layer}.tif"
