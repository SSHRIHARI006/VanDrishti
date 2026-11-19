"""Survey mode: KML boundary + drone/aerial orthophoto (+ DSM/DTM or CHM) → per-tree inventory.

Reuses the satellite pipeline's context, density, vegetation, quality and
inventory stages; replaces canopy height and tree detection with survey data
and adds per-tree species classification.
"""

from __future__ import annotations

import traceback
from pathlib import Path

import numpy as np
from pyproj import Transformer
from rasterio.features import geometry_mask

from . import pipeline as sat
from .config import settings
from .jobs import Job
from .processing import render
from .processing import site_prior
from .processing import species as sp
from .processing import survey as sv
from .processing.trees import SURVEY_PARAMS, TreeParams, detect_trees
from .sources import gee

SURVEY_CHM_RES_M = 0.5
# IDTReeS: scores 0.1–0.2 add ~3 points of recall (0.49 → 0.52) at the lowest precision; flag them for review.
LOW_DETECTION_SCORE = 0.2
SURVEY_MIN_AREA_KM2 = 0.0003  # 0.03 ha (a single 20 m plot is 0.04 ha)

SURVEY_STAGES = [
    {"id": "aoi", "name": "Read boundary", "description": "Parse the KML/KMZ, validate area and location"},
    {"id": "survey", "name": "Check survey data", "description": "Coordinate system, resolution and coverage of uploads"},
    {"id": "chm", "name": "Canopy height", "description": "Survey DSM − DTM (or uploaded CHM) on a 0.5 m grid"},
    {"id": "context", "name": "Satellite & terrain", "description": "Sentinel-2 composite, Copernicus DEM, ESA WorldCover"},
    {"id": "site_species", "name": "Site species prior",
     "description": "Likely tree species from climate, soil and worldwide records"},
    {"id": "trees", "name": "Detect trees", "description": "DeepForest crown detection on the orthophoto, tiled and de-duplicated"},
    {"id": "species", "name": "Classify species", "description": "Local species model on crown colour, texture and structure"},
    {"id": "density", "name": "Canopy density", "description": "Cover per grid cell with Forest Survey of India classes"},
    {"id": "vegetation", "name": "Vegetation & terrain", "description": "NDVI condition, land cover and slope"},
    {"id": "quality", "name": "Quality checks", "description": "Flag unusual trees, uncertain species and data problems"},
    {"id": "inventory", "name": "Inventory & reports", "description": "Tree table, map layers and exports"},
]

SURVEY_FILES = ("ortho", "dsm", "dtm", "chm")


def stage_survey(ctx, files: dict[str, Path]) -> None:
    job = ctx.job
    if "ortho" not in files:
        job.event("error", "ORTHO_MISSING", "An orthophoto (RGB GeoTIFF) is required in survey mode")
        raise sat.StageError("Orthophoto missing")
    info = {}
    for kind, path in files.items():
        try:
            info[kind] = sv.inspect(path, ctx.aoi.geom_wgs84)
        except sv.SurveyError as exc:
            job.event("error", "SURVEY_FILE_INVALID", str(exc), action="Re-export the file as a georeferenced GeoTIFF")
            raise sat.StageError(str(exc)) from exc

    o = info["ortho"]
    if o["bands"] < 3:
        job.event("error", "ORTHO_BANDS", f"Orthophoto has {o['bands']} band(s); RGB (3 bands) is required")
        raise sat.StageError("Orthophoto is not RGB")
    if o["res_m"] > sv.MAX_ORTHO_RES_M:
        job.event("error", "ORTHO_TOO_COARSE", f"Orthophoto resolution {o['res_m']} m is too coarse for crowns",
                  action="Use drone imagery at 2–30 cm, or run satellite mode instead")
        raise sat.StageError("Orthophoto too coarse")
    if o["res_m"] > sv.WARN_ORTHO_RES_M:
        job.event("warning", "ORTHO_COARSE", f"Orthophoto resolution {o['res_m']} m; small crowns may be missed",
                  action="Fly lower (3–5 cm GSD) for the next survey")
    for kind, i in info.items():
        if i["aoi_coverage_pct"] < 20:
            job.event("error", "NO_COVERAGE", f"{i['file']} covers only {i['aoi_coverage_pct']}% of the boundary",
                      action="Check that the survey and the KML refer to the same block")
            raise sat.StageError(f"{kind} does not cover the boundary")
        if i["aoi_coverage_pct"] < 95:
            job.event("warning", "PARTIAL_COVERAGE",
                      f"{i['file']} covers {i['aoi_coverage_pct']}% of the boundary",
                      action="Trees outside the surveyed part are not counted")
    if "dsm" in files and "dtm" not in files and "chm" not in files:
        job.event("warning", "DTM_MISSING", "A DSM was uploaded without a DTM",
                  action="Heights fall back to satellite canopy height; upload the DTM from photogrammetry")

    ctx.survey_info = info
    ctx.survey_files = files
    job.finish_stage("survey", f"Orthophoto {o['res_m']} m, {o['aoi_coverage_pct']}% coverage; "
                               f"height inputs: {', '.join(k.upper() for k in files if k != 'ortho') or 'none'}",
                     {k: {kk: v for kk, v in i.items() if kk in ("res_m", "crs", "aoi_coverage_pct", "bands")}
                      for k, i in info.items()})


