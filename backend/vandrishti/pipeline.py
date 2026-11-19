"""Assessment pipeline: KML boundary → satellite data → tree inventory.

Each stage records progress, a one-line summary, metrics and events on the
Job so the dashboard can show the run step by step. Recoverable problems are
logged as events and the run continues; only fatal problems fail the job.
"""

from __future__ import annotations

import json
import shutil
import traceback
from dataclasses import dataclass, field

import numpy as np
from pyproj import Transformer
from rasterio.features import geometry_mask
from shapely.geometry import mapping
from shapely.ops import transform as shp_transform

from . import exports
from .aoi import AOI, INDIA_BBOX, AOIError, load_aoi
from .config import settings
from .jobs import Job
from .processing import density as dens
from .processing import render
from .processing import site_prior
from .processing import vegetation as veg
from .processing.trees import SATELLITE_PARAMS, TreeParams, detect_trees
from .sources import gee

SATELLITE_STAGES = [
    {"id": "aoi", "name": "Read boundary", "description": "Parse the KML/KMZ, validate area and location"},
    {"id": "chm", "name": "Canopy height", "description": "Meta/WRI 1 m canopy height model (Earth Engine)"},
    {"id": "context", "name": "Satellite & terrain", "description": "Sentinel-2 composite, Copernicus DEM, ESA WorldCover"},
    {"id": "site_species", "name": "Site species prior",
     "description": "Likely tree species from climate, soil and worldwide records"},
    {"id": "trees", "name": "Detect trees", "description": "Tree tops, crowns and heights from canopy height"},
    {"id": "density", "name": "Canopy density", "description": "Cover per grid cell with Forest Survey of India classes"},
    {"id": "vegetation", "name": "Vegetation & terrain", "description": "NDVI condition, land cover and slope"},
    {"id": "quality", "name": "Quality checks", "description": "Flag unusual trees and data problems"},
    {"id": "inventory", "name": "Inventory & reports", "description": "Tree table, map layers and exports"},
]

DEFAULT_OPTIONS = {
    "canopy_threshold_m": 5.0,
    "min_tree_height_m": 5.0,
    "grid_cell_m": 25.0,
    "s2_start": None,
    "s2_end": None,
}


SATELLITE_METHOD = {
    "detection_method": "CHM local maxima + watershed (Meta 1 m)",
    "height_source": "Meta/WRI Global Canopy Height 1 m",
    "species_status": "not_determined_satellite_mode",
}

SATELLITE_CONFIDENCE = {
    "tree_count": {"level": "Low–Medium",
                   "reason": "1 m satellite canopy height resolves only larger, separated crowns "
                             "(14 % of labelled crowns found on the IDTReeS benchmark)"},
    "tree_height": {"level": "Medium",
                    "reason": "Satellite canopy height: ±6 m vs field-measured trees on the benchmark, "
                              "underestimates by 3–5 m"},
    "canopy_density": {"level": "Medium–High",
                       "reason": "Density class matches airborne LiDAR on 77 % of benchmark plots, within one "
                                 "class on 97 %; moderately dense stands can read as open"},
    "species": {"level": "Not available",
                "reason": "Per-tree species needs drone imagery plus local field labels (survey mode); "
                          "a site-level list of likely species is given from climate and soil"},
}


class StageError(RuntimeError):
    """Fatal problem in a stage; the message is shown to the user."""


@dataclass
class Context:
    job: Job
    aoi: AOI | None = None
    grid1: gee.Grid | None = None
    grid10: gee.Grid | None = None
    to_wgs84: object = None
    aoi_mask1: np.ndarray | None = None
    aoi_mask10: np.ndarray | None = None
    chm: np.ndarray | None = None
    s2: np.ndarray | None = None
    s2_meta: dict = field(default_factory=dict)
    s2_ndvi: np.ndarray | None = None
    dem: np.ndarray | None = None
    worldcover: np.ndarray | None = None
    trees: dict | None = None
    tree_lonlat: tuple | None = None
    density: dict | None = None
    site_scored: list | None = None
    site_env: dict | None = None
    site_in_india: bool = False
    summary: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    mode: str = "satellite"
    method: dict = field(default_factory=lambda: dict(SATELLITE_METHOD))
    confidence: dict | None = None
    min_area_km2: float = 0.01


