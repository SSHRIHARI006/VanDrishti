"""Validate Vandrishti's methods against the IDTReeS benchmark (NEON OSBS, MLBS, TALL).

Measures, against hand-delineated crowns and field measurements:
  1. Crown detection  – DeepForest on 10 cm RGB (survey mode), CHM watershed on LiDAR,
                        and CHM watershed on Meta 1 m satellite canopy height (satellite mode).
  2. Tree height      – LiDAR CHM and Meta satellite CHM vs field-measured height.
  3. Species          – class-balanced Random Forest, cross-validated by plot, with and
                        without hyperspectral features; coverage/accuracy of the Unknown threshold.
It also trains the RGB + structure species model the survey pipeline uses and saves it,
tagged with the region it is valid for.

Usage:
    python validation/idtrees_validation.py --data "../idtrees datset" [--skip-satellite] [--skip-deepforest]

Caveats reported with the results: IDTReeS crowns cover field-surveyed trees only, so
precision is a lower bound; DeepForest's pretraining used NEON imagery, possibly from these sites.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import rasterio
import shapefile
from pyproj import Transformer
from rasterio.features import geometry_mask, shapes
from shapely.geometry import Polygon, box, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from vandrishti.processing.species import FEATURES, crown_features  # noqa: E402
from vandrishti.processing.survey import pad_to_patch  # noqa: E402
from vandrishti.processing.trees import SATELLITE_PARAMS, SURVEY_PARAMS, detect_trees  # noqa: E402

IOU = 0.4
MIN_SPECIES_SAMPLES = 15
OUT = ROOT / "results" / "idtrees"
# NEON AOP hyperspectral water-absorption and noisy edge bands (1-based ranges, inclusive)
BAD_HSI_BANDS = [(1, 10), (188, 212), (278, 318), (355, 369)]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_plots(data: Path) -> dict[str, dict]:
    train = data / "IDTREES_competition_train_v2" / "train"
    test = data / "IDTREES_competition_test_v2" / "task2"
    field = {r["indvdID"]: r for r in csv.DictReader(open(train / "Field" / "train_data.csv", encoding="utf-8"))}
    rs_by_id = {r["id"]: r["rsFile"] for r in csv.DictReader(open(train / "Field" / "itc_rsFile.csv", encoding="utf-8"))}

    plots: dict[str, dict] = {}

    def plot_entry(split_dir: Path, split: str, rs_file: str) -> dict:
        name = rs_file.replace(".tif", "")
        if name not in plots:
            rs = split_dir / "RemoteSensing"
            plots[name] = {"plot": name, "site": name.split("_")[0], "split": split,
                           "rgb": rs / "RGB" / rs_file, "chm": rs / "CHM" / rs_file, "hsi": rs / "HSI" / rs_file,
                           "crowns": []}
        return plots[name]

    for shp in sorted((train / "ITC").glob("train_*.shp")):
        r = shapefile.Reader(str(shp))
        for rec, shp_ in zip(r.records(), r.shapes()):
            rs_file = rs_by_id.get(str(rec["id"]))
            if not rs_file:
                continue
            f = field.get(rec["indvdID"], {})
            h = f.get("height")
            plot_entry(train, "train", rs_file)["crowns"].append({
                "indvdID": rec["indvdID"], "geom": Polygon(shp_.points),
                "taxon": f.get("taxonID") or None,
                "height": float(h) if h not in (None, "", "NA") else None,
            })
    for shp in sorted((test / "ITC").glob("test_*.shp")):
        r = shapefile.Reader(str(shp))
        for rec, shp_ in zip(r.records(), r.shapes()):
            plot_entry(test, "test", rec["plotID"])["crowns"].append(
                {"indvdID": rec["indvdID"], "geom": Polygon(shp_.points), "taxon": None, "height": None})
    return {k: v for k, v in plots.items() if v["rgb"].exists() and v["chm"].exists()}


def tile_bounds(path: Path):
    with rasterio.open(path) as src:
        return box(*src.bounds)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def match(preds: list, truth: list, iou_thr: float) -> list[float]:
    """One-to-one greedy IoU matching; returns IoUs of matched pairs."""
    if not preds or not truth:
        return []
    tree = STRtree(truth)
    cands = []
    for pi, p in enumerate(preds):
        for ti in tree.query(p):
            inter = p.intersection(truth[ti]).area
            if inter <= 0:
                continue
            iou = inter / (p.area + truth[ti].area - inter)
            if iou >= iou_thr:
                cands.append((iou, pi, int(ti)))
    cands.sort(reverse=True)
    used_p, used_t, out = set(), set(), []
    for iou, pi, ti in cands:
        if pi not in used_p and ti not in used_t:
            used_p.add(pi)
            used_t.add(ti)
            out.append(iou)
    return out


def detection_scores(per_plot: dict[str, list], plots: dict, iou_thr: float) -> dict:
    tp = n_pred = n_true = 0
    ious = []
    by_site = defaultdict(lambda: [0, 0, 0])
    for name, preds in per_plot.items():
        truth = [c["geom"] for c in plots[name]["crowns"]]
        m = match(preds, truth, iou_thr)
        tp += len(m)
        n_pred += len(preds)
        n_true += len(truth)
        ious += m
        s = by_site[plots[name]["site"]]
        s[0] += len(m)
        s[1] += len(preds)
        s[2] += len(truth)
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_true if n_true else 0.0
    return {
        "plots": len(per_plot), "labelled_crowns": n_true, "predictions": n_pred, "matched": tp,
        "recall": round(r, 3), "precision_lower_bound": round(p, 3),
        "f1_lower_bound": round(2 * p * r / (p + r), 3) if p + r else 0.0,
        "mean_iou_matched": round(float(np.mean(ious)), 3) if ious else None,
        "recall_by_site": {k: round(v[0] / v[2], 3) if v[2] else None for k, v in sorted(by_site.items())},
    }


# ---------------------------------------------------------------------------
# Detection methods
# ---------------------------------------------------------------------------

def deepforest_predictions(plots: dict) -> dict[str, list[tuple[float, Polygon]]]:
    from deepforest import main

    model = main.deepforest()
    model.load_model("weecology/deepforest-tree")
    out = {}
    for name, p in plots.items():
        with rasterio.open(p["rgb"]) as src:
            img = np.moveaxis(src.read([1, 2, 3]), 0, -1).astype("float32")
            t = src.transform
        h, w = img.shape[:2]
        df = model.predict_image(image=pad_to_patch(img))
        preds = []
        if df is not None:
            df = df[((df.xmin + df.xmax) / 2 < w) & ((df.ymin + df.ymax) / 2 < h)]
            for r in df.itertuples():
                x0, y0 = t * (r.xmin, r.ymax)
                x1, y1 = t * (r.xmax, r.ymin)
                preds.append((float(r.score), box(x0, y0, x1, y1)))
        out[name] = preds
    return out


def chm_predictions(chm: np.ndarray, transform, params) -> list[Polygon]:
    res = abs(transform.a)
    t = detect_trees(chm, res, np.ones(chm.shape, bool), params)
    if not t["count"]:
        return []
    polys: dict[int, Polygon] = {}
    for geom, v in shapes(t["labels"].astype(np.int32), mask=t["labels"] > 0, transform=transform):
        g = shape(geom)
        if int(v) not in polys or g.area > polys[int(v)].area:
            polys[int(v)] = g
    return list(polys.values())


def lidar_predictions(plots: dict) -> dict[str, list[Polygon]]:
    out = {}
    for name, p in plots.items():
        with rasterio.open(p["chm"]) as src:
            out[name] = chm_predictions(src.read(1).astype(np.float32), src.transform, SURVEY_PARAMS)
    return out


def meta_chm_tiles(plots: dict) -> dict[str, tuple[np.ndarray, object]]:
    from vandrishti.sources import gee

    def one(item):
        name, p = item
        with rasterio.open(p["chm"]) as src:  # sites differ: TALL is UTM 16N, OSBS/MLBS 17N
            grid = gee.Grid.for_bounds(src.crs.to_epsg(), tuple(src.bounds), 1.0, pad_m=0)
        return name, (gee.fetch_chm(grid), grid.transform)

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(one, plots.items()))


# ---------------------------------------------------------------------------
# Height
# ---------------------------------------------------------------------------

def crown_height(chm: np.ndarray, transform, geom) -> float | None:
    m = geometry_mask([geom], out_shape=chm.shape, transform=transform, invert=True, all_touched=True)
    vals = chm[m & np.isfinite(chm)]
    return float(np.percentile(vals, 95)) if vals.size else None


def height_metrics(pairs: list[tuple[float, float]]) -> dict:
    if not pairs:
        return {}
    pred, truth = np.array(pairs).T
    err = pred - truth
    ss = np.sum((truth - truth.mean()) ** 2)
    return {"n": len(pairs), "mae_m": round(float(np.abs(err).mean()), 2),
            "rmse_m": round(float(np.sqrt((err ** 2).mean())), 2), "bias_m": round(float(err.mean()), 2),
            "r2": round(float(1 - np.sum(err ** 2) / ss), 3) if ss else None}


# ---------------------------------------------------------------------------
# Species
# ---------------------------------------------------------------------------

def good_bands(n: int) -> np.ndarray:
    keep = np.ones(n, bool)
    for a, b in BAD_HSI_BANDS:
        keep[a - 1:min(b, n)] = False
    return keep


def species_samples(plots: dict) -> tuple[np.ndarray, np.ndarray, list[str], list[str], list]:
    X_rgb, X_hsi, y, groups, lonlat = [], [], [], [], []
    for name, p in plots.items():
        crowns = [c for c in p["crowns"] if c["taxon"]]
        if not crowns:
            continue
        with rasterio.open(p["rgb"]) as src:
            rgb, rt = src.read([1, 2, 3]), src.transform
            to_wgs = Transformer.from_crs(src.crs, 4326, always_xy=True).transform
        with rasterio.open(p["chm"]) as src:
            chm, ct = src.read(1).astype(np.float32), src.transform
        with rasterio.open(p["hsi"]) as src:
            hsi, ht = src.read().astype(np.float32), src.transform
        keep = good_bands(hsi.shape[0])
        boxes = []
        for c in crowns:
            xmin, ymin, xmax, ymax = c["geom"].bounds
            h = crown_height(chm, ct, c["geom"])
            boxes.append({"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
                          "height_m": h if h is not None else np.nan, "crown_area_m2": c["geom"].area})
            m = geometry_mask([c["geom"]], out_shape=hsi.shape[1:], transform=ht, invert=True, all_touched=True)
            spec = hsi[:, m][keep]
            X_hsi.append(spec.mean(axis=1) if spec.size else np.full(keep.sum(), np.nan))
            y.append(c["taxon"])
            groups.append(name)
            lonlat.append(to_wgs(*c["geom"].centroid.coords[0]))
        X_rgb.append(crown_features(rgb, rt, boxes))
    X_rgb = np.vstack(X_rgb)
    X_hsi = np.vstack(X_hsi)
    return X_rgb, X_hsi, y, groups, lonlat


def evaluate_species(X: np.ndarray, y: np.ndarray, groups: list[str], use_pca: int | None) -> dict:
    from sklearn.decomposition import PCA
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import classification_report
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    proba = np.zeros((len(y), len(np.unique(y))))
    classes = np.unique(y)
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(X, y, groups):
        steps = [SimpleImputer(strategy="median")]
        if use_pca:
            steps += [StandardScaler(), PCA(n_components=use_pca, random_state=0)]
        steps.append(RandomForestClassifier(n_estimators=400, max_depth=14, class_weight="balanced",
                                            random_state=0, n_jobs=-1))
        model = make_pipeline(*steps).fit(X[tr], y[tr])
        idx = np.searchsorted(classes, model.classes_)
        proba[np.ix_(te, idx)] = model.predict_proba(X[te])
    pred = classes[proba.argmax(axis=1)]
    conf = proba.max(axis=1)
    rep = classification_report(y, pred, output_dict=True, zero_division=0)
    thresholds = []
    for t in (0.0, 0.3, 0.4, 0.5, 0.6, 0.7):
        sel = conf >= t
        thresholds.append({"threshold": t, "coverage": round(float(sel.mean()), 3),
                           "accuracy_on_assigned": round(float((pred[sel] == y[sel]).mean()), 3) if sel.any() else None})
    return {
        "samples": int(len(y)), "classes": int(len(classes)),
        "accuracy": round(rep["accuracy"], 3), "macro_f1": round(rep["macro avg"]["f1-score"], 3),
        "weighted_f1": round(rep["weighted avg"]["f1-score"], 3),
        "per_class": {c: {"precision": round(rep[c]["precision"], 3), "recall": round(rep[c]["recall"], 3),
                          "f1": round(rep[c]["f1-score"], 3), "support": int(rep[c]["support"])} for c in classes},
        "unknown_threshold": thresholds,
    }


def taxon_names(data: Path) -> dict[str, str]:
    f = next(data.rglob("taxonID_ScientificName.csv"))
    with open(f, encoding="utf-8") as fh:
        return {r["taxonID"]: r["scientificName"] for r in csv.DictReader(fh)}


def train_pipeline_model(X: np.ndarray, y: np.ndarray, lonlat: list, metrics: dict, threshold: float,
                         names: dict[str, str] | None = None) -> Path:
    from sklearn.ensemble import RandomForestClassifier

    X = np.where(np.isfinite(X), X, np.nanmedian(X, axis=0))
    clf = RandomForestClassifier(n_estimators=400, max_depth=14, class_weight="balanced", random_state=0, n_jobs=-1)
    clf.fit(X, y)
    lons, lats = np.array(lonlat).T
    pad = 0.05
    bundle = {
        "model": clf, "features": FEATURES, "classes": sorted(set(y)), "threshold": threshold,
        "scientific_names": {c: names[c] for c in set(y) if names and c in names},
        "region": "NEON OSBS/MLBS (Florida & Virginia, USA)",
        "bbox": [float(lons.min() - pad), float(lats.min() - pad), float(lons.max() + pad), float(lats.max() + pad)],
        "trained_on": f"{len(y)} IDTReeS field-labelled crowns (NEON OSBS/MLBS), {date.today().isoformat()}",
        "metrics": {"accuracy": metrics["accuracy"], "macro_f1": metrics["macro_f1"], "cv": "5-fold grouped by plot"},
    }
    path = ROOT / "models" / "species" / "idtrees_neon_osbs_mlbs.joblib"
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)
    return path


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def figures(results: dict, height_pairs: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(height_pairs), figsize=(5 * len(height_pairs), 4.2))
    for ax, (label, pairs) in zip(np.atleast_1d(axes), height_pairs.items()):
        if not pairs:
            continue
        pred, truth = np.array(pairs).T
        ax.scatter(truth, pred, s=8, alpha=0.5, color="#2f7d4c")
        lim = [0, max(truth.max(), pred.max()) + 2]
        ax.plot(lim, lim, "--", color="grey", lw=1)
        m = results["height"][label]
        ax.set_title(f"{label}\nRMSE {m['rmse_m']} m, bias {m['bias_m']} m, n={m['n']}", fontsize=9)
        ax.set_xlabel("Field-measured height (m)")
        ax.set_ylabel("Estimated height (m)")
        ax.set_xlim(lim)
        ax.set_ylim(lim)
    fig.tight_layout()
    fig.savefig(OUT / "height_scatter.png", dpi=150)
    plt.close(fig)

    det = results["detection"]
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    names = list(det)
    ax.barh(names, [det[n]["recall"] for n in names], color="#3f9b35")
    for i, n in enumerate(names):
        ax.text(det[n]["recall"] + 0.01, i, f"{det[n]['recall']:.2f}", va="center", fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_xlabel(f"Recall of labelled crowns (IoU ≥ {IOU})")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(OUT / "detection_recall.png", dpi=150)
    plt.close(fig)


def write_markdown(results: dict) -> None:
    L = [f"# IDTReeS validation — {results['date']}", "",
         f"Benchmark: IDTReeS 2020 (NEON OSBS, MLBS, TALL), {results['plots']} plots of 20 m × 20 m. "
         f"Matching: one-to-one, IoU ≥ {IOU}.", "",
         "## 1. Crown detection", "",
         "| Method (mode) | Plots | Labelled crowns | Predictions | Recall | Precision (lower bound) | Mean IoU |",
         "|---|---|---|---|---|---|---|"]
    for name, d in results["detection"].items():
        L.append(f"| {name} | {d['plots']} | {d['labelled_crowns']} | {d['predictions']} | **{d['recall']}** | "
                 f"{d['precision_lower_bound']} | {d['mean_iou_matched']} |")
    L += ["", "Recall by site: " + "; ".join(f"{n}: {d['recall_by_site']}" for n, d in results["detection"].items()), "",
          "## 2. Tree height vs field measurement", "", "| Source | n | MAE (m) | RMSE (m) | Bias (m) | R² |",
          "|---|---|---|---|---|---|"]
    for name, h in results["height"].items():
        if h:
            L.append(f"| {name} | {h['n']} | {h['mae_m']} | {h['rmse_m']} | {h['bias_m']} | {h['r2']} |")
    L += ["", "## 3. Species classification (5-fold CV grouped by plot)", "",
          "| Features | Samples | Classes | Accuracy | Macro F1 | Weighted F1 |", "|---|---|---|---|---|---|"]
    for name, s in results["species"].items():
        L.append(f"| {name} | {s['samples']} | {s['classes']} | {s['accuracy']} | {s['macro_f1']} | {s['weighted_f1']} |")
    best = max(results["species"], key=lambda k: results["species"][k]["macro_f1"])
    L += ["", f"Per-species results ({best}):", "", "| Species | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
    for c, m in sorted(results["species"][best]["per_class"].items(), key=lambda kv: -kv[1]["support"]):
        L.append(f"| {c} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |")
    L += ["", "Unknown threshold (uncertain trees are reported as Unknown instead of guessed). "
          "The survey pipeline deploys the RGB + height model (drones give RGB) with threshold 0.5:", "",
          "| Threshold | " + " | ".join(f"{k}: share assigned / accuracy" for k in results["species"]) + " |",
          "|---|" + "---|" * len(results["species"])]
    for i, t in enumerate(next(iter(results["species"].values()))["unknown_threshold"]):
        cells = [f"{v['unknown_threshold'][i]['coverage']} / {v['unknown_threshold'][i]['accuracy_on_assigned']}"
                 for v in results["species"].values()]
        L.append(f"| {t['threshold']} | " + " | ".join(cells) + " |")
    L += ["", "## Caveats", "",
          "- IDTReeS crowns cover field-surveyed trees only, so unmatched predictions are not necessarily false: "
          "precision is a lower bound; recall is the reliable detection metric.",
          "- DeepForest was pretrained on NEON imagery that may include these sites; its recall may be optimistic.",
          "- Species are US species; an Indian deployment trains the same model on local field labels.",
          f"- Species with fewer than {MIN_SPECIES_SAMPLES} labels are grouped as 'Other'."]
    (OUT / "validation.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT.parent / "idtrees datset")
    ap.add_argument("--skip-satellite", action="store_true", help="Skip Meta canopy height (needs Earth Engine)")
    ap.add_argument("--skip-deepforest", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--update-satellite", action="store_true",
                    help="Recompute satellite/LiDAR rows only; keep DeepForest and species results from validation.json")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    plots = load_plots(args.data)
    labelled = {k: v for k, v in plots.items() if v["crowns"]}
    print(f"{len(labelled)} plots with {sum(len(p['crowns']) for p in labelled.values())} labelled crowns")
    results = {"date": date.today().isoformat(), "plots": len(labelled), "iou_threshold": IOU,
               "detection": {}, "height": {}, "species": {}}
    previous = None
    if args.update_satellite:
        previous = json.loads((OUT / "validation.json").read_text(encoding="utf-8"))
        results["detection"] = {k: v for k, v in previous["detection"].items() if k.startswith("DeepForest")}
        args.skip_deepforest = True

    t = time.time()
    if not args.skip_deepforest:
        df = deepforest_predictions(labelled)
        for thr in (0.1, 0.2, 0.3):
            results["detection"][f"DeepForest RGB, score ≥ {thr} (survey mode)"] = detection_scores(
                {k: [g for s, g in v if s >= thr] for k, v in df.items()}, labelled, IOU)
        print(f"DeepForest done ({time.time() - t:.0f} s)")
    results["detection"]["CHM watershed on LiDAR (survey CHM)"] = detection_scores(
        lidar_predictions(labelled), labelled, IOU)

    meta = {}
    if not args.skip_satellite:
        t = time.time()
        meta = meta_chm_tiles(labelled)
        results["detection"]["CHM watershed on Meta 1 m (satellite mode)"] = detection_scores(
            {k: chm_predictions(np.nan_to_num(c), tr, SATELLITE_PARAMS) for k, (c, tr) in meta.items()}, labelled, IOU)
        print(f"Satellite CHM done ({time.time() - t:.0f} s)")

    pairs = {"LiDAR CHM (survey)": [], "Meta 1 m CHM (satellite)": []}
    for name, p in labelled.items():
        with rasterio.open(p["chm"]) as src:
            chm, tr = src.read(1).astype(np.float32), src.transform
        for c in p["crowns"]:
            if c["height"] is None:
                continue
            h = crown_height(chm, tr, c["geom"])
            if h is not None:
                pairs["LiDAR CHM (survey)"].append((h, c["height"]))
            if name in meta:
                hm = crown_height(meta[name][0], meta[name][1], c["geom"])
                if hm is not None:
                    pairs["Meta 1 m CHM (satellite)"].append((hm, c["height"]))
    results["height"] = {k: height_metrics(v) for k, v in pairs.items()}

    if previous is not None:
        results["species"], results["species_model"] = previous["species"], previous.get("species_model")
        (OUT / "validation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        write_markdown(results)
        figures(results, pairs)
        print(f"Updated {OUT / 'validation.md'}")
        return 0

    train_plots = {k: v for k, v in labelled.items() if v["split"] == "train"}
    X_rgb, X_hsi, y, groups, lonlat = species_samples(train_plots)
    counts = Counter(y)
    y = np.array([s if counts[s] >= MIN_SPECIES_SAMPLES else "Other" for s in y])
    X_rgb_imp = np.where(np.isfinite(X_rgb), X_rgb, np.nanmedian(X_rgb, axis=0))
    results["species"]["RGB + height (drone-equivalent)"] = evaluate_species(X_rgb_imp, y, groups, None)
    X_all = np.hstack([X_rgb_imp, X_hsi])
    results["species"]["RGB + height + hyperspectral (PCA 20)"] = evaluate_species(X_all, y, groups, 20)
    model_path = train_pipeline_model(X_rgb, y, lonlat, results["species"]["RGB + height (drone-equivalent)"],
                                      args.threshold, taxon_names(args.data))
    results["species_model"] = str(model_path.relative_to(ROOT))

    (OUT / "validation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_markdown(results)
    figures(results, pairs)
    print(f"Wrote {OUT / 'validation.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
