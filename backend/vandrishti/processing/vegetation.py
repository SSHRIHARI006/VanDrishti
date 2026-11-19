"""Stand-level vegetation condition (Sentinel-2), land cover (WorldCover) and terrain (DEM)."""

from __future__ import annotations

import numpy as np

NDVI_CLASSES = [
    ("non_vegetated", "Non-vegetated", -1.0, 0.2, "#b9a27a"),
    ("sparse", "Sparse / stressed vegetation", 0.2, 0.4, "#e6d36a"),
    ("moderate", "Moderate vegetation", 0.4, 0.6, "#8fc45a"),
    ("dense", "Dense healthy vegetation", 0.6, 1.01, "#1f7a2e"),
]

# Leaf habit from the drop in NDVI between the leaf-on season and the dry season.
LEAF_HABIT = [
    (1, "evergreen", "Evergreen (stays green)", 0.0, 0.2, "#0b5d1e"),
    (2, "semi_deciduous", "Semi-deciduous (partly sheds)", 0.2, 0.45, "#c9a227"),
    (3, "deciduous", "Deciduous (sheds leaves)", 0.45, 1.01, "#b5651d"),
]
LEAF_ON_MIN_NDVI = 0.4

WORLDCOVER = {
    10: ("Tree cover", "#006400"),
    20: ("Shrubland", "#ffbb22"),
    30: ("Grassland", "#ffff4c"),
    40: ("Cropland", "#f096ff"),
    50: ("Built-up", "#fa0000"),
    60: ("Bare / sparse vegetation", "#b4b4b4"),
    70: ("Snow and ice", "#f0f0f0"),
    80: ("Permanent water", "#0064c8"),
    90: ("Herbaceous wetland", "#0096a0"),
    95: ("Mangroves", "#00cf75"),
    100: ("Moss and lichen", "#fae6a0"),
}


def ndvi(s2: np.ndarray) -> np.ndarray:
    """s2 bands: B2, B3, B4, B8, B11, B12."""
    red, nir = s2[2], s2[3]
    with np.errstate(invalid="ignore", divide="ignore"):
        return (nir - red) / (nir + red)


def ndvi_class(value: float) -> str:
    if not np.isfinite(value):
        return "unknown"
    for code, _, lo, hi, _ in NDVI_CLASSES:
        if lo <= value < hi:
            return code
    return "unknown"


def ndvi_summary(nd: np.ndarray, mask10: np.ndarray) -> dict:
    vals = nd[mask10 & np.isfinite(nd)]
    if vals.size == 0:
        return {"available": False}
    shares = {}
    for code, _, lo, hi, _ in NDVI_CLASSES:
        shares[code] = round(float(((vals >= lo) & (vals < hi)).mean() * 100), 1)
    return {
        "available": True,
        "mean_ndvi": round(float(vals.mean()), 3),
        "class_pct": shares,
        "valid_pct": round(float(np.isfinite(nd[mask10]).mean() * 100), 1),
    }


def leaf_fall(nd_on: np.ndarray, nd_dry: np.ndarray, tree_mask: np.ndarray | None = None) -> np.ndarray:
    """Fraction of leaf-on NDVI lost in the dry season (0–1), NaN outside vegetated tree pixels."""
    with np.errstate(invalid="ignore", divide="ignore"):
        drop = np.clip((nd_on - nd_dry) / nd_on, 0.0, 1.0)
    ok = np.isfinite(nd_on) & np.isfinite(nd_dry) & (nd_on >= LEAF_ON_MIN_NDVI)
    if tree_mask is not None:
        ok &= tree_mask
    return np.where(ok, drop, np.nan).astype(np.float32)


def leaf_habit_classes(drop: np.ndarray) -> np.ndarray:
    out = np.zeros(drop.shape, np.uint8)
    for value, _, _, lo, hi, _ in LEAF_HABIT:
        out[(drop >= lo) & (drop < hi)] = value
    return out


def leaf_fall_summary(drop: np.ndarray, mask10: np.ndarray) -> dict:
    vals = drop[mask10 & np.isfinite(drop)]
    if vals.size == 0:
        return {"available": False}
    shares = {code: round(float(((vals >= lo) & (vals < hi)).mean() * 100), 1) for _, code, _, lo, hi, _ in LEAF_HABIT}
    return {
        "available": True,
        "mean_drop_pct": round(float(vals.mean() * 100), 1),
        "class_pct": shares,
        "dominant": max(shares, key=shares.get),
        "tree_area_pct": round(float(vals.size / max(int(mask10.sum()), 1) * 100), 1),
    }


def worldcover_summary(wc: np.ndarray, mask10: np.ndarray) -> dict:
    vals = wc[mask10 & np.isfinite(wc)].astype(int)
    if vals.size == 0:
        return {}
    codes, counts = np.unique(vals, return_counts=True)
    total = counts.sum()
    return {
        WORLDCOVER.get(int(c), (f"Class {c}", ""))[0]: round(float(n / total * 100), 1)
        for c, n in sorted(zip(codes, counts), key=lambda t: -t[1])
    }


def slope_deg(dem: np.ndarray, res: float) -> np.ndarray:
    gy, gx = np.gradient(np.nan_to_num(dem, nan=np.nanmean(dem)), res)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def terrain_summary(dem: np.ndarray, mask10: np.ndarray, res: float) -> dict:
    vals = dem[mask10 & np.isfinite(dem)]
    if vals.size == 0:
        return {"available": False}
    sl = slope_deg(dem, res)[mask10]
    return {
        "available": True,
        "elevation_min_m": round(float(vals.min()), 1),
        "elevation_max_m": round(float(vals.max()), 1),
        "elevation_mean_m": round(float(vals.mean()), 1),
        "slope_mean_deg": round(float(np.nanmean(sl)), 1),
        "slope_max_deg": round(float(np.nanmax(sl)), 1),
        "steep_area_pct": round(float((sl > 20).mean() * 100), 1),
    }
