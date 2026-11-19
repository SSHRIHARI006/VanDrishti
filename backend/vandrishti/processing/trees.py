"""Individual tree detection and crown delineation from a canopy height model.

Method (classical, no training data needed):
  1. Smooth the CHM to suppress within-crown noise.
  2. Tree tops = local maxima with a height-dependent search radius
     (taller trees have wider crowns, so neighbouring maxima are suppressed
     over a larger distance).
  3. Crowns = marker-controlled watershed from the tree tops, limited to
     pixels at least `crown_fraction` of the tree's own height.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from skimage.morphology import disk
from skimage.segmentation import watershed

HEIGHT_OUTLIER_M = 40.0
MIN_CROWN_M2 = 2.0


@dataclass
class TreeParams:
    min_height_m: float = 5.0
    smooth_sigma_m: float = 0.5
    window_scale: float = 1.0
    crown_min_height_m: float = 2.0
    crown_fraction: float = 0.4


# Meta's 1 m CHM is smooth and stored in whole metres, so a narrower search
# window is needed than for a sharp drone/LiDAR CHM.
SATELLITE_PARAMS = TreeParams(smooth_sigma_m=0.5, window_scale=0.6)
SURVEY_PARAMS = TreeParams(smooth_sigma_m=0.3, window_scale=1.0)


def max_crown_radius_m(height: np.ndarray) -> np.ndarray:
    return np.clip(0.5 + 0.3 * height, 2.0, 8.0)


def window_radius_m(height: np.ndarray, scale: float = 1.0) -> np.ndarray:
    """Search radius for tree tops; roughly half the expected crown width."""
    return np.clip((0.8 + 0.12 * height) * scale, 1.0, 4.5)


def find_tree_tops(chm_s: np.ndarray, res: float, min_height: float, scale: float = 1.0) -> np.ndarray:
    """Boolean mask of tree-top pixels (one pixel per top)."""
    radii_m = np.arange(1.0, 4.51, 0.5)
    want = window_radius_m(chm_s, scale)
    is_top = np.zeros(chm_s.shape, dtype=bool)
    for i, r_m in enumerate(radii_m):
        r_px = max(1, int(round(r_m / res)))
        local_max = ndimage.maximum_filter(chm_s, footprint=disk(r_px), mode="nearest")
        lo = radii_m[i - 1] if i > 0 else -np.inf
        in_bin = (want > lo) & (want <= r_m) if i < len(radii_m) - 1 else want > lo
        is_top |= in_bin & (chm_s >= local_max)
    is_top &= chm_s >= min_height
    # Flat-topped crowns give plateaus of equal maxima: keep one pixel per plateau.
    labels, n = ndimage.label(is_top, structure=np.ones((3, 3)))
    out = np.zeros_like(is_top)
    if n:
        for r, c in ndimage.maximum_position(chm_s, labels, np.arange(1, n + 1)):
            out[r, c] = True
    return out


def detect_trees(chm: np.ndarray, res: float, aoi_mask: np.ndarray, params: TreeParams) -> dict:
    """Detect trees inside `aoi_mask`.

    Returns a dict with a crown label raster and per-tree arrays
    (row, col, height, crown area, diameter, flags).
    """
    chm0 = np.nan_to_num(chm, nan=0.0)
    chm_s = ndimage.gaussian_filter(chm0, sigma=params.smooth_sigma_m / res)

    tops = find_tree_tops(chm_s, res, params.min_height_m, params.window_scale) & aoi_mask
    markers, n = ndimage.label(tops)
    if n == 0:
        return {"labels": np.zeros(chm.shape, np.int32), "count": 0}

    canopy = chm0 >= params.crown_min_height_m
    labels = watershed(-chm_s, markers, mask=canopy | tops).astype(np.int32)

    idx = np.arange(1, n + 1)
    rows, cols = np.nonzero(tops)
    order = np.argsort(markers[rows, cols])
    rows, cols = rows[order], cols[order]
    height = np.asarray(ndimage.maximum(chm0, labels, idx), dtype=np.float32)

    # Trim each crown to pixels >= crown_fraction of its own height and within
    # a plausible crown radius; leftover canopy stays unattributed.
    h_px = np.zeros(n + 1, np.float32)
    h_px[1:] = height
    r_max = np.zeros(n + 1, np.float32)
    r_max[1:] = max_crown_radius_m(height)
    top_r = np.zeros(n + 1, np.float32)
    top_c = np.zeros(n + 1, np.float32)
    top_r[1:], top_c[1:] = rows, cols
    rr, cc = np.nonzero(labels)
    lab = labels[rr, cc]
    dist_m = np.hypot(rr - top_r[lab], cc - top_c[lab]) * res
    drop = (chm0[rr, cc] < h_px[lab] * params.crown_fraction) | (dist_m > r_max[lab])
    labels[rr[drop], cc[drop]] = 0

    px_area = res * res
    area = np.bincount(labels.ravel(), minlength=n + 1)[1:] * px_area

    keep = area >= MIN_CROWN_M2
    remap = np.zeros(n + 1, np.int32)
    remap[1:][keep] = np.arange(1, keep.sum() + 1)
    labels = remap[labels]

    area, height, rows, cols = area[keep], height[keep], rows[keep], cols[keep]
    flags = [[] for _ in range(len(area))]
    for i in np.nonzero(height > HEIGHT_OUTLIER_M)[0]:
        flags[i].append("height_outlier")

    canopy_in_aoi = canopy & aoi_mask
    return {
        "unattributed_canopy_fraction": float(
            ((labels == 0) & canopy_in_aoi & (chm0 >= params.min_height_m)).sum()
            / max(1, (canopy_in_aoi & (chm0 >= params.min_height_m)).sum())
        ),
        "labels": labels,
        "count": int(keep.sum()),
        "rows": rows,
        "cols": cols,
        "height_m": height,
        "crown_area_m2": area,
        "crown_diameter_m": 2.0 * np.sqrt(area / np.pi),
        "flags": flags,
        "chm_smoothed": chm_s,
    }
