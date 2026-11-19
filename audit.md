# VAN DRISHTI AI — COMPLETE REPOSITORY AUDIT

## Mission

You are a senior ML/CV engineer, geospatial data scientist, remote-sensing researcher, backend engineer and technical interviewer.

You have been given the complete source repository:

`https://github.com/sujalappa/Vandrishti-AI`

Your task is to perform an exhaustive, evidence-backed technical audit of this project.

The ultimate objective is to produce a complete technical dossier that allows another AI assistant to train the project owner for:

1. Technical interviews (SWE, ML Engineer, CV Engineer, Data Scientist).
2. Research/project defence.
3. Final academic and hackathon presentations.
4. Resume writing and project positioning.
5. Deep understanding of the actual implementation.
6. Defending architectural and algorithmic decisions.
7. Explaining every important data source, experiment, model, metric and limitation.

The project owner should be able to explain the system from raw data ingestion all the way to the final GIS inventory, and defend why every component was selected.

---

# STRICT AUDIT RULES

These rules are mandatory.

1. Do not modify source code, data, configurations or model artifacts.
2. Do not assume that the README accurately reflects the implementation.
3. Inspect the actual source code, configuration, training scripts, validation scripts, datasets, model artifacts, generated results and documentation.
4. Do not infer missing hyperparameters.
5. Do not invent performance numbers.
6. Do not present a proposed feature as implemented.
7. Do not present synthetic data as real field data.
8. Do not present aircraft benchmark results as drone-flight results.
9. Do not mix results from different datasets, evaluation protocols or model versions.
10. Do not report an accuracy without identifying the evaluation dataset and protocol.
11. Every important technical claim must have repository evidence.
12. Cite exact file paths, function names, line ranges and relevant artifacts wherever possible.
13. If code and documentation disagree, report both versions and identify which is supported by executable implementation.
14. If an experiment cannot be reproduced, state why.
15. Distinguish between:
    - Implemented and working.
    - Implemented but not independently validated.
    - Experimentally evaluated.
    - Sample/demo capability.
    - Proposed/future capability.
16. Never claim that the project is a legally certified replacement for statutory forest surveys.
17. Do not claim the project has been deployed operationally at WCL unless deployment evidence supports it.
18. Preserve the distinction between the original IDTReeS experimental prototype and the current VanDrishti architecture.
19. Read the visual contents of relevant figures, diagrams and screenshots, not just their extracted text.
20. Do not stop at the README. Inspect the entire repository.

First record:
- Git commit SHA.
- Branch.
- Repository state.
- Number of files.
- Available datasets.
- Model artifacts.
- Python dependencies.
- Node dependencies.
- Current test status.

Do not install large dependencies, download huge external datasets or execute long training runs without approval. Static inspection and lightweight verification are preferred.

---

# PART 1 — PROJECT OVERVIEW

Produce a precise project summary.

Explain:

- What problem the project solves.
- Why forest inventory is needed before forest-land diversion.
- What tree-level information is required.
- Why manual enumeration is difficult.
- What the platform automates.
- Who the intended users are.
- How the platform supports WCL and forest-clearance assessment.
- What outputs it generates.
- What it does NOT replace.

Explain the difference between:

1. Satellite-based forest screening.
2. Drone-based detailed forest assessment.

Produce a concise 60-second, 90-second and 3-minute project explanation.

Also produce:
- Technical project description.
- Non-technical project description.
- Resume-oriented description.
- Research-oriented description.
- Interview-oriented description.

---

# PART 2 — REPOSITORY STRUCTURE AND CODE MAP

Inspect the full repository recursively.

Create a comprehensive code map covering:

- backend/
- frontend/
- training/
- validation/
- results/
- samples/
- models/
- docs/
- presentation/
- deployment configuration.

For every important file identify:

- Purpose.
- Main classes.
- Main functions.
- Inputs.
- Outputs.
- Dependencies.
- Downstream callers.
- Whether it is actually executed.

