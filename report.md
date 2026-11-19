# Van-drishti AI — Implementation Audit

**Repository:** `sujalappa/van-drishti-ai` (source repository; the Hugging Face Space of the same name is a built artifact of it)
**Audit date:** 2026-11-02
**Scope:** all backend pipeline, source-connector, processing, export, training, validation and deployment code; the main frontend views/components; the committed model/niche artifacts; the committed sample outputs; and the live Space metadata, health endpoint and seeded job records.
**Code changes:** none. This file is the only write.

The pasted brief asked for `VAN_DRISHTI_IMPLEMENTATION_AUDIT.md`; the explicit instruction in the request was “create a report in root, report.md”, so this file is at `report.md`.

---

## 0. How this audit was done, and what “verified” means here

Evidence used:

- Full read of the backend pipeline/source/processing/export code, `deploy/space/app.py`, `tools/build_space.py`, `training/**`, `validation/**`, and the frontend views, API layer, map/3D components and types.
- Arithmetic checks against the committed niche artifacts (`models/niches/tree_niches.json`, `tree_niches.npz`) and the committed sample inventories/PDFs (`presentation/3_sample_outputs/**`).
- Live Hugging Face API: `https://huggingface.co/api/spaces/sujalappa/van-drishti-ai`, its `requirements.txt`, `app.py`, and the two seeded `data/jobs/*/job.json` records.
- Live endpoints `GET /api/health` and `GET /api/auth/status`.

Not done:

- No new Earth Engine downloads, drone inference, PDF generation, or end-to-end job was run.
- `pytest` was **not** run: this environment has no `pytest`, and is missing `scikit-image`, `fastapi`, `rasterio`, `shapely`, `pyproj`, `reportlab`, `joblib` and `scikit-learn`. The repository contains tests, but this audit cannot claim they pass.
- No QGIS/ArcGIS, Google Earth, or browser interaction test was performed.
- Timings quoted from seed jobs are the timings recorded when those jobs were produced. They are **not** measurements of the current Space container (see §12.6).

### Status labels used in this report

1. **Implemented and working** — code exists, is reachable from a live route, and a completed artifact or direct code path demonstrates execution.
2. **Implemented but not verified** — code exists but was not exercised by the committed samples or this audit; or depends on external data/model not present.
3. **Mock / demo data** — committed sample job, benchmark data, or precomputed artifact presented as a demonstration.
4. **Proposed but not implemented** — described in proposal/docs but no production code path.

“Working” here means it executes and produces the documented artifact; it does not mean the output is scientifically or legally exact.

---

## 1. Bottom line

1. **The satellite pipeline is real and runs end-to-end on real public data.** It fetches Meta/WRI canopy height, Sentinel-2, Copernicus DEM and ESA WorldCover through Google Earth Engine, detects trees, builds density cells, and writes CSV/GeoJSON/KMZ/Shapefile/PDF/GeoTIFF.
2. **Satellite tree detection is a screening tool, not enumeration.** On the 121.5 ha Chandrapur sample, 4,846 crowns are detected but **79.8 % of canopy area is unattributed**; the system itself reports an estimated total of **18,235–44,310**. Benchmark recall of labelled crowns is **13.6 %** on Meta 1 m data.
3. **Drone survey mode is real code but has never been validated on drone data.** The repository explicitly says all survey results use NEON **aircraft** data (10 cm RGB + LiDAR CHM). No drone flight, no Indian field labels, and no Indian species model exist.
4. **The “species prior” is site-level, not per-tree.** It ranks 493 taxa by share of climate/soil-similar GBIF records. In satellite mode no tree gets a species. In survey mode a separate Random Forest assigns species only if a model covers the site; the live model covers Florida/Virginia, so the seeded survey run labels 10 of 20 trees **Unknown** (the committed sample PDF, from a different job id, separately reports 18/20 below the raw 0.50 threshold).
5. **The two headline record counts are different quantities, not a deduplication error.** `398,592` is the sum of sampled (page-capped) GBIF records across 493 taxa; `76,369` is the number of India-thinned `(5 km cell, species)` reference rows actually used at runtime. The presentation pairs the first with a method that uses the second.
6. **The live Space is RUNNING on ZeroGPU hardware but performs all inference on CPU.** A `@spaces.GPU(duration=1)` no-op exists only to satisfy the ZeroGPU runtime; `VANDRISHTI_DEEPFOREST_ACCELERATOR=cpu` is forced. Auth is enabled and Earth Engine is configured.
7. **Several documentation/report contradictions are real and user-visible** — most importantly, every survey PDF is generated with the header “Mode: satellite (KML only)” and satellite-only method text, and the committed sample PDFs contain a confidence section that the current `report.py` cannot generate.

---

## 2. Application architecture

### 2.1 Frontend

| Item | Implementation | Evidence |
|---|---|---|
| Framework | React 19.2 + TypeScript 6, Vite 8 | `frontend/package.json` |
| Mapping | MapLibre GL 6 | `frontend/src/components/MapView.tsx`, `BoundaryDraw.tsx` |
| Basemaps | Esri World Imagery raster tiles; OpenStreetMap streets; AWS Terrarium terrain tiles | `MapView.tsx`, `mapExtras.ts` |
| Routing | Hand-rolled hash router (`#/`, `#/jobs/<12-hex>`, `#/users`); no React Router | `frontend/src/App.tsx` |
| State/data | `fetch` wrapper + `localStorage` bearer token; job poll every 800 ms | `frontend/src/api.ts`, `pages/JobPage.tsx` |
| 3D view | Custom `fill-extrusion` “trees” made of stacked discs, vertical exaggeration 1.2 | `frontend/src/components/trees3d.ts` |
| Maps/overlays | PNG overlays (≤2048 px) placed by four corner coordinates; GeoJSON layers | `MapView.tsx`, `backend/vandrishti/processing/render.py` |
| Draw boundary | Polygon/rectangle inside a site circle; emits GeoJSON polygon plus `role: site_extent` point/radius | `BoundaryDraw.tsx`, `backend/vandrishti/aoi.py` |

The 3D trees are a visualisation construct: crown radius comes from `crown_diameter_m` (clamped to a 1–8 m radius), shape/colour is a regex heuristic on species code/name, and heights are extruded. They are not measured 3D geometry and have no analytical role.

### 2.2 Backend and API

| Item | Implementation | Evidence |
|---|---|---|
| Framework | FastAPI, app version `0.1.0` | `backend/vandrishti/api.py` |
| Server | Uvicorn locally; Gradio `Server` on the Space | `deploy/space/app.py` |
| Concurrency | `ThreadPoolExecutor(max_workers=2)`, in-process | `api.py` |
| Job store | Files under `data/jobs/<12-hex>/` (`job.json`, `events.jsonl`, inputs, outputs) | `jobs.py` |
| Database | None | — |
| Auth | Optional PBKDF2-SHA256 (310,000 rounds), HMAC bearer token, 12 h TTL, 5-failure/5-min lockout, optional HF dataset mirror | `auth.py` |
| Static app | `api.py` mounts `frontend/dist` at `/` if present; Space mounts `/assets` and `/maplibre` manually | `api.py`, `deploy/space/app.py` |

**API routes** (all under the app-wide `require_user` dependency; health/login/status are open):

```
GET    /api/health
GET    /api/samples
POST   /api/jobs
POST   /api/jobs/from-sample/{filename}
POST   /api/jobs/survey
GET    /api/samples/survey
POST   /api/jobs/from-survey-sample/{sample_id}
GET    /api/jobs
GET    /api/jobs/{job_id}
GET    /api/jobs/{job_id}/files/{filename}
GET    /api/auth/status
POST   /api/auth/login
GET    /api/auth/users
POST   /api/auth/users
DELETE /api/auth/users/{username}
POST   /api/auth/password
```

Only files registered in `job.state["outputs"]` (layers, rasters, exports) or stage previews can be downloaded; `job.json`/`events.jsonl` are deliberately blocked (`api.py::_allowed_files`, tested in `backend/tests/test_api.py`).

### 2.3 Job management

- `Job.create()` makes a random 12-hex id and a state object with mode, options, stages, outputs, summary, provenance and event counts (`jobs.py`).
- Every mutation (`start_stage`, `finish_stage`, `skip_stage`, `fail_stage`, `event`, `set_*`, `update`, `add_provenance`) writes `job.json` immediately through a temp-file replace with retries for Windows file locks.
- `events.jsonl` is append-only; each record is `{time, level, code, stage, message, action, data}`.
- Worker runs are submitted directly to the two-thread executor; there is **no queue service, no cancellation endpoint, no job deletion, and no resume**. A restart marks any `queued`/`running` job failed (`JOB_INTERRUPTED`) at startup.
- Stage failure semantics: `StageError` fails that stage and the job; unexpected exceptions write `error.log` and fail the job. Recoverable data problems are events and the run continues.

### 2.4 Storage and caching

| Path | Content | Key / lifetime |
|---|---|---|
| `data/jobs/<id>/` | Inputs, `job.json`, `events.jsonl`, previews, exports | Per job; no eviction |
| `data/cache/*.tif` | Downloaded CHM/DEM/WorldCover/S2 rasters | SHA-1 of `grid.key()` = `epsg_xmin_ymax_res_widthxheight` |
| `data/cache/s2_<start>_<end>_<hash>.json` | Sentinel-2 scene count | Same grid hash |
| `data/cache/env_<sha1(geom_wkb)>.json` | Site climate/soil/ecoregion | Per boundary geometry |
| `data/cache/gbif_local_<lat>_<lon>_50.json` | GBIF species keys within 50 km | Per rounded location |
| `data/cache/gbif/*.json` | Raw GBIF API responses during niche-table build | Content hash of request |
| `data/cache/niche_ee_samples.joblib` | Earth Engine samples during niche-table build | Build cache |
| `models/niches/` | Committed niche table (`json` + `npz`) | Versioned in git |
| `models/species/*.joblib` | Regional species RF bundles | **Git-ignored**; not in a fresh clone |

Caching is keyed by grid geometry, not by dataset version or code version. A changed Earth Engine asset, changed cloud-mask rule, or changed processing parameter will silently reuse old cached rasters for the same grid. Repeats can therefore run offline, but provenance does not record whether a layer came from cache or was freshly downloaded.

### 2.5 Deployment configuration (source side)

- `deploy/space/README.md` is the Space card: `sdk: gradio`, `sdk_version: 6.30.0`, `app_file: app.py`, `python_version: "3.12"`.
- `deploy/space/app.py` imports `spaces` before torch, inserts `backend/` on `sys.path`, forces `VANDRISHTI_MAX_SURVEY_UPLOAD_MB=200` and `VANDRISHTI_DEEPFOREST_ACCELERATOR=cpu`, imports the FastAPI app, copies only `/api/*` routes onto a Gradio `Server`, and mounts `frontend/dist`.
- `tools/build_space.py` assembles `deploy/space/build`: backend, `frontend/dist`, `models`, `samples`, two seeded jobs, `app.py`, `README.md`, and a generated `requirements.txt`. It pins `scikit-learn` and `deepforest` to the build machine’s installed versions and appends `pandas` and `torchvision`.
- `deploy/space/build/` is git-ignored. The repository root is **not** the Space layout; the Space is flat (`app.py`, `backend/`, `frontend/`, `models/`, `samples/`, `data/jobs/`).
- Build reproducibility gap: the default seed ids are `28c7761ac343` and `f5186ceaffd3`, and `data/` is git-ignored. A fresh clone has no `data/jobs`, so `tools/build_space.py` cannot complete without a locally populated data directory.

---

## 3. The processing pipeline

### 3.1 Satellite mode: exactly nine stages

Defined in `SATELLITE_STAGES`, `backend/vandrishti/pipeline.py`, executed by `_run_satellite()` → `run_steps()`.

| # | Stage id | Name | Function | Seed-job duration* | Fatal conditions |
|---|---|---|---|---|---|
| 1 | `aoi` | Read boundary | `stage_aoi` | <1 s | invalid KML/KMZ/GeoJSON, no polygon, area below 1 ha or above 10 km² |
| 2 | `chm` | Canopy height | `stage_chm` | 1 s | Earth Engine failure, no data, ≥99 % gaps |
| 3 | `context` | Satellite & terrain | `stage_context` | <1 s | none; each layer is optional and logged |
| 4 | `site_species` | Site species prior | `stage_site_species` | <1 s | none; any exception is caught and the stage skipped |
| 5 | `trees` | Detect trees | `stage_trees` | 3 s | unexpected algorithm error; zero trees is a warning, not fatal |
| 6 | `density` | Canopy density | `stage_density` | 1 s | unexpected error |
| 7 | `vegetation` | Vegetation & terrain | `stage_vegetation` | <1 s | none; skipped if every optional layer fails |
| 8 | `quality` | Quality checks | `stage_quality` | <1 s | unexpected error |
| 9 | `inventory` | Inventory & reports | `stage_inventory` | 4 s | CSV/GeoJSON/KMZ/Shapefile error; PDF failure is caught and logged |

