# Vandrishti AI: presentation evidence pack

Every claim in the presentation, with the file that proves it. All numbers come from scripts in this
repository and can be re-run (`validation/`).

## Key numbers (for slides)

| Claim | Number | Proof |
|---|---|---|
| Satellite density class matches airborne LiDAR | **77 %** of 529 plots same class, **97 %** within one class | `2_validation/satellite_vs_lidar.md`, `satellite_vs_lidar.png` |
| Satellite canopy cover vs LiDAR | MAE 9.6 percentage points, correlation 0.92 | same |
| Drone mode finds labelled trees | **52 %** recall (IoU ≥ 0.4) vs 34 % LiDAR-only, 14 % satellite | `2_validation/validation.md`, `detection_recall.png` |
| Tree height, drone/LiDAR vs field-measured | RMSE 4.1 m (1,057 trees) | `2_validation/height_scatter.png` |
| Tree height, satellite vs field-measured | RMSE 6.2 m, underestimates ~3 m | same |
| Species, RGB drone camera | 41 % overall; **68 %** on the trees it labels (threshold 0.5), rest Unknown | `2_validation/validation.md` §3 |
| Species with hyperspectral | 53 % overall; **89 %** on the trees it labels | same |
| Satellite run time | ~10–60 s for a 1.2 km² block on a laptop | `1_dashboard/satellite_mode/` step durations |
| Cost of satellite mode | No data or licence cost per run | `docs/architecture.md` |

Benchmark: IDTReeS 2020 (NEON OSBS Florida, MLBS Virginia, TALL Alabama): 10 cm RGB, LiDAR, hyperspectral,
1,765 hand-delineated crowns, 1,166 field-measured trees.

**Say this with the numbers:** IDTReeS labels only field-surveyed trees, so recall is the reliable detection
metric (precision is a lower bound). Species results are US species; India needs local field labels.

> **No drone data has been flown yet.** All "drone survey mode" results use NEON *aircraft* survey data
> (10 cm RGB + airborne LiDAR, via IDTReeS), the same file types a drone survey delivers. Present them as
> "validated on aerial survey data equivalent to drone output", never as drone results or as results on Indian
> forests. Drone photogrammetry heights may be less accurate than LiDAR under dense canopy. The next step is a
> pilot drone flight over one WCL block with 20–30 field plots (see `../docs/drone_survey_spec.md`).

## Evidence by evaluation criterion

| Criterion (weight) | What to show | Files |
|---|---|---|
| Methodology (10 %) | Pipeline diagram, two modes, methods | `../docs/img/pipeline.svg`, `../docs/methodology.md` |
| Scope & generalisation (5 %) | Runs on any KML in India; validated on 3 forest types | `1_dashboard/satellite_mode/01_home_upload.png`, `2_validation/satellite_vs_lidar.md` (by site) |
| Deployment architecture (5 %) | Architecture diagram, deployment options | `../docs/architecture.md` |
| Rare events (5 %) | Event log with actions, Unknown species, confidence ratings, unknown-threshold table | `1_dashboard/satellite_mode/08_quality_events_confidence.png`, `1_dashboard/drone_survey_mode/07_step_details_event_log.png`, `../docs/methodology.md` §6 |
| Minimum-cost site deployment (5 %) | Free satellite mode; drone only for Stage-II | `../docs/architecture.md` (cost table) |
| End-to-end demo with events, visualization, SOP (10 %) | Live steps, 2D/3D map, SOP | `1_dashboard/*/02_*`, `03_map_3d.png`, `../docs/SOP.md` |
| Integration with existing systems (5 %) | KMZ, Shapefile, CSV, PDF, REST API | `3_sample_outputs/`, `1_dashboard/satellite_mode/10_exports.png` |
| Implementation time / team (15 %) | 6-month plan, roles | Proposal document |
| Innovation (10 %) | KML-in / inventory-out; honest confidence; region-locked species models | `1_dashboard/`, `../docs/methodology.md` |
| Realistic implementation (10 %) | Validated numbers incl. limitations; drone data spec | `2_validation/`, `../docs/drone_survey_spec.md` |

## Folder contents

```
1_dashboard/
  satellite_mode/       Chandrapur Forest Block A (121.5 ha, KML only)
    01_home_upload            Upload page, two modes
    02_map_trees              4,846 detected trees on satellite basemap
    03_map_3d                 Trees extruded by height (3D tilt)
    04_density_fsi_classes    Forest Survey of India density classes on a 25 m grid
    05_statistics             KPIs, FSI area, height histogram, NDVI, land cover
    06_tree_inventory         Per-tree table
    07_locate_single_tree     Click a row → map zooms to that tree
    08_quality_events_confidence  Confidence per output + rare events with actions
    09_data_sources           Datasets, licences, dates
    10_exports                PDF, CSV, KMZ, Shapefile, GeoJSON, GeoTIFF
    11_mobile_view            Works on a phone
  drone_survey_mode/    IDTReeS plot OSBS_231 (10 cm RGB + LiDAR canopy height)
    01_survey_upload          Orthophoto / DSM / DTM / CHM inputs, sample surveys
    02_live_steps_running     Step-by-step progress while running
    03_map_orthophoto_trees   DeepForest trees on the survey orthophoto
    04_statistics_species     Species composition incl. Unknown
    05_tree_inventory_species Species, confidence, detection score per tree
    06_quality_events         Survey confidence ratings and events
    07_step_details_event_log All 10 steps with durations and events
2_validation/
  validation.md             Crown detection, height, species (full tables)
  satellite_vs_lidar.md     Satellite mode vs airborne LiDAR on 529 plots
  detection_recall.png      Recall by method (bar chart)
  height_scatter.png        Estimated vs field-measured height
  satellite_vs_lidar.png    Satellite vs LiDAR canopy cover and height
3_sample_outputs/
  satellite_block_a/        PDF report, CSV, KMZ (open in Google Earth), Shapefile
  drone_survey_idtrees/     PDF report, CSV, KMZ
```

## Refreshing this pack

1. Start the app (`cd backend && uvicorn vandrishti.api:app --port 8000`) and run the samples.
2. Re-run validation: `python validation/idtrees_validation.py` (~40 min on CPU) and
   `python validation/satellite_vs_lidar.py` (~1 min).
3. Copy the new figures and job outputs from `results/idtrees/` and `data/jobs/<id>/` into this folder.