Trace actual call graphs rather than merely describing filenames.

Create two complete execution traces:

A. Satellite mode:
API request → AOI validation → job creation → data acquisition → processing stages → inventory generation → report/export.

B. Drone mode:
API request → survey validation → job creation → raster processing → DeepForest inference → height/species processing → inventory/export.

Identify all code paths that are unused, dead, duplicated, experimental or no longer referenced.

---

# PART 3 — SATELLITE MODE: COMPLETE DATA PIPELINE

Inspect:

`backend/vandrishti/pipeline.py`

Trace every processing stage in execution order.

For each stage report:

- Function name.
- Input files/data.
- External dependencies.
- Processing algorithm.
- Output files.
- Metadata created.
- Duration.
- Error handling.
- Events logged.
- Whether output is cached.
- What happens when the stage fails.

Inspect all functions called by the pipeline, including modules under:

`backend/vandrishti/processing/`

## 3.1 Boundary ingestion

Inspect `aoi.py`.

Determine:

- Supported formats: KML, KMZ, GeoJSON and others.
- Polygon parsing.
- Multipart polygons.
- Invalid geometries.
- Geometry repair.
- Area validation.
- Minimum/maximum supported AOI size.
- Boundary coordinate system.
- Reprojection strategy.
- UTM-zone determination.
- Security checks.
- Malformed-file handling.
- Boundary clipping logic.

Explain the complete lifecycle of an uploaded KML.

## 3.2 Data acquisition

Inspect:

`backend/vandrishti/sources/gee.py`

Document the exact Google Earth Engine datasets and collection IDs.

For each dataset report:

- Official dataset name.
- Earth Engine asset/collection ID.
- Provider.
- Spatial resolution.
- Temporal coverage.
- Bands used.
- Units.
- Native CRS.
- Licence.
- Acquisition date filters.
- Cloud masking.
- Scale factors.
- Resampling.
- Clipping.
- No-data behaviour.
- Download strategy.
- Caching.
- Retry strategy.
- Chunking.
- Export format.

Cover:

### Meta/WRI Global Canopy Height
- Exact source product.
- Canopy height band.
- Resolution.
- Temporal limitations.
- How pixels are downloaded.
- What the raster values mean.
- Why it is suitable for screening.
- Known errors.

### Sentinel-2
- Exact collection.
- Bands.
- Cloud Score+ or other cloud masking.
- Temporal selection.
- Median compositing.
- NDVI.
- Seasonal leaf-fall analysis.
- Missing-data handling.

### Copernicus DEM
- Source.
- Resolution.
- Elevation.
- Terrain derivation.
- Slope calculation.

### ESA WorldCover
- Collection/version.
- Class mapping.
- Land-cover shares.
- Use in quality checks and vegetation interpretation.

## 3.3 Data acquisition mathematics

Explain:

- Raster clipping.
- Pixel resolution.
- Affine transformation.
- Raster bounds.
- Raster alignment.
- Resampling algorithms.
- Nodata propagation.
- UTM reprojection.
- Pixel-to-world coordinate transformation.

Explicitly identify when nearest-neighbour, bilinear or other resampling methods are used.

## 3.4 Caching and offline behaviour

Inspect `gee.py`, `config.py` and `pipeline.py`.

Determine:

- Cache directory structure.
- Cache key.
- How AOIs are identified.
- Whether cache validity depends on acquisition date.
- Whether failed requests are cached.
- Whether an earlier assessment can run offline.
- Whether partial cache files are handled safely.

---

# PART 4 — SATELLITE TREE DETECTION

Inspect:

`backend/vandrishti/processing/trees.py`

This is a critical section.

Trace the exact tree-detection algorithm.

Document:

1. Input canopy-height raster.
2. Gaussian smoothing.
3. Local maxima detection.
4. Local neighbourhood size.
5. Height-dependent radius.
6. Minimum tree height.
7. Suppression of nearby maxima.
8. Plateau handling.
9. Marker creation.
10. Watershed segmentation.
11. Crown clipping.
12. Crown-radius limits.
13. Minimum/maximum crown sizes.
14. Height estimation.
15. Crown area computation.
16. Tree ID assignment.
17. Boundary filtering.
18. Duplicate suppression.

Find the exact equations.

In particular verify whether these formulas are actually implemented:

`r = (0.8 + 0.12*h) * scale`

and

`crown_radius = 0.5 + 0.3*h`

Do not assume that documentation values are the values used by the current code.

## Closed-canopy estimation

Inspect how unassigned canopy is calculated.

Identify:

- Definition of unassigned canopy.
- How canopy pixels are identified.
- Median detected crown area.
- 25th and 75th percentile crown areas.
- Estimated extra trees.
- Lower and upper population estimate.
- Treatment of overlapping crowns.
- Whether already detected crowns are removed before estimating leftover canopy.
- Units.

Derive the exact equations.

For the example with 4,846 detections and 18,235–44,310 estimated trees, trace the actual calculation.

Explain why the displayed number is an extrapolation, not individually detected trees.

---

# PART 5 — DRONE / SURVEY MODE

Inspect:

`backend/vandrishti/pipeline_survey.py`

and:

`backend/vandrishti/processing/survey.py`

Trace all ten steps.

Document:

- Required boundary.
- Orthophoto.
- DSM.
- DTM.
- Optional CHM.
- Input validation.
- Spatial coverage checks.
- Pixel resolution.
- CRS.
- Radiometric requirements.
- Missing files.
- No-data handling.
- Height fallback behaviour.

## 5.1 Drone image preparation

Determine:

- Expected image formats.
- RGB bands.
- Ground sampling distance.
- Reprojection.
- Resampling.
- Tiling size.
- Tile overlap.
- Padding.
- Pixel normalization.
- Coordinate restoration.
- Window-to-global geometry transformations.

Verify the documented 40 m / 400-pixel windows.

Explain how the code avoids missing trees at image borders.

## 5.2 DeepForest architecture

Inspect exact implementation.

Determine:

- DeepForest package version.
- Model architecture.
- RetinaNet details.
- Backbone.
- Pretrained checkpoint.
- Source of pretraining.
- Input dimensions.
- Internal resizing.
- Model confidence threshold.
- Inference batch size.
- Hardware/device selection.
- Whether model is fine-tuned.
- Whether any local training script exists.
- Prediction output type.
- Box coordinate convention.
- NMS algorithm.
- NMS threshold.
- Tiling and duplicate merge.

Explain the complete inference process:

Orthophoto → raster windows → RGB tensor → model → boxes → coordinate restoration → NMS → geospatial tree records.

Do not call bounding boxes masks.

## 5.3 Small-image padding

Explain why small survey images are padded to 400 px.

Trace the code and establish whether this is necessary because of DeepForest's training/inference resize behaviour.

Verify the documented increase in recall from 0.15 to 0.52.

Identify the exact experiment that produced this result.

## 5.4 Drone versus aircraft benchmark

This distinction is critical.

The repository states that no drone flight has actually been conducted for the project.

Determine exactly:

- Which samples come from NEON / IDTReeS aircraft data.
- Which data is synthetic.
- Which files imitate drone input formats.
- Whether the model has ever been run on a real WCL drone survey.
- Which screenshots represent sample aircraft data.

Ensure every result is described as aerial/aircraft-equivalent data where appropriate, never as a completed Indian drone flight.

---

# PART 6 — SPECIES CLASSIFICATION AND TRAINING

Inspect:

- `backend/vandrishti/processing/species.py`
- `training/`
- all training configuration files
- all model artifacts.

Explain the full species-classification architecture.

## 6.1 Feature engineering

Determine every feature extracted from each crown.

Cover:

- RGB band means.
- RGB standard deviation.
- Colour ratios.
- Excess green.
- Brightness.
- Texture.
- Height.
- Crown area.
- HSI features.
- Any dimensionality reduction.
- PCA, if used.
- Feature ordering.
- NaN handling.
- Feature normalization.