def stage_chm(ctx) -> None:
    job, aoi, files = ctx.job, ctx.aoi, ctx.survey_files
    grid = gee.Grid.for_bounds(aoi.utm_epsg, aoi.geom_utm.bounds, SURVEY_CHM_RES_M)
    chm, source = sv.build_chm(grid, files.get("chm"), files.get("dsm"), files.get("dtm"))
    if chm is None:
        job.event("warning", "CHM_FALLBACK", "No survey height data (DSM + DTM or CHM) was uploaded",
                  action="Tree heights use Meta 1 m satellite canopy height instead (lower accuracy)")
        grid = gee.Grid.for_bounds(aoi.utm_epsg, aoi.geom_utm.bounds, 1.0)
        try:
            chm = gee.fetch_chm(grid)
        except gee.GEEError as exc:
            job.event("error", "CHM_UNAVAILABLE", str(exc))
            raise sat.StageError(str(exc)) from exc
        source = "Meta/WRI Global Canopy Height 1 m (fallback)"
        job.add_provenance(gee.PROVENANCE["chm"])
        ctx.height_is_survey = False
    else:
        ctx.height_is_survey = True
        job.add_provenance({"dataset": source, "source": "user upload", "resolution_m": SURVEY_CHM_RES_M,
                            "license": "Owner of the survey", "notes": "Resampled to a 0.5 m UTM grid."})
    ctx.grid1, ctx.chm = grid, chm
    ctx.method["height_source"] = source
    ctx.aoi_mask1 = geometry_mask([aoi.geom_utm], out_shape=chm.shape, transform=grid.transform, invert=True)
    inside = chm[ctx.aoi_mask1]
    valid = inside[np.isfinite(inside)]
    if valid.size == 0:
        job.event("error", "CHM_NO_DATA", "Canopy height has no valid pixels inside the boundary")
        raise sat.StageError("No canopy height inside the boundary")
    vmax = max(20.0, float(np.percentile(valid, 99)))
    render.save_continuous(chm, job.path("chm.png"), "YlGn", 0, vmax, ctx.aoi_mask1)
    job.set_raster("chm", "chm.png", render.corners_wgs84(grid, ctx.to_wgs84), "Canopy height (m)",
                   {"type": "continuous", "cmap": "YlGn", "min": 0, "max": round(vmax, 1), "unit": "m"})
    job.finish_stage("chm", f"{source}: mean {valid.mean():.1f} m, max {valid.max():.0f} m",
                     {"source": source, "resolution_m": grid.res, "mean_m": round(float(valid.mean()), 1),
                      "max_m": round(float(valid.max()), 1)}, preview="chm.png")