def merged_options(options: dict | None) -> dict:
    out = dict(DEFAULT_OPTIONS)
    for k, v in (options or {}).items():
        if k in DEFAULT_OPTIONS and v not in (None, ""):
            out[k] = v
    for k in ("canopy_threshold_m", "min_tree_height_m", "grid_cell_m"):
        out[k] = float(out[k])
    out["grid_cell_m"] = min(max(out["grid_cell_m"], 10.0), 100.0)
    return out


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def stage_aoi(ctx: Context, filename: str, data: bytes) -> None:
    job = ctx.job
    try:
        aoi = load_aoi(filename, data, settings.max_aoi_km2, settings.warn_aoi_km2, ctx.min_area_km2)
    except AOIError as exc:
        job.event("error", "AOI_INVALID", str(exc), action="Fix the boundary file and upload again")
        raise StageError(str(exc)) from exc
    for w in aoi.warnings:
        job.event("warning", "AOI_WARNING", w)
    ctx.aoi = aoi
    ctx.to_wgs84 = aoi.to_wgs84()
    if job.state.get("auto_name"):
        job.update("name", aoi.name)
    job.update("aoi", aoi.summary())
    (job.dir / "aoi.geojson").write_text(json.dumps(render.feature_collection([
        {"type": "Feature", "geometry": aoi.summary()["geojson"], "properties": {"name": aoi.name}}
    ])))
    job.set_layer("aoi", "aoi.geojson", "Assessment boundary")
    job.finish_stage(
        "aoi",
        f"{aoi.name}: {aoi.summary()['area_ha']} ha, UTM zone {aoi.utm_epsg - 32600}N",
        {"area_ha": aoi.summary()["area_ha"], "utm_epsg": aoi.utm_epsg},
    )


def stage_chm(ctx: Context) -> None:
    job, aoi = ctx.job, ctx.aoi
    ctx.grid1 = gee.Grid.for_bounds(aoi.utm_epsg, aoi.geom_utm.bounds, 1.0)
    try:
        chm = gee.fetch_chm(ctx.grid1)
    except gee.GEEError as exc:
        job.event("error", "CHM_UNAVAILABLE", str(exc), action="Check Earth Engine access or upload survey data")
        raise StageError(str(exc)) from exc
    ctx.chm = chm
    ctx.aoi_mask1 = geometry_mask([aoi.geom_utm], out_shape=chm.shape, transform=ctx.grid1.transform, invert=True)

    inside = chm[ctx.aoi_mask1]
    gap_pct = float(np.isnan(inside).mean() * 100)
    if gap_pct >= 99:
        job.event("error", "CHM_NO_DATA", "Canopy height has no valid pixels inside the boundary")
        raise StageError("No canopy height data inside the boundary")
    if gap_pct > 5:
        job.event("warning", "CHM_GAPS", f"{gap_pct:.1f}% of the area has no canopy height data",
                  action="Gaps are excluded from density; tree counts there are missing")

    valid = inside[np.isfinite(inside)]
    vmax = max(20.0, float(np.percentile(valid, 99))) if valid.size else 20.0
    render.save_continuous(chm, job.path("chm.png"), "YlGn", 0, vmax, ctx.aoi_mask1)
    job.set_raster("chm", "chm.png", render.corners_wgs84(ctx.grid1, ctx.to_wgs84), "Canopy height (m)",
                   {"type": "continuous", "cmap": "YlGn", "min": 0, "max": round(vmax, 1), "unit": "m"})
    shutil.copy(gee.cache_path("chm", ctx.grid1), job.path("canopy_height_1m.tif"))
    job.set_export("chm_tif", "canopy_height_1m.tif", "Canopy height GeoTIFF (1 m)")
    job.add_provenance(gee.PROVENANCE["chm"])
    job.finish_stage(
        "chm",
        f"1 m canopy height: mean {np.mean(valid):.1f} m, max {np.max(valid):.0f} m",
        {"mean_m": round(float(np.mean(valid)), 1), "max_m": float(np.max(valid)), "gap_pct": round(gap_pct, 2),
         "pixels": int(inside.size)},
        preview="chm.png",
    )


