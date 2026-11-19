"""Google Earth Engine data access.

All layers are requested on a north-up grid in the AOI's UTM zone, so every
array shares one coordinate system and area/distance maths stays in metres.
Downloads are chunked (Earth Engine caps each request) and cached as GeoTIFFs
so repeat runs and demos work without re-downloading.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from ..config import settings

CHUNK_PX = 1024
_init_lock = threading.Lock()
_initialized = False

META_CHM = "projects/meta-forest-monitoring-okw37/assets/CanopyHeight"
COP_DEM = "COPERNICUS/DEM/GLO30_2024_1"
S2_SR = "COPERNICUS/S2_SR_HARMONIZED"
S2_CLOUDSCORE = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
WORLDCOVER = "ESA/WorldCover/v200"
S2_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
WORLDCLIM = "WORLDCLIM/V1/BIO"
ECOREGIONS = "RESOLVE/ECOREGIONS/2017"
SOIL = {
    "sand": "OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02",
    "clay": "OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02",
    "ph": "OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02",
    "soc": "OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02",
}
# Climate + topsoil variables that describe where a tree species can grow (same set offline and at runtime).
ENV_BIO = ["bio01", "bio04", "bio05", "bio06", "bio12", "bio15", "bio17"]
ENV_VARS = ENV_BIO + list(SOIL)

PROVENANCE = {
    "chm": {
        "dataset": "Meta / WRI Global Canopy Height Map (1 m)",
        "source": META_CHM,
        "resolution_m": 1,
        "license": "CC BY 4.0",
        "citation": "Tolan et al. (2024), Remote Sensing of Environment 300:113888",
        "notes": "Model-predicted canopy height from Maxar imagery (mostly 2018–2020); "
                 "mean absolute error about 2.8 m, tall trees tend to be underestimated.",
    },
    "dem": {
        "dataset": "Copernicus DEM GLO-30",
        "source": COP_DEM,
        "resolution_m": 30,
        "license": "Contains modified Copernicus data",
        "notes": "Bare-earth elevation; resampled to 10 m for display and slope.",
    },
    "s2": {
        "dataset": "Sentinel-2 L2A surface reflectance (harmonized)",
        "source": S2_SR,
        "resolution_m": 10,
        "license": "Contains modified Copernicus Sentinel data",
        "notes": "Median composite of cloud-masked scenes (Cloud Score+ >= 0.6).",
    },
    "s2_dry": {
        "dataset": "Sentinel-2 L2A dry-season composite (leaf-fall layer)",
        "source": S2_SR,
        "resolution_m": 10,
        "license": "Contains modified Copernicus Sentinel data",
        "notes": "NDVI drop from the leaf-on to the dry season separates deciduous from evergreen canopy. "
                 "Fire, grazing or felling between the two seasons also lowers NDVI.",
    },
    "worldcover": {
        "dataset": "ESA WorldCover 2021 v200",
        "source": WORLDCOVER,
        "resolution_m": 10,
        "license": "CC BY 4.0, © ESA WorldCover project",
        "notes": "Land-cover context (tree cover, cropland, built-up, bare, water).",
    },
    "climate": {
        "dataset": "WorldClim v1.4 bioclimatic variables",
        "source": WORLDCLIM,
        "resolution_m": 1000,
        "license": "Free for non-commercial use; cite Hijmans et al. (2005)",
        "citation": "Hijmans et al. (2005), International Journal of Climatology 25:1965–1978",
        "notes": "1960–1990 climate normals: temperature, seasonality, rainfall, dry-season rainfall.",
    },
    "soil": {
        "dataset": "OpenLandMap soil texture, pH and organic carbon (topsoil)",
        "source": "OpenLandMap/SOL/*/v02",
        "resolution_m": 250,
        "license": "CC BY-SA 4.0",
        "citation": "Hengl (2018), OpenLandMap / Zenodo",
        "notes": "Machine-learning soil maps; sand and clay %, pH (H2O), organic carbon.",
    },
    "ecoregion": {
        "dataset": "RESOLVE Ecoregions 2017",
        "source": ECOREGIONS,
        "license": "CC BY 4.0",
        "citation": "Dinerstein et al. (2017), BioScience 67:534–545",
        "notes": "846 ecoregions in 14 biomes; used to name the site's biome.",
    },
    "gbif": {
        "dataset": "GBIF tree occurrence records (worldwide) and GlobalTreeSearch species list",
        "source": "api.gbif.org; BGCI GlobalTreeSearch",
        "license": "Records CC0 / CC BY per dataset; GlobalTreeSearch © BGCI",
        "citation": "GBIF.org occurrence data; BGCI (2025) GlobalTreeSearch, DOI 10.13140/RG.2.2.27733.23522",
        "notes": "Each species' climate and soil range is learned from its worldwide records.",
    },
}


class GEEError(RuntimeError):
    pass


def init_ee():
    global _initialized
    import ee

    with _init_lock:
        if _initialized:
            return ee
        if not settings.gee_project:
            raise GEEError("GEE_PROJECT is not set. Add it to .env (see .env.example)")
        try:
            key = os.environ.get("GEE_SERVICE_ACCOUNT_KEY", "").strip()
            if key:
                # Hosted deployments: the service-account JSON key is passed as a secret.
                creds = ee.ServiceAccountCredentials(json.loads(key)["client_email"], key_data=key)
                ee.Initialize(creds, project=settings.gee_project)
            else:
                ee.Initialize(project=settings.gee_project)
        except Exception as exc:
            raise GEEError(
                f"Earth Engine login failed ({exc}). Run 'earthengine authenticate' on this machine, "
                "or set GEE_SERVICE_ACCOUNT_KEY"
            ) from exc
        _initialized = True
    return ee


@dataclass
class Grid:
    epsg: int
    xmin: float
    ymax: float
    res: float
    width: int
    height: int

    @property
    def transform(self):
        return from_origin(self.xmin, self.ymax, self.res, self.res)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.xmin, self.ymax - self.height * self.res, self.xmin + self.width * self.res, self.ymax)

    @classmethod
    def for_bounds(cls, epsg: int, bounds, res: float, pad_m: float = 20.0) -> "Grid":
        minx, miny, maxx, maxy = bounds
        xmin = math.floor((minx - pad_m) / res) * res
        ymin = math.floor((miny - pad_m) / res) * res
        xmax = math.ceil((maxx + pad_m) / res) * res
        ymax = math.ceil((maxy + pad_m) / res) * res
        return cls(epsg, xmin, ymax, res, int(round((xmax - xmin) / res)), int(round((ymax - ymin) / res)))

    def key(self) -> str:
        return f"{self.epsg}_{self.xmin:.0f}_{self.ymax:.0f}_{self.res:g}_{self.width}x{self.height}"


def _download_chunk(ee, image, grid: Grid, col0: int, row0: int, w: int, h: int) -> np.ndarray:
    request = {
        "expression": image,
        "fileFormat": "GEO_TIFF",
        "grid": {
            "dimensions": {"width": w, "height": h},
            "affineTransform": {
                "scaleX": grid.res,
                "shearX": 0,
                "translateX": grid.xmin + col0 * grid.res,
                "shearY": 0,
                "scaleY": -grid.res,
                "translateY": grid.ymax - row0 * grid.res,
            },
            "crsCode": f"EPSG:{grid.epsg}",
        },
    }
    last_exc = None
    for _ in range(3):
        try:
            raw = ee.data.computePixels(request)
            with rasterio.open(io.BytesIO(raw)) as src:
                return src.read().astype(np.float32)
        except Exception as exc:  # network hiccups / transient EE errors
            last_exc = exc
    raise GEEError(f"Earth Engine download failed: {last_exc}")


def download(build_image, grid: Grid, nbands: int, cache_name: str, nodata: float = -9999.0) -> np.ndarray:
    """Download an ee.Image onto `grid`, returning (bands, rows, cols) float32 with NaN nodata.

    `build_image(ee)` is only called on a cache miss, so cached areas need no
    Earth Engine connection at all (offline demos, repeat runs).
    """
    cache = cache_path(cache_name, grid)
    if cache.exists():
        with rasterio.open(cache) as src:
            arr = src.read().astype(np.float32)
        arr[arr == nodata] = np.nan
        return arr

    ee = init_ee()
    image = build_image(ee).unmask(nodata).toFloat()
    out = np.full((nbands, grid.height, grid.width), nodata, dtype=np.float32)
    jobs = [
        (c, r, min(CHUNK_PX, grid.width - c), min(CHUNK_PX, grid.height - r))
        for r in range(0, grid.height, CHUNK_PX)
        for c in range(0, grid.width, CHUNK_PX)
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = pool.map(lambda j: (j, _download_chunk(ee, image, grid, *j)), jobs)
        for (c, r, w, h), data in results:
            out[:, r:r + h, c:c + w] = data[:nbands, :h, :w]

    cache.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        cache, "w", driver="GTiff", width=grid.width, height=grid.height, count=nbands,
        dtype="float32", crs=f"EPSG:{grid.epsg}", transform=grid.transform, nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(out)
    out[out == nodata] = np.nan
    return out


def cache_path(name: str, grid: Grid) -> Path:
    digest = hashlib.sha1(grid.key().encode()).hexdigest()[:16]
    return settings.cache_dir / f"{name}_{digest}.tif"


def _region(ee, grid: Grid):
    minx, miny, maxx, maxy = grid.bounds
    return ee.Geometry.Rectangle([minx, miny, maxx, maxy], f"EPSG:{grid.epsg}", False)


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

def fetch_chm(grid: Grid) -> np.ndarray:
    def build(ee):
        col = ee.ImageCollection(META_CHM).filterBounds(_region(ee, grid))
        if col.size().getInfo() == 0:
            raise GEEError("Meta canopy height has no coverage for this area")
        return col.mosaic().select([0]).rename("chm")

    return download(build, grid, 1, "chm")[0]


def fetch_dem(grid: Grid) -> np.ndarray:
    def build(ee):
        col = ee.ImageCollection(COP_DEM).filterBounds(_region(ee, grid)).select("DEM")
        return col.mosaic().setDefaultProjection(col.first().projection()).resample("bilinear")

    return download(build, grid, 1, "dem")[0]


def fetch_worldcover(grid: Grid) -> np.ndarray:
    return download(lambda ee: ee.ImageCollection(WORLDCOVER).first().select("Map"), grid, 1, "worldcover")[0]


def environment_image(ee):
    bio = ee.Image(WORLDCLIM).select(ENV_BIO)
    soil = [ee.Image(asset).select("b0").rename(name) for name, asset in SOIL.items()]
    return bio.addBands(soil)


def fetch_site_environment(geom_wgs84) -> dict:
    """Mean climate and soil over the boundary, plus its RESOLVE ecoregion and biome."""
    from shapely.geometry import mapping

    digest = hashlib.sha1(geom_wgs84.wkb).hexdigest()[:16]
    path = settings.cache_dir / f"env_{digest}.json"
    if path.exists():
        return json.loads(path.read_text())
    ee = init_ee()
    region = ee.Geometry(mapping(geom_wgs84))
    values = environment_image(ee).reduceRegion(
        ee.Reducer.mean(), region, scale=250, bestEffort=True, maxPixels=1e8).getInfo()
    if any(values.get(k) is None for k in ENV_VARS):
        # boundary smaller than a soil pixel or on a data gap: fall back to its centre point
        c = geom_wgs84.centroid
        values = environment_image(ee).reduceRegion(
            ee.Reducer.first(), ee.Geometry.Point([c.x, c.y]), scale=250).getInfo()
    info = ee.FeatureCollection(ECOREGIONS).filterBounds(region.centroid(1)).first().getInfo()
    eco = info["properties"] if info else {}
    out = {
        "env": {k: values.get(k) for k in ENV_VARS},
        "ecoregion": eco.get("ECO_NAME"),
        "biome": eco.get("BIOME_NAME"),
        "realm": eco.get("REALM"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def post_monsoon_window(today: date | None = None) -> tuple[str, str]:
    """Most recent complete Oct–Jan leaf-on, low-cloud season."""
    today = today or date.today()
    end_year = today.year if today.month >= 2 else today.year - 1
    return f"{end_year - 1}-10-01", f"{end_year}-02-01"


def dry_season_window(leaf_on_end: str, today: date | None = None) -> tuple[str, str]:
    """The Mar–mid-May leaf-off season that follows the leaf-on window (the one before it if not yet complete)."""
    today = today or date.today()
    year = int(leaf_on_end[:4])
    if date(year, 5, 16) > today:
        year -= 1
    return f"{year}-03-01", f"{year}-05-16"


def s2_collection(ee, region, start: str, end: str):
    s2 = ee.ImageCollection(S2_SR).filterBounds(region).filterDate(start, end)
    cs = ee.ImageCollection(S2_CLOUDSCORE).filterBounds(region).filterDate(start, end)
    linked = s2.linkCollection(cs, ["cs"])
    return linked.map(lambda im: im.select(S2_BANDS).updateMask(im.select("cs").gte(0.6)))


def fetch_s2(grid: Grid, start: str, end: str) -> tuple[np.ndarray, dict]:
    """Cloud-masked median composite. Returns (bands[B2,B3,B4,B8,B11,B12] reflectance 0–1, meta)."""
    name = f"s2_{start}_{end}"
    meta_path = cache_path(name, grid).with_suffix(".json")
    if meta_path.exists():
        n_scenes = json.loads(meta_path.read_text())["scenes"]
    else:
        ee = init_ee()
        n_scenes = ee.ImageCollection(S2_SR).filterBounds(_region(ee, grid)).filterDate(start, end).size().getInfo()
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps({"scenes": int(n_scenes)}))
    if n_scenes == 0:
        return np.full((len(S2_BANDS), grid.height, grid.width), np.nan, np.float32), {
            "scenes": 0, "start": start, "end": end
        }

    def build(ee):
        col = s2_collection(ee, _region(ee, grid), start, end)
        return col.median().divide(10000).addBands(col.select("B4").count().rename("clear"))

    arr = download(build, grid, len(S2_BANDS) + 1, name)
    bands, clear_count = arr[:-1], arr[-1]
    return bands, {
        "scenes": int(n_scenes),
        "start": start,
        "end": end,
        "median_clear_observations": float(np.nanmedian(clear_count)) if np.isfinite(clear_count).any() else 0.0,
    }
