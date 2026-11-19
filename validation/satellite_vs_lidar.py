"""Satellite mode vs airborne LiDAR on every IDTReeS plot: canopy cover, density class and canopy height.

For each 20 m × 20 m plot, the canopy height model used by satellite mode (Meta/WRI 1 m, via Earth Engine)
is compared with the NEON airborne LiDAR canopy height model of the same plot, the most accurate
reference available. Both are read on the plot's own 1 m UTM grid.

Metrics:
  - canopy cover (share of pixels with canopy >= 5 m): MAE, bias, correlation
  - Forest Survey of India density class (VDF/MDF/OF/NF): agreement and confusion matrix
  - plot canopy height (95th percentile): MAE, RMSE, bias

Usage:
    python validation/satellite_vs_lidar.py [--data "../idtrees datset"]
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from vandrishti.processing.density import FSI_CLASSES, fsi_class  # noqa: E402
from vandrishti.sources import gee  # noqa: E402

CANOPY_M = 5.0
OUT = ROOT / "results" / "idtrees"
CLASSES = [c[0] for c in FSI_CLASSES]


def plot_tiles(data: Path) -> dict[str, Path]:
    dirs = [data / "IDTREES_competition_train_v2" / "train" / "RemoteSensing" / "CHM",
            data / "IDTREES_competition_test_v2" / "task1" / "RemoteSensing" / "CHM",
            data / "IDTREES_competition_test_v2" / "task2" / "RemoteSensing" / "CHM"]
    tiles = {}
    for d in dirs:
        for p in sorted(d.glob("*.tif")):
            tiles.setdefault(p.stem, p)
    return tiles


def compare(item):
    name, path = item
    with rasterio.open(path) as src:
        lidar = src.read(1).astype(np.float32)
        grid = gee.Grid.for_bounds(src.crs.to_epsg(), tuple(src.bounds), 1.0, pad_m=0)  # TALL is UTM 16N, others 17N
    meta = gee.fetch_chm(grid)
    h, w = min(lidar.shape[0], meta.shape[0]), min(lidar.shape[1], meta.shape[1])
    lidar, meta = lidar[:h, :w], meta[:h, :w]
    ok = np.isfinite(lidar) & np.isfinite(meta) & (lidar > -1)
    if ok.sum() < 0.8 * h * w:
        return None
    l, m = lidar[ok], meta[ok]
    return {
        "plot": name, "site": name.split("_")[0],
        "cover_lidar": float((l >= CANOPY_M).mean() * 100), "cover_sat": float((m >= CANOPY_M).mean() * 100),
        "p95_lidar": float(np.percentile(l, 95)), "p95_sat": float(np.percentile(m, 95)),
    }


def stats(pred: np.ndarray, ref: np.ndarray) -> dict:
    err = pred - ref
    return {"mae": round(float(np.abs(err).mean()), 2), "rmse": round(float(np.sqrt((err ** 2).mean())), 2),
            "bias": round(float(err.mean()), 2), "r": round(float(np.corrcoef(pred, ref)[0, 1]), 3)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT.parent / "idtrees datset")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    tiles = plot_tiles(args.data)
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = [r for r in pool.map(compare, tiles.items()) if r]
    print(f"{len(rows)} of {len(tiles)} plots compared")

    cl, cs = np.array([r["cover_lidar"] for r in rows]), np.array([r["cover_sat"] for r in rows])
    hl, hs = np.array([r["p95_lidar"] for r in rows]), np.array([r["p95_sat"] for r in rows])
    ref_cls = [fsi_class(v) for v in cl]
    sat_cls = [fsi_class(v) for v in cs]
    confusion = {a: {b: 0 for b in CLASSES} for a in CLASSES}
    for a, b in zip(ref_cls, sat_cls):
        confusion[a][b] += 1
    agree = float(np.mean([a == b for a, b in zip(ref_cls, sat_cls)]))
    within_one = float(np.mean([abs(CLASSES.index(a) - CLASSES.index(b)) <= 1 for a, b in zip(ref_cls, sat_cls)]))

    by_site = {}
    for site in sorted({r["site"] for r in rows}):
        idx = [i for i, r in enumerate(rows) if r["site"] == site]
        by_site[site] = {"plots": len(idx), "cover": stats(cs[idx], cl[idx]), "height_p95": stats(hs[idx], hl[idx]),
                         "class_agreement": round(float(np.mean([ref_cls[i] == sat_cls[i] for i in idx])), 3)}

    res = {
        "date": date.today().isoformat(), "plots": len(rows), "canopy_threshold_m": CANOPY_M,
        "reference": "NEON airborne LiDAR canopy height model (IDTReeS)",
        "satellite": "Meta/WRI Global Canopy Height 1 m (as used by satellite mode)",
        "canopy_cover_pct": stats(cs, cl), "canopy_height_p95_m": stats(hs, hl),
        "fsi_class_agreement": round(agree, 3), "fsi_class_within_one": round(within_one, 3),
        "fsi_confusion_lidar_rows_satellite_cols": confusion, "by_site": by_site,
    }
    (OUT / "satellite_vs_lidar.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    c, h = res["canopy_cover_pct"], res["canopy_height_p95_m"]
    L = [f"# Satellite mode vs airborne LiDAR — {res['date']}", "",
         f"{len(rows)} IDTReeS plots (20 m × 20 m; NEON OSBS, MLBS, TALL). Reference: {res['reference']}. "
         f"Satellite: {res['satellite']}. Canopy = height ≥ {CANOPY_M:g} m.", "",
         "| Output | MAE | RMSE | Bias (satellite − LiDAR) | Correlation r |", "|---|---|---|---|---|",
         f"| Canopy cover (percentage points) | {c['mae']} | {c['rmse']} | {c['bias']} | {c['r']} |",
         f"| Plot canopy height, 95th percentile (m) | {h['mae']} | {h['rmse']} | {h['bias']} | {h['r']} |", "",
         f"**Forest Survey of India density class:** same class as LiDAR on **{agree:.0%}** of plots; "
         f"within one class on {within_one:.0%}.", "",
         "Confusion (rows: LiDAR class, columns: satellite class):", "",
         "| LiDAR \\ Satellite | " + " | ".join(CLASSES) + " |", "|---|" + "---|" * len(CLASSES)]
    for a in CLASSES:
        L.append(f"| {a} | " + " | ".join(str(confusion[a][b]) for b in CLASSES) + " |")
    L += ["", "By site:", "", "| Site | Plots | Cover MAE (pp) | Cover bias (pp) | Height RMSE (m) | Height bias (m) | Class agreement |",
          "|---|---|---|---|---|---|---|"]
    for s, v in by_site.items():
        L.append(f"| {s} | {v['plots']} | {v['cover']['mae']} | {v['cover']['bias']} | {v['height_p95']['rmse']} | "
                 f"{v['height_p95']['bias']} | {v['class_agreement']:.0%} |")
    L += ["", "Notes: a 20 m plot is smaller than the 25 m density cell used in the dashboard, so these are "
          "plot-scale comparisons; the LiDAR survey and the satellite imagery behind the Meta model are from "
          "different dates (2018–2020), so some differences are real change."]
    (OUT / "satellite_vs_lidar.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for ax, (x, y, lab, st) in zip(axes, [(cl, cs, "Canopy cover (%)", c), (hl, hs, "Plot canopy height p95 (m)", h)]):
        ax.scatter(x, y, s=10, alpha=0.5, color="#2f7d4c")
        lim = [0, max(x.max(), y.max()) * 1.05]
        ax.plot(lim, lim, "--", color="grey", lw=1)
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel(f"LiDAR {lab.lower()}")
        ax.set_ylabel(f"Satellite {lab.lower()}")
        ax.set_title(f"{lab}: MAE {st['mae']}, bias {st['bias']}, r {st['r']}", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "satellite_vs_lidar.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {OUT / 'satellite_vs_lidar.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
