# Vandrishti AI: the complete guide (start here)

For anyone new to the project, with no remote-sensing or GIS background needed. Read this first; the other
documents go deeper on specific parts.

---

## 1. The problem

Before forest land can be used for coal mining, the law requires a record of **every tree in the area**:
its location, species, height and crown size, the total number of trees, and how dense the forest is. Today
survey teams walk the forest measuring trees by hand. It is slow, sometimes dangerous in rugged terrain, and
results vary between surveyors.

**Vandrishti AI** automates the first pass. The user uploads the boundary of the area (a KML file); the system
fetches satellite or drone data for exactly that area, finds and measures the trees, and produces a tree list,
maps and a report, showing every step as it runs.

---

## 2. Concepts you need

**Pixel and raster.** A satellite or drone image is a grid of small squares called pixels. Each pixel stores a
number: a colour, or a height. Such a grid is called a **raster**.

**Resolution** is the ground size of one pixel:

| Resolution | Example | What you can see |
|---|---|---|
| 10 m | Sentinel-2 satellite | One pixel is larger than a tree: forest patches only |
| 1 m | Meta canopy-height map | Large individual trees |
| 10 cm | Drone or aircraft photo | Individual crowns and branches |

**KML / KMZ.** The file format Google Earth uses to store shapes on a map. A mining block's boundary is a
polygon in a KML file. A KMZ is a zipped KML.

**Coordinates.**
- *Latitude / longitude* (degrees) are good for saying where something is, but a degree is ~111 km, so they
  are bad for measuring.
- *UTM* is a flat grid in metres, used for measuring areas and distances. Chandrapur is in UTM zone 44N.
- Rule used everywhere in this project: **calculate in UTM metres, convert to latitude/longitude only for
  display and export.**

**The three height layers (the key idea).**
- **DSM** (Digital Surface Model): height of the top of everything: tree tops, roofs.
- **DTM** (Digital Terrain Model): height of the bare ground.
- **CHM** (Canopy Height Model) = **DSM − DTM**: how tall things stand above the ground.

In a CHM each tree looks like a small hill, and the top of the hill is the tree top. Finding trees and
measuring their height both come from this one idea.

**NDVI.** A number calculated from the red and near-infrared light a satellite records. Healthy leaves reflect
a lot of infrared, so NDVI above 0.6 means dense healthy vegetation and below 0.2 means bare ground.

**Canopy density** is the share of the ground covered by tree crowns seen from above. India's official
**Forest Survey of India (FSI)** classes:

| Class | Canopy cover |
|---|---|
| Very Dense Forest (VDF) | 70 % or more |
| Moderately Dense Forest (MDF) | 40–70 % |
| Open Forest (OF) | 10–40 % |
| Scrub / non-forest | below 10 % |

---

## 3. Where the data comes from

**Free satellite data, through Google Earth Engine** (Google's platform that hosts these datasets; the
project uses a Google Cloud project registered for Earth Engine):

| Dataset | Gives | Used for |
|---|---|---|
| Meta/WRI Global Canopy Height, 1 m | Height of vegetation everywhere, predicted by Meta's AI from satellite imagery | Finding trees, heights, canopy density |
| Sentinel-2, 10 m | Colour + infrared images every ~5 days | Vegetation health (NDVI), current condition |
| Copernicus DEM, 30 m | Ground elevation | Slope, terrain |
| ESA WorldCover, 10 m | Land type (forest, crop, water, built-up) | Cross-checking results |

**Drone survey data (in real use, flown for WCL):** a 10 cm photo mosaic (orthophoto) and a DSM + DTM made from
the same drone photos. See [drone_survey_spec.md](drone_survey_spec.md).

**IDTReeS (for testing only):** a US research benchmark. An aircraft flew over forests with a camera and LiDAR,
then scientists walked in and measured trees by hand: species, height and crown outlines. We compare our results
against their measurements to get honest accuracy numbers. **No drone has been flown for this project yet:**
the "drone mode" results use this aircraft data, which has the same file types a drone delivers.

---

## 4. Two modes, one pipeline

