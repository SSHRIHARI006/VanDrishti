# Methodology, rare events and limitations

Audience: evaluators and technical reviewers. Numbers come from `validation/idtrees_validation.py`
(full tables in [results/idtrees/validation.md](../results/idtrees/validation.md)).

## 1. Coordinate handling

Every layer is requested or reprojected onto a north-up grid in the block's own **UTM zone** (EPSG:326xx),
so areas, crown sizes, distances and density are computed in metres. Coordinates are converted to WGS84 only
for display and export. Canopy height is used at 1 m (satellite) or 0.5 m (survey); Sentinel-2, DEM and
WorldCover at 10 m.

## 2. Tree detection

**Canopy height model (both modes).** CHM = DSM − DTM. Trees appear as peaks.

1. Light Gaussian smoothing (σ = 0.5 m satellite, 0.3 m survey) removes within-crown noise.
2. **Tree tops**: local maxima ≥ 5 m within a height-dependent radius, `r = (0.8 + 0.12·h) × scale`,
   clipped to 1–4.5 m. Taller trees have wider crowns, so nearby maxima are suppressed over a larger distance.
   Flat-topped plateaus keep one pixel.
3. **Crowns**: marker-controlled watershed from the tops on the inverted CHM, restricted to canopy ≥ 2 m,
   then trimmed to pixels ≥ 40 % of the tree's height and within a plausible crown radius
   `0.5 + 0.3·h` m (2–8 m).
4. **Height** = maximum CHM in the crown; **crown area** = crown pixels × pixel area.

**Satellite mode caveat.** Meta's 1 m CHM is smooth and stored in whole metres, so touching crowns in closed
canopy cannot be separated. The pipeline measures the share of canopy not assigned to any detected crown and
reports an **estimated total** = detected trees + unassigned canopy area ÷ median detected crown area (range
from the 25th–75th percentile crown areas), labelled as an extrapolation.

**Survey mode: DeepForest.** A RetinaNet detector pretrained on NEON aerial imagery. The orthophoto is
resampled to 10 cm on the UTM grid, split into overlapping 400 px (40 m) windows, predicted, and duplicate boxes
at window edges removed by non-maximum suppression, so large mosaics are counted once. Images smaller than one
window are zero-padded to 400 px: the model rescales inputs to a fixed size, and a smaller image would be
magnified beyond its training scale (on IDTReeS this raised recall from 0.15 to 0.52). Height = 95th percentile
of the survey CHM in the box; crown area = CHM pixels ≥ 40 % of that height in the box.

## 3. Species

Per crown: mean and standard deviation of R, G, B, excess green, G/R ratio, brightness, texture, height and
crown area. A class-balanced Random Forest (400 trees) is trained on field-labelled crowns of the region;
species with fewer than 15 labels become *Other*. Each model stores the bounding box of its training data and
is used only for blocks inside it. Predictions below the confidence threshold (0.5) are reported as
**Unknown**.

## 4. Canopy density and vegetation

- Canopy cover per 25 m cell = share of pixels with CHM ≥ 5 m; classified as Forest Survey of India classes:
  Very Dense ≥ 70 %, Moderately Dense 40–70 %, Open 10–40 %, Scrub/non-forest < 10 %.
- Sentinel-2: median of cloud-masked scenes (Cloud Score+ ≥ 0.6) from the post-monsoon window (Oct–Jan) →
  NDVI and vegetation-condition classes.
- ESA WorldCover land-cover shares; Copernicus DEM elevation and slope.

## 5. Validation on IDTReeS (NEON OSBS, MLBS, TALL; 393 plots; 1,765 labelled crowns)

**Crown detection** (one-to-one matching, IoU ≥ 0.4):