Create a table with:
feature name | formula | input | units | purpose.

## 6.2 Random Forest

Verify the exact deployed/trained classifier.

Report:

- Number of trees.
- Maximum depth.
- Minimum samples per leaf.
- Maximum features.
- Class weights.
- Random seed.
- Feature dimensionality.
- Training data size.
- Species classes.
- Other-class logic.
- Confidence calculation.
- Unknown threshold.

Verify the documented 400-tree model.

## 6.3 Regional model restrictions

Determine:

- How a model is associated with a geographical region.
- Whether training data bounds are stored.
- How an assessment decides whether a model is appropriate.
- How a model is prevented from being applied outside its training region.
- How unknown predictions are handled.
- How rare species are grouped into Other.

Explain the scientific rationale for region-specific species models.

## 6.4 Field-label requirements

Verify the claim that 150–300 labelled trees can produce a usable first model.

Inspect sample-plot design:

- Plot size.
- Number of plots.
- Sampling strategy.
- Species distribution.
- Label schema.
- Required attributes.
- Field GPS accuracy.
- Training/validation split.

State whether 150–300 is experimentally validated or a recommendation.

## 6.5 Species validation

Explain:

- Grouped 5-fold CV by plot.
- Why ordinary random splitting is dangerous.
- Accuracy.
- Macro F1.
- Weighted F1.
- Per-class precision/recall/F1.
- Confidence thresholds.
- Coverage versus accuracy.
- Unknown predictions.

Explain the difference between:
- Overall accuracy.
- Accuracy among accepted predictions.
- Percentage of trees assigned a label.

Verify the reported results:

RGB + height:
- Accuracy 0.41
- Macro F1 0.255

RGB + height + hyperspectral:
- Accuracy 0.532
- Macro F1 0.410

Threshold 0.5:
- RGB accepted coverage 30.1%, accuracy among accepted 68%.
- Hyperspectral accepted coverage 19.7%, accuracy among accepted 89%.

Trace each number to a results file and calculation.

---

# PART 7 — HEIGHT ESTIMATION

Inspect all height-related code.

Explain the difference between:

## Satellite height
- Meta/WRI Global Canopy Height.
- Raster values.
- Pixel height.
- Per-tree extraction.
- Bias.
- Accuracy limitations.
- Temporal issues.

## Drone / survey height
- DSM.
- DTM.
- CHM = DSM - DTM.
- Height within a crown box.
- P95 calculation.
- Nodata handling.
- Units.
- Height fallback.

Verify whether the current code uses the maximum or P95.

Document all height validation metrics.

Verify the 1,057 field-measured trees and:
- LiDAR MAE.
- LiDAR RMSE.
- LiDAR bias.
- R².
- Satellite MAE.
- Satellite RMSE.
- Satellite bias.
- R².

Explain why the LiDAR height can overestimate understory trees due to neighbouring canopy within the reference crown.

Explain why satellite CHM tends to underestimate tall trees.

---

# PART 8 — CANOPY DENSITY AND FSI CLASSIFICATION

Inspect:

`backend/vandrishti/processing/density.py`

Document exact implementation.

Explain:

- 25 m grid creation.
- CHM threshold.
- Pixel counting.
- Cell area.
- Canopy percentage.
- FSI classes.
- Hectare conversion.
- Partial cells at AOI edges.
- No-data cells.
- Geometry CRS.
- Raster-to-grid transformation.

Verify:

- VDF ≥70%.
- MDF 40–70%.
- OF 10–40%.
- Scrub/non-forest <10%.

Explain the difference between:

1. Crown-union canopy cover.
2. CHM-threshold pixel canopy cover.
3. FSI classification.

## Density validation

Inspect:

`validation/satellite_vs_lidar.py`

Document:

- Reference LiDAR processing.
- Satellite CHM.
- Matching of plots.
- Reference threshold.
- Calculation of MAE.
- Correlation.
- Bias.
- Classification confusion matrix.
- Site-wise results.

Verify results for 529 plots:
- 77% exact class agreement.
- 97% within one class.
- Cover MAE approximately 9.64 percentage points.
- Correlation approximately 0.919.
- Bias approximately −5.79 percentage points.

Explain why class agreement is more meaningful than raw tree-count agreement for satellite mode.

---

# PART 9 — VEGETATION AND TERRAIN ANALYSIS

Inspect:

`backend/vandrishti/processing/vegetation.py`

Explain:

- NDVI calculation.
- Sentinel-2 bands.
- Cloud masking.
- Seasonal composites.
- Leaf-fall analysis.
- Land-cover calculation.
- WorldCover classes.
- DEM processing.
- Slope.
- Elevation.
- Terrain visualization.
- Missing pixels.
- Data-source disagreement.

Identify all thresholds and formulas.

Explain possible confounders:
- Fire.
- Grazing.
- Clearing.
- Seasonal differences.
- Cloud contamination.

---

# PART 10 — QUALITY CONTROL AND EVENT SYSTEM

Inspect:

- `backend/vandrishti/jobs.py`
- `backend/vandrishti/pipeline.py`
- `backend/vandrishti/pipeline_survey.py`
- `docs/methodology.md`
- frontend event-log components.

Produce a complete list of events.

For every event report:

- Event code.
- Severity.
- Trigger.
- Detection logic.
- Actual action.
- User-facing message.
- Whether processing continues.
- Whether the output is marked uncertain.

Cover:
- Cloud gaps.
- Closed canopy.
- Missing DTM.
- Partial survey.
- Unusual height.
- Rare species.
- Unknown species.
- Recent clearing.
- Source disagreement.
- Bad geometry.
- Invalid boundary.
- Earth Engine failure.
- Retry.

Explain the philosophy of transparent uncertainty.

Determine how confidence is computed. Do not assume every confidence field is a calibrated probability.

---

# PART 11 — VALIDATION AUDIT

Inspect the complete `validation/` directory and all associated results.

For each validation script, explain:

- Dataset.
- Site.
- Inputs.
- Reference labels.
- Processing.
- Matching.
- Metric formulas.
- Thresholds.
- Train/test split.
- Random seeds.
- Output files.
- Reproducibility.

## 11.1 Crown detection

Verify exact matching logic.

Report:
- Number of plots.
- Number of labelled crowns.
- Predictions.
- IoU threshold.
- TP / FP / FN.
- Recall.
- Precision.
- Mean IoU.
- Results by site.

Explain the incomplete-ground-truth problem and why precision is a lower bound.

## 11.2 Height

Verify all 1,057 comparisons.

Explain how reference height is measured.

## 11.3 Species

Verify grouped CV.
Confirm that no plot contributes trees to both train and test folds.

## 11.4 Satellite versus LiDAR

Verify all 529 plots.
Inspect the confusion matrix.
Explain why moderately dense forest is sometimes classified as open.

## 11.5 Data leakage audit

Search the entire current repository for:
- Ground-truth labels copied into predictions.
- Field measurements inserted into model outputs.
- Test data used during training.
- Site overlap.
- Pretrained-model benchmark overlap.
- Feature leakage.
- Duplicate image patches.
- Target leakage during feature calculation.

Compare the current implementation with the earlier prototype's leakage and CRS mistakes.

Determine whether these earlier issues have genuinely been fixed.

---

# PART 12 — MODEL AND EXPERIMENT INVENTORY

Create a table of every model, algorithm and experiment:

| Model | Mode | Task | Input | Output | Training | Evaluation | Status |
|---|---|---|---|---|---|---|---|

Include:
- DeepForest/RetinaNet.
- CHM watershed.
- Random Forest.
- PCA.
- NDVI.
- Any earlier Faster R-CNN experiment.
- Any other model discovered.