\*From the seeded Chandrapur job `28c7761ac343`, total 9 s (`2026-10-12T11:09:28Z` → `11:09:37Z`). This job predates the Space creation timestamp (`11:19:17Z`), so these are pre-upload/precomputed timings, not Space-container timings. The repository docs separately claim 15–60 s for a 1.2 km² block on a laptop, with first-run downloads slower.

**Stage details.**

1. **Read boundary** — `stage_aoi` → `aoi.load_aoi`.
   - Inputs: uploaded bytes + filename (`.kml`, `.kmz`, `.geojson`, `.json`).
   - Parsing: `defusedxml` for KML; zip entry count ≤50 and uncompressed size ≤20 MB for KMZ; GeoJSON FeatureCollection accepted; polygons are `make_valid` + `unary_union`; non-polygon geometry rejected.
   - CRS: WGS84 lon/lat validated; UTM zone computed from centroid (`326xx` north, `327xx` south); all downstream metric work in that UTM zone.
   - Outputs: `ctx.aoi`, `aoi.geojson` layer, area/UTM metrics.
   - Warnings: area >5 km², outside India bbox (68–98°E, 6–37.5°N), multiple polygons merged.
2. **Canopy height** — `stage_chm` → `gee.Grid.for_bounds(...,1.0)` → `gee.fetch_chm`.
   - Inputs: AOI UTM bounds (padded 20 m), Meta/WRI CHM asset.
   - Outputs: 1 m float CHM array, `chm.png`, `canopy_height_1m.tif` (a copy of the full cached GeoTIFF, including padding), AOI mask, provenance.
   - Gaps: NaN fraction inside AOI; ≥99 % fatal, >5 % warning.
   - Failure: `GEEError` is fatal with `CHM_UNAVAILABLE`.
3. **Satellite & terrain** — `stage_context`.
   - Builds a 10 m UTM grid and an `all_touched` AOI mask.
   - Sentinel-2 composite (`fetch_s2`) with cloud handling; DEM (`fetch_dem`); WorldCover (`fetch_worldcover`).
   - Each layer is independent: S2 failure ⇒ warning and vegetation analysis may be skipped; DEM failure ⇒ terrain skipped; WorldCover failure ⇒ land-cover/habitat context skipped. The stage still finishes.
4. **Site species prior** — `stage_site_species` → `_site_species`.
   - Loads the niche table, fetches site climate/soil via Earth Engine, optional 50 km GBIF lookup, habitat shares from WorldCover, then `site_prior.score_species`.
   - Any exception is caught, `error.log` is written, the stage is skipped and a `SITE_PRIOR_FAILED` warning is logged. It never fails the assessment.
5. **Detect trees** — `stage_trees` → `processing.trees.detect_trees` (see §5).
   - Inputs: CHM, 1 m resolution, AOI mask, `TreeParams` with the user’s minimum height.
   - Outputs: crown label raster, per-tree row/col/height/crown area/diameter/flags, crown preview, extrapolated count range, `CLOSED_CANOPY` warning when >50 % canopy is unattributed.
   - Coordinates converted from pixel centres in UTM to WGS84 with `pyproj`.
6. **Canopy density** — `stage_density` → `processing.density.density_grid` and `summarize` (see §7).
   - Outputs: `density_grid.geojson`, classified PNG, FSI class areas, cover summary.
7. **Vegetation & terrain** — `stage_vegetation` → `processing.vegetation`.
   - NDVI and classes, dry-season leaf-fall classes, WorldCover shares, elevation/slope.
   - Optional; if all inputs are absent the stage is `skipped`.
8. **Quality checks** — `stage_quality`.
   - Builds confidence ratings (`SATELLITE_CONFIDENCE` in satellite mode, `survey_confidence` in survey mode), counts flagged trees, compares canopy cover with WorldCover tree cover (>40 pp ⇒ `SOURCE_DISAGREEMENT`), and checks dense canopy with low NDVI (<0.35 ⇒ `POSSIBLE_CHANGE`). In satellite mode it logs `SPECIES_NOT_AVAILABLE`.
9. **Inventory & reports** — `stage_inventory`.
   - Joins per-tree values to the 10 m NDVI/DEM grid and the density cell; writes `trees.geojson`, `crowns.geojson`, the summary, then `exports.write_all` (CSV, GeoJSON registration, KMZ, Shapefile, PDF).
   - PDF failure is caught inside `write_all` and logged as `REPORT_FAILED`; the other outputs survive.

### 3.2 Survey mode: eleven stages

Defined in `SURVEY_STAGES`, `backend/vandrishti/pipeline_survey.py`, executed by `run_survey_job()`.

| # | Stage id | Name | Function | Seed-job duration* |
|---|---|---|---|---|
| 1 | `aoi` | Read boundary | `pipeline.stage_aoi` | <1 s |
| 2 | `survey` | Check survey data | `stage_survey` | <1 s |
| 3 | `chm` | Canopy height | `stage_chm` | <1 s |
| 4 | `context` | Satellite & terrain | `pipeline.stage_context` | <1 s |
| 5 | `site_species` | Site species prior | `pipeline.stage_site_species` | 13 s |
| 6 | `trees` | Detect trees | `stage_trees` | 49 s |
| 7 | `species` | Classify species | `stage_species` | 1 s |
| 8 | `density` | Canopy density | `pipeline.stage_density` | <1 s |
| 9 | `vegetation` | Vegetation & terrain | `pipeline.stage_vegetation` | <1 s |
| 10 | `quality` | Quality checks | `survey_confidence` + `pipeline.stage_quality` | <1 s |
| 11 | `inventory` | Inventory & reports | `pipeline.stage_inventory` | <1 s |

\*From seeded job `f5186ceaffd3`, total 63 s (`2026-09-26T15:51:17Z` → `15:52:20Z`). This predates the Space and is a precomputed sample.

Survey mode reuses the satellite context, site-prior, density, vegetation, quality and inventory stages. It replaces the 1 m CHM with a survey CHM (0.5 m target grid), replaces watershed detection with DeepForest, and adds `species`.

### 3.3 Satellite vs drone in one table

| | Satellite mode | Drone survey mode |
|---|---|---|
| Required input | Boundary only | Boundary + RGB orthophoto; DSM+DTM or CHM recommended |
| Height source | Meta/WRI 1 m CHM; no temporal choice | Uploaded CHM, or DSM − DTM; fallback to Meta 1 m |
| Detection | CHM Gaussian smoothing + local maxima + marker-controlled watershed | DeepForest RetinaNet tiled prediction; fallback to watershed if unavailable |
| Per-tree species | Never | Regional Random Forest if a model bbox covers the site, else `Unknown`/none |
| Crown representation | Raster watershed label; crown polygon from label | Box → inscribed ellipse polygon; area from CHM pixels above 40 % of height |
| Per-tree height | Maximum CHM in crown | 95th percentile CHM in box |
| Density | Same 25 m FSI grid | Same 25 m FSI grid |
| Typical seed output | 4,846 trees on 121.5 ha; 18,235–44,310 range | 20 trees on 0.036 ha; 10 Unknown + 10 labelled |
| Seed runtime | 9 s (precomputed, cached/local) | 63 s (precomputed, CPU) |
| Validation basis | 529 IDTReeS plots vs airborne LiDAR | 393 IDTReeS plots vs field crowns/heights; NEON aircraft, not drone |

---

## 4. Satellite data

All satellite layers are requested through Google Earth Engine on a north-up UTM grid, using `ee.data.computePixels` with an affine transform (`backend/vandrishti/sources/gee.py::_download_chunk`). Downloads are chunked at 1024 × 1024 px, four worker threads, three attempts per chunk, and cached as GeoTIFFs.

| Dataset | Exact asset | Native res | Temporal selection | Use |
|---|---|---|---|---|
| Meta / WRI Global Canopy Height | `projects/meta-forest-monitoring-okw37/assets/CanopyHeight` | 1 m | **None**; `filterBounds(...).mosaic()` over the whole collection | Tree detection, height, density, crown area |
| Sentinel-2 L2A harmonized | `COPERNICUS/S2_SR_HARMONIZED` | 10/20/60 m | Default most recent complete Oct 1 – Feb 1; auto-widen to Sep 1 – Apr 1; user options `s2_start`/`s2_end` accepted | NDVI, true colour, leaf fall |
| Cloud Score+ | `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | 10 m | Linked to each S2 scene; `cs >= 0.6` | Cloud mask |
| Copernicus DEM | `COPERNICUS/DEM/GLO30_2024_1` | 30 m | Static | Elevation, slope |
| ESA WorldCover | `ESA/WorldCover/v200` | 10 m | First image (2021 product) | Land cover, habitat weighting, tree mask |
| WorldClim BIO | `WORLDCLIM/V1/BIO` | ~1 km | 1960–1990 normals | Site climate features |
| OpenLandMap soil | `OpenLandMap/SOL/SOL_{SAND,CLAY,PH-H2O,ORGANIC-CARBON}.../v02` | 250 m | Static | Site soil features |
| RESOLVE Ecoregions | `RESOLVE/ECOREGIONS/2017` | vector | Static | Ecoregion/biome label |
| GBIF + GlobalTreeSearch | `api.gbif.org`, BGCI CSV | point records | Build: 1970–2026; runtime local lookup: all records within 50 km | Species prior |

### 4.1 Sentinel-2 retrieval and cloud handling

`s2_collection()`:

```python
s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(start, end)
cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED").filterBounds(region).filterDate(start, end)
linked = s2.linkCollection(cs, ["cs"])
linked.map(lambda im: im.select(["B2","B3","B4","B8","B11","B12"])
                         .updateMask(im.select("cs").gte(0.6)))