def stage_context(ctx: Context) -> None:
    job, aoi = ctx.job, ctx.aoi
    opts = job.state["options"]
    ctx.grid10 = gee.Grid.for_bounds(aoi.utm_epsg, aoi.geom_utm.bounds, 10.0)
    ctx.aoi_mask10 = geometry_mask([aoi.geom_utm], out_shape=(ctx.grid10.height, ctx.grid10.width),
                                   transform=ctx.grid10.transform, invert=True, all_touched=True)
    parts = []

    start, end = opts.get("s2_start"), opts.get("s2_end")
    if not (start and end):
        start, end = gee.post_monsoon_window()
    try:
        s2, meta = gee.fetch_s2(ctx.grid10, start, end)
        valid = float(np.isfinite(s2[2][ctx.aoi_mask10]).mean() * 100)
        if valid < 90:
            wide_start, wide_end = f"{int(end[:4]) - 1}-09-01", f"{end[:4]}-04-01"
            job.event("warning", "S2_CLOUD_GAPS",
                      f"Only {valid:.0f}% of the area had cloud-free Sentinel-2 pixels ({start} to {end})",
                      action=f"Auto-recovered: widened the window to {wide_start} – {wide_end}")
            s2, meta = gee.fetch_s2(ctx.grid10, wide_start, wide_end)
            valid = float(np.isfinite(s2[2][ctx.aoi_mask10]).mean() * 100)
        meta["valid_pct"] = round(valid, 1)
        if valid < 50:
            job.event("warning", "S2_UNAVAILABLE", "Not enough cloud-free Sentinel-2 data for vegetation analysis",
                      action="Vegetation condition is skipped; other outputs are unaffected")
        else:
            ctx.s2, ctx.s2_meta = s2, meta
            render.save_truecolor(s2, job.path("s2_truecolor.png"), ctx.aoi_mask10)
            job.set_raster("s2_truecolor", "s2_truecolor.png", render.corners_wgs84(ctx.grid10, ctx.to_wgs84),
                           f"Sentinel-2 true colour ({meta['start']} – {meta['end']})")
            job.add_provenance({**gee.PROVENANCE["s2"], "period": f"{meta['start']} to {meta['end']}",
                                "scenes": meta["scenes"]})
            parts.append(f"Sentinel-2 {meta['scenes']} scenes ({valid:.0f}% clear)")
    except gee.GEEError as exc:
        job.event("warning", "S2_FAILED", f"Sentinel-2 download failed: {exc}", action="Vegetation condition skipped")

    try:
        ctx.dem = gee.fetch_dem(ctx.grid10)
        job.add_provenance(gee.PROVENANCE["dem"])
        parts.append("DEM")
    except gee.GEEError as exc:
        job.event("warning", "DEM_FAILED", f"Terrain download failed: {exc}", action="Terrain statistics skipped")

    try:
        ctx.worldcover = gee.fetch_worldcover(ctx.grid10)
        job.add_provenance(gee.PROVENANCE["worldcover"])
        parts.append("WorldCover")
    except gee.GEEError as exc:
        job.event("warning", "WORLDCOVER_FAILED", f"Land cover download failed: {exc}")

    job.finish_stage("context", ", ".join(parts) if parts else "No context layers available",
                     {"s2": ctx.s2_meta}, preview="s2_truecolor.png" if ctx.s2 is not None else None)


NICHES_FILE = "tree_niches.json"