def stage_trees(ctx) -> None:
    job, aoi = ctx.job, ctx.aoi
    opts = job.state["options"]
    ortho_path, res, ortho_grid = sv.working_ortho(ctx.survey_files["ortho"], aoi.geom_utm.bounds,
                                                    aoi.utm_epsg, job.path("working_ortho.tif"))
    ctx.ortho_path, ctx.ortho_grid = ortho_path, ortho_grid
    rgb, _ = sp.read_rgb(ortho_path)
    step = max(1, int(np.ceil(max(rgb.shape[1:]) / render.MAX_OVERLAY_PX)))
    mask = geometry_mask([aoi.geom_utm], out_shape=rgb.shape[1:], transform=ortho_grid.transform, invert=True)
    render.save_truecolor(rgb[[2, 1, 0], ::step, ::step].astype(np.float32) / 255.0, job.path("ortho.png"),
                          mask[::step, ::step])
    del rgb
    job.set_raster("ortho", "ortho.png", render.corners_wgs84(ortho_grid, ctx.to_wgs84), "Survey orthophoto")

    if sv.deepforest_available():
        boxes = sv.detect_crowns(ortho_path, ortho_grid)
        # Coarse fallback heights must not veto crowns seen in the survey imagery.
        min_h = opts["min_tree_height_m"] if ctx.height_is_survey else 0.0
        measured = sv.measure_boxes(boxes, ctx.chm, ctx.grid1, aoi.geom_utm, min_h)
        found = measured["trees"]
        ctx.method["detection_method"] = "DeepForest RetinaNet (NEON-pretrained) on survey orthophoto"
        if measured["low_vegetation"]:
            job.event("info", "LOW_VEGETATION",
                      f"{measured['low_vegetation']} detected crowns are below {opts['min_tree_height_m']:g} m",
                      action="Treated as shrubs/regeneration and excluded from the tree count")
        weak = sum(1 for t in found if t["score"] < LOW_DETECTION_SCORE)
        if weak:
            job.event("warning", "LOW_CONFIDENCE_DETECTIONS", f"{weak} trees detected with confidence below {LOW_DETECTION_SCORE}",
                      action="Flagged 'low_detection_confidence' for field verification")
        n = len(found)
        flags = [(["low_detection_confidence"] if t["score"] < LOW_DETECTION_SCORE else []) +
                 (["height_outlier"] if t["height_m"] > 40 else []) +
                 ([] if ctx.height_is_survey else ["height_from_satellite"]) for t in found]
        if found and not ctx.height_is_survey:
            job.event("warning", "HEIGHT_UNVERIFIED",
                      f"Heights for {len(found)} trees come from 1 m satellite canopy height",
                      action="All crowns seen in the imagery are kept; heights are flagged 'height_from_satellite'")
        ctx.trees = {
            "count": n,
            "rows": np.array([t["row"] for t in found], int),
            "cols": np.array([t["col"] for t in found], int),
            "height_m": np.array([t["height_m"] for t in found], np.float32),
            "crown_area_m2": np.array([t["crown_area_m2"] for t in found], np.float32),
            "crown_diameter_m": np.array([np.sqrt((t["xmax"] - t["xmin"]) * (t["ymax"] - t["ymin"])) for t in found]),
            "score": np.array([t["score"] for t in found], np.float32),
            "crown_geoms_utm": [t["crown_geom"] for t in found],
            "boxes": found,
            "flags": flags,
        }
        xs = np.array([t["cx"] for t in found])
        ys = np.array([t["cy"] for t in found])
    else:
        job.event("warning", "DEEPFOREST_UNAVAILABLE", "DeepForest is not installed on this server",
                  action="Fell back to canopy-height tree detection; install deepforest for crown detection")
        params = TreeParams(**{**SURVEY_PARAMS.__dict__, "min_height_m": opts["min_tree_height_m"]})
        t = detect_trees(ctx.chm, ctx.grid1.res, ctx.aoi_mask1, params)
        t.setdefault("rows", np.array([], int))
        t.setdefault("cols", np.array([], int))
        ctx.trees = t
        n = t["count"]
        ctx.method["detection_method"] = "CHM local maxima + watershed (survey CHM)"
        xs = ctx.grid1.xmin + (t["cols"] + 0.5) * ctx.grid1.res
        ys = ctx.grid1.ymax - (t["rows"] + 0.5) * ctx.grid1.res

    if n == 0:
        job.event("warning", "NO_TREES", "No trees were detected inside the boundary",
                  action="Check the orthophoto covers the boundary and the minimum tree height")
        ctx.tree_lonlat = (np.array([]), np.array([]))
        ctx.summary["tree_count"] = {"detected": 0, "estimated_total": 0, "estimated_low": 0,
                                     "estimated_high": 0, "method": "individually detected"}
        job.finish_stage("trees", "No trees detected", {"detected": 0}, preview="ortho.png")
        return
    lon, lat = Transformer.from_crs(aoi.utm_epsg, 4326, always_xy=True).transform(xs, ys)
    ctx.tree_lonlat = (np.asarray(lon), np.asarray(lat))
    ctx.summary["tree_count"] = {"detected": n, "estimated_total": n, "estimated_low": n, "estimated_high": n,
                                 "method": "individually detected crowns"}
    h = ctx.trees["height_m"]
    area_ha = aoi.area_km2 * 100
    job.finish_stage(
        "trees", f"{n:,} trees detected ({n / area_ha:.0f}/ha), median height {np.median(h):.1f} m",
        {"detected": n, "per_ha": round(n / area_ha, 1), "ortho_res_m": round(res, 3),
         "height_median_m": round(float(np.median(h)), 1),
         "mean_detection_score": round(float(np.mean(ctx.trees["score"])), 3) if "score" in ctx.trees else None},
        preview="ortho.png",
    )


