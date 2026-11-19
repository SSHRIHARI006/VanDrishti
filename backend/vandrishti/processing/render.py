"""Raster → PNG overlays and raster/vector → GeoJSON in WGS84."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from PIL import Image
from rasterio.features import shapes
from shapely.geometry import box, mapping, shape
from shapely.ops import transform as shp_transform

matplotlib.use("Agg")
from matplotlib import colormaps  # noqa: E402

MAX_OVERLAY_PX = 2048


def corners_wgs84(grid, to_wgs84) -> list[list[float]]:
    """Image corners (top-left, top-right, bottom-right, bottom-left) as [lon, lat]."""
    minx, miny, maxx, maxy = grid.bounds
    pts = [(minx, maxy), (maxx, maxy), (maxx, miny), (minx, miny)]
    return [list(to_wgs84(x, y)) for x, y in pts]


def _downsample(arr: np.ndarray) -> np.ndarray:
    step = int(np.ceil(max(arr.shape[-2:]) / MAX_OVERLAY_PX))
    return arr[..., ::step, ::step] if step > 1 else arr


def save_continuous(arr, path: Path, cmap: str, vmin: float, vmax: float, mask=None) -> None:
    a = _downsample(np.asarray(arr, dtype=np.float32))
    m = _downsample(mask) if mask is not None else np.ones(a.shape, bool)
    norm = np.clip((np.nan_to_num(a, nan=vmin) - vmin) / (vmax - vmin), 0, 1)
    rgba = (colormaps[cmap](norm) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(m & np.isfinite(a), 235, 0)
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def save_categorical(arr, path: Path, colors: dict, mask=None) -> None:
    a = _downsample(np.asarray(arr))
    m = _downsample(mask) if mask is not None else np.ones(a.shape, bool)
    rgba = np.zeros(a.shape + (4,), np.uint8)
    for value, hex_color in colors.items():
        sel = a == value
        rgba[sel, :3] = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
        rgba[sel, 3] = 220
    rgba[~m] = 0
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def save_truecolor(s2: np.ndarray, path: Path, mask=None) -> None:
    rgb = np.stack([s2[2], s2[1], s2[0]], axis=-1)
    lo, hi = np.nanpercentile(rgb, 2), np.nanpercentile(rgb, 98)
    img = np.clip((np.nan_to_num(rgb, nan=lo) - lo) / max(hi - lo, 1e-6), 0, 1) ** 0.8
    img = _downsample(np.moveaxis(img, -1, 0))
    rgba = np.zeros(img.shape[1:] + (4,), np.uint8)
    rgba[..., :3] = (np.moveaxis(img, 0, -1) * 255).astype(np.uint8)
    m = _downsample(mask) if mask is not None else np.ones(rgba.shape[:2], bool)
    rgba[..., 3] = np.where(m, 255, 0)
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def crowns_to_features(labels: np.ndarray, transform, to_wgs84, simplify_m: float) -> dict[int, dict]:
    """Polygonize the crown label raster; returns {label: GeoJSON geometry (WGS84)}."""
    out: dict[int, tuple] = {}
    for geom, value in shapes(labels.astype(np.int32), mask=labels > 0, transform=transform):
        v = int(value)
        g = shape(geom)
        if v not in out or g.area > out[v][0].area:
            out[v] = (g, None)
    result = {}
    for v, (g, _) in out.items():
        g = g.simplify(simplify_m, preserve_topology=True)
        result[v] = mapping(shp_transform(to_wgs84, g))
    return result


def cell_polygon(grid, cell_px: int, row: int, col: int, aoi_utm, to_wgs84) -> dict:
    size = cell_px * grid.res
    x0 = grid.xmin + col * size
    y1 = grid.ymax - row * size
    cell = box(x0, y1 - size, x0 + size, y1).intersection(aoi_utm)
    return mapping(shp_transform(to_wgs84, cell))


def feature_collection(features: list[dict], **extra) -> dict:
    return {"type": "FeatureCollection", "features": features, **extra}
