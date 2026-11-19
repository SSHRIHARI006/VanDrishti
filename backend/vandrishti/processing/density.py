"""Canopy density on a regular grid, classified with Forest Survey of India classes."""

from __future__ import annotations

import numpy as np

# Forest Survey of India canopy-density classes (India State of Forest Report).
FSI_CLASSES = [
    ("VDF", "Very Dense Forest", 70.0, 100.01, "#0b5d1e"),
    ("MDF", "Moderately Dense Forest", 40.0, 70.0, "#3f9b35"),
    ("OF", "Open Forest", 10.0, 40.0, "#a7d46f"),
    ("NF", "Scrub / Non-forest", 0.0, 10.0, "#e8dcb5"),
]


def fsi_class(cover_pct: float) -> str:
    for code, _, lo, hi, _ in FSI_CLASSES:
        if lo <= cover_pct < hi:
            return code
    return "NF"


def canopy_mask(chm: np.ndarray, threshold_m: float) -> np.ndarray:
    return np.nan_to_num(chm, nan=0.0) >= threshold_m


def density_grid(
    chm: np.ndarray,
    res: float,
    aoi_mask: np.ndarray,
    tree_rows: np.ndarray,
    tree_cols: np.ndarray,
    tree_heights: np.ndarray,
    cell_m: float,
    canopy_threshold_m: float,
    min_aoi_fraction: float = 0.1,
) -> dict:
    """Aggregate canopy cover and tree counts into square cells.

    Returns cells (row/col index, cover %, trees, trees/ha, mean height, FSI class,
    fraction of the cell inside the AOI) plus per-pixel cover for trees.
    """
    canopy = canopy_mask(chm, canopy_threshold_m) & aoi_mask
    cpx = max(1, int(round(cell_m / res)))
    h, w = chm.shape
    nr, nc = -(-h // cpx), -(-w // cpx)

    def block_sum(a: np.ndarray) -> np.ndarray:
        pad = np.zeros((nr * cpx, nc * cpx), dtype=np.float64)
        pad[:h, :w] = a
        return pad.reshape(nr, cpx, nc, cpx).sum(axis=(1, 3))

    aoi_px = block_sum(aoi_mask)
    canopy_px = block_sum(canopy)
    cover = np.divide(canopy_px, aoi_px, out=np.zeros_like(canopy_px), where=aoi_px > 0) * 100

    tree_cell_r, tree_cell_c = tree_rows // cpx, tree_cols // cpx
    counts = np.zeros((nr, nc))
    hsum = np.zeros((nr, nc))
    np.add.at(counts, (tree_cell_r, tree_cell_c), 1)
    np.add.at(hsum, (tree_cell_r, tree_cell_c), tree_heights)

    cells = []
    full = cpx * cpx
    for r in range(nr):
        for c in range(nc):
            frac = aoi_px[r, c] / full
            if frac < min_aoi_fraction:
                continue
            area_ha = aoi_px[r, c] * res * res / 10000
            n = int(counts[r, c])
            cells.append({
                "row": r,
                "col": c,
                "aoi_fraction": round(float(frac), 3),
                "canopy_cover_pct": round(float(cover[r, c]), 1),
                "fsi_class": fsi_class(float(cover[r, c])),
                "detected_trees": n,
                "trees_per_ha": round(n / area_ha, 1) if area_ha > 0 else 0.0,
                "mean_tree_height_m": round(float(hsum[r, c] / n), 1) if n else None,
                "area_ha": round(area_ha, 4),
            })

    tree_cover = cover[tree_cell_r, tree_cell_c] if len(tree_rows) else np.array([])
    return {"cells": cells, "cell_px": cpx, "tree_cover_pct": tree_cover, "cover_grid": cover}


def summarize(cells: list[dict], chm: np.ndarray, aoi_mask: np.ndarray, canopy_threshold_m: float, res: float) -> dict:
    canopy = canopy_mask(chm, canopy_threshold_m) & aoi_mask
    aoi_px = int(aoi_mask.sum())
    area_by_class = {code: 0.0 for code, *_ in FSI_CLASSES}
    for cell in cells:
        area_by_class[cell["fsi_class"]] += cell["area_ha"]
    total = sum(area_by_class.values()) or 1.0
    return {
        "canopy_cover_pct": round(float(canopy.sum() / max(1, aoi_px) * 100), 1),
        "canopy_area_ha": round(float(canopy.sum() * res * res / 10000), 2),
        "fsi_area_ha": {k: round(v, 2) for k, v in area_by_class.items()},
        "fsi_area_pct": {k: round(v / total * 100, 1) for k, v in area_by_class.items()},
        "dominant_fsi_class": max(area_by_class, key=area_by_class.get),
    }