Distinguish learned models from deterministic algorithms.

Explain why different approaches are used in satellite and drone modes.

---

# PART 13 — DATASETS AND TRAINING DATA AUDIT

Inspect the actual `samples/`, `data/`, `training/` and `validation/` directories.

For every dataset report:

- Name.
- Source.
- Licence.
- Site.
- Original format.
- Spatial resolution.
- Image dimensions.
- Bands.
- Number of records.
- Number of labelled trees.
- Number of labelled crowns.
- Ground-truth fields.
- Acquisition year/date.
- Whether data is synthetic or real.
- What stage consumes it.

Create a complete inventory of all datasets.

Explain the difference between:
- IDTReeS benchmark.
- NEON aircraft data.
- Local drone data specification.
- Synthetic demonstration data.
- Indian pilot data, if present.

Do not describe the IDTReeS US data as Indian ground truth.

---

# PART 14 — EXACT END-TO-END DATA FLOW

Produce detailed sequence diagrams for both modes.

For each mode trace:

1. User upload.
2. File validation.
3. AOI creation.
4. Job ID creation.
5. Data acquisition.
6. Processing.
7. Intermediate artifact storage.
8. Tree inventory generation.
9. Quality events.
10. Reporting.
11. Export.
12. Frontend rendering.

For every stage specify:
- Python function.
- File path.
- Input.
- Output.
- Data format.
- Coordinate system.
- Relevant metrics.

Explain what happens if each stage fails.

---

# PART 15 — BACKEND AND SYSTEM DESIGN

Inspect:

- api.py
- jobs.py
- config.py
- auth.py
- aoi.py
- exports.py
- report.py
- all route handlers.

Explain:

- FastAPI architecture.
- API endpoints.
- Authentication.
- Upload validation.
- Background task/job handling.
- Job persistence.
- Stage progress.
- Polling.
- Event logs.
- Cache.
- File storage.
- Error handling.
- CORS.
- Security.
- File-size restrictions.
- Concurrent jobs.
- Restart behaviour.
- Cleanup.

Explain whether jobs survive process restarts.

Explain the scalability limitations of the file-backed job system.

Do not call the system distributed or enterprise-scale unless the implementation supports that.

---

# PART 16 — FRONTEND AND VISUALIZATION

Inspect:

- frontend/src/App.tsx
- pages
- components
- MapView.tsx
- trees3d.ts
- StatsView.tsx
- TreeTable.tsx
- EventLog.tsx.

Explain:

- React architecture.
- MapLibre integration.
- Raster rendering.
- Vector overlays.
- GeoJSON.
- 3D tree rendering.
- Height extrusion.
- Tree selection.
- Map filtering.
- Search.
- Statistics.
- Progress updates.
- Event logs.
- Data downloads.

Determine whether 3D models are instanced or rendered separately.

Explain how map coordinates and visual coordinates are handled.

---

# PART 17 — EXPORTS AND REPORTING

Inspect:

- exports.py
- report.py
- sample output files.

Explain how the project generates:

- PDF reports.
- CSV.
- GeoJSON.
- KMZ.
- Shapefile.
- Canopy-height GeoTIFF.

For each format specify:
- Schema.
- Attributes.
- CRS.
- Units.
- Consumers.
- Limitations.

Inspect actual sample files and verify their consistency with the report statistics.

---

# PART 18 — DEPLOYMENT AND COST

Inspect:

- deploy/
- deploy/space/
- Dockerfiles.
- requirements.
- .env.example.
- architecture.md.
- Hugging Face Space configuration.

Determine:

- Current entry point.
- Deployment target.
- Runtime.
- CPU/GPU usage.
- Earth Engine authentication.
- Secret configuration.
- Persistent storage.
- Cache persistence.
- Memory.
- CPU.
- Storage.
- Time limits.
- Concurrency.
- Build process.
- Restart behaviour.
- Logging.

Explain the difference between:
- Local deployment.
- Hugging Face Spaces deployment.
- WCL office-PC deployment.
- Enterprise/on-prem deployment.