```

- Median composite of the masked collection, divided by 10,000; plus a `clear` band counting valid red observations.
- `post_monsoon_window()` returns the most recent complete `YYYY-10-01` to `YYYY+1-02-01`; on 2026-11-02 that is **2025-10-01 to 2026-02-01**, matching the seed job.
- If valid pixels inside the AOI are **<90 %**, the window is automatically widened to `end_year-1-09-01` – `end_year-04-01` and logged as `S2_CLOUD_GAPS`.
- If still **<50 %**, vegetation analysis is skipped (`S2_UNAVAILABLE`); the rest of the run continues.
- There is no Sentinel-2 Scene Classification Layer, cirrus/snow mask, shadow mask, or per-pixel cloud-probability threshold beyond Cloud Score+ ≥ 0.6. The “valid” metric is finite red-band pixels after median compositing, not an independently validated cloud-free fraction.

### 4.2 Site environment

`fetch_site_environment()`:

- `reduceRegion(ee.Reducer.mean(), region, scale=250, bestEffort=True, maxPixels=1e8)` over the 7 WorldClim BIO variables plus sand, clay, pH and organic carbon.
- If any variable is `None`, falls back to `reduceRegion(ee.Reducer.first(), centroid, scale=250)`.
- Reads the RESOLVE ecoregion intersecting the boundary centroid.
- Caches the result as JSON keyed by the WKB hash of the boundary.

WorldClim is sampled at 250 m even though its native resolution is ~1 km; this is an oversampling of the GEE asset, not independent 250 m information.

### 4.3 Clipping, reprojection, resampling

- All raster requests are made **directly on the AOI’s UTM grid** via `computePixels` + `affineTransform`, so there is no separate clip step for GEE layers. The grid is padded 20 m around the AOI bounds.
- CHM at 1 m; S2/DEM/WorldCover at 10 m. DEM explicitly calls `.resample("bilinear")`; CHM, S2 and WorldCover use the default GEE sampling (nearest) for their request.
- AOI masks: `rasterio.features.geometry_mask`; 1 m mask is centre-based, 10 m mask uses `all_touched=True`.
- `canopy_height_1m.tif` is a byte-for-byte copy of the cached CHM GeoTIFF, i.e. the full padded grid with `-9999` nodata, **not clipped to the boundary**.
- Survey rasters use `rasterio.warp.reproject` with bilinear resampling onto the survey grid (`processing/survey.py::warp_to_grid`).

### 4.4 Nodata handling

- GEE download uses `-9999` sentinel, replaced by `NaN` on read; cached rasters keep `-9999` as the GeoTIFF nodata value.
- CHM gaps inside the AOI are measured; ≥99 % is fatal, >5 % warns.
- S2 finite-pixel share controls the cloud warnings.
- **Density does not exclude CHM gaps**: `density.canopy_mask` converts NaN to 0 and the denominator includes all AOI pixels. This contradicts the `CHM_GAPS` event action text, which says “Gaps are excluded from density” (`pipeline.py` vs `processing/density.py`). In practice gaps lower the measured cover.
- Tree detection treats NaN as 0 before smoothing/watershed, so gaps cannot become tree tops.

### 4.5 Provenance

`gee.PROVENANCE` stores dataset, exact asset/source, resolution, licence, citation and notes. The pipeline appends these records to `job.state["provenance"]`; the dashboard Sources tab and PDF section 6 render them. Sentinel-2 entries add the actual period and scene count; survey CHM adds a generic “user upload” record.

Limitations of provenance:

- No per-pixel or per-file hash, no download timestamp, no cache-hit flag, no GEE asset version beyond the hard-coded asset id.
- The static CHM note says mean absolute error “about 2.8 m”, while the repository’s own benchmark table reports **4.89 m MAE** against field heights. These are different comparisons (global published vs IDTReeS), but the report does not reconcile them.
- The processed sample’s PDF provenance is generated from the same static records; it is not an independent audit trail.

---

## 5. Tree detection (satellite)

Source: `backend/vandrishti/processing/trees.py`.

### 5.1 Algorithm

1. **Fill and smooth**
   - `chm0 = np.nan_to_num(chm, nan=0.0)`.
   - `chm_s = gaussian_filter(chm0, sigma=smooth_sigma_m / res)`.
   - Satellite `smooth_sigma_m = 0.5 m`; survey `0.3 m`.
2. **Height-dependent local maxima**
   - `window_radius_m(h) = clip((0.8 + 0.12*h) * scale, 1.0, 4.5)`.
   - Satellite `scale = 0.6`; survey `scale = 1.0` (from `SATELLITE_PARAMS` / `SURVEY_PARAMS`).
   - Search radii are evaluated in bins `1.0, 1.5, …, 4.5 m`; `r_px = max(1, round(r_m / res))`.
   - For each bin: `local_max = maximum_filter(chm_s, footprint=disk(r_px), mode="nearest")`; a pixel is a top if `chm_s >= local_max` and its desired radius falls in that bin.
   - Tops must satisfy `chm_s >= min_height_m` (default 5.0 m).
3. **Plateau de-duplication**
   - `ndimage.label(is_top, structure=ones((3,3)))`; one `maximum_position` per connected plateau is kept. Flat-topped crowns therefore produce one marker, not a cluster.
4. **Marker-controlled watershed**
   - `markers, n = ndimage.label(tops)`.
   - `canopy = chm0 >= crown_min_height_m` (2.0 m).
   - `labels = watershed(-chm_s, markers, mask=canopy | tops)`.
   - `-chm_s` makes watershed flow away from peaks; `mask` limits labels to canopy or tops.
5. **Crown trimming**
   - For every labelled pixel, compute distance in metres from its marker: `dist_m = hypot(rr - top_r[label], cc - top_c[label]) * res`.
   - Drop a pixel if `chm0 < 0.4 * tree_height` or `dist_m > max_crown_radius_m(height)`.
   - `max_crown_radius_m(h) = clip(0.5 + 0.3*h, 2.0, 8.0)`.
   - Remaining pixels with `area < 2.0 m²` are removed and labels are remapped.
6. **Per-tree attributes**
   - `height_m = maximum(chm0, labels, tree_index)` — the **maximum** CHM in the trimmed crown.
   - `crown_area_m2 = pixel_count * res²`.
   - `crown_diameter_m = 2 * sqrt(area / pi)` (circle-equivalent diameter).
   - `flags` currently only adds `height_outlier` when `height > 40 m`.
7. **Unattributed canopy**
   - Numerator: `(labels == 0) & canopy_in_aoi & (chm0 >= min_height)`.
   - Denominator: `canopy_in_aoi & (chm0 >= min_height)`.
   - Returned as `unattributed_canopy_fraction`.

### 5.2 Exact extrapolation formula

In `pipeline.stage_trees`:

```python
canopy_m2 = count(chm >= min_height_m inside AOI) * res**2
unattributed = res["unattributed_canopy_fraction"]
p25, p50, p75 = percentile(res["crown_area_m2"], [25, 50, 75])
extra = canopy_m2 * unattributed

estimated_total = int(n + extra / p50)
estimated_low   = int(n + extra / p75)
estimated_high  = int(n + extra / p25)
```

Why the range is inverted: a **smaller** assumed crown area yields **more** trees, so the low count divides by the 75th-percentile crown area and the high count by the 25th.

On the seeded Chandrapur job:

- detected `n = 4,846`
- `unattributed = 0.798` (79.8 %)
- canopy ≥5 m inside AOI = 93.97 ha
- median crown area `p50 = 33.0 m²`
- `estimated_total = 27,568`
- range `18,235 – 44,310`

This is an extrapolation over unresolved canopy, not a count of detected stems. It assumes the unresolved canopy has the same crown-size distribution as the detected crowns — an assumption the code does not test.

### 5.3 Parameters and thresholds

| Parameter | Value | Where |
|---|---|---|
| Minimum tree height | 5.0 m default; UI/API option | `DEFAULT_OPTIONS`; `TreeParams.min_height_m` |
| Smoothing sigma | 0.5 m satellite, 0.3 m survey | `SATELLITE_PARAMS`, `SURVEY_PARAMS` |
| Search-window scale | 0.6 satellite, 1.0 survey | same |
| Search-window formula | `clip((0.8 + 0.12h) * scale, 1, 4.5) m` | `window_radius_m` |
| Maximum crown radius | `clip(0.5 + 0.3h, 2, 8) m` | `max_crown_radius_m` |
| Minimum crown height for watershed | 2.0 m | `TreeParams.crown_min_height_m` |
| Crown trim fraction | 0.4 of own height | `TreeParams.crown_fraction` |
| Minimum crown area | 2.0 m² | `MIN_CROWN_M2` |
| Height outlier | >40 m | `HEIGHT_OUTLIER_M` |
| Local-maximum bins | 1.0–4.5 m, step 0.5 | `find_tree_tops` |
| AOI clipping | tops masked to AOI; watershed mask is **not** AOI-clipped | `detect_trees` |

### 5.4 Duplicate handling, boundary clipping, coordinates

- **Duplicates:** plateau labelling gives one marker per flat top; watershed labels are mutually exclusive; crowns below 2 m² are deleted. There is no explicit non-maximum suppression between neighbouring detected trees beyond the search window.
- **Boundary:** tree tops are restricted to `aoi_mask`. The watershed mask is `canopy | tops`, **not** the AOI mask, so a crown can grow into canopy pixels outside the boundary. Crown area therefore includes outside-boundary pixels, and crown polygons can cross the boundary. `unattributed_canopy_fraction` is computed inside the AOI only. Survey mode also keeps a box if its **centre** is inside the AOI, so box crowns can spill outside.
- **Coordinates:** pixel centre → UTM:
  - `x = grid.xmin + (col + 0.5) * res`
  - `y = grid.ymax - (row + 0.5) * res`
  - then `Transformer.from_crs(utm_epsg, 4326, always_xy=True)`.

### 5.5 Detection validation

Source: `validation/idtrees_validation.py`, results `results/idtrees/validation.md` (2026-09-24), IDTReeS 2020, 393 plots, 1,765 hand-delineated crowns, one-to-one greedy IoU ≥ 0.4 matching.

| Method | Recall | Precision (lower bound) | Mean IoU |
|---|---|---|---|
| DeepForest RGB, score ≥ 0.1 | 0.517 | 0.175 | 0.617 |
| DeepForest RGB, score ≥ 0.2 | 0.493 | 0.242 | 0.620 |
| DeepForest RGB, score ≥ 0.3 | 0.455 | 0.303 | 0.625 |
| CHM watershed on LiDAR CHM | 0.343 | 0.217 | 0.561 |
| CHM watershed on Meta 1 m | **0.136** | 0.179 | 0.546 |

The satellite-mode recall is 13.6 % of labelled crowns. This is the empirical basis for the “lower bound” wording, and it is the strongest evidence against “every tree” claims.

---

## 6. Species prior

Source: `backend/vandrishti/processing/site_prior.py`; build: `training/build_species_niches.py`.

### 6.1 What is built

For each candidate tree taxon:

1. Query GBIF occurrence records (`taxonKey`, coordinates, `hasGeospatialIssue=false`, `occurrenceStatus=PRESENT`, `year=1970,2026`, accepted basis-of-record list).
2. Sample up to five non-India countries (300 records each) plus India at offsets 0, 600 and 3000 (300 each) → **maximum 2,400 sampled records per taxon**.
3. Thin locations to a 0.05° (~5 km) grid; cap retained niche points at 800 per taxon.
4. Sample WorldClim BIO + OpenLandMap soil at each retained cell centre via Earth Engine.
5. Sample ESA WorldCover at each Indian record location to estimate habitat shares.
6. Store per-taxon niche points, climate/soil values, habitat shares, record counts and an envelope radius.

Candidate selection:

- Indian plant species with ≥30 GBIF India records, restricted to names present in the BGCI GlobalTreeSearch CSV, top 500 by India record count.
- Plus a hard-coded list of 41 central-Indian anchor trees.
- Plus species/genera predicted by any local species model.
- Taxa with fewer than 20 usable locations are dropped.

The committed table contains **493 taxa** (`models/niches/tree_niches.json`), built 2026-09-26.

### 6.2 Exact reconciliation of 398,592 vs 76,369

| Number | Where it comes from | What it actually is |
|---|---|---|
| **398,592** | `n_records_total = sum(t["n_records"] for t in taxa)` in `build_species_niches.py` | Sum of **sampled** GBIF records per taxon, before 5 km thinning. Each taxon is page-capped at 2,400 (5 countries × 300 + 3 India pages × 300), so this is not the complete GBIF record count and is not a set of distinct global records. |
| **76,369** | `n_reference_records = len(ref_taxon)` | Number of **India reference rows** written to `ref_z`: one row per (Indian 5 km cell, species) that has both environment and land-cover values. This is the set actually used for an Indian site. |
| **140,970** | `tree_niches.npz["points"]` shape | Per-taxon niche points after 5 km thinning and the 800-point cap; used for non-India scoring and for model-class priors. |

So the two headline numbers are **not supposed to match**. `398,592` is a sampled worldwide record count; `76,369` is the India reference-row count used by the runtime method. The proposal’s phrase “493 species, 398,592 records” is misleading when placed next to a runtime method described as “1,500 nearest of 76,369 records” — the 398,592 records are not the pool being searched for an Indian site.

Additional precision:

- “493 species” is really **493 taxa**. The live seeded survey site’s prior output includes a row named `Magnolia` (a genus), and the builder explicitly adds model taxa that may be genera. At the Chandrapur site only **146 of 493** taxa survive the prior’s minimum-share filter.
- Some entries are shrubs/small trees in common usage (e.g. `Helicteres isora`, `Woodfordia fruticosa` appear in the top Chandrapur list). Membership is inherited from GlobalTreeSearch, not independently checked against a growth-form field.
- `n_records` per species is capped at 2,400; e.g. `Mangifera indica` has `n_records: 2400`, `n_locations: 796`, despite `india_records: 89714`. The table’s `india_records` is a GBIF count, not the number of points used.

### 6.3 Runtime scoring

`score_species(env, table, in_india, local_keys, site_habitat)`:

1. Build the site vector:
   - raw 11 variables: `bio01, bio04, bio05, bio06, bio12, bio15, bio17, sand, clay, ph, soc`
   - `log1p` for `bio12`, `bio17`, `soc`
   - standardize with the table’s global mean/std.
2. **India:** find the `REF_K = 1500` nearest rows in `ref_z` by Euclidean distance in the 11-D standardized space. No geographic distance, ecoregion filter, or species-range model is used.
3. **Outside India:** find the `NICHE_K = 400` nearest points among the model/species’ own worldwide niche points.
4. Kernel weights: `w = exp(-0.5 * (d / median(d_nearest))²)`. Bandwidth is the median distance of the selected neighbours.
5. Habitat reweighting (India only), per reference row:
   - `ratio_g = (site_habitat[g] + 0.02) / (baseline[g] + 0.02)`
   - multiply the kernel weight by the row’s habitat-group ratio.
   - `HABITAT_GROUPS`: forest = WorldCover 10, 95; shrub/grass = 20, 30; cropland = 40; built = 50; other = 60, 70, 80, 90, 100.
6. Planted-species discount (India only):
   - `odds(b) = (1-b)/b`, with `b` clipped to 0.02–0.98.
   - `natural = clip(odds(species_built_share) / odds(baseline_built_share), 0.1, 5.0)`.
   - `discount = (1 - site_built) * natural + site_built`.
   - Species recorded mostly in built-up land are down-weighted at a natural forest site; at a fully urban site the discount is neutral.
7. Local boost: any species whose GBIF key appears in the 50 km facet gets its share multiplied by `LOCAL_BOOST = 1.5`.
8. Normalize to 100 %, drop shares below `MIN_SHARE_PCT = 0.1`, sort descending, round to one decimal.

The ranking formula is therefore:

```
share_species ∝ Σ_{i ∈ kNN} exp(-0.5 (d_i / median(d))²)
              × habitat_ratio_i
              × planted_discount_species
              × (1.5 if recorded within 50 km else 1)
