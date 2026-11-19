"""Drone / aerial survey inputs: raster checks, canopy height model, DeepForest crown detection."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_geom
from shapely.geometry import Point, box, mapping, shape
from shapely.affinity import scale as shp_scale

DEEPFOREST_RES_M = 0.1  # the NEON-pretrained model expects ~10 cm imagery
MAX_ORTHO_RES_M = 1.0
WARN_ORTHO_RES_M = 0.3

_model = None
_model_lock = threading.Lock()


class SurveyError(ValueError):
    """Survey input cannot be used; the message is shown to the user."""


def inspect(path: Path, aoi_wgs84) -> dict:
    """Basic facts about an uploaded raster, including how much of the AOI it covers."""
    try:
        src = rasterio.open(path)
    except Exception as exc:
        raise SurveyError(f"{path.name} is not a readable GeoTIFF ({exc})") from exc
    with src:
        if src.crs is None:
            raise SurveyError(f"{path.name} has no coordinate system; export it as a georeferenced GeoTIFF")
        footprint = box(*src.bounds)
        aoi_native = shape(transform_geom("EPSG:4326", src.crs, mapping(aoi_wgs84)))
        covered = aoi_native.intersection(footprint).area / aoi_native.area if aoi_native.area else 0.0
        res = abs(src.res[0]) * (src.crs.linear_units_factor[1] if src.crs.is_projected else 111_320.0)
        return {
            "file": path.name,
            "crs": src.crs.to_string(),
            "res_m": round(float(res), 3),
            "bands": src.count,
            "width": src.width,
            "height": src.height,
            "aoi_coverage_pct": round(float(covered) * 100, 1),
            "dtype": src.dtypes[0],
        }


def warp_to_grid(path: Path, grid, bands=None, resampling=Resampling.bilinear) -> np.ndarray:
    """Reproject a raster onto a UTM Grid; returns (bands, rows, cols) float32 with NaN nodata."""
    with rasterio.open(path) as src:
        idx = bands or list(range(1, src.count + 1))
        out = np.full((len(idx), grid.height, grid.width), np.nan, np.float32)
        for i, b in enumerate(idx):
            reproject(
                source=rasterio.band(src, b),
                destination=out[i],
                dst_transform=grid.transform,
                dst_crs=f"EPSG:{grid.epsg}",
                dst_nodata=np.nan,
                resampling=resampling,
            )
    return out


def build_chm(grid, chm_path=None, dsm_path=None, dtm_path=None) -> tuple[np.ndarray | None, str | None]:
    if chm_path:
        chm = warp_to_grid(chm_path, grid, [1])[0]
        return np.clip(chm, 0, None), "Uploaded canopy height model"
    if dsm_path and dtm_path:
        dsm = warp_to_grid(dsm_path, grid, [1])[0]
        dtm = warp_to_grid(dtm_path, grid, [1])[0]
        return np.clip(dsm - dtm, 0, None), "Survey DSM − DTM"
    return None, None


def working_ortho(path: Path, grid_bounds, epsg: int, out_path: Path) -> tuple[Path, float, object]:
    """Write the orthophoto as 8-bit RGB on a UTM grid at ~10 cm for DeepForest."""
    from ..sources.gee import Grid

    with rasterio.open(path) as src:
        native = abs(src.res[0]) * (src.crs.linear_units_factor[1] if src.crs.is_projected else 111_320.0)
    res = max(DEEPFOREST_RES_M, native)
    grid = Grid.for_bounds(epsg, grid_bounds, res, pad_m=0)
    rgb = warp_to_grid(path, grid, [1, 2, 3])
    valid = np.isfinite(rgb).all(axis=0)
    lo, hi = np.nanpercentile(rgb, 0.5), np.nanpercentile(rgb, 99.5)
    if hi > 255 or lo < 0 or rgb.dtype != np.uint8:
        rgb = (np.clip((np.nan_to_num(rgb, nan=lo) - lo) / max(hi - lo, 1e-6), 0, 1) * 255)
    rgb8 = np.nan_to_num(rgb, nan=0).astype(np.uint8)
    rgb8[:, ~valid] = 0
    with rasterio.open(out_path, "w", driver="GTiff", width=grid.width, height=grid.height, count=3,
                       dtype="uint8", crs=f"EPSG:{epsg}", transform=grid.transform, compress="deflate") as dst:
        dst.write(rgb8)
    return out_path, res, grid


def _deepforest():
    global _model
    with _model_lock:
        if _model is None:
            from deepforest import main

            m = main.deepforest()
            m.load_model("weecology/deepforest-tree")
            accelerator = os.environ.get("VANDRISHTI_DEEPFOREST_ACCELERATOR")
            if accelerator:  # e.g. "cpu" on hosts where a GPU is visible but not usable by this process
                m.config.accelerator = accelerator
                m.create_trainer()
            _model = m
    return _model


def deepforest_available() -> bool:
    try:
        import deepforest  # noqa: F401
        return True
    except ImportError:
        return False


PATCH_PX = 400


def pad_to_patch(img: np.ndarray, size: int = PATCH_PX) -> np.ndarray:
    """Zero-pad (H, W, 3) so both sides are at least one patch.

    The detector rescales every input to a fixed size; an image smaller than the
    400 px training patch gets magnified more than in training, crowns look too
    large and detection collapses. Padding keeps the 10 cm scale.
    """
    h, w = img.shape[:2]
    return np.pad(img, ((0, max(0, size - h)), (0, max(0, size - w)), (0, 0)))


def detect_crowns(ortho_path: Path, ortho_grid) -> list[dict]:
    """Run DeepForest tiled prediction; returns boxes in UTM metres with scores.

    predict_tile splits the orthophoto into overlapping 40 m patches and removes
    duplicate boxes at patch edges (non-max suppression), so large mosaics are
    counted once.
    """
    model = _deepforest()
    with rasterio.open(ortho_path) as src:
        img = np.moveaxis(src.read([1, 2, 3]), 0, -1).astype(np.float32)
    h, w = img.shape[:2]
    df = model.predict_tile(image=pad_to_patch(img), patch_size=PATCH_PX, patch_overlap=0.25, iou_threshold=0.15)
    if df is None or len(df) == 0:
        return []
    df = df[((df.xmin + df.xmax) / 2 < w) & ((df.ymin + df.ymax) / 2 < h)]
    res, x0, y0 = ortho_grid.res, ortho_grid.xmin, ortho_grid.ymax
    return [
        {
            "xmin": x0 + r.xmin * res, "xmax": x0 + r.xmax * res,
            "ymax": y0 - r.ymin * res, "ymin": y0 - r.ymax * res,
            "score": float(r.score),
        }
        for r in df.itertuples()
    ]


def measure_boxes(boxes: list[dict], chm: np.ndarray, grid, aoi_utm, min_height: float, crown_fraction=0.4) -> dict:
    """Attach CHM height and crown area to each box; drop boxes outside the AOI or below min height."""
    keep, low_veg = [], 0
    for b in boxes:
        cx, cy = (b["xmin"] + b["xmax"]) / 2, (b["ymin"] + b["ymax"]) / 2
        if not aoi_utm.contains(Point(cx, cy)):
            continue
        c0 = max(0, int((b["xmin"] - grid.xmin) / grid.res))
        c1 = min(grid.width, int(np.ceil((b["xmax"] - grid.xmin) / grid.res)))
        r0 = max(0, int((grid.ymax - b["ymax"]) / grid.res))
        r1 = min(grid.height, int(np.ceil((grid.ymax - b["ymin"]) / grid.res)))
        win = chm[r0:r1, c0:c1]
        vals = win[np.isfinite(win)]
        if vals.size == 0:
            continue
        h = float(np.percentile(vals, 95))
        if h < min_height:
            low_veg += 1
            continue
        crown_px = int((vals >= h * crown_fraction).sum())
        w, hgt = b["xmax"] - b["xmin"], b["ymax"] - b["ymin"]
        ellipse = shp_scale(Point(cx, cy).buffer(1.0, 24), w / 2, hgt / 2)
        keep.append({**b, "cx": cx, "cy": cy, "height_m": h,
                     "crown_area_m2": max(crown_px * grid.res ** 2, 1.0),
                     "crown_geom": ellipse,
                     "row": min(grid.height - 1, max(0, int((grid.ymax - cy) / grid.res))),
                     "col": min(grid.width - 1, max(0, int((cx - grid.xmin) / grid.res)))})
    return {"trees": keep, "low_vegetation": low_veg}