def stage_species(ctx) -> None:
    job = ctx.job
    t = ctx.trees
    if not t["count"]:
        job.skip_stage("species", "No trees to classify")
        return
    lon, lat = ctx.aoi.geom_wgs84.centroid.coords[0]
    bundle = sp.model_for_location(settings.models_dir / "species", lon, lat)
    if bundle is None or "boxes" not in t:
        t["species"] = [sp.UNKNOWN] * t["count"]
        t["species_confidence"] = np.zeros(t["count"])
        ctx.method["species_status"] = "no_local_model"
        job.event("info", "NO_SPECIES_MODEL", "No species model has been trained for this region yet"
                  if bundle is None else "Species need DeepForest crowns, which are unavailable in this run",
                  action="Label 150–300 trees in field plots and run training/train_species.py; "
                         "species then appear automatically in the next run")
        ctx.species_available = False
        job.skip_stage("species", "No local species model: all trees marked Unknown")
        return
    rgb, transform = sp.read_rgb(ctx.ortho_path)
    X = sp.crown_features(rgb, transform, t["boxes"])
    proba = bundle["model"].predict_proba(X)
    classes = [str(c) for c in bundle["model"].classes_]
    raw_labels, raw_conf = sp.label(proba, classes, bundle["threshold"])
    prior = None
    if ctx.site_env and bundle.get("scientific_names"):
        table = site_prior.load_niches(settings.models_dir / "niches" / sat.NICHES_FILE)
        prior = site_prior.prior_for_classes(ctx.site_env, table, classes, bundle["scientific_names"],
                                             ctx.site_scored, ctx.site_in_india) if table else None
    if prior is None:
        labels, conf = raw_labels, raw_conf
    else:
        gate = site_prior.presence_gate(prior)
        labels, conf = sp.label(site_prior.adjust_probabilities(proba, gate, tau=1.0), classes, bundle["threshold"])
        t["species_confidence_raw"] = raw_conf
        changed = [i for i in range(len(labels)) if labels[i] != raw_labels[i]]
        for i in changed:
            t["flags"][i] = t["flags"][i] + ["species_prior_adjusted"]
        unlikely = [c for c, g in zip(classes, gate) if not g]
        job.event("info", "SPECIES_SITE_PRIOR",
                  f"Site check: {', '.join(unlikely) or 'no species'} unlikely at this location; "
                  f"{len(changed)} of {len(labels)} labels changed",
                  action="Unlikely species are down-weighted, never excluded; image-only confidence is kept in the "
                         "inventory (species_confidence_image_only)",
                  data={"site_prior": {c: round(float(p), 3) for c, p in zip(classes, prior)}})
    t["species"], t["species_confidence"] = labels, conf
    ctx.method["species_status"] = f"classified ({bundle.get('region', 'local')} model" + (
        " + site species prior)" if prior is not None else ")")
    ctx.species_available = True
    counts: dict[str, int] = {}
    for s in labels:
        counts[s] = counts.get(s, 0) + 1
    ctx.summary["species"] = dict(sorted(counts.items(), key=lambda kv: -kv[1]))
    unknown = counts.get(sp.UNKNOWN, 0)
    if unknown / len(labels) > 0.3:
        job.event("warning", "MANY_UNKNOWN_SPECIES",
                  f"{unknown} of {len(labels)} trees ({unknown / len(labels):.0%}) are below the "
                  f"{bundle['threshold']:.2f} confidence threshold",
                  action="Marked Unknown rather than guessed; add field labels for these crown types")
    # Only meaningful for real blocks; in a tiny plot every species has 1–2 trees.
    rare = [s for s, c in counts.items() if s != sp.UNKNOWN and c <= 2] if len(labels) >= 50 else []
    if rare:
        job.event("info", "RARE_SPECIES", f"Rare species detected: {', '.join(rare)}",
                  action="Rare predictions are the least reliable; verify these trees in the field")
    for i, s in enumerate(labels):
        if s == sp.UNKNOWN:
            t["flags"][i] = t["flags"][i] + ["species_uncertain"]
    job.event("info", "SPECIES_MODEL", f"Species model: {bundle.get('trained_on', 'local labels')}",
              data=bundle.get("metrics", {}))
    top = ", ".join(f"{k} {v}" for k, v in list(ctx.summary["species"].items())[:4])
    job.finish_stage("species", f"{len(counts) - (1 if unknown else 0)} species; {top}",
                     {"species_counts": ctx.summary["species"], "threshold": bundle["threshold"],
                      "model": bundle.get("trained_on")})


