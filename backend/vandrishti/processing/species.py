"""Per-crown species classification from survey imagery.

A species model is region-specific: it is trained on field-labelled trees from
the same area (see training/train_species.py) and saved as a joblib bundle:
    {"model", "features", "classes", "threshold", "region", "bbox", "trained_on", "metrics"}
Predictions below the confidence threshold become "Unknown" instead of a guess.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import rasterio

FEATURES = [
    "r_mean", "g_mean", "b_mean", "r_std", "g_std", "b_std",
    "exg_mean", "gr_ratio", "brightness", "texture", "height_m", "crown_area_m2",
]
UNKNOWN = "Unknown"


def crown_features(rgb: np.ndarray, transform, trees: list[dict]) -> np.ndarray:
    """Colour, texture and structure features for each crown's inner box.

    rgb: (3, rows, cols) array of the working orthophoto with its affine transform.
    """
    inv = ~transform
    rows = []
    for t in trees:
        # inner 60 % of the box, to avoid neighbouring crowns at the edges
        dx, dy = (t["xmax"] - t["xmin"]) * 0.2, (t["ymax"] - t["ymin"]) * 0.2
        c0, r0 = inv * (t["xmin"] + dx, t["ymax"] - dy)
        c1, r1 = inv * (t["xmax"] - dx, t["ymin"] + dy)
        r0, r1 = sorted((int(r0), int(np.ceil(r1))))
        c0, c1 = sorted((int(c0), int(np.ceil(c1))))
        win = rgb[:, max(r0, 0):max(r1, r0 + 1), max(c0, 0):max(c1, c0 + 1)].reshape(3, -1).astype(np.float32)
        win = win[:, win.sum(axis=0) > 0]
        if win.shape[1] == 0:
            win = np.zeros((3, 1), np.float32)
        r, g, b = win
        bright = win.mean(axis=0)
        rows.append([
            r.mean(), g.mean(), b.mean(), r.std(), g.std(), b.std(),
            (2 * g - r - b).mean(), g.mean() / max(r.mean(), 1.0), bright.mean(), bright.std() / max(bright.mean(), 1.0),
            t["height_m"], t["crown_area_m2"],
        ])
    return np.asarray(rows, dtype=np.float32)


def model_for_location(models_dir: Path, lon: float, lat: float) -> dict | None:
    """Pick the species model whose training region (bbox) contains the location.

    A model trained in one region must never label trees in another: a US model
    applied in India would silently produce wrong species.
    """
    for path in sorted(models_dir.glob("*.joblib")):
        bundle = joblib.load(path)
        x0, y0, x1, y1 = bundle.get("bbox", (0, 0, 0, 0))
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            return bundle
    return None


def label(proba: np.ndarray, classes, threshold: float) -> tuple[list[str], np.ndarray]:
    best = proba.argmax(axis=1)
    conf = proba[np.arange(len(best)), best]
    labels = [str(classes[i]) if c >= threshold else UNKNOWN for i, c in zip(best, conf)]
    return labels, conf


def classify(bundle: dict, X: np.ndarray) -> tuple[list[str], np.ndarray]:
    proba = bundle["model"].predict_proba(X)
    return label(proba, np.asarray(bundle["model"].classes_), bundle["threshold"])


def read_rgb(path: Path) -> tuple[np.ndarray, object]:
    with rasterio.open(path) as src:
        return src.read([1, 2, 3]), src.transform