def stage_site_species(ctx: Context) -> None:
    """Optional context: a failure here is logged and skipped, never fails the assessment."""
    try:
        _site_species(ctx)
    except Exception as exc:
        (ctx.job.dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        ctx.site_scored = None
        ctx.summary.pop("site_species", None)
        ctx.job.event("warning", "SITE_PRIOR_FAILED", f"Site species prior failed: {exc}",
                      action="Skipped; tree detection and all other outputs are unaffected (details in error.log)")
        ctx.job.skip_stage("site_species", "Site species prior failed; see events")


def _site_species(ctx: Context) -> None:
    """Rank the tree species this site's climate and soil suit, using worldwide records (a prior, not a count)."""
    job, aoi = ctx.job, ctx.aoi
    table = site_prior.load_niches(settings.models_dir / "niches" / NICHES_FILE)
    if table is None:
        job.event("info", "NO_NICHE_TABLE", "The species niche table has not been built on this machine",
                  action="Run training/build_species_niches.py once (needs internet and Earth Engine)")
        job.skip_stage("site_species", "Species niche table not available")
        return
    try:
        site = gee.fetch_site_environment(aoi.geom_wgs84)
    except gee.GEEError as exc:
        job.event("warning", "SITE_ENV_FAILED", f"Climate and soil download failed: {exc}",
                  action="Site species prior skipped; other outputs are unaffected")
        job.skip_stage("site_species", "Climate and soil data unavailable")
        return
    env = site["env"]
    if any(env.get(v) is None for v in table["variables"]):
        job.event("warning", "SITE_ENV_GAPS", "Climate or soil data missing for this boundary",
                  action="Site species prior skipped")
        job.skip_stage("site_species", "Climate or soil data missing")
        return
    c = aoi.geom_wgs84.centroid
    x0, y0, x1, y1 = INDIA_BBOX
    in_india = x0 <= c.x <= x1 and y0 <= c.y <= y1
    local = site_prior.local_species_keys(c.x, c.y, settings.cache_dir)
    if local is None:
        job.event("warning", "GBIF_UNAVAILABLE", "Could not reach GBIF for species recorded near the site",
                  action="Ranked from climate and soil only")
    habitat = (site_prior.habitat_shares(ctx.worldcover[ctx.aoi_mask10])
               if ctx.worldcover is not None and ctx.aoi_mask10 is not None else None)
    scored = site_prior.score_species(env, table, in_india, local, habitat)
    ctx.site_scored, ctx.site_env, ctx.site_in_india = scored, env, in_india
    for key in ("climate", "soil", "ecoregion", "gbif"):
        job.add_provenance(gee.PROVENANCE[key])
    top = [{k: s[k] for k in ("name", "english_name", "local_name", "family", "share_pct", "similar_site_records",
                              "recorded_nearby", "often_planted")} for s in scored[:15]]
    ctx.summary["site_species"] = {
        "ecoregion": site.get("ecoregion"), "biome": site.get("biome"), "realm": site.get("realm"),
        "climate": {
            "mean_temp_c": round(env["bio01"] / 10, 1), "max_temp_c": round(env["bio05"] / 10, 1),
            "min_temp_c": round(env["bio06"] / 10, 1), "annual_rain_mm": round(env["bio12"]),
            "dry_quarter_rain_mm": round(env["bio17"]), "rain_seasonality": round(env["bio15"]),
        },
        "soil": {"sand_pct": round(env["sand"]), "clay_pct": round(env["clay"]), "ph": round(env["ph"] / 10, 1),
                 "organic_carbon_g_kg": round(env["soc"] * 5)},
        "species": top,
        "n_candidates": len(table["taxa"]), "n_suitable": len(scored),
        "n_reference_records": table.get("n_reference_records"), "in_india": in_india,
        "n_records": table.get("n_records_total"), "table_built": table.get("built"),
        "method": ("Share of each species among tree records from the places in India most like this site "
                   f"({site_prior.REF_K:,} nearest of {table.get('n_reference_records', 0):,} records by climate and soil"
                   + (", re-weighted to this site's land cover: " + ", ".join(
                       f"{g.replace('_', '/')} {v:.0%}" for g, v in habitat.items() if v >= 0.05) if habitat else "")
                   + ")" if in_india else
                   f"Share of each species among its worldwide records nearest to this site's climate and soil "
                   f"({site_prior.NICHE_K} nearest)")
                  + (", with a boost for species recorded within 50 km" if local else ""),
        "caveat": "Predicted likelihood of occurrence, not a tree count. Confirm with a drone survey or field plots.",
    }
    names = ", ".join(f"{s['local_name'] or s['name']} {s['share_pct']}%" for s in scored[:3])
    job.finish_stage(
        "site_species",
        f"{site.get('ecoregion') or 'Unknown ecoregion'}: {len(scored)} of {len(table['taxa'])} tree species "
        f"recorded in similar places; top {names}",
        {"ecoregion": site.get("ecoregion"), "biome": site.get("biome"), "n_suitable": len(scored),
         "top": [(s["name"], s["share_pct"]) for s in scored[:10]]},
    )


def stage_trees(ctx: Context) -> None:
    job = ctx.job
    opts = job.state["options"]
    params = TreeParams(**{**SATELLITE_PARAMS.__dict__, "min_height_m": opts["min_tree_height_m"]})
    res = detect_trees(ctx.chm, ctx.grid1.res, ctx.aoi_mask1, params)
    ctx.trees = res
    area_ha = ctx.aoi.area_km2 * 100
    n = res["count"]

    if n == 0:
        job.event("warning", "NO_TREES",
                  f"No trees taller than {params.min_height_m:g} m were detected",
                  action="Area may be non-forest; check the boundary or the height threshold")
        ctx.tree_lonlat = (np.array([]), np.array([]))
        job.finish_stage("trees", "No trees detected", {"detected": 0})
        return

    xs = ctx.grid1.xmin + (res["cols"] + 0.5) * ctx.grid1.res
    ys = ctx.grid1.ymax - (res["rows"] + 0.5) * ctx.grid1.res
    lon, lat = Transformer.from_crs(ctx.aoi.utm_epsg, 4326, always_xy=True).transform(xs, ys)
    ctx.tree_lonlat = (np.asarray(lon), np.asarray(lat))

    # Canopy the 1 m data cannot split into crowns → extrapolated count range.
    canopy_m2 = float((np.nan_to_num(ctx.chm) >= params.min_height_m)[ctx.aoi_mask1].sum()) * ctx.grid1.res ** 2
    unattributed = res["unattributed_canopy_fraction"]
    p25, p50, p75 = np.percentile(res["crown_area_m2"], [25, 50, 75])
    extra = canopy_m2 * unattributed
    estimate = {
        "detected": n,
        "estimated_total": int(n + extra / p50),
        "estimated_low": int(n + extra / p75),
        "estimated_high": int(n + extra / p25),
        "method": "detected crowns + unresolved canopy area ÷ detected crown area (median, IQR for range)",
    }
    ctx.summary["tree_count"] = estimate
    if unattributed > 0.5:
        job.event("warning", "CLOSED_CANOPY",
                  f"{unattributed * 100:.0f}% of the canopy could not be split into individual crowns at 1 m resolution",
                  action=f"Detected count ({n}) is a lower bound; estimated total "
                         f"{estimate['estimated_low']:,}–{estimate['estimated_high']:,} trees. "
                         "A drone survey resolves individual crowns")

    tall = [i for i, f in enumerate(res["flags"]) if "height_outlier" in f]
    if tall:
        job.event("warning", "HEIGHT_OUTLIER", f"{len(tall)} trees taller than 40 m (unusual for this region)",
                  action="Marked 'height_outlier' in the inventory; verify in the field")

    crown_h = np.zeros(res["labels"].max() + 1, np.float32)
    crown_h[1:] = res["height_m"]
    render.save_continuous(np.where(res["labels"] > 0, crown_h[res["labels"]], np.nan),
                           job.path("crowns.png"), "viridis", 0, max(20.0, float(res["height_m"].max())),
                           ctx.aoi_mask1)
    job.set_raster("crowns", "crowns.png", render.corners_wgs84(ctx.grid1, ctx.to_wgs84),
                   "Detected crowns (coloured by height)")
    h = res["height_m"]
    job.finish_stage(
        "trees",
        f"{n:,} trees detected ({n / area_ha:.0f}/ha); estimated total {estimate['estimated_low']:,}–"
        f"{estimate['estimated_high']:,}",
        {"detected": n, "detected_per_ha": round(n / area_ha, 1), **{k: v for k, v in estimate.items() if k != "method"},
         "height_median_m": round(float(np.median(h)), 1), "height_p95_m": round(float(np.percentile(h, 95)), 1),
         "crown_area_median_m2": round(float(p50), 1), "unattributed_canopy_pct": round(unattributed * 100, 1)},
        preview="crowns.png",
    )


def stage_density(ctx: Context) -> None:
    job = ctx.job
    opts = job.state["options"]
    t = ctx.trees
    rows = t.get("rows", np.array([], int))
    cols = t.get("cols", np.array([], int))
    heights = t.get("height_m", np.array([]))
    d = dens.density_grid(ctx.chm, ctx.grid1.res, ctx.aoi_mask1, rows, cols, heights,
                          opts["grid_cell_m"], opts["canopy_threshold_m"])
    ctx.density = d
    summary = dens.summarize(d["cells"], ctx.chm, ctx.aoi_mask1, opts["canopy_threshold_m"], ctx.grid1.res)
    ctx.summary["density"] = summary

    features = []
    for cell in d["cells"]:
        geom = render.cell_polygon(ctx.grid1, d["cell_px"], cell["row"], cell["col"], ctx.aoi.geom_utm, ctx.to_wgs84)
        features.append({"type": "Feature", "geometry": geom,
                         "properties": {k: v for k, v in cell.items() if k not in ("row", "col")}})
    (job.dir / "density_grid.geojson").write_text(json.dumps(render.feature_collection(
        features, cell_size_m=opts["grid_cell_m"], canopy_threshold_m=opts["canopy_threshold_m"])))
    job.set_layer("density", "density_grid.geojson", f"Canopy density ({opts['grid_cell_m']:g} m cells)")

    codes = {c[0]: i + 1 for i, c in enumerate(dens.FSI_CLASSES)}
    class_grid = np.zeros(d["cover_grid"].shape, np.int16)
    for cell in d["cells"]:
        class_grid[cell["row"], cell["col"]] = codes[cell["fsi_class"]]
    cell_grid = gee.Grid(ctx.grid1.epsg, ctx.grid1.xmin, ctx.grid1.ymax, d["cell_px"] * ctx.grid1.res,
                         class_grid.shape[1], class_grid.shape[0])
    render.save_categorical(class_grid, job.path("density.png"),
                            {codes[c[0]]: c[4] for c in dens.FSI_CLASSES})
    job.set_raster("density", "density.png", render.corners_wgs84(cell_grid, ctx.to_wgs84),
                   "Forest density class (FSI)",
                   {"type": "categorical", "items": [{"label": f"{c[1]} ({c[2]:g}–{min(c[3], 100):g}%)", "color": c[4]}
                                                     for c in dens.FSI_CLASSES]})
    names = {c[0]: c[1] for c in dens.FSI_CLASSES}
    job.finish_stage(
        "density",
        f"Canopy cover {summary['canopy_cover_pct']}%, mostly {names[summary['dominant_fsi_class']]}",
        summary,
        preview="density.png",
    )


def stage_vegetation(ctx: Context) -> None:
    job = ctx.job
    parts, metrics = [], {}
    if ctx.s2 is not None:
        nd = veg.ndvi(ctx.s2)
        ctx.summary["ndvi"] = metrics["ndvi"] = veg.ndvi_summary(nd, ctx.aoi_mask10)
        render.save_continuous(nd, job.path("ndvi.png"), "RdYlGn", 0.0, 0.9, ctx.aoi_mask10)
        job.set_raster("ndvi", "ndvi.png", render.corners_wgs84(ctx.grid10, ctx.to_wgs84), "NDVI (vegetation vigour)",
                       {"type": "continuous", "cmap": "RdYlGn", "min": 0, "max": 0.9, "unit": "NDVI"})
        ctx.s2_ndvi = nd
        parts.append(f"mean NDVI {metrics['ndvi']['mean_ndvi']}")
        try:
            dry_start, dry_end = gee.dry_season_window(ctx.s2_meta["end"])
            s2_dry, dry_meta = gee.fetch_s2(ctx.grid10, dry_start, dry_end)
            tree_mask = (np.nan_to_num(ctx.worldcover) == 10) if ctx.worldcover is not None else None
            drop = veg.leaf_fall(nd, veg.ndvi(s2_dry), tree_mask)
            leaf = veg.leaf_fall_summary(drop, ctx.aoi_mask10)
            if leaf["available"]:
                leaf.update(leaf_on=f"{ctx.s2_meta['start']} to {ctx.s2_meta['end']}", dry=f"{dry_start} to {dry_end}")
                ctx.summary["leaf_fall"] = metrics["leaf_fall"] = leaf
                render.save_categorical(veg.leaf_habit_classes(np.nan_to_num(drop, nan=-1.0)),
                                        job.path("leaf_fall.png"), {v[0]: v[5] for v in veg.LEAF_HABIT},
                                        ctx.aoi_mask10)
                job.set_raster("leaf_fall", "leaf_fall.png", render.corners_wgs84(ctx.grid10, ctx.to_wgs84),
                               "Seasonal leaf fall (Sentinel-2)",
                               {"type": "categorical", "items": [{"label": v[2], "color": v[5]}
                                                                 for v in veg.LEAF_HABIT]})
                job.add_provenance({**gee.PROVENANCE["s2_dry"], "period": f"{dry_start} to {dry_end}",
                                    "scenes": dry_meta["scenes"]})
                parts.append(f"dry-season NDVI drop {leaf['mean_drop_pct']}%")
            else:
                job.event("info", "LEAF_FALL_UNAVAILABLE", "No clear dry-season Sentinel-2 pixels over tree cover",
                          action="Seasonal leaf-fall layer skipped; other outputs are unaffected")
        except gee.GEEError as exc:
            job.event("warning", "LEAF_FALL_FAILED", f"Dry-season Sentinel-2 download failed: {exc}",
                      action="Seasonal leaf-fall layer skipped")
    if ctx.worldcover is not None:
        ctx.summary["landcover"] = metrics["landcover_pct"] = veg.worldcover_summary(ctx.worldcover, ctx.aoi_mask10)
        wc = np.nan_to_num(ctx.worldcover).astype(int)
        render.save_categorical(wc, job.path("landcover.png"), {k: v[1] for k, v in veg.WORLDCOVER.items()},
                                ctx.aoi_mask10)
        present = set(np.unique(wc[ctx.aoi_mask10]))
        job.set_raster("landcover", "landcover.png", render.corners_wgs84(ctx.grid10, ctx.to_wgs84),
                       "Land cover (ESA WorldCover)",
                       {"type": "categorical", "items": [{"label": v[0], "color": v[1]}
                                                         for k, v in veg.WORLDCOVER.items() if k in present]})
        top = next(iter(metrics["landcover_pct"].items()), None)
        if top:
            parts.append(f"{top[0]} {top[1]}%")
    if ctx.dem is not None:
        ctx.summary["terrain"] = metrics["terrain"] = veg.terrain_summary(ctx.dem, ctx.aoi_mask10, ctx.grid10.res)
        if metrics["terrain"].get("available"):
            parts.append(f"slope mean {metrics['terrain']['slope_mean_deg']}°")
            if metrics["terrain"]["steep_area_pct"] > 25:
                job.event("info", "STEEP_TERRAIN",
                          f"{metrics['terrain']['steep_area_pct']}% of the area is steeper than 20°",
                          action="Field verification teams should plan for rugged access")
    if not parts:
        job.skip_stage("vegetation", "No vegetation or terrain layers available")
        return
    job.finish_stage("vegetation", ", ".join(parts), metrics,
                     preview="ndvi.png" if ctx.s2 is not None else None)


def stage_quality(ctx: Context) -> None:
    job = ctx.job
    t = ctx.trees
    n = t["count"]
    flagged = sum(1 for f in t.get("flags", []) if f)
    ratings = {
        **(ctx.confidence or SATELLITE_CONFIDENCE),
        "vegetation_condition": {"level": "Medium" if ctx.s2 is not None else "Not available",
                                 "reason": "Sentinel-2 10 m, stand level"},
    }
    ctx.quality = {"confidence": ratings, "flagged_trees": flagged}

    if ctx.s2 is not None and ctx.worldcover is not None:
        wc_tree = float((ctx.worldcover[ctx.aoi_mask10] == 10).mean() * 100)
        cover = ctx.summary["density"]["canopy_cover_pct"]
        if abs(wc_tree - cover) > 40:
            job.event("warning", "SOURCE_DISAGREEMENT",
                      f"Canopy cover from height data ({cover}%) differs from WorldCover tree cover ({wc_tree:.0f}%)",
                      action="The area may have changed since the canopy height imagery (clearing or regrowth); "
                             "verify with recent imagery")
        ndvi_vals = ctx.s2_ndvi[ctx.aoi_mask10 & np.isfinite(ctx.s2_ndvi)]
        if cover > 40 and ndvi_vals.size and float(np.mean(ndvi_vals)) < 0.35:
            job.event("warning", "POSSIBLE_CHANGE",
                      "Dense canopy in the height data but low current NDVI",
                      action="Possible recent clearing, fire or leaf-off imagery; verify before using counts")

    if ctx.mode == "satellite":
        job.event("info", "SPECIES_NOT_AVAILABLE",
                  "Species are not assigned to individual trees in satellite mode",
                  action="See 'Likely species at this site' in Statistics; upload drone survey data with local "
                         "species labels to classify each tree")
    job.finish_stage(
        "quality",
        f"{flagged} trees flagged for review; confidence ratings assigned",
        {"flagged_trees": flagged, "detected": n, "event_counts": job.state["event_counts"]},
    )


def stage_inventory(ctx: Context) -> None:
    job = ctx.job
    t = ctx.trees
    n = t["count"]
    records = []
    if n:
        lon, lat = ctx.tree_lonlat
        cover = ctx.density["tree_cover_pct"]
        cells_by_rc = {}
        cpx = ctx.density["cell_px"]
        for cell in ctx.density["cells"]:
            cells_by_rc[(cell["row"], cell["col"])] = cell["fsi_class"]
        nd = ctx.s2_ndvi
        xs = ctx.grid1.xmin + (t["cols"] + 0.5) * ctx.grid1.res
        ys = ctx.grid1.ymax - (t["rows"] + 0.5) * ctx.grid1.res
        c10 = np.clip(((xs - ctx.grid10.xmin) // ctx.grid10.res).astype(int), 0, ctx.grid10.width - 1)
        r10 = np.clip(((ctx.grid10.ymax - ys) // ctx.grid10.res).astype(int), 0, ctx.grid10.height - 1)
        species = t.get("species")
        species_conf = t.get("species_confidence")
        species_raw = t.get("species_confidence_raw")
        for i in range(n):
            ndvi_v = float(nd[r10[i], c10[i]]) if nd is not None else None
            ground = float(ctx.dem[r10[i], c10[i]]) if ctx.dem is not None else None
            records.append({
                "tree_id": f"T{i + 1:06d}",
                "latitude": round(float(lat[i]), 7),
                "longitude": round(float(lon[i]), 7),
                "height_m": round(float(t["height_m"][i]), 1),
                "crown_area_m2": round(float(t["crown_area_m2"][i]), 1),
                "crown_diameter_m": round(float(t["crown_diameter_m"][i]), 1),
                "local_canopy_density_pct": round(float(cover[i]), 1),
                "fsi_density_class": cells_by_rc.get((int(t["rows"][i] // cpx), int(t["cols"][i] // cpx))),
                "ndvi": round(ndvi_v, 3) if ndvi_v is not None and np.isfinite(ndvi_v) else None,
                "vegetation_condition": veg.ndvi_class(ndvi_v) if ndvi_v is not None else None,
                "ground_elevation_m": round(ground, 1) if ground is not None and np.isfinite(ground) else None,
                "species": species[i] if species is not None else None,
                "species_confidence": round(float(species_conf[i]), 3) if species_conf is not None else None,
                "species_confidence_image_only": round(float(species_raw[i]), 3) if species_raw is not None else None,
                "species_status": ctx.method["species_status"],
                "detection_score": round(float(t["score"][i]), 3) if "score" in t else None,
                "detection_method": ctx.method["detection_method"],
                "height_source": ctx.method["height_source"],
                "quality_flags": t["flags"][i],
            })

    tree_features = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
                      "properties": r} for r in records]
    (job.dir / "trees.geojson").write_text(json.dumps(render.feature_collection(tree_features)))
    job.set_layer("trees", "trees.geojson", "Detected trees")

    if n:
        if "crown_geoms_utm" in t:
            crowns = {i + 1: mapping(shp_transform(ctx.to_wgs84, g)) for i, g in enumerate(t["crown_geoms_utm"])}
        else:
            crowns = render.crowns_to_features(t["labels"], ctx.grid1.transform, ctx.to_wgs84, simplify_m=0.5)
        crown_features = [
            {"type": "Feature", "geometry": crowns[i + 1],
             "properties": {"tree_id": records[i]["tree_id"], "height_m": records[i]["height_m"],
                            "crown_area_m2": records[i]["crown_area_m2"]}}
            for i in range(n) if (i + 1) in crowns
        ]
        (job.dir / "crowns.geojson").write_text(json.dumps(render.feature_collection(crown_features)))
        job.set_layer("crowns", "crowns.geojson", "Tree crowns")

    area_ha = ctx.aoi.area_km2 * 100
    heights = np.array([r["height_m"] for r in records]) if records else np.array([])
    ctx.summary.update({
        "area_ha": round(area_ha, 2),
        "mode": ctx.mode,
        "height": {
            "mean_m": round(float(heights.mean()), 1) if n else None,
            "median_m": round(float(np.median(heights)), 1) if n else None,
            "max_m": round(float(heights.max()), 1) if n else None,
            "histogram": exports.height_histogram(heights),
        },
        "crown_area_median_m2": round(float(np.median(t["crown_area_m2"])), 1) if n else None,
        "quality": ctx.quality,
        "s2": ctx.s2_meta,
    })
    job.update("summary", ctx.summary)

    made = exports.write_all(job, records)
    job.finish_stage("inventory", f"{n:,} tree records; exports: {', '.join(made)}",
                     {"records": n, "exports": made})


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_satellite_job(job: Job, filename: str, data: bytes) -> None:
    """Worker entry point; never lets an exception escape silently into the thread pool."""
    try:
        _run_satellite(job, filename, data)
    except Exception:
        (job.dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        try:
            job.event("error", "INTERNAL_ERROR", "Assessment stopped unexpectedly", action="See error.log")
            job.set_status("failed")
        except Exception:
            pass


def _run_satellite(job: Job, filename: str, data: bytes) -> None:
    ctx = Context(job=job)
    run_steps(job, filename, [
        ("aoi", lambda: stage_aoi(ctx, filename, data)),
        ("chm", lambda: stage_chm(ctx)),
        ("context", lambda: stage_context(ctx)),
        ("site_species", lambda: stage_site_species(ctx)),
        ("trees", lambda: stage_trees(ctx)),
        ("density", lambda: stage_density(ctx)),
        ("vegetation", lambda: stage_vegetation(ctx)),
        ("quality", lambda: stage_quality(ctx)),
        ("inventory", lambda: stage_inventory(ctx)),
    ])


def run_steps(job: Job, filename: str, steps: list) -> None:
    job.event("info", "JOB_STARTED", f"Assessment started for '{filename}'")
    for stage_id, fn in steps:
        job.start_stage(stage_id)
        try:
            fn()
        except StageError as exc:
            job.fail_stage(stage_id, str(exc))
            job.set_status("failed")
            return
        except Exception as exc:  # unexpected bug: keep the traceback for debugging
            (job.dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            job.event("error", "INTERNAL_ERROR", f"Unexpected error in '{stage_id}': {exc}",
                      action="See error.log in the job folder")
            job.fail_stage(stage_id, f"Unexpected error: {exc}")
            job.set_status("failed")
            return
    job.event("info", "JOB_COMPLETED", "Assessment completed")
    job.set_status("completed")
