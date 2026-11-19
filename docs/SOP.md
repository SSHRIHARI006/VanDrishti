# Standard Operating Procedure: tree inventory for a forest-diversion block

Audience: WCL environment and survey staff. Purpose: produce a first-pass tree inventory and canopy-density
assessment for a block proposed for forest diversion, and decide where field verification is needed.

## 1. Prepare the boundary

1. Export the block boundary from the lease map or GIS as **KML or KMZ** (Google Earth: right-click the polygon
   → *Save Place As… → KMZ*). GeoJSON is also accepted.
2. The boundary must be a **closed polygon** in WGS84 longitude/latitude. Several polygons in one file are merged.
3. Keep one run to **10 km² or less**; split larger blocks into parts. Runs above 5 km² show a warning and take longer.

## 2. Choose the mode

| Situation | Mode |
|---|---|
| Screening, planning, Stage-I estimates, no drone data yet | **Satellite** (boundary only) |
| Stage-II inventory, species needed, closed-canopy forest | **Drone survey** (boundary + orthophoto + DSM/DTM) |

For a drone survey, collect data to the [drone survey specification](drone_survey_spec.md).

## 3. Run the assessment

1. Open Vandrishti AI → **New assessment**, choose *Satellite* or *Drone survey*.
2. Upload the boundary (and survey files), give the assessment a name (e.g. *Durgapur OCM Block 3*), and click
   **Run assessment**.
3. Default options suit central Indian forests: minimum tree height 5 m, canopy threshold 5 m, density cell 25 m.
   Change them only on the instruction of the project lead, and record the change in the report.
4. Watch the **Processing steps** panel. Each step shows its result; the **Event log** lists warnings and the
   action taken.

## 4. Review events before using the results

| Event | Meaning | Action |
|---|---|---|
| `CLOSED_CANOPY` | Satellite data cannot split touching crowns | Use the count range, not the detected count; plan a drone survey for enumeration |
| `S2_CLOUD_GAPS` | Clouds in the default season | System widened the date window automatically; no action unless `S2_UNAVAILABLE` follows |
| `SOURCE_DISAGREEMENT`, `POSSIBLE_CHANGE` | Height data and current imagery disagree (clearing, fire, regrowth) | Check recent imagery; field-verify before submission |
| `HEIGHT_OUTLIER` | Trees above 40 m | Verify those trees in the field |
| `CHM_FALLBACK`, `HEIGHT_UNVERIFIED` | Survey had no DSM/DTM | Re-upload with the DTM, or accept satellite heights (flagged) |
| `PARTIAL_COVERAGE` | Survey does not cover the whole boundary | Fly the missing part; trees outside coverage are not counted |
| `MANY_UNKNOWN_SPECIES`, `RARE_SPECIES` | Species model is unsure or sees rare species | Field-identify the flagged trees; add them to the training labels |
| `NO_SPECIES_MODEL` | No model trained for this region | Collect field plots (section 6) |
| Any `error` | The run stopped | Follow the action shown, fix the input and run again |

Also check the **Quality & events** tab: each output has a confidence level (High / Medium / Low / Not
available) with the reason.

## 5. Use the outputs

| Output | Use |
|---|---|
| PDF assessment report | Attach to the internal file; summary, maps, density classes, confidence, data sources |
| Tree inventory CSV | One row per tree: location, height, crown, density, species, flags |
| KMZ | Open in Google Earth for review meetings and site visits |
| Shapefile | Load into QGIS/ArcGIS or the company GIS |
| Canopy height GeoTIFF | Further GIS analysis |

Trees with quality flags (`height_outlier`, `species_uncertain`, `low_detection_confidence`,
`height_from_satellite`) form the **field verification list**: filter the CSV by the `quality_flags` column.

## 6. Field verification and species training

1. Lay out **20–30 sample plots of 0.1 ha** across the density classes shown on the map.
2. In each plot record, per tree: GPS position, species, height and girth at breast height (GBH).
3. Digitise crowns on the orthophoto (or use GPS points), save as GeoJSON with a `species` field.
4. Train the regional species model:
   `python training/train_species.py --ortho ortho.tif --chm chm.tif --labels plots.geojson --region "WCL Chandrapur"`
5. The model is stored with its region; later runs inside that region classify species automatically. Runs
   elsewhere are never classified with it.

## 7. Record keeping

Keep the job folder (`data/jobs/<id>/`): it contains the input files, all outputs, the event log and the
data-source list, so any figure in a report can be traced back to its inputs.
