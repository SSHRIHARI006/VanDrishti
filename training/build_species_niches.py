"""Build the tree-species niche table used for the site species prior.

For each candidate tree species we learn its climate and soil "comfort zone" from
its worldwide GBIF records: sample WorldClim + OpenLandMap soil at every record
location, and keep those points as the species' niche (its envelope in climate/soil space).
The WorldCover class at each Indian record gives its habitat (forest, farmland, town).
At runtime a site's climate and soil are scored against every niche.

Candidates: tree species (BGCI GlobalTreeSearch) with >= --min-records GBIF
records in India, the --top most recorded, plus every species a trained
species model can predict (so its predictions can be corrected too).

Usage:
    python training/build_species_niches.py [--top 300] [--out models/niches/tree_niches.json]

Needs internet (GBIF API) and Earth Engine (GEE_PROJECT in .env). Raw API
responses are cached in data/cache/gbif so a rerun is fast.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from vandrishti.processing.site_prior import HABITAT_GROUPS, LOG_VARS, niche_features  # noqa: E402
from vandrishti.sources import gee  # noqa: E402

API = "https://api.gbif.org/v1"
CACHE = ROOT / "data" / "cache" / "gbif"
GTS_CSV = ROOT / "data" / "reference" / "global_tree_search.csv"
CELL_DEG = 0.05          # thinning grid (~5 km): one point per cell per species
PREV_CELL_DEG = 0.1      # prevalence grid (~10 km): occupied cells in India
BASIS = ["HUMAN_OBSERVATION", "PRESERVED_SPECIMEN", "OCCURRENCE", "OBSERVATION", "MATERIAL_SAMPLE"]
session = requests.Session()


def get(path: str, params: list[tuple[str, str]] | dict) -> dict:
    items = sorted(params.items()) if isinstance(params, dict) else sorted(params)
    key = hashlib.sha1((path + json.dumps(items)).encode()).hexdigest()
    f = CACHE / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    for attempt in range(5):
        try:
            r = session.get(API + path, params=items, timeout=60)
            if r.status_code == 200:
                CACHE.mkdir(parents=True, exist_ok=True)
                f.write_text(r.text, encoding="utf-8")
                return r.json()
            if r.status_code == 404:
                return {}
        except requests.RequestException:
            pass
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GBIF request failed: {path} {items}")


def tree_names() -> set[str]:
    with open(GTS_CSV, encoding="utf-8-sig") as f:
        rows = csv.reader(f)
        next(rows)
        return {r[0].strip() for r in rows if r and r[0].strip()}


def india_candidates(min_records: int, top: int) -> list[dict]:
    facet = get("/occurrence/search", {"country": "IN", "kingdomKey": "6", "hasCoordinate": "true",
                                       "limit": "0", "facet": "speciesKey", "facetLimit": "8000"})
    counts = [(int(c["name"]), c["count"]) for c in facet["facets"][0]["counts"] if c["count"] >= min_records]
    with ThreadPoolExecutor(16) as ex:
        infos = list(ex.map(lambda kc: get(f"/species/{kc[0]}", {}), counts))
    trees = tree_names()
    out = []
    for (key, n), info in zip(counts, infos):
        name = info.get("canonicalName")
        if name in trees and info.get("rank") == "SPECIES":
            out.append({"key": key, "name": name, "rank": "SPECIES", "family": info.get("family"), "india_records": n})
    print(f"{len(counts)} plant species with >= {min_records} India records; {len(out)} are trees")
    return sorted(out, key=lambda t: -t["india_records"])[:top]


def model_taxa() -> list[dict]:
    """Species (or genera) any trained species model predicts, matched to GBIF."""
    out = []
    for path in sorted((ROOT / "models" / "species").glob("*.joblib")):
        for code, sci in joblib.load(path).get("scientific_names", {}).items():
            m = get("/species/match", {"name": sci, "kingdom": "Plantae"})
            if m.get("usageKey") and m.get("rank") in ("SPECIES", "GENUS"):
                key = m.get("speciesKey") or m.get("genusKey") or m["usageKey"]
                out.append({"key": key, "name": m.get("canonicalName"), "rank": m["rank"], "family": m.get("family"),
                            "india_records": 0, "model_code": code})
    return out


def _query(key: int) -> list[tuple[str, str]]:
    return [("taxonKey", str(key)), ("hasCoordinate", "true"), ("hasGeospatialIssue", "false"),
            ("occurrenceStatus", "PRESENT"), ("year", "1970,2026")] + [("basisOfRecord", b) for b in BASIS]


def _page(base: list, offset: int) -> list[tuple[float, float]]:
    try:
        res = get("/occurrence/search", base + [("limit", "300"), ("offset", str(offset))])
    except RuntimeError as exc:  # one failing page should not stop the build; the niche uses the other pages
        print(f"  skipped a page: {exc}", flush=True)
        return []
    return [(r["decimalLongitude"], r["decimalLatitude"]) for r in res.get("results", [])
            if "decimalLongitude" in r and abs(r["decimalLatitude"]) < 85]


def occurrence_points(key: int, n_countries: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """(worldwide points, India points). Sampled country by country so the niche covers the species'
    whole range, native and planted; shallow pages only, since deep GBIF paging is very slow."""
    base = _query(key)
    facet = get("/occurrence/search", base + [("limit", "0"), ("facet", "country"), ("facetLimit", "12")])
    countries = [c["name"] for c in (facet.get("facets") or [{}])[0].get("counts", [])]
    world, india = [], []
    for cc in [c for c in countries if c != "IN"][:n_countries]:
        world += _page(base + [("country", cc)], 0)
    if "IN" in countries:
        for off in (0, 600, 3000):
            india += _page(base + [("country", "IN")], off)
    if not world and not india:
        world = _page(base, 0)
    return np.asarray(world, float).reshape(-1, 2), np.asarray(india, float).reshape(-1, 2)


def cells(pts: np.ndarray, deg: float) -> set[tuple[int, int]]:
    return {(int(np.floor(x / deg)), int(np.floor(y / deg))) for x, y in pts}


def sample_environment(cell_ids: list[tuple[int, int]]) -> dict[tuple[int, int], list]:
    """Climate + soil at each thinning-cell centre, via Earth Engine reduceRegions in batches."""
    ee = gee.init_ee()
    img = gee.environment_image(ee)
    batches = [cell_ids[i:i + 4000] for i in range(0, len(cell_ids), 4000)]

    def run(batch):
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([(i + 0.5) * CELL_DEG, (j + 0.5) * CELL_DEG]), {"i": i, "j": j})
                                   for i, j in batch])
        for attempt in range(4):
            try:
                feats = img.reduceRegions(fc, ee.Reducer.first(), scale=1000).getInfo()["features"]
                return [((f["properties"]["i"], f["properties"]["j"]), [f["properties"].get(v) for v in gee.ENV_VARS])
                        for f in feats]
            except Exception as exc:  # EE rate limits / transient errors
                print("  retry EE batch:", str(exc)[:100])
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("Earth Engine sampling failed")

    out = {}
    with ThreadPoolExecutor(4) as ex:
        for k, res in enumerate(ex.map(run, batches)):
            out.update(res)
            print(f"  environment batch {k + 1}/{len(batches)}")
    return out


def english_name(key: int) -> str | None:
    res = get(f"/species/{key}/vernacularNames", {"limit": "200"}).get("results", [])
    names = Counter(r["vernacularName"].strip().capitalize() for r in res if r.get("language") == "eng")
    return names.most_common(1)[0][0] if names else None


# Core trees of central Indian dry and moist deciduous forests (Champion & Seth types 3B/C1, 5A/C1b, 5A/C3).
# Always considered as candidates: GBIF India records are town-biased and some names differ from
# GlobalTreeSearch (e.g. Anogeissus -> Conocarpus). Their scores still come only from the data.
ANCHOR_TREES = [
    "Tectona grandis", "Terminalia elliptica", "Anogeissus latifolia", "Lagerstroemia parviflora",
    "Diospyros melanoxylon", "Madhuca longifolia", "Buchanania cochinchinensis", "Boswellia serrata",
    "Pterocarpus marsupium", "Dalbergia latifolia", "Cleistanthus collinus", "Hardwickia binata",
    "Soymida febrifuga", "Chloroxylon swietenia", "Lannea coromandelica", "Butea monosperma", "Terminalia bellirica",
    "Terminalia chebula", "Haldina cordifolia", "Mitragyna parvifolia", "Schleichera oleosa", "Ougeinia oojeinensis",
    "Gmelina arborea", "Garuga pinnata", "Kydia calycina", "Bridelia retusa", "Aegle marmelos",
    "Semecarpus anacardium", "Holarrhena pubescens", "Wrightia tinctoria", "Cassia fistula", "Shorea robusta",
    "Senegalia catechu", "Albizia procera", "Grewia tiliifolia", "Terminalia arjuna", "Syzygium cumini",
    "Bombax ceiba", "Phyllanthus emblica", "Holoptelea integrifolia", "Millettia pinnata",
]


def anchor_taxa() -> list[dict]:
    out = []
    for name in ANCHOR_TREES:
        m = get("/species/match", {"name": name, "kingdom": "Plantae"})
        key = m.get("speciesKey")
        if not key:
            continue
        info = get(f"/species/{key}", {})
        n = get("/occurrence/search", {"taxonKey": str(key), "country": "IN", "hasCoordinate": "true", "limit": "0"})
        out.append({"key": key, "name": info.get("canonicalName") or name, "rank": "SPECIES",
                    "family": info.get("family"), "india_records": n.get("count", 0)})
    return out


def sample_habitat(points: list[tuple[float, float]]) -> dict[tuple[float, float], int]:
    """ESA WorldCover class at each (rounded) record location."""
    ee = gee.init_ee()
    img = ee.ImageCollection(gee.WORLDCOVER).first().select("Map")
    batches = [points[i:i + 5000] for i in range(0, len(points), 5000)]

    def run(batch):
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([x, y]), {"x": x, "y": y}) for x, y in batch])
        for attempt in range(4):
            try:
                feats = img.reduceRegions(fc, ee.Reducer.first(), scale=10).getInfo()["features"]
                return [((f["properties"]["x"], f["properties"]["y"]), f["properties"].get("first")) for f in feats]
            except Exception as exc:
                print("  retry EE batch:", str(exc)[:100])
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("Earth Engine sampling failed")

    out = {}
    with ThreadPoolExecutor(4) as ex:
        for k, res in enumerate(ex.map(run, batches)):
            out.update({p: v for p, v in res if v is not None})
            print(f"  land-cover batch {k + 1}/{len(batches)}", flush=True)
    return out


def envelope_radius(z: np.ndarray, k: int = 3) -> float:
    """Typical gap between a species' own record locations in niche space (90th pct of k-NN distance)."""
    from sklearn.neighbors import NearestNeighbors

    k = min(k, len(z) - 1)
    d, _ = NearestNeighbors(n_neighbors=k + 1).fit(z).kneighbors(z)
    return float(np.quantile(d[:, k], 0.9))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=500)
    ap.add_argument("--min-records", type=int, default=30)
    ap.add_argument("--min-cells", type=int, default=20, help="skip species with fewer usable locations")
    ap.add_argument("--max-points", type=int, default=800, help="niche points kept per species")
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "niches" / "tree_niches.json")
    args = ap.parse_args()

    taxa = india_candidates(args.min_records, args.top)
    seen = {t["key"]: t for t in taxa}
    for t in anchor_taxa() + model_taxa():
        if t["key"] in seen:
            if t.get("model_code"):
                seen[t["key"]]["model_code"] = t["model_code"]
        else:
            taxa.append(t)
            seen[t["key"]] = t
    print(f"{len(taxa)} taxa; fetching occurrence records", flush=True)

    done = [0]

    def fetch(t):
        out = occurrence_points(t["key"])
        done[0] += 1
        if done[0] % 25 == 0:
            print(f"  records fetched for {done[0]}/{len(taxa)} taxa", flush=True)
        return out

    with ThreadPoolExecutor(6) as ex:
        pts = list(ex.map(fetch, taxa))
    for t, (world, india) in zip(taxa, pts):
        both = np.vstack([world, india])
        t["_cells"] = cells(both, CELL_DEG)
        t["_india_pts"] = {(round(float(x), 3), round(float(y), 3)) for x, y in india}  # one land-cover sample per ~100 m
        t["india_cells"] = len(cells(india, PREV_CELL_DEG))
        t["global_cells"] = len(cells(both, PREV_CELL_DEG))
        t["n_records"] = len(both)

    ee_cache = ROOT / "data" / "cache" / "niche_ee_samples.joblib"
    env, habitat = joblib.load(ee_cache) if ee_cache.exists() else ({}, {})
    all_cells = sorted(set().union(*(t["_cells"] for t in taxa)))
    todo = [c for c in all_cells if c not in env]
    print(f"{len(all_cells)} unique locations ({len(todo)} new); sampling climate and soil in Earth Engine", flush=True)
    if todo:
        env.update(sample_environment(todo))
    india_pts = sorted(set().union(*(t["_india_pts"] for t in taxa)))
    todo = [p for p in india_pts if p not in habitat]
    print(f"{len(india_pts)} India record locations ({len(todo)} new); sampling land cover", flush=True)
    if todo:
        habitat.update(sample_habitat(todo))
    ee_cache.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump((env, habitat), ee_cache)

    raw = np.array([v for v in env.values() if all(x is not None for x in v)], dtype=float)
    feats_all = niche_features(raw)
    mean, std = feats_all.mean(axis=0), feats_all.std(axis=0)

    group_of = {c: g for g, codes in HABITAT_GROUPS.items() for c in codes}
    rng = np.random.default_rng(0)
    group_idx = {g: i for i, g in enumerate(HABITAT_GROUPS)}
    out_taxa, arrays = [], []
    ref_z, ref_taxon, ref_hab = [], [], []
    for t in taxa:
        rows = [env[c] for c in t["_cells"] if c in env and all(x is not None for x in env[c])]
        if len(rows) < args.min_cells:
            print(f"  skip {t['name']}: {len(rows)} usable locations")
            continue
        z = (niche_features(np.asarray(rows, dtype=float)) - mean) / std
        if len(z) > args.max_points:
            z = z[rng.choice(len(z), args.max_points, replace=False)]
        hab = Counter(group_of.get(habitat.get(p), "other") for p in t["_india_pts"] if p in habitat)
        n_hab = sum(hab.values())
        out_taxa.append({
            "key": t["key"], "name": t["name"], "rank": t["rank"], "family": t.get("family"),
            "english_name": english_name(t["key"]) if t["rank"] == "SPECIES" else None,
            "model_code": t.get("model_code"),
            "n_records": t["n_records"], "n_locations": len(z),
            "india_records": t["india_records"], "india_cells": t["india_cells"], "global_cells": t["global_cells"],
            "envelope_radius": round(envelope_radius(z), 4),
            "habitat": {g: round(hab[g] / n_hab, 3) for g in HABITAT_GROUPS} if n_hab >= 20 else None,
            "points_offset": sum(len(x) for x in arrays), "points_count": len(z),
        })
        arrays.append(z.astype(np.float32))
        for x, y in t["_india_pts"]:
            cell = (int(np.floor(x / CELL_DEG)), int(np.floor(y / CELL_DEG)))
            row = env.get(cell)
            if row is None or any(v is None for v in row):
                continue
            ref_z.append(row)
            ref_taxon.append(len(out_taxa) - 1)
            ref_hab.append(group_idx[group_of.get(habitat.get((x, y)), "other")])

    pooled = Counter(group_of.get(v, "other") for v in habitat.values())
    table = {
        "built": date.today().isoformat(),
        "variables": gee.ENV_VARS,
        "log_variables": LOG_VARS,
        "scaler": {"mean": mean.round(6).tolist(), "std": std.round(6).tolist()},
        "habitat_baseline": {g: round(pooled[g] / max(sum(pooled.values()), 1), 3) for g in HABITAT_GROUPS},
        "sources": ["GBIF.org occurrence API (worldwide records, 1970+)", "BGCI GlobalTreeSearch", gee.WORLDCLIM,
                    "OpenLandMap soil v02", gee.WORLDCOVER],
        "n_records_total": int(sum(t["n_records"] for t in taxa)),
        "habitat_groups": list(HABITAT_GROUPS),
        "n_reference_records": len(ref_taxon),
        "points_file": args.out.with_suffix(".npz").name,
        "taxa": out_taxa,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ref = (niche_features(np.asarray(ref_z, dtype=float)) - mean) / std
    np.savez_compressed(args.out.with_suffix(".npz"), points=np.vstack(arrays), ref_z=ref.astype(np.float32),
                        ref_taxon=np.asarray(ref_taxon, np.int16), ref_hab=np.asarray(ref_hab, np.int8))
    args.out.write_text(json.dumps(table), encoding="utf-8")
    print(f"saved {args.out}: {len(out_taxa)} taxa from {table['n_records_total']:,} records; "
          f"{len(ref_taxon):,} Indian reference records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