```

### 6.4 What the percentages mean

`share_pct` is the species’ **share of the weighted nearest occurrence records**, not:

- a population share,
- a stem count,
- a probability that any particular tree is that species,
- an area share.

The code and report both state “predicted likelihood of occurrence, not a tree count.” The validation table measures how poorly these shares reconstruct plot composition: 39–47 percentage-point composition error. That is direct evidence they are not population estimates.

### 6.5 How the prior is used per tree (survey only)

`prior_for_classes()` maps model class codes to canonical scientific names in the niche table. If at least two classes map:

- In India, weights come from the site’s `scored` shares; otherwise from the nearest worldwide records of the model’s own classes.
- Unmappable classes get a neutral `1/n` weight; the result is normalized.
- `presence_gate(prior, 0.02)` returns 1 for species at/above 2 % and 0 below.
- `adjust_probabilities(p, gate, tau=1.0)` computes `p' ∝ p · max(gate, 0.02)^1.0`, renormalizes, and then applies the confidence threshold.

Important details:

- Survey calls this with **`tau = 1.0`**, not the `0.5` default of `adjust_probabilities` and not the docstring’s “tempered τ < 1”. The validation table reports all three; the deployed path is the τ = 1 presence-gate variant.
- The gate down-weights unlikely species but the `0.02` floor keeps them non-zero; it never hard-excludes.
- Changed labels get the flag `species_prior_adjusted`; raw image-only confidence is retained as `species_confidence_image_only` in the job record/GeoJSON, but **not in the CSV**.

### 6.6 Validation of the prior

`results/idtrees/site_prior.md` (1,109 labelled crowns, 12 classes, 5-fold grouped by plot):

| Method | Accuracy | Macro F1 | Share assigned ≥0.5 | Accuracy when assigned | Plot composition error |
|---|---|---|---|---|---|
| Image only (RF) | 41 % | 0.255 | 30 % | 68 % | 39.1 pp |
| Image + prior τ=0.25 | 41 % | 0.259 | 32 % | 68 % | — |
| Image + prior τ=0.5 | 40 % | 0.250 | 34 % | 68 % | 43.7 pp |
| Image + prior τ=1.0 | 39 % | 0.228 | 42 % | 61 % | — |
| Image + presence gate | **42 %** | **0.265** | 35 % | 68 % | — |
| Oracle presence gate | 43 % | 0.267 | 36 % | 69 % | — |

Only 7 % of the image-only errors predict a species that does not occur at the site — the ceiling for any location prior. The prior improves accuracy by about one point, not by solving species classification.

### 6.7 Data/reproducibility caveats

- The niche build needs `data/reference/global_tree_search.csv`, which is **not in the repository** (`data/` is git-ignored). The built table is committed, but the build cannot be reproduced from a fresh clone without that CSV, GBIF access and Earth Engine.
- The live runtime GBIF lookup has a 20 s timeout and caches by rounded lat/lon. On failure it logs `GBIF_UNAVAILABLE` and scores without the 50 km boost.
- The table is frozen at 2026-09-26. New records, taxonomic changes and model classes are not automatically incorporated.

---

## 7. Drone survey mode

Sources: `backend/vandrishti/pipeline_survey.py`, `backend/vandrishti/processing/survey.py`, `backend/vandrishti/processing/species.py`, `training/train_species.py`.

### 7.1 Actual input requirements

| Input | Required | Accepted | Code behaviour |
|---|---|---|---|
| Boundary | Yes | KML/KMZ/GeoJSON | Same parser as satellite |
| Orthophoto (`ortho`) | Yes | GeoTIFF, ≥3 bands, any projected CRS | Must be georeferenced; no CRS is fatal |
| DSM | Optional | GeoTIFF, one band, metres | Used with DTM to build CHM |
| DTM | Optional | GeoTIFF, one band, metres | Used with DSM |
| CHM | Optional | GeoTIFF, one band, metres | Takes precedence over DSM−DTM |
| Field labels | For species | GeoJSON points/polygons with `species` | Used only by `training/train_species.py`, not uploaded at runtime |

Validation in `stage_survey`:

- Missing orthophoto ⇒ fatal `ORTHO_MISSING`.
- Raster unreadable / no CRS ⇒ fatal `SURVEY_FILE_INVALID`.
- Orthophoto <3 bands ⇒ fatal `ORTHO_BANDS`.
- Orthophoto resolution > `MAX_ORTHO_RES_M = 1.0 m` ⇒ fatal `ORTHO_TOO_COARSE`; the event action text says “Use drone imagery at 2–30 cm”.
- Resolution > `WARN_ORTHO_RES_M = 0.3 m` ⇒ warning `ORTHO_COARSE`.
- AOI coverage <20 % ⇒ fatal `NO_COVERAGE`; <95 % ⇒ warning `PARTIAL_COVERAGE`.
- DSM without DTM and without CHM ⇒ warning `DTM_MISSING`.
- No height raster at all ⇒ `CHM_FALLBACK` and satellite Meta 1 m CHM is used; every tree is flagged `height_from_satellite`.
- Minimum survey AOI = `SURVEY_MIN_AREA_KM2 = 0.0003 km²` (0.03 ha).
- Space upload cap: `VANDRISHTI_MAX_SURVEY_UPLOAD_MB=200`; backend default is 2048 MB.

### 7.2 Orthophoto format and resolution

`working_ortho()`:

```python
res = max(DEEPFOREST_RES_M, native)   # DEEPFOREST_RES_M = 0.1 m
```

- It does **not** upsample to 10 cm. A 2–3 cm image is resampled to 10 cm; a 20 cm image stays 20 cm; a 1 m image is accepted (with a warning above 30 cm) and stays 1 m.
- It writes an 8-bit, 3-band RGB GeoTIFF on the AOI UTM grid (`working_ortho.tif`).
- If the source is not uint8 or has values outside 0–255, it applies a 0.5–99.5 percentile stretch to 0–255.
- No radiometric calibration, colour balance, seam-line correction, or orthomosaic quality check is performed.
- `DEEPFOREST_RES_M = 0.1` is a hard-coded expectation of the NEON-pretrained model, not a property derived from the upload.

### 7.3 DSM/DTM → CHM

`build_chm()`:

- If `chm` is uploaded: warp band 1 onto the 0.5 m survey grid (`SURVEY_CHM_RES_M = 0.5`), clip negatives to 0.
- Else if both DSM and DTM: warp both, compute `dsm - dtm`, clip negatives to 0.
- Else: return `None`, which triggers the satellite fallback.
- There is **no** point-cloud processing, ground classification, pit-free CHM, spike removal, or vertical-datum reconciliation. The system trusts the delivered DSM/DTM.
- The survey CHM is used at 0.5 m for detection/species/density, but the density cell size remains the user’s `grid_cell_m` (default 25 m).

### 7.4 DeepForest model and inference

`processing/survey.py::_deepforest()`:

- Lazy import `deepforest.main`; `main.deepforest()`; `load_model("weecology/deepforest-tree")`.
- Live Space pins `deepforest==2.1.0`; the backend requirements file does **not** include DeepForest at all, so a manual `pip install deepforest` is required for survey mode locally.
- Pretrained weights, **not fine-tuned** on Indian or project data.
- If `VANDRISHTI_DEEPFOREST_ACCELERATOR` is set, it overrides the Lightning accelerator; the Space sets it to `cpu`.
- The model is a singleton behind a lock; the first call downloads/loads weights.

`detect_crowns()`:

- Reads the working RGB GeoTIFF.
- `pad_to_patch()` zero-pads images smaller than 400 px so the detector does not magnify them beyond its training scale. The repository docs claim this raised IDTReeS recall from 0.15 to 0.52.
- `model.predict_tile(image=..., patch_size=400, patch_overlap=0.25, iou_threshold=0.15)`.
- Tiles are 400 px = 40 m at 10 cm. Overlap 25 %; duplicate boxes at tile edges are suppressed by DeepForest NMS at IoU 0.15.
- Boxes whose **centre** falls outside the original (unpadded) image are dropped.
- Boxes are converted from pixel coordinates to UTM metres using the working grid; the result is a list of `{xmin, xmax, ymin, ymax, score}`.

`measure_boxes()`:

- Keep a box only if its centre is inside the AOI polygon.
- Height = **95th percentile** of finite CHM values in the box.
- If survey height data exists, boxes below `min_tree_height_m` are excluded and counted as `LOW_VEGETATION`; if heights came from satellite fallback, `min_h = 0.0` so coarse satellite heights do not veto crowns seen in the imagery.
- `crown_area_m2 = count(CHM >= 0.4 * height) * res²`, minimum 1.0 m².
- `crown_geom` is an **ellipse inscribed in the box** (`Point(cx,cy).buffer(1.0, 24)` scaled by box width/2 and height/2).
- `crown_diameter_m` is later computed as `sqrt(box_width * box_height)`, not as `2*sqrt(area/pi)` and not as the ellipse diameter. Satellite and survey therefore use different crown-diameter definitions.
- Box `score` is retained; `LOW_DETECTION_SCORE = 0.2` adds `low_detection_confidence` below that.

### 7.5 Output boxes vs masks

- DeepForest produces **boxes**, not instance masks.
- The pipeline converts each box to an ellipse polygon for display/export and computes crown area from CHM pixels inside the box, not from the ellipse.
- Consequently `crown_area_m2` and the exported crown polygon area are not the same quantity; the Shapefile `crowns.shp` polygon area will not equal the CSV `crown_area_m2`.
- No panoptic/instance segmentation, no mask refinement, no overlap resolution between neighbouring ellipses.

### 7.6 Per-tree species classifier

`stage_species()`:

1. Find a model: `species.model_for_location(models/species, lon, lat)` loads every `*.joblib` in sorted filename order and returns the first whose `bbox` contains the AOI centroid.
2. If no model, or no DeepForest boxes: all trees get `species = "Unknown"`, confidence 0, `species_status = "no_local_model"`, stage skipped, `NO_SPECIES_MODEL` event.
3. Otherwise:
   - Read RGB + transform from the working orthophoto.
   - `crown_features()` computes 12 features over the inner 60 % of each box: R/G/B means and stds, excess green mean, G/R ratio, brightness mean, brightness coefficient of variation, height, crown area.
   - `bundle["model"].predict_proba(X)`.
   - Raw labels use `bundle["threshold"]` (default 0.5); below threshold ⇒ `Unknown`.
   - If the site prior and model `scientific_names` exist, apply `presence_gate` + `adjust_probabilities(tau=1.0)`, recompute labels/confidence, and flag changed labels.
   - Count species; warn if >30 % Unknown (`MANY_UNKNOWN_SPECIES`); flag rare species with ≤2 trees when ≥50 trees were classified (`RARE_SPECIES`).
   - Add `species_uncertain` to every Unknown tree.

Training (`training/train_species.py`):

- Inputs: one or more orthophotos, optional CHMs, a GeoJSON of labelled trees with a `species` property, a region name.
- Points get a square crown of `--point-crown-m` (default 6 m); polygons use their bounds.
- Features are the same 12 used at inference.
- Species with fewer than `--min-samples` (default 8; validation uses 15) become `Other`.
- Model: `RandomForestClassifier(n_estimators=300, max_depth=12, class_weight="balanced", random_state=0)`.
- Cross-validation: `StratifiedKFold` (not grouped by plot) with `cross_val_predict`, so trees from the same plot can appear in train and test. This is a methodological difference from `validation/idtrees_validation.py`, which uses `StratifiedGroupKFold` by plot.
- Bundle: `{model, features, classes, scientific_names, threshold, region, bbox, trained_on, metrics}`; bbox is the label extent ±0.05° (~5 km).
- No training data is shipped. The Space’s model is the IDTReeS US model described below.