| | Satellite mode | Drone survey mode |
|---|---|---|
| You upload | KML boundary only | KML + orthophoto + DSM/DTM (or CHM) |
| Cost per run | Nothing | A drone flight |
| Trees | Large, separated crowns; count range in dense forest | Every visible crown |
| Height | ±6 m | ±4 m |
| Species | No (forest class only) | Yes, with a model trained on local field labels |
| Density | Yes, FSI classes | Yes |

Both use the same stages, the same dashboard and the same outputs. Satellite mode is the free screening tool for
every block; drone mode is the detailed tool for blocks going to Stage-II clearance.

---

## 5. What happens in a run (satellite mode, 8 steps)

1. **Read boundary.** Opens the KML/KMZ, checks it is a closed polygon between 1 ha and 10 km², rejects
   malicious files, warns if outside India, and picks the UTM zone.
2. **Canopy height.** Downloads Meta's 1 m heights for the area from Earth Engine, in chunks, and caches them
   on disk so the next run (and an offline demo) is instant.
3. **Satellite and terrain.** Downloads Sentinel-2 for October–January (post-monsoon: trees in leaf, few clouds),
   removes cloudy pixels and takes the median of the remaining images. If clouds leave gaps, it widens the date
   window automatically and logs that. Also downloads the DEM and WorldCover.
4. **Detect trees.**
   - *Tree tops*: pixels that are the highest point in their neighbourhood and at least 5 m tall; taller trees
     get a bigger neighbourhood because their crowns are wider.
   - *Crowns*: from each top, "pour water downhill" (the watershed algorithm); each top claims the pixels around
     it until it meets a neighbour. Crowns are capped at a realistic width for the tree's height.
   - *Height*: the highest point in the crown.
   - In dense forest, 1 m data cannot separate touching crowns, so the system reports **detected trees**
     (mapped one by one) and an **estimated total** (leftover canopy ÷ typical crown size), clearly labelled.
5. **Canopy density.** Splits the area into 25 m squares, measures the share of each covered by canopy of 5 m or
   more, and gives each square an FSI class.
6. **Vegetation and terrain.** NDVI, land-cover shares, slope.
7. **Quality checks.** Flags unusual trees (over 40 m), warns when data sources disagree (possible recent
   clearing), and gives every output a confidence level with the reason.
8. **Inventory and reports.** One row per tree (ID, latitude/longitude, height, crown, local density, class,
   NDVI, flags) plus exports: PDF report, CSV, KMZ for Google Earth, Shapefile for QGIS/ArcGIS, GeoJSON, and the
   canopy-height GeoTIFF.

## 6. What changes in drone survey mode (10 steps)

- **Check survey data**: the files must have coordinates, be sharp enough, and cover the boundary.
- **Canopy height** comes from the drone DSM − DTM. Without them it falls back to satellite heights and flags
  every tree `height_from_satellite`.
- **Detect trees with DeepForest**, an AI model (a RetinaNet neural network) trained on thousands of hand-labelled
  tree crowns in aerial photos. It draws a box around each crown with a confidence score. Large mosaics are cut
  into overlapping 40 m tiles and duplicate boxes at tile edges are removed, so no tree is counted twice.
  Images smaller than DeepForest's 400-pixel training size are padded; without that, detection collapses.
- **Classify species.** For each crown: colour, colour variation, greenness, texture, height and crown size go
  into a Random Forest (hundreds of decision trees that vote). The model must be trained on field-labelled trees
  from the same region, and it is only used inside the region it was trained in. If it is less than 50 % sure,
  the tree is marked **Unknown** instead of guessed.

To get species for a WCL area, field staff label 150–300 trees in sample plots and run
`training/train_species.py`; after that, species appear automatically for blocks in that region.

---

## 7. Events: how problems are handled

Each step can log an **event**: a level (info / warning / error), what happened, and the action taken or
recommended. Examples:

- `S2_CLOUD_GAPS`: too cloudy, so the date window was widened automatically.
- `CLOSED_CANOPY`: crowns can't be separated, so a count range is given.
- `CHM_FALLBACK`: no drone heights, so satellite heights were used and flagged.
- `MANY_UNKNOWN_SPECIES`: many trees below the confidence threshold, marked Unknown.