| Method | Mode | Recall | Precision (lower bound) |
|---|---|---|---|
| DeepForest on 10 cm RGB, score ≥ 0.1 | Survey | **0.52** | 0.18 |
| DeepForest, score ≥ 0.3 | Survey | 0.46 | 0.30 |
| CHM watershed on LiDAR CHM | Survey (height only) | 0.34 | 0.22 |
| CHM watershed on Meta 1 m CHM | Satellite | 0.14 | 0.18 |

IDTReeS delineates only field-surveyed trees, so detections of unlabelled trees count as false positives:
precision is a lower bound and recall is the reliable measure.

**Height vs field measurement** (1,057 trees):

| Source | MAE | RMSE | Bias |
|---|---|---|---|
| LiDAR CHM (survey) | 2.7 m | 4.1 m | +1.9 m |
| Meta 1 m CHM (satellite) | 4.9 m | 6.2 m | −3.2 m |

The positive LiDAR bias comes from taller neighbouring canopy inside the labelled crown of understory trees;
the satellite CHM underestimates tall trees, consistent with its published accuracy.

**Satellite mode vs airborne LiDAR, all 529 plots** (`validation/satellite_vs_lidar.py`,
[full table](../results/idtrees/satellite_vs_lidar.md)): the satellite canopy height model is compared with
NEON airborne LiDAR on each plot.

| Satellite output | Agreement with LiDAR |
|---|---|
| Forest Survey of India density class | same class on **77 %** of plots, within one class on **97 %** |
| Canopy cover | MAE 9.6 percentage points, correlation 0.92, bias −5.8 points |
| Plot canopy height (95th percentile) | MAE 5.1 m, bias −4.6 m |

The main confusion is moderately dense plots read as open forest (satellite cover is biased low), so density
is rated Medium–High in satellite mode.

**Species** (5-fold cross-validation grouped by plot, 12 classes, 1,109 crowns):

| Features | Accuracy | Macro F1 | At threshold 0.5: share labelled / accuracy |
|---|---|---|---|
| RGB + height (drone camera) | 0.41 | 0.26 | 30 % / 0.68 |
| RGB + height + hyperspectral | 0.53 | 0.41 | 20 % / 0.89 |

Spectral information is the strongest lever for species: a multispectral drone camera is the recommended
upgrade. Grouping folds by plot keeps trees of one plot out of both training and test.

## 6. Rare events and robustness

| Event | Detection | Handling |
|---|---|---|
| Cloud cover in the season | Share of valid Sentinel-2 pixels < 90 % | Automatically widens the window to Sep–Apr; skips vegetation analysis if still < 50 % |
| Closed canopy (unresolvable crowns) | Unassigned canopy > 50 % | Reports count range; recommends drone survey |
| Rare / uncertain species | Confidence < threshold; species with ≤ 2 trees in a block | Reported as Unknown / flagged for field identification, never guessed |
| Unusual trees | Height > 40 m | `height_outlier` flag |
| Land-cover change since imagery | Canopy vs WorldCover difference > 40 points; dense canopy with NDVI < 0.35 | Warning: verify with recent imagery |
| Missing or partial survey data | No DTM; coverage < 95 % | Falls back to satellite heights (flagged); counts only covered area |
| Bad inputs | Not a polygon, wrong size, not georeferenced, too coarse | Run stops with a clear message and the fix |
| Data-source failure | Earth Engine error | Retries; optional layers are skipped with a warning |

Every event is logged with the action taken and appears in the dashboard, the PDF report and the job folder.

## 7. Limitations

- The satellite canopy-height model reflects imagery mostly from 2018–2020; recent clearing or growth is not
  captured (the change checks above flag likely cases).
- Satellite mode gives stand-level forest class, not species.
- Girth (GBH), needed for compensatory-afforestation and NPV calculations, is not measured by remote sensing;
  it requires field plots or locally calibrated height–crown–girth allometry.
- Validation species are US species; Indian deployment needs local field labels (see SOP section 6).
- DeepForest's pretraining used NEON imagery that may include the validation sites, so its recall may be
  optimistic for new regions until fine-tuned on local drone imagery.