### 7.7 Unknown-class logic

- Confidence below `threshold` (0.5 default) ⇒ `Unknown`, never a guess.
- `species_uncertain` flag; >30 % Unknown warning.
- `Unknown` is excluded from named species counts in the dashboard.
- The prior gate is not a hard exclusion: it down-weights to a 0.02 floor.
- If the site prior changes a label, `species_prior_adjusted` is added and the image-only confidence is kept separately.

### 7.8 Height extraction in survey mode

- Survey CHM: 0.5 m target grid, from uploaded CHM or DSM − DTM.
- Per tree: 95th percentile of CHM values in the DeepForest box.
- Units: metres, no conversion.
- If no survey height data: Meta 1 m satellite CHM; every tree flagged `height_from_satellite`; heights are not used to veto detections (`min_h = 0`).
- `height_outlier` if >40 m.
- No per-tree height confidence value; only the stage-level confidence rating.

### 7.9 Evaluation metrics actually available

From `results/idtrees/validation.md` (IDTReeS 2020; NEON OSBS/MLBS/TALL; **aircraft**, not drone):

**Crown detection** (393 plots, 1,765 labelled crowns, IoU ≥ 0.4):

| Method | Recall | Precision (lower bound) | Mean IoU |
|---|---|---|---|
| DeepForest, score ≥ 0.1 | 0.517 | 0.175 | 0.617 |
| DeepForest, score ≥ 0.2 | 0.493 | 0.242 | 0.620 |
| DeepForest, score ≥ 0.3 | 0.455 | 0.303 | 0.625 |
| CHM watershed on LiDAR | 0.343 | 0.217 | 0.561 |

Recall by site at score ≥ 0.1: MLBS 0.475, OSBS 0.501, TALL 0.745.

**Height vs field measurement** (1,057 trees):

| Source | MAE | RMSE | Bias | R² |
|---|---|---|---|---|
| LiDAR CHM | 2.7 m | 4.12 m | +1.93 m | 0.444 |
| Meta 1 m CHM | 4.89 m | 6.20 m | −3.24 m | −0.258 |

**Species** (1,109 crowns, 12 classes, 5-fold grouped by plot):

| Features | Accuracy | Macro F1 | Weighted F1 | At threshold 0.5: assigned / accuracy |
|---|---|---|---|---|
| RGB + height (drone-equivalent) | 0.410 | 0.255 | 0.410 | 30.1 % / 68 % |
| RGB + height + hyperspectral (PCA 20) | 0.532 | 0.410 | 0.530 | 19.7 % / 89 % |

The production pipeline uses RGB + height only; hyperspectral is a validation experiment, not an implemented input path.

### 7.10 What the live survey job actually did

Seeded job `f5186ceaffd3` (“IDTReeS OSBS plot 231”):

- 0.036 ha; orthophoto 0.1 m, 3 bands, 100 % coverage; uploaded CHM 1.0 m, resampled to 0.5 m.
- DeepForest detected **20 trees** (554/ha), median height 15.3 m, mean detection score 0.327.
- Species model: `idtrees_neon_osbs_mlbs.joblib`, 1,109 IDTReeS labelled crowns, trained 2026-09-24.
- Result: **Unknown 10, ACRU 7, PIPA2 2, QULA2 1**; 18 of 20 flagged; 4 low-confidence detections; 2 crowns below 5 m excluded as low vegetation.
- The live event log confirms the site-prior check changed **8 of 20 labels** (`SPECIES_SITE_PRIOR`), leaving 10 `Unknown`; it also logs `MANY_UNKNOWN_SPECIES` as “10 of 20 trees (50%)”.
- The separate committed sample PDF (`1b3410f0db95`, a different job id) says 18 of 20 trees (90 %) are below the raw 0.50 confidence threshold. That is an older/pre-prior artifact; it is direct evidence that the evidence pack and the current code are out of sync.
- This is an honest demonstration of the Unknown policy, but it is the opposite of “species of each tree” as a reliable product.

---

## 8. Canopy density

Source: `backend/vandrishti/processing/density.py`.

### 8.1 Threshold and cell construction

- Canopy mask: `chm >= canopy_threshold_m`, default **5.0 m**; NaN → 0.
- Then `& aoi_mask`.
- `cpx = max(1, round(cell_m / res))`; at 1 m and 25 m cells, `cpx = 25`.
- The grid is padded to a multiple of `cpx`; block sums compute:
  - `aoi_px` = AOI pixels in the cell
  - `canopy_px` = canopy pixels in the cell
- Per-cell cover:

```
canopy_cover_pct = 100 * canopy_px / aoi_px        (0 if aoi_px = 0)
aoi_fraction     = aoi_px / (cpx²)
area_ha          = aoi_px * res² / 10000
```

- Cells with `aoi_fraction < 0.1` are omitted from the cell list. This creates a user-visible edge effect: trees in such cells can still be detected but their `fsi_density_class` is blank in the inventory. The committed satellite CSV has 4 blank classes in 4,846 rows; the survey CSV has 2 in 20.

### 8.2 FSI classes

`FSI_CLASSES`:

| Code | Name | Cover |
|---|---|---|
| VDF | Very Dense Forest | 70 – 100.01 % |
| MDF | Moderately Dense Forest | 40 – 70 % |
| OF | Open Forest | 10 – 40 % |
| NF | Scrub / Non-forest | 0 – 10 % |

`fsi_class()` returns the first matching class, so 70 % is VDF, 40 % is MDF, 10 % is OF, 0 % is NF.

### 8.3 Hectare aggregation

`summarize()`:

- whole-AOI `canopy_cover_pct = canopy.sum() / aoi_px` (pixel count, not the mean of cell percentages);
- `canopy_area_ha = canopy.sum() * res² / 10000`;
- `fsi_area_ha[class] = Σ area_ha of cells in that class` (cells clipped to AOI, not full 625 m²);
- `fsi_area_pct = area_by_class / sum(area_by_class) * 100`;
- `dominant_fsi_class = argmax(area_by_class)`.

Because cells with `<10 %` AOI overlap are omitted, the FSI area total can differ slightly from the AOI area. In the satellite seed job, FSI areas sum to 121.44 ha against a 121.51 ha AOI; the per-cell rounding explains the gap.

### 8.4 Nodata handling

- CHM NaN is converted to 0, so gaps count as non-canopy in both numerator and denominator (denominator includes all AOI pixels). This **biases cover downward** where CHM has gaps and contradicts the `CHM_GAPS` action text “Gaps are excluded from density”.
- S2/DEM/WorldCover gaps are not part of this calculation.
- The density grid GeoJSON is computed from the same CHM; there is no independent gap mask.

### 8.5 Validation

`results/idtrees/satellite_vs_lidar.md` (529 IDTReeS 20 m plots; reference NEON airborne LiDAR CHM; satellite Meta 1 m; canopy ≥5 m):

| Output | MAE | RMSE | Bias (satellite − LiDAR) | Correlation |
|---|---|---|---|---|
| Canopy cover (percentage points) | 9.64 | 15.75 | −5.79 | 0.919 |
| Plot canopy height p95 (m) | 5.06 | 6.19 | −4.61 | 0.777 |

FSI class: same class on **77 %** of plots, within one class on **97 %**.

Confusion matrix (rows LiDAR, columns satellite): VDF 306/23/6/2; MDF 15/42/53/8; OF 0/3/54/13; NF 0/0/0/4.

By site: MLBS 56 plots, 98 % class agreement; OSBS 321 plots, **64 %**; TALL 152 plots, 97 %. The weak site is OSBS, where satellite cover is biased −10.4 pp.

Caveat: a 20 m plot is smaller than the 25 m production cell; these are plot-scale comparisons, and the LiDAR/CHM dates differ. There is **no Indian validation** of density classes.

---

## 9. Height

### 9.1 Satellite height

- Source: Meta/WRI 1 m CHM, no temporal filtering.
- Per tree: **maximum** CHM value inside the trimmed watershed crown (`ndimage.maximum(chm0, labels, idx)`).
- Units: metres, rounded to 1 decimal in the inventory.
- Crown height is not corrected for the model’s known underestimation of tall trees.
- `height_outlier` flag for >40 m.
- Stage-level confidence “Medium”; report reason “±6 m vs field-measured trees, underestimates by 3–5 m”.

### 9.2 Drone height

- Source: uploaded CHM, or DSM − DTM, on a 0.5 m UTM grid; fallback Meta 1 m.
- Per tree: **95th percentile** of CHM values in the DeepForest box.
- If fallback satellite height: `height_from_satellite` on every tree; heights are not used to reject detections.
- `height_outlier` >40 m.
- Stage-level confidence “High” only when `height_is_survey` is true; otherwise “Medium”.

### 9.3 Inconsistency between modes

The two modes use different per-tree statistics (max vs p95), different crown geometry (watershed label vs box), and different crown-diameter formulas. The PDF’s generic method text does not explain this. Comparisons of “mean height” between satellite and survey outputs are therefore not apples-to-apples.

### 9.4 Height validation

From `results/idtrees/validation.md` (1,057 field-measured trees):

| Source | MAE | RMSE | Bias | R² |
|---|---|---|---|---|
| LiDAR CHM (survey) | 2.7 m | 4.12 m | +1.93 m | 0.444 |
| Meta 1 m CHM (satellite) | 4.89 m | 6.20 m | −3.24 m | −0.258 |

The positive LiDAR bias is attributed in the docs to taller neighbouring canopy inside labelled understory crowns. The satellite R² is negative: it is worse than predicting the mean field height for this sample.

---

## 10. Quality, edge cases, retries and logging

### 10.1 Event catalogue

All events are written by `Job.event(level, code, message, action, stage, data)`. Codes in the codebase:

| Area | Codes |
|---|---|
| Job lifecycle | `JOB_STARTED`, `JOB_COMPLETED`, `JOB_INTERRUPTED`, `INTERNAL_ERROR` |
| Boundary | `AOI_INVALID`, `AOI_WARNING` |
| Canopy height | `CHM_UNAVAILABLE`, `CHM_NO_DATA`, `CHM_GAPS`, `CHM_FALLBACK` |
| Sentinel-2 | `S2_CLOUD_GAPS`, `S2_UNAVAILABLE`, `S2_FAILED` |
| Context | `DEM_FAILED`, `WORLDCOVER_FAILED`, `LEAF_FALL_FAILED`, `LEAF_FALL_UNAVAILABLE`, `STEEP_TERRAIN` |
| Site prior | `NO_NICHE_TABLE`, `SITE_ENV_FAILED`, `SITE_ENV_GAPS`, `GBIF_UNAVAILABLE`, `SITE_PRIOR_FAILED` |
| Trees | `NO_TREES`, `CLOSED_CANOPY`, `HEIGHT_OUTLIER`, `LOW_VEGETATION` |
| Survey inputs | `ORTHO_MISSING`, `SURVEY_FILE_INVALID`, `ORTHO_BANDS`, `ORTHO_TOO_COARSE`, `ORTHO_COARSE`, `NO_COVERAGE`, `PARTIAL_COVERAGE`, `DTM_MISSING` |
| Survey detection | `DEEPFOREST_UNAVAILABLE`, `LOW_CONFIDENCE_DETECTIONS`, `HEIGHT_UNVERIFIED` |
| Species | `SPECIES_NOT_AVAILABLE`, `NO_SPECIES_MODEL`, `SPECIES_MODEL`, `SPECIES_SITE_PRIOR`, `MANY_UNKNOWN_SPECIES`, `RARE_SPECIES` |
| Quality | `SOURCE_DISAGREEMENT`, `POSSIBLE_CHANGE` |
| Reports | `REPORT_FAILED` |

### 10.2 Edge cases