Recoverable problems never stop a run; only fatal ones do (for example a KML with no polygon). The
[SOP](SOP.md) tells staff what to do for each event.

---

## 8. How the software is built

```
Browser dashboard  ⇄  Backend API (FastAPI, Python)  →  Pipeline worker  →  Earth Engine / DeepForest
                              ↓
                  data/jobs/<id>/  (inputs, outputs, event log)
```

- **Dashboard** (React + MapLibre): upload page; live step list that refreshes every second; map with 3D trees;
  statistics, tree table, quality, data sources and exports.
- **Backend** (FastAPI): accepts uploads, starts a background job, serves results.
- **Pipeline** (`backend/vandrishti/pipeline.py`, `pipeline_survey.py`): the stages above.
- **Each run is a folder** holding its inputs, outputs and event log, so any number in a report can be traced
  back to its data.

Code map and setup instructions: [../README.md](../README.md). Design details:
[architecture.md](architecture.md).

---

## 9. How accurate is it? (validation)

Tested on IDTReeS: 529 plots with airborne LiDAR, 1,765 hand-drawn crowns, 1,057 field-measured heights.

**How detection is scored.** IoU (intersection over union) measures how much a predicted crown overlaps a real
one, from 0 to 1; a match needs IoU ≥ 0.4. *Recall* is the share of real trees found. IDTReeS drew only some of
the trees in each plot, so correct detections of undrawn trees count as wrong: precision is only a lower bound,
and recall is the number to trust.

| What | Result |
|---|---|
| Satellite density class vs airborne LiDAR | same class on **77 %** of plots, within one class on **97 %** |
| Satellite canopy cover vs LiDAR | average difference 9.6 percentage points, correlation 0.92 |
| Trees found: drone mode (DeepForest) | **52 %** |
| Trees found: LiDAR heights only | 34 % |
| Trees found: satellite mode | 14 % (large separated trees only) |
| Height vs field-measured: LiDAR | ±4.1 m |
| Height vs field-measured: satellite | ±6.2 m, about 3 m too low |
| Species, RGB camera | 41 % overall; 68 % on the trees it is confident about |
| Species, with hyperspectral | 53 % overall; 89 % on the trees it is confident about |

**What this means.** Satellite mode is reliable for **density** and useful for screening, rough for individual
trees and heights. Drone mode is the tool for enumeration and species. Species improve most with more spectral
information, so a multispectral drone camera is the recommended upgrade.

Species cross-validation is **grouped by plot**: trees from the same plot never appear in both training and
testing, which would inflate the score. Full tables: [../results/idtrees/](../results/idtrees/).

**Lessons from the earlier prototype.** An earlier codebase reported an F1 score of 0.96. It had measured
distances in degrees instead of metres (so every prediction "matched" some tree) and copied the correct answers
into its predictions. The numbers above come from corrected, reproducible scripts (`validation/`).

---

## 10. Limitations to state openly

- No drone survey has been flown yet; drone-mode numbers come from aircraft data of the same type.
- Validation forests are in the USA. Indian forests (teak, sal, dry-deciduous) need a pilot survey and field
  plots to calibrate.
- The satellite canopy-height map is based mostly on 2018–2020 imagery; recent changes are only caught by the
  change warnings.
- Girth (GBH), needed for compensatory-afforestation and NPV calculations, cannot be measured from above; it
  needs field plots or locally calibrated formulas.

---

## Where to go next

| If you want to… | Read |
|---|---|
| Run the system | [../README.md](../README.md) |
| Operate it as a WCL team | [SOP.md](SOP.md) |
| Commission a drone survey | [drone_survey_spec.md](drone_survey_spec.md) |
| Understand the design, deployment and cost | [architecture.md](architecture.md) |
| See the exact methods and rare-event rules | [methodology.md](methodology.md) |
| Prepare for questions | [FAQ.md](FAQ.md) |
| Find the evidence for each claim | [../presentation/README.md](../presentation/README.md) |