Verify cost claims.

Distinguish free data access from compute, hosting, survey and operational costs.

---

# PART 19 — REPRODUCIBILITY AND TESTING

Inspect requirements and tests.

Determine:
- Test count.
- Tests passed.
- Unit tests.
- Integration tests.
- Validation scripts.
- Reproducibility.
- Random seeds.
- Dependency versions.
- Model checkpoint versions.
- External API dependencies.

Identify what can be run from a clean clone.

Determine whether all sample runs work without downloading new data.

Do not execute 40-minute validation or large model training runs unless explicitly asked.

---

# PART 20 — CONTRADICTIONS AND CLAIMS AUDIT

This is one of the most important sections.

Compare:

- README.md.
- docs/GUIDE.md.
- docs/FAQ.md.
- docs/methodology.md.
- docs/SOP.md.
- presentation/README.md.
- source code.
- validation code.
- result artifacts.
- actual sample outputs.

Investigate every inconsistency.

Examples to check:

1. 8 satellite stages versus 9 stages in the Hugging Face dashboard.
2. 10 drone stages versus actual pipeline functions.
3. Different claims about 10 cm / 3–10 cm drone resolution.
4. The difference between aircraft data and real drone data.
5. DeepForest pretrained versus fine-tuned.
6. Species model training versus deployed model loading.
7. Confidence calculation.
8. Run time and hardware claims.
9. Canopy-height model resolution.
10. Difference between 393 plots and 529 plots.
11. Difference between 1,765 crowns and 1,166 field-measured trees.
12. Satellite individual detection recall versus density agreement.
13. Per-tree species predictions versus stand-level species priors.
14. Synthetic demo outputs versus real benchmarks.
15. Any claims of Indian field validation.

For each discrepancy report:

- Claim A.
- Source A.
- Claim B.
- Source B.
- Actual verified implementation.
- Correct wording to use.
- Remaining uncertainty.

---

# PART 21 — PERFORMANCE AND SCIENTIFIC LIMITATIONS

Give a frank technical critique.

Identify:
- Weak canopy separation.
- Outdated global canopy-height imagery.
- Height bias.
- DeepForest domain shift.
- Pretraining data overlap.
- Species class imbalance.
- Hyperspectral data availability.
- Field-label requirements.
- Lack of Indian drone flights.
- GBH limitations.
- Resolution mismatches.
- Processing time.
- Data-source outages.
- Caching limitations.
- Job-persistence concerns.

For each limitation describe:
- Why it occurs.
- Its effect.
- How it is measured.
- Whether it is addressed.
- Best next improvement.

---

# PART 22 — RESUME-SAFE CLAIMS

Create three categories.

A. Fully supported claims.

B. True with explicit qualification.

C. Claims that must not be made.

Generate:
- Three resume bullet options emphasizing ML/CV.
- Three emphasizing geospatial data engineering.
- Three emphasizing end-to-end backend/platform engineering.
- One balanced project summary.
- A skills/technology list.

Every resume metric must have its dataset and evaluation protocol noted.

Avoid inflated claims.

---

# PART 23 — TEAM CONTRIBUTION

Do not assume the project owner implemented every component.

Identify the work areas that are technically distinct.

Prepare a contribution template that can be personalized based on what the owner actually did.

Include likely interviewer questions:
- What did you personally implement?
- Which model did you train?
- Which data processing code did you write?
- Which experiments did you run?
- What did you debug?
- What design decision did you make?
- What was your most significant contribution?

Do not fabricate personal contributions.

---

# PART 24 — TECHNICAL INTERVIEW QUESTION BANK

Generate at least 120 questions organized by topic:

1. Project understanding.
2. Remote sensing.
3. Satellite data.
4. Google Earth Engine.
5. Data acquisition.
6. Raster processing.
7. CRS.
8. Geospatial geometry.
9. Local maxima.
10. Watershed.
11. DeepForest.
12. RetinaNet.
13. Image tiling.
14. NMS.
15. Random Forest.
16. Feature engineering.
17. PCA.
18. Species classification.
19. Class imbalance.
20. Confidence and Unknown class.
21. CHM and height estimation.
22. Canopy-density calculations.
23. FSI classifications.
24. Model evaluation.
25. Data leakage.
26. Generalization.
27. FastAPI.
28. React / MapLibre.
29. Job processing.
30. Deployment.
31. Scaling.
32. Reliability.
33. Failure analysis.
34. Indian forest applicability.
35. Research limitations.

For every question provide:

- Full answer.
- Short interview answer.
- Technical explanation.
- Relevant formula where applicable.
- Exact code evidence.
- Likely follow-up question.
- Common incorrect answer to avoid.

Include a separate set of difficult panel questions designed to challenge project assumptions.

---

# PART 25 — VIVA EXPLANATION OF EVERY MAJOR ALGORITHM

For every significant algorithm explain it at three levels:

1. Beginner.
2. Technical interview.
3. Mathematical / implementation level.

Cover:

- CRS transformations.
- Raster clipping.
- Raster resampling.
- Gaussian smoothing.
- Local maxima.
- Height-dependent neighbourhoods.
- Watershed.
- NMS.
- DeepForest.
- RetinaNet.
- Random Forest.
- PCA.
- NDVI.
- CHM.
- FSI density classification.
- MAE.
- RMSE.
- IoU.
- Precision.
- Recall.
- Macro F1.
- Grouped cross-validation.
- Correlation.

---

# PART 26 — FINAL DELIVERABLES

Create the following documents inside a new directory:

`AUDIT_OUTPUT/`

Do not modify existing project files.

### 1. MASTER_CONTEXT.md
Complete project context that can be passed to another LLM.

### 2. IMPLEMENTATION_AUDIT.md
Exact implementation, function references and call graphs.

### 3. DATA_AND_DATASETS.md
All input datasets, formats, resolutions, metadata and training data.

### 4. ML_CV_DEEP_DIVE.md
Models, training, features, hyperparameters, experiments and evaluation.

### 5. VALIDATION_AND_METRICS.md
Every experiment, metric, protocol, plot and limitation.

### 6. SYSTEM_ARCHITECTURE.md
Backend, frontend, jobs, data storage, deployment and integration.

### 7. INTERVIEW_BIBLE.md
At least 120 detailed interview questions with answers.

### 8. RESUME_POSITIONING.md
Safe resume claims, bullets and technology stack.

### 9. CLAIMS_AND_CONFLICTS.md
Contradiction report and safe wording.

### 10. TEAM_CONTRIBUTION_TEMPLATE.md
Personal-contribution preparation.

### 11. PRESENTATION_GUIDE.md
Final presentation narrative, slide-by-slide speaker notes and demo sequence.

### 12. LEARNING_ROADMAP.md
A structured study plan to understand the project from beginner level to advanced technical defence.

---

# FINAL QUALITY REQUIREMENTS

Before finishing:

1. Check every reported metric against its actual result file.
2. Check every training parameter against the training code/config.
3. Check every deployment claim against actual deployment files.
4. Check every dataset claim against files present in the repository.
5. Verify drone versus aircraft claims.
6. Verify species-prior versus per-tree classification terminology.
7. Flag any unverified mathematical extrapolation.
8. Do not hide weaknesses.
9. Do not describe a benchmark result as Indian field validation.
10. Do not confuse sample/demo output with model validation.

The final report should be detailed enough that another AI assistant could teach the project owner the entire project without needing to rediscover the repository.

At the end, provide:

- A short executive summary.
- Ten most important technical concepts.
- Twenty highest-priority interview questions.
- Ten likely panel challenges.
- Five biggest limitations.
- Five strongest scientifically defensible achievements.

Do not stop after producing a README summary. This is a full technical and scientific audit.

create a REPORT.md in root for this