| Case | Detection | Handling |
|---|---|---|
| Cloudy imagery | finite S2 pixels <90 %; <50 % | Widen Oct–Feb to Sep–Apr; if still <50 %, skip vegetation analysis |
| Closed / touching canopy | unattributed canopy >50 % | `CLOSED_CANOPY` warning; detected count declared a lower bound; extrapolated range |
| Missing CHM pixels | gap % inside AOI | >5 % warning; ≥99 % fatal; **density treats gaps as non-canopy despite the event text saying they are excluded** |
| No trees | `n == 0` | Warning; empty inventory/exports still produced; stage not failed |
| Tall trees | height >40 m | `height_outlier` flag; no correction |
| Recent clearing | WorldCover tree cover vs CHM cover difference >40 pp; or cover >40 % with mean NDVI <0.35 | Warning only; no change detection, no date of change |
| Survey without DTM | DSM only or no height raster | `DTM_MISSING` / `CHM_FALLBACK`; satellite heights, flagged |
| Survey coverage <95 % | AOI intersection | Warning; trees outside surveyed area are not counted |
| Survey coverage <20 % | AOI intersection | Fatal |
| Too-coarse orthophoto | >1.0 m | Fatal |
| Orthophoto 30 cm–1 m | >0.3 m | Warning; processed at native resolution |
| Species model absent | No bbox match | All `Unknown`; stage skipped; `NO_SPECIES_MODEL` |
| >30 % Unknown | Species counts | `MANY_UNKNOWN_SPECIES` warning |
| Rare species | ≤2 trees, ≥50 classified | `RARE_SPECIES` info |
| Server restart | startup scan of job list | `queued`/`running` jobs marked failed, `JOB_INTERRUPTED`; no resume |
| Export failure | exception during CSV/KMZ/Shapefile | Job fails; PDF failure is non-fatal and logged |

### 10.3 Retry strategy

- GEE chunk download: **3 attempts, no delay**, then `GEEError`. This covers transient `computePixels` failures but not sustained rate limits.
- GBIF runtime 50 km lookup: no retry; 20 s timeout; returns `None` and logs `GBIF_UNAVAILABLE`.
- GBIF build (`build_species_niches.py`): 5 attempts with 2/4/6/8/10 s sleeps; 404 returns `{}`; a failed page is skipped.
- Earth Engine sampling during build: 4 attempts with 5/10/15/20 s sleeps.
- DeepForest inference: no retry; one model load/inference failure fails the stage.
- PDF: failure caught; no retry.
- There is no job-level retry, no dead-letter queue, no exponential backoff for GEE, and no circuit breaker.

### 10.4 Event logging and audit trail

- `events.jsonl` is append-only; `job.json.event_counts` aggregates info/warning/error.
- The dashboard shows all events with code/message/action; the Quality tab filters out info; the PDF includes only warning/error events.
- Stage records include `started_at`, `finished_at`, `summary`, `metrics`, `preview`, `status`; the UI computes durations.
- No log rotation, no retention policy, no structured trace ids beyond the job id.
- `error.log` holds Python tracebacks for unexpected failures; it is not downloadable through the API (and should not be).

### 10.5 Concurrency and safety

- Two worker threads per process; a third submitted job waits in the executor queue. No queue-depth limit or timeout.
- File-backed state is safe within one process (locks + atomic replace) but not across multiple Uvicorn workers/replicas; the Space runs one replica.
- Upload safety: extension allow-list, size caps, `defusedxml`, KMZ entry/size caps, filename regex, output allow-list, job-id regex.
- Auth: PBKDF2-SHA256, constant-time compare, token expiry, login lockout; file downloads accept `?token=` because `<img>`/download links cannot send headers.
- No rate limit on job creation; no CSRF token (bearer header); TLS is provided by the hosting platform.

---

## 11. Outputs and exact schema

### 11.1 Files produced

Satellite job files:

| File | What it is |
|---|---|
| `aoi.geojson` | Boundary FeatureCollection |
| `chm.png` | Rendered canopy-height overlay with alpha mask |
| `canopy_height_1m.tif` | Copy of the cached Meta CHM GeoTIFF (padded grid, `-9999` nodata) |
| `s2_truecolor.png` | Sentinel-2 true-colour overlay |
| `ndvi.png` | NDVI overlay |
| `leaf_fall.png` | Categorical leaf-habit overlay |
| `landcover.png` | WorldCover categorical overlay |
| `crowns.png` | Crown label raster coloured by height |
| `density.png` | FSI class raster/PNG |
| `trees.geojson` | Tree points with full properties |
| `crowns.geojson` | Crown polygons |
| `density_grid.geojson` | 25 m cells (cover, FSI, trees/ha, mean height, area) |
| `tree_inventory.csv` | Per-tree table |
| `tree_inventory.kmz` | Google Earth: boundary, density cells, tree placemarks |
| `tree_inventory_shapefile.zip` | `trees.shp` points + `crowns.shp` polygons + `.prj` |
| `assessment_report.pdf` | PDF report |
| `job.json`, `events.jsonl` | State and log |
| `input/<boundary>` | Original upload |

Survey job files: same, except `working_ortho.tif` and `ortho.png` instead of `canopy_height_1m.tif`; **no survey CHM GeoTIFF is exported**. The survey job’s `exports` list has CSV, GeoJSON, KMZ, Shapefile, PDF — no `chm_tif`.

### 11.2 CSV schema (exact)

`CSV_FIELDS` in `backend/vandrishti/exports.py`:

```
tree_id, latitude, longitude, height_m, crown_area_m2, crown_diameter_m,
local_canopy_density_pct, fsi_density_class, ndvi, vegetation_condition,
ground_elevation_m, species, species_confidence, species_status,
detection_method, height_source, quality_flags
```

Details:

- `tree_id` = `T000001` style.
- Coordinates rounded to 7 decimals (WGS84).
- `quality_flags` joined with `;`.
- `fsi_density_class` can be empty for cells with <10 % AOI overlap (4 rows in the satellite sample; 2 in the survey sample).
- `species` is empty in satellite mode; `species_status` is `not_determined_satellite_mode`.
- Survey `species_status` is `classified (...)` or `no_local_model`.
- **Omitted from CSV despite existing in the record:** `detection_score` and `species_confidence_image_only`. The GeoJSON has them.
- `vegetation_condition` is a class string (`non_vegetated`, `sparse`, `moderate`, `dense`) or empty if NDVI is unavailable.
- `ground_elevation_m` is the 10 m DEM value sampled at the tree point, not a measured ground height.

### 11.3 GeoJSON schema

`trees.geojson` is a WGS84 FeatureCollection of Points. Each feature’s properties are:

```
tree_id, latitude, longitude, height_m, crown_area_m2, crown_diameter_m,
local_canopy_density_pct, fsi_density_class, ndvi, vegetation_condition,
ground_elevation_m, species, species_confidence, species_confidence_image_only,
species_status, detection_score, detection_method, height_source, quality_flags
```

`crowns.geojson`: polygons with `tree_id`, `height_m`, `crown_area_m2`.
`density_grid.geojson`: polygons with `aoi_fraction`, `canopy_cover_pct`, `fsi_class`, `detected_trees`, `trees_per_ha`, `mean_tree_height_m`, `area_ha`; FeatureCollection extras `cell_size_m`, `canopy_threshold_m`.

### 11.4 KMZ

`write_kmz()` writes a single `doc.kml` inside a zip:

- boundary polygon with yellow outline;
- density cells as polygons styled by FSI class (folder initially hidden);
- tree Placemarks as points, styled by height bin, with a description of height, crown area, local density, FSI class and NDVI.

It does **not** include crown polygons, species, confidence or quality flags. Icons are Google’s `placemark_circle.png`.

### 11.5 Shapefile

`write_shapefile_zip()` uses pyshp in memory, WGS84 WKT1 ESRI:

- `trees.shp` (POINT): `tree_id`, `height_m`, `crown_m2`, `crown_dm`, `cover_pct`, `fsi_class`, `ndvi`, `ground_m`, `species`, `flags`.
- `crowns.shp` (POLYGON) if crowns exist: `tree_id`, `height_m`, `crown_m2`.
- No `.cpg`; DBF field widths are fixed (`species` C30, `flags` C60), so long names/flags can be truncated.
- Survey crowns are ellipses, but `crown_m2` comes from CHM pixels, not ellipse area.

### 11.6 PDF report

`backend/vandrishti/report.py` uses ReportLab A4 + matplotlib:

1. Summary table (area, detected trees, estimated range, cover, dominant FSI class, median/max height, median crown area, mean NDVI).
2. FSI density table and height histogram chart.
3. Land cover and terrain table.
4. Site species prior table (top 10).
5. Events (warnings/errors only).
6. Data sources/provenance.
7. Method and limitations bullet list.

Critical defects:

- `report.py` hard-codes **“Mode: satellite (KML only)”** and satellite-only method text. Every survey PDF is mislabelled, including `presentation/3_sample_outputs/drone_survey_idtrees/assessment_report.pdf`, which also says “Crowns resolvable in 1 m canopy height” and “Estimated total canopy trees 20 – 20”.
- The committed sample PDFs contain a **“4. Confidence of outputs”** section. The current `report.py` has no such section at all. The sample PDFs are therefore not reproducible from the current source; either the artifacts are stale or the confidence-table code was removed. Both sample PDFs also show section numbering (4 confidence, 5 events, 6 sources, 7 method) that the current code cannot produce.
- The report has no per-tree inventory table; it is a summary document.
- Images are inserted at fixed 80 × 80 mm, which can distort aspect ratio.

### 11.7 Maps and 3D

- 2D: MapLibre raster overlays from PNGs with four corner coordinates, GeoJSON layers for trees/crowns/density/boundary, Esri imagery/OSM basemap, AWS terrain + hillshade.
- 3D: `trees3d.ts` builds trunk + stacked-disc crown extrusions per tree. It caps crown radius at 8 m, uses `VERTICAL_EXAGGERATION = 1.2`, and switches disc segments/tiers for large jobs (>3,000 and >20,000 trees). This is a visual aid, not a measured 3D model.
- Species shapes/colours are regex heuristics (e.g. teak → umbrella shape, pine → cone). They do not encode measured crown geometry.

### 11.8 Provenance

- `job.state["provenance"]` is a list of dataset records; UI Sources tab and PDF section 6 render them.
- It is static metadata plus period/scene counts for S2 and a generic “user upload” entry for survey CHM.
- It does not record file hashes, download times, cache hits, model version/hash, code version, or the exact GBIF query date used for the site prior. “100 % traceable” is therefore an overstatement.

---

## 12. Current live deployment

Evidence captured 2026-11-02 from the HF API and live endpoints.

| Item | Live value |
|---|---|
| Space | `sujalappa/van-drishti-ai`, public, SDK Gradio 6.30.0, Python 3.12, `app_file: app.py` |
| Runtime | **RUNNING**, hardware `zero-a10g`, 1 replica, `gcTimeout` 172800 s |
| Storage | `usedStorage` 41,167,619 bytes (~41 MB) |
| Created / last modified | 2026-10-12T11:19:17Z / 2026-10-13T11:09:20Z |
| GEE | `/api/health` → `gee_project_configured: true` |
| Auth | `/api/auth/status` → `enabled: true`, no anonymous user |
| Entry point | `app.py` identical in structure to `deploy/space/app.py`: imports `spaces`, forces CPU DeepForest and 200 MB survey upload, copies `/api/*` from the FastAPI app onto a Gradio `Server`, serves `frontend/dist` |
| Installed model stack | `scikit-learn==1.9.1`, `deepforest==2.1.0`, `pandas`, `torchvision`; torch/gradio/spaces supplied by the Space runtime |
| Model files present | `models/niches/*`, `models/species/idtrees_neon_osbs_mlbs.joblib`, and an unreferenced `models/species_model.joblib` |
| Seeded jobs | `28c7761ac343` (satellite, Chandrapur) and `f5186ceaffd3` (survey, IDTReeS 231) |

### 12.1 Which modes actually run

- Both modes are reachable: the API has both create routes and both live seed jobs are `completed`.
- New satellite runs should work if a signed-in user submits a boundary, because GEE is configured. This audit did **not** submit a new job, so this is “implemented, not verified on the live Space”.
- New survey runs will execute orthophoto validation, CHM/fallback, DeepForest and density. Species will be **Unknown** for an Indian site because the only live model is the IDTReeS US model whose bbox covers Florida/Virginia, not India.
- Login is required: auth is enabled, and the API dependency applies to every non-open route. Public visitors cannot run jobs without credentials.

### 12.2 Sample data used

