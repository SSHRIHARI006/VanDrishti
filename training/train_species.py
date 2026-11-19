"""Train a local species model from field-labelled trees.

Field teams record species for trees in sample plots (GPS point per tree, or a
crown polygon digitised on the orthophoto). This script extracts the same crown
features the survey pipeline uses, trains a class-balanced Random Forest, and
writes models/species/<region>.joblib. The pipeline uses it automatically for
boundaries inside the model's training region (its bounding box), and never elsewhere.

Usage:
    python training/train_species.py --ortho survey/ortho.tif --chm survey/chm.tif \
        --labels plots/labelled_trees.geojson --region "WCL Chandrapur" [--out models/species/wcl_chandrapur.joblib]

Labels: GeoJSON (WGS84) Points or Polygons with a "species" property.
Points get a square crown of --point-crown-m metres.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.warp import transform_geom
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from vandrishti.processing.species import FEATURES, crown_features  # noqa: E402

OTHER = "Other"


def label_boxes(labels_path: Path, crs, point_crown_m: float) -> list[dict]:
    fc = json.loads(labels_path.read_text(encoding="utf-8"))
    out = []
    for f in fc["features"]:
        sp = (f.get("properties") or {}).get("species")
        if not sp:
            continue
        g = shape(transform_geom("EPSG:4326", crs, f["geometry"]))
        if g.geom_type == "Point":
            h = point_crown_m / 2
            xmin, ymin, xmax, ymax = g.x - h, g.y - h, g.x + h, g.y + h
        else:
            xmin, ymin, xmax, ymax = g.bounds
        out.append({"species": str(sp), "xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
                    "cx": (xmin + xmax) / 2, "cy": (ymin + ymax) / 2})
    return out


def chm_stats(chm_path: Path | None, boxes: list[dict]) -> None:
    if chm_path is None:
        for b in boxes:
            b["height_m"], b["crown_area_m2"] = np.nan, (b["xmax"] - b["xmin"]) * (b["ymax"] - b["ymin"])
        return
    with rasterio.open(chm_path) as src:
        for b in boxes:
            win = src.window(b["xmin"], b["ymin"], b["xmax"], b["ymax"]).round_offsets().round_lengths()
            vals = src.read(1, window=win, boundless=True, fill_value=np.nan).astype(float)
            vals = vals[np.isfinite(vals)]
            h = float(np.percentile(vals, 95)) if vals.size else np.nan
            b["height_m"] = h
            b["crown_area_m2"] = float((vals >= 0.4 * h).sum() * abs(src.res[0] * src.res[1])) if vals.size else np.nan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ortho", nargs="+", required=True, help="RGB orthophoto GeoTIFF(s)")
    ap.add_argument("--chm", nargs="*", default=None, help="Canopy height GeoTIFF(s), same order as --ortho")
    ap.add_argument("--labels", required=True, type=Path, help="GeoJSON of labelled trees (species property)")
    ap.add_argument("--region", required=True, help="Region the model is valid for, e.g. 'WCL Chandrapur'")
    ap.add_argument("--out", type=Path, default=None, help="Default: models/species/<region>.joblib")
    ap.add_argument("--min-samples", type=int, default=8, help="Species with fewer labels are grouped as 'Other'")
    ap.add_argument("--threshold", type=float, default=0.5, help="Confidence below which predictions become Unknown")
    ap.add_argument("--point-crown-m", type=float, default=6.0)
    args = ap.parse_args()

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import classification_report
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    chms = args.chm or [None] * len(args.ortho)
    X_parts, y, lonlat = [], [], []
    for ortho, chm in zip(args.ortho, chms):
        with rasterio.open(ortho) as src:
            boxes = [b for b in label_boxes(args.labels, src.crs, args.point_crown_m)
                     if src.bounds.left <= b["cx"] <= src.bounds.right and src.bounds.bottom <= b["cy"] <= src.bounds.top]
            if not boxes:
                continue
            rgb, transform, crs = src.read([1, 2, 3]), src.transform, src.crs
        chm_stats(Path(chm) if chm else None, boxes)
        X_parts.append(crown_features(rgb, transform, boxes))
        y += [b["species"] for b in boxes]
        to_wgs = Transformer.from_crs(crs, 4326, always_xy=True).transform
        lonlat += [to_wgs(b["cx"], b["cy"]) for b in boxes]
    if not y:
        print("No labelled trees fall inside the orthophoto(s).")
        return 1

    X = np.vstack(X_parts)
    X = np.where(np.isfinite(X), X, np.nanmedian(X, axis=0))
    counts = Counter(y)
    y = np.array([s if counts[s] >= args.min_samples else OTHER for s in y])
    final = Counter(y)
    print(f"{len(y)} labelled crowns: " + ", ".join(f"{k} {v}" for k, v in final.most_common()))
    if len(final) < 2:
        print("Need at least two classes with enough labels to train.")
        return 1

    clf = RandomForestClassifier(n_estimators=300, max_depth=12, class_weight="balanced", random_state=0, n_jobs=-1)
    folds = max(2, min(5, min(final.values())))
    pred = cross_val_predict(clf, X, y, cv=StratifiedKFold(folds, shuffle=True, random_state=0))
    report = classification_report(y, pred, output_dict=True, zero_division=0)
    print(classification_report(y, pred, zero_division=0))

    clf.fit(X, y)
    lons, lats = np.array(lonlat).T
    pad = 0.05  # ~5 km around the labelled plots
    bundle = {
        "model": clf,
        "features": FEATURES,
        "classes": sorted(final),
        # labels are botanical names; the site species prior matches classes by these
        "scientific_names": {c: c for c in final if c != OTHER},
        "threshold": args.threshold,
        "region": args.region,
        "bbox": [float(lons.min() - pad), float(lats.min() - pad), float(lons.max() + pad), float(lats.max() + pad)],
        "trained_on": f"{len(y)} field-labelled crowns, {args.region}, {date.today().isoformat()}",
        "metrics": {
            "cv_folds": folds,
            "accuracy": round(report["accuracy"], 3),
            "macro_f1": round(report["macro avg"]["f1-score"], 3),
            "per_class_recall": {k: round(v["recall"], 3) for k, v in report.items() if k in final},
        },
    }
    if args.out is None:
        slug = "".join(ch if ch.isalnum() else "_" for ch in args.region.lower()).strip("_")
        args.out = ROOT / "models" / "species" / f"{slug}.joblib"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.out)
    print(f"Saved {args.out}  (accuracy {bundle['metrics']['accuracy']}, macro F1 {bundle['metrics']['macro_f1']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
