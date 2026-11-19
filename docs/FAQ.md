# FAQ and demo script

For the team presenting Vandrishti AI. Short, honest answers to the questions evaluators are likely to ask, and a
five-minute demo sequence.

## Likely questions

**Can it identify species in Indian forests today?**
Not from satellite data; free satellite data is too coarse for species. With a drone orthophoto plus 150–300
field-labelled trees from the region, the training script builds a regional species model, and later runs in
that region classify species automatically. A model is never applied outside the region it was trained in, and
uncertain trees are reported as Unknown rather than guessed.

**Have you tested with drone data?**
Not yet. Drone-mode results use NEON aircraft survey data (10 cm RGB + LiDAR), the same file types a drone
survey produces. The next step is a pilot flight over one WCL block with 20–30 field plots.

**How accurate is it?**
Satellite density class matches airborne LiDAR on 77 % of 529 benchmark plots (97 % within one class). Drone
mode finds 52 % of hand-labelled crowns with heights within ±4 m; satellite mode finds 14 %, so it is a screening
tool, not an enumeration tool. Details: `results/idtrees/`.

**Why are these numbers lower than the earlier prototype's F1 of 0.96?**
The earlier evaluation measured distances in degrees instead of metres, so every prediction matched some tree,
and it copied ground-truth labels into its predictions. These numbers come from corrected, reproducible scripts.

**Why is precision so low?**
The benchmark only outlines field-surveyed trees, so correctly detected trees that were not outlined count as
false positives. Precision is a lower bound; recall is the reliable detection metric.

**How do you handle rare events?**
Every stage logs events with the action taken: cloud gaps (date window widened automatically), closed canopy
(count range), missing drone heights (satellite fallback, flagged), partial coverage, unusual tree heights, data
sources that disagree (possible recent clearing), rare or uncertain species (Unknown). Recoverable problems never
stop a run. See `docs/methodology.md` §6 and the SOP event table.

**What does deployment cost?**
Satellite mode needs no data or licence purchase and runs on an office PC. Drone surveys are commissioned only
for blocks that need enumeration or species. The software stack is open source.

**How does it fit into existing WCL systems?**
Outputs are KMZ (Google Earth), Shapefile (QGIS/ArcGIS), CSV, GeoTIFF and a PDF report; a REST API lets other
systems submit boundaries and fetch results.

**How do you avoid counting a tree twice in large drone images?**
The image is processed in overlapping 40 m tiles and duplicate boxes at tile edges are removed (non-maximum
suppression).

**What about girth (GBH) for compensatory afforestation and NPV?**
Girth cannot be measured from above. It needs field plots, or height–crown–girth formulas calibrated locally
from those plots. This is part of the pilot.

**What happens if Earth Engine is down or there is no internet?**
Downloaded data is cached per area, so previously run blocks work offline. Earth Engine calls are retried; if an
optional layer fails, the run continues with a warning.

**Why Google Earth Engine?**
It hosts all four datasets and returns only the pixels inside the boundary. The same datasets are also
published on open cloud buckets, so the data layer can be switched if commercial terms require it.

## Five-minute demo

1. **Home page (30 s).** Two modes: satellite (KML only, free) and drone survey. Point to the pipeline flow.
2. **Run *Chandrapur Forest Block A* (1 min).** Watch the eight steps complete with their summaries. Point at the
   `CLOSED_CANOPY` warning and its action in the event log.
3. **Map (1 min).** 4,846 trees coloured by height; tick *3D trees* and tilt; switch on *Density class (FSI)*;
   click a tree for its attributes.
4. **Statistics and Quality (1 min).** Canopy cover, FSI areas, height histogram; the confidence table with
   reasons.
5. **Exports (30 s).** Download the PDF report; open the KMZ in Google Earth.
6. **Drone survey sample (1 min).** Switch to *Drone survey*, run *IDTReeS plot with LiDAR heights*: orthophoto,
   DeepForest crowns, species with Unknown, and the survey event log.
7. **Close with the validation slide** (`presentation/2_validation/`).

Backup if the network fails: previously run blocks load from cache; the PDF reports and KMZ files in
`presentation/3_sample_outputs/` open offline.