**Satellite:** `samples/chandrapur_forest_block_a.kml`, 121.5 ha, UTM 44N. Seeded job `28c7761ac343`:
- 4,846 trees, 39.9/ha; 79.8 % unattributed canopy; estimated total 27,568, range 18,235–44,310.
- Cover 77.3 %; VDF 90.45 ha / 74.5 %, MDF 5.92 ha, OF 7.67 ha, NF 17.40 ha.
- Median height 12.0 m, max 28 m; median crown 33 m²; mean NDVI 0.676.
- 80 % of canopy not separable; one warning (`CLOSED_CANOPY`), 3 info events.
- Total recorded runtime 9 s.

**Survey:** `samples/survey/idtrees_osbs_231/` (10 cm aerial RGB + 1 m LiDAR CHM; boundary + CHM; no DSM/DTM). Seeded job `f5186ceaffd3`:
- 0.036 ha, UTM 17N, orthophoto 0.1 m / 3 bands / 100 % coverage, CHM 1.0 m uploaded.
- 20 trees, 554/ha, median height 15.3 m, mean detection score 0.327.
- Species: Unknown 10, ACRU 7, PIPA2 2, QULA2 1; 18 flagged. Final Unknown share is 50 %; the separate committed sample PDF reports 18/20 (90 %) below the raw 0.50 threshold.
- Total recorded runtime 63 s.

The survey sample is **NEON aircraft data**, not drone data. `presentation/README.md` says this explicitly: “No drone data has been flown yet.”

The other survey sample, `samples/survey/neon_osbs_029/`, is 10 cm RGB without height data; it exercises the satellite-height fallback and its warnings.

### 12.3 Is output persistent?

- New jobs are written to `data/jobs/` inside the container. The Space repository file list contains only the two seeded jobs; there is no committed `data/cache`. That does not prove the running container has no cache, but nothing in the repository preserves one across restarts.
- The container filesystem is ephemeral on HF Spaces unless persistent storage is configured. No persistent-storage configuration is visible in the repository or the Space metadata; the only persistence path in code is the optional `VANDRISHTI_USERS_REPO` mirror for `users.json`.
- Therefore: seeded jobs persist because they are uploaded files; **new job outputs should be treated as non-persistent** and re-run after a restart. This is a deployment limitation, not a code bug.

### 12.4 CPU/GPU and ZeroGPU

- All inference is CPU: `VANDRISHTI_DEEPFOREST_ACCELERATOR=cpu` is set before importing DeepForest; Random Forest, watershed, raster IO and PDF generation are CPU.
- The Space requests `zero-a10g` hardware, but `deploy/space/app.py` only defines:

```python
@spaces.GPU(duration=1)
def _noop():
    pass
```

- `_noop` is never called. It exists solely because ZeroGPU requires at least one decorated function. ZeroGPU is **not used for inference**.
- A GPU would only help DeepForest on large mosaics; the docs say satellite mode is CPU-bound and fast.

### 12.5 Resource and time limits

| Limit | Value | Source |
|---|---|---|
| Max AOI per run | 10 km² | `VANDRISHTI_MAX_AOI_KM2` |
| AOI warning | 5 km² | `VANDRISHTI_WARN_AOI_KM2` |
| Min AOI, satellite | 0.01 km² (1 ha) | `Context.min_area_km2` |
| Min AOI, survey | 0.0003 km² (0.03 ha) | `SURVEY_MIN_AREA_KM2` |
| Boundary upload | 20 MB | `VANDRISHTI_MAX_UPLOAD_MB` |
| Survey raster upload | 2048 MB default; **200 MB on Space** | config + `deploy/space/app.py` |
| Grid cell | clamped 10–100 m | `merged_options` |
| Concurrent jobs | 2 threads | `ThreadPoolExecutor(max_workers=2)` |
| Job timeout | none in code | — |
| HF inactivity timeout | `gcTimeout` 172800 s reported | HF API |

`merged_options` clamps only `grid_cell_m`; it does **not** bound `min_tree_height_m` or `canopy_threshold_m`. The frontend restricts them to 2–20 and 1–20, but an API caller can submit arbitrary floats.

### 12.6 Timing claims and what the live data shows

- The 9 s and 63 s figures are from the **seeded job records**, created before the Space existed (satellite job 10 minutes before Space creation; survey two weeks before). They are not measurements of the current Space container.
- The docs claim 15–60 s for a 1.2 km² satellite block (first run slower) and 30–60 s for a 20 m survey plot. The 9 s satellite sample is consistent with a warm cache/local run; the 63 s survey sample is slightly over the documented upper bound.
- No cold-start Space timing, large-block timing, or 10 km² timing exists in the repository. “Sub-minute” is supported only by the cached/precomputed satellite sample.

### 12.7 Live discrepancies worth knowing

- `models/species_model.joblib` is in the Space but is **not** loaded by `model_for_location`, which only globs `models/species/*.joblib`. It is a dead artifact unless manually moved.
- The live Space has no `data/cache` in its repository file list; a first run after a restart must download from Earth Engine.
- The presentation sample PDFs use job ids `6908e7a943bb` and `1b3410f0db95`, not the live seed ids `28c7761ac343`/`f5186ceaffd3`. The numbers match, but they are different runs/artifacts.

---

## 13. Claims vs implementation

### 13.1 The specific claims in the request

| Claim / question | What the code and artifacts show | Verdict |
|---|---|---|
| **493 species / 398,592 records vs 76,369 records** | The niche table has 493 **taxa** (including at least the genus `Magnolia`). `398,592` is `sum(n_records)` of page-capped GBIF samples per taxon (up to 2,400/taxon), not complete GBIF. `76,369` is the number of India-thinned reference rows actually used at runtime. The runtime method for an Indian site is “1,500 nearest of 76,369”, so the 398,592 figure is not the searched pool. | **Real numbers, misleading pairing.** Not a deduplication contradiction; the presentation compares a build-time sample count with a runtime reference count. “493 species” should be “493 taxa”. |
| **Drone imagery 2–3 cm vs 3–10 cm** | No “2–3 cm” claim appears anywhere in the repository. The repository claims: proposal slide 4 “3–10 cm”; `docs/drone_survey_spec.md` accepts “2–10 cm” and recommends 3–5 cm flight GSD; the code’s fatal threshold is 1.0 m, warning above 0.3 m, and the error action says “2–30 cm”. `working_ortho()` resamples to `max(0.1 m, native)`, so anything finer than 10 cm is downsampled to 10 cm and anything coarser stays coarse. | **Inconsistent documentation; no 2–3 cm source.** The system cannot exploit 2–3 cm imagery. Fix the stated GSD and make the code/spec agree. |
| **4,846 detections vs 18,235–44,310 estimated trees** | Both are computed by `stage_trees`. 4,846 is detected, individually mapped crowns; 18,235–44,310 is the extrapolation from 79.8 % unresolved canopy. The PDF reports both; some slides say “4,846 trees mapped” without the range. | **Not a contradiction, but a lower bound presented as a count.** 4,846 must never be read as total stems. |
| **Claimed sub-minute runtime** | Seed satellite job: 9 s (precomputed before the Space existed). Seed survey job: 63 s. Docs: 15–60 s satellite, 30–60 s survey. No cold-start or 10 km² measurement exists. | **Partially supported.** Sub-minute holds for the cached/precomputed satellite sample, not for the survey sample, and not proven on the live Space. |
| **Species classification vs site-level prior** | Satellite: no per-tree species; only a site list. Survey: per-tree Random Forest only if a regional model covers the site; otherwise `Unknown`/none. The site prior is a record-share list, not a classifier and not a count. The live survey run labels 10/20 `Unknown` (the PDF reports 18/20 below the raw threshold). | **Two different features; “species of each tree” is conditional and unproven in India.** |
| **“Every tree” / “every crown” / “exact inventory”** | Satellite recall 13.6 % of labelled crowns; 79.8 % of canopy unattributed. DeepForest recall 51.7 % on IDTReeS. | **Unsupported.** The system is a screening/first-pass tool. |
| **“Drone survey mode” validation** | All survey metrics use NEON **aircraft** 10 cm RGB + LiDAR CHM. `presentation/README.md`: “No drone data has been flown yet.” | **Misnamed.** It is aerial-survey mode validated on benchmark aircraft data. |
| **77 % density-class agreement** | True on 529 IDTReeS 20 m plots vs airborne LiDAR; within one class 97 %. By site: OSBS 64 %, MLBS 98 %, TALL 97 %. | **True but US-only.** No Indian validation. |
| **“100 % traceable”** | Static provenance, event log and stage metrics exist, but no hashes, cache-hit flags, model hashes or code version. | **Overstated.** Processes are logged; individual values are not fully reproducible from provenance alone. |
| **“Cover counts trees only, not grass or crops”** (proposal slide 9) | Cover = CHM ≥5 m. The Meta CHM is model-predicted and has no growth-form mask; tall shrubs, bamboos, palms or tall crops can exceed 5 m. | **Unsupported as written.** It is a height threshold, not a tree classifier. |
| **“Confirmed on the ground by drone survey and field plots”** (proposal slide 7) | No drone flight, no Indian field plots, no Indian species model in the repo or Space. | **Contradicted by the project’s own evidence pack.** |
| **“6 formats” / “PDF, CSV, KMZ, Shapefile…”** | Satellite exports CSV, GeoJSON, KMZ, Shapefile, PDF, GeoTIFF (6). Survey exports no GeoTIFF, so 5. | **True only in satellite mode.** |
| **“PDF report”** | Implemented, but survey PDFs say “Mode: satellite (KML only)”, and sample PDFs contain a confidence section absent from current `report.py`. | **Implemented, partially broken.** |
| **Girth / GBH / NPV / compensatory afforestation** | Docs explicitly say girth cannot be measured remotely and needs field plots; no code. | **Proposed but not implemented** (the docs are honest about this). |
| **“Free / ₹0” data cost** | Earth Engine project is registered for non-commercial use; docs advise reviewing commercial terms or switching to open buckets. | **True for non-commercial/demo use, not automatically for an operating company.** |

### 13.2 Other internal contradictions found

1. **`CHM_GAPS` action vs density code.** The event says gaps are excluded from density; `density.canopy_mask` turns NaN into 0 and keeps all AOI pixels in the denominator. Gaps lower cover.
2. **Drone spec vs code resampling.** `drone_survey_spec.md` says the system resamples to 10 cm; `working_ortho()` uses `max(0.1, native)`, so it only downsamples finer imagery, never upsamples coarser.
3. **Orthophoto acceptance text.** Fatal message says “2–30 cm” in the action, but `MAX_ORTHO_RES_M = 1.0 m` accepts up to 1 m; warning begins above 0.3 m.
4. **Survey PDF mode.** `report.py` hard-codes satellite mode and satellite limitations; the committed survey PDF demonstrates the bug.
5. **Sample PDFs vs current report code.** Sample PDFs have “4. Confidence of outputs”; current `report.py` has no confidence table. They cannot be regenerated by the current source.
6. **Per-tree height statistic differs by mode.** Satellite uses maximum CHM in the crown; survey uses p95 in the box. Docs discuss both but do not clearly flag the difference.
7. **Crown diameter formulas differ.** Satellite `2*sqrt(area/pi)`; survey `sqrt(box_width * box_height)`.
8. **`adjust_probabilities` docstring** says τ < 1 (tempered), but `pipeline_survey.stage_species` calls it with `tau=1.0`.
9. **`train_species.py` CV is not group-aware.** Validation uses `StratifiedGroupKFold` by plot; the training script uses `StratifiedKFold`, which can leak same-plot trees across folds and inflate its reported metrics.
10. **Sample output job ids differ from live seed ids.** Presentation outputs `6908e7a943bb`/`1b3410f0db95`; live seeds `28c7761ac343`/`f5186ceaffd3`. The same headline numbers appear, but they are not the same artifacts.
11. **README says survey heights within ±4 m** while the validation table reports RMSE 4.12 m and MAE 2.7 m. “Within ±4 m” is closer to RMSE than a per-tree bound.
12. **`models/species_model.joblib` is live but unreferenced.** Only `models/species/*.joblib` is loaded. It is dead weight or a packaging mistake.
13. **`docs/drone_survey_spec.md` requires a KML/KMZ boundary**, but the API also accepts GeoJSON. Minor documentation gap.
14. **Sample survey PDF says “Crowns resolvable in 1 m canopy height”** even though the survey CHM is 0.5 m and detection is DeepForest boxes. The report template is not mode-aware.

---

## 14. Feature status matrix

### 14.1 Implemented and working