def survey_confidence(ctx) -> dict:
    df = ctx.method["detection_method"].startswith("DeepForest")
    return {
        "tree_count": {"level": "High" if df else "Medium",
                       "reason": "Individual crowns detected in survey imagery" if df
                       else "Canopy-height detection (DeepForest unavailable)"},
        "tree_height": {"level": "High" if getattr(ctx, "height_is_survey", False) else "Medium",
                        "reason": ctx.method["height_source"]},
        "canopy_density": {"level": "High", "reason": "Canopy cover from survey canopy height model"},
        "species": ({"level": "Medium", "reason": "Local species model with Unknown below the confidence threshold"}
                    if getattr(ctx, "species_available", False)
                    else {"level": "Not available", "reason": "No species model trained for this region yet"}),
    }


def run_survey_job(job: Job, boundary_name: str, boundary: bytes, files: dict[str, Path]) -> None:
    try:
        ctx = sat.Context(job=job, mode="survey", min_area_km2=SURVEY_MIN_AREA_KM2)
        ctx.method.update({"species_status": "pending"})

        def quality():
            ctx.confidence = survey_confidence(ctx)
            sat.stage_quality(ctx)

        sat.run_steps(job, boundary_name, [
            ("aoi", lambda: sat.stage_aoi(ctx, boundary_name, boundary)),
            ("survey", lambda: stage_survey(ctx, files)),
            ("chm", lambda: stage_chm(ctx)),
            ("context", lambda: sat.stage_context(ctx)),
            ("site_species", lambda: sat.stage_site_species(ctx)),
            ("trees", lambda: stage_trees(ctx)),
            ("species", lambda: stage_species(ctx)),
            ("density", lambda: sat.stage_density(ctx)),
            ("vegetation", lambda: sat.stage_vegetation(ctx)),
            ("quality", quality),
            ("inventory", lambda: sat.stage_inventory(ctx)),
        ])
    except Exception:
        (job.dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        job.event("error", "INTERNAL_ERROR", "Assessment stopped unexpectedly", action="See error.log")
        job.set_status("failed")