| Feature | Evidence |
|---|---|
| KML/KMZ/GeoJSON parsing and validation | `aoi.py`; tests in `backend/tests/test_core.py` (not run here); live satellite job parsed the sample KML |
| UTM grid, area, centroid, CRS conversion | `aoi.py`, `gee.Grid`; seed job reports UTM 44N / 121.5 ha |
| Earth Engine CHM fetch, chunking, caching, GeoTIFF export | `sources/gee.py`; live job produced `canopy_height_1m.tif` |
| Sentinel-2 composite, cloud mask, NDVI, leaf fall | `gee.fetch_s2`, `vegetation.py`; live job produced NDVI/leaf-fall layers |
| Copernicus DEM elevation/slope | `gee.fetch_dem`, `vegetation.terrain_summary`; live job metrics |
| ESA WorldCover land cover | `gee.fetch_worldcover`, `vegetation.worldcover_summary`; live metrics |
| Site species prior (table build + runtime) | `site_prior.py`, committed 493-taxa table; live job top-10 list |
| Satellite local-maxima + watershed detection | `processing/trees.py`; 4,846 trees in seed job |
| Unattributed-canopy extrapolation range | `pipeline.stage_trees`; 18,235–44,310 |
| Canopy density / FSI grid | `processing/density.py`; live 77.3 % cover, VDF 90.45 ha |
| Tree inventory records | `pipeline.stage_inventory`; 4,846 CSV rows |
| CSV, GeoJSON, KMZ, Shapefile, PDF exports | `exports.py`, `report.py`; live exports list |
| Satellite CHM GeoTIFF export | `stage_chm` copies cache; present in satellite job |
| Dashboard, 2D map, 3D view, tree table, event log | `frontend/src/**`; live frontend served |
| File-backed jobs, stages, events, provenance | `jobs.py`; live `job.json`/`events.jsonl` |
| Optional sign-in and admin user management | `auth.py`; live status `enabled: true` |
| Survey orthophoto validation and CHM construction | `pipeline_survey.stage_survey`, `survey.build_chm`; live survey job |
| DeepForest crown detection (CPU) | `survey.detect_crowns`; live 20-tree survey job |
| Per-tree species RF when a model covers the site | `species.py`, `pipeline_survey.stage_species`; live survey labels (US model) |
| Survey fallback to CHM watershed if DeepForest absent | `pipeline_survey.stage_trees`; code path present, not exercised live |
| Survey satellite-height fallback with flags | `CHM_FALLBACK`, `height_from_satellite`; code path, not in seeded survey |
| HF Space deployment and both seed jobs | live Space `RUNNING`, both jobs `completed` |

### 14.2 Implemented but not verified

| Feature | Why unverified |
|---|---|
| New satellite run on the live Space | GEE reports configured, but no new job was submitted in this audit |
| New survey run on the live Space | DeepForest installed, but no new job was submitted |
| DSM + DTM → CHM path | No committed sample uses DSM/DTM; the sample uses uploaded CHM |
| Indian per-tree species model | No Indian labels or model in repo/Space |
| `training/train_species.py` on Indian field plots | Script exists; no data |
| First-run GEE download reliability/timing on Space | No cold-start records |
| Offline cache reuse | Code supports it; not exercised here; Space repo has no cache |
| Shapefile opens correctly in QGIS/ArcGIS | Not tested; no `.cpg`, possible ring/field-width issues |
| KMZ opens correctly in Google Earth | Not tested here |
| Current `report.py` reproduces sample PDFs | It cannot; sample PDFs contain a confidence section absent from code |
| Auth user mirror to private HF dataset | Code exists; no dataset configured/verified |
| 10 km² block performance | No record; only 1.215 km² seed |
| DeepForest on large mosaics/GPU | CPU only in live; no large-mosaic record |
| 200 MB survey upload path | Configured; not exercised |
| Drawn boundary + `site_extent` | UI code exists; not exercised end-to-end |
| 3D view at >20,000 trees | Code has LOD switches; no performance test |
| Runtime GBIF 50 km lookup | Cached/live prior exists; failure path not tested live |
| `models/species_model.joblib` | Unreferenced; provenance unknown |

### 14.3 Mock / demo data

| Item | What it is |
|---|---|
| `data/jobs/28c7761ac343` | Precomputed satellite demo job, bundled into the Space; created before the Space existed |
| `data/jobs/f5186ceaffd3` | Precomputed survey demo job, bundled into the Space; NEON aircraft plot, not drone |
| `samples/chandrapur_forest_block_a.kml` | Demo boundary near Chandrapur; not confirmed as an actual WCL diversion block |
| `samples/chandrapur_mine_edge_block_b.kmz` | Second demo boundary |
| `samples/survey/idtrees_osbs_231/` | IDTReeS/NEON benchmark plot with 10 cm aerial RGB + LiDAR CHM; used as a drone surrogate |
| `samples/survey/neon_osbs_029/` | NEON/DeepForest sample tile; RGB only, exercises satellite-height fallback |
| `presentation/3_sample_outputs/**` | Precomputed PDFs/CSVs/KMZ/Shapefile for the evidence pack; job ids differ from live seeds |
| `presentation/1_dashboard/**`, `2_validation/**` | Screenshots and validation figures; illustrative artifacts |
| `models/species_model.joblib` (live only) | Unreferenced model file; may be an earlier artifact |

There is **no synthetic/mock data inside the processing pipeline itself**. Sample jobs use real public datasets; the “demo” aspect is that the jobs are precomputed and seeded, not that the rasters are fabricated.

### 14.4 Proposed but not implemented

| Proposal | Status in code |
|---|---|
| Girth / GBH measurement | Not implemented; docs say field plots or local allometry are required |
| NPV / compensatory-afforestation valuation | Not implemented |
| Height–crown–girth allometry | Not implemented |
| Actual drone survey / Indian field plots | Not done; explicitly stated in `presentation/README.md` |
| Indian regional species model | Not present |
| Multispectral/hyperspectral production species classification | Only a validation experiment; production uses RGB + height |
| LiDAR point-cloud processing / ground classification | Not implemented; only uploaded CHM/DSM/DTM rasters |
| Change detection / recent-clearing mapping | Only heuristic warnings (`SOURCE_DISAGREEMENT`, `POSSIBLE_CHANGE`) |
| Per-tree species in satellite mode | Not implemented; only site prior |
| Exact stem enumeration in closed canopy | Not implemented; extrapolation only |
| Persistent job storage / database | Not implemented; file-backed ephemeral on Space |
| Job queue, cancellation, resume | Not implemented |
| Multi-worker/multi-replica job coordination | Not implemented; single process assumed |
| GPU / ZeroGPU inference | GPU reserved but unused; CPU forced |
| Automated retraining / active learning from field checks | Not implemented; manual training script |
| Organisation SSO | Not implemented; docs suggest a reverse proxy |
| Commercial Earth Engine / open-bucket data switch | Not implemented; docs recommend review |
| Legal/regulatory-grade enumeration | Not supported; report itself says decision-support estimate |

---

## 15. Limitations of this audit and how to reproduce

### 15.1 What this audit could not check

- **Tests:** `pytest` and several runtime dependencies are absent from this environment. The repository’s tests are therefore reported as present, not passing.
- **Validation rerun:** `validation/idtrees_validation.py` and `satellite_vs_lidar.py` need the IDTReeS dataset at `../idtrees datset` (the default path contains a space/typo) and Earth Engine access. The metrics in this report are read from committed `results/idtrees/*.json|md`, not recomputed.
- **Niche-table rebuild:** needs `data/reference/global_tree_search.csv` (not committed) plus GBIF and Earth Engine.
- **Live new jobs:** no boundary was uploaded to the live Space; “new satellite/survey works” is inferred from routes, installed packages and the health endpoint, not demonstrated.
- **Visual/GIS outputs:** no browser, QGIS, ArcGIS or Google Earth test.
- **Cold-start performance:** not measured; the only timings are precomputed seed jobs.

### 15.2 Commands that would reproduce the checks (not run here)

```bash
# backend tests (needs Python 3.11–3.13, pip install -r backend/requirements.txt, pytest)
cd backend && python -m pytest

# validation (needs the external IDTReeS dataset and Earth Engine auth)
python validation/idtrees_validation.py --data "../idtrees datset"
python validation/satellite_vs_lidar.py --data "../idtrees datset"

# niche table rebuild (needs GBIF, Earth Engine and data/reference/global_tree_search.csv)
python training/build_species_niches.py --top 500

# local app
cd backend && uvicorn vandrishti.api:app --port 8000

# Space assembly (needs frontend/dist and data/jobs/<seed ids>)
cd frontend && npm ci && npm run build
python tools/build_space.py 28c7761ac343 f5186ceaffd3
```

### 15.3 Highest-value fixes, in order

1. **Make the report mode-aware.** Pass `ctx.mode` into `report.py`; remove the hard-coded “Mode: satellite (KML only)”; add survey method/limitations text. This is a user-visible correctness bug.
2. **Reconcile the sample PDFs with the source.** Either restore the confidence section in `report.py` or regenerate the evidence pack from current code. Do not ship artifacts the code cannot produce.
3. **Fix the density/gap contradiction.** Either exclude CHM-gap pixels from the density denominator or change the `CHM_GAPS` action text. Current behaviour silently lowers cover.
4. **Make one GSD story.** Align proposal (3–10 cm), spec (2–10 cm), code fatal/warn thresholds (1.0 m/0.3 m) and the resampling rule. Decide whether the system should upsample to 10 cm; currently it does not.
5. **State the record counts correctly.** “493 taxa, 398,592 sampled GBIF records at build time, 76,369 India reference rows used at runtime” — never “493 species / 398,592 records” next to a 76,369-record method.
6. **Stop calling survey mode “drone” in results.** Label it “aerial survey / drone-equivalent benchmark” until a real drone flight and Indian field labels exist.
7. **Expose the limitations in the headline UI.** The 4,846 count should always sit next to “lower bound; 18,235–44,310 estimated” and the 13.6 % recall, not only in the Quality tab.
8. **Add per-tree species confidence to CSV** (`detection_score`, `species_confidence_image_only`) or document that GeoJSON is the complete record.
9. **Make the model artifacts reproducible.** Either commit a small, licensed Indian model or provide a documented build step with labels; remove the unreferenced `models/species_model.joblib`.
10. **Persist jobs or say they are ephemeral.** Add HF persistent storage or a download/export workflow; otherwise users lose new runs on restart.

---

## 16. Final classification summary

| Area | Classification |
|---|---|
| Frontend (React/MapLibre/3D) | **Implemented and working** (visualisation only; 3D is stylised) |
| FastAPI + file-backed jobs + events | **Implemented and working** |
| HF Space deployment | **Implemented and working**; new-run performance unverified, outputs non-persistent, ZeroGPU unused |
| Satellite nine-step pipeline | **Implemented and working** on real GEE data |
| Satellite data sources (CHM/S2/DEM/WorldCover/WorldClim/OpenLandMap/GBIF) | **Implemented and working**; CHM temporal provenance weak, cache versioning absent |
| Satellite tree detection | **Implemented and working**; **13.6 % recall**, screening only |
| Extrapolated count range | **Implemented and working**; assumption-dependent, not enumeration |
| Canopy density / FSI | **Implemented and working**; validated on US plots, gap handling contradicts docs |
| Height | **Implemented**, but satellite is weak (RMSE 6.2 m, R² −0.26); mode statistics differ |
| Site species prior | **Implemented and working**; shares are record shares, not population; 493 taxa not 493 validated species |
| Drone survey mode | **Implemented but not verified on drone/Indian data**; demoed on NEON aircraft |
| DeepForest detection | **Implemented and working**; pretrained, not fine-tuned; 51.7 % recall |
| Per-tree species | **Implemented but conditional**; only with a regional model, otherwise Unknown; live demo 10/20 Unknown (50 %) |
| CSV/GeoJSON/KMZ/Shapefile/PDF | **Implemented and working**; PDF survey labelling broken; CSV omits two fields |
| Canopy-height GeoTIFF | **Implemented in satellite mode only**; padded, unclipped cache copy |
| Validation artifacts | **Committed and credible**, but not reproducible without the external IDTReeS dataset |
| Girth/GBH/NPV, Indian model, real drone flight, change detection | **Proposed but not implemented** |

**Overall:** this is a genuine end-to-end geospatial ML prototype with unusually honest in-product uncertainty reporting (lower-bound counts, Unknown species, confidence ratings, event log). It is not an enumeration or legal-compliance system, and several public-facing claims — “every tree”, “species of each tree”, “drone-validated”, “100 % traceable”, “sub-minute” — are stronger than the implementation supports. The most urgent defects are the mode-blind PDF, the misleading species/record framing, and the density-gap contradiction.
