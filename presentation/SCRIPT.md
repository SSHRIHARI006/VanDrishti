# Van-drishti AI: presentation script

For the team presenting `Vandrishti_AI_Proposal.pptx` (24 slides). The words to say are in plain text;
*[italic brackets]* are actions (click, point, pause). Each slide's section is also in that slide's speaker notes,
so it shows in PowerPoint's presenter view.

**Length:** about 16 minutes at a calm pace. For a 7–8 minute slot, use only the lines marked **(core)** on
slides 5, 12, 15, 17, 18 and 19 and skip the rest of those slides.
**Speakers:** split at natural breaks, for example Speaker 1: slides 1–4, Speaker 2: slides 5–15,
Speaker 3: slides 16–23. Hand over with the name: "Now [name] will show you how it handles problems."

**Structure note:** concept → objectives → two modes → proposed solution with the live demo link (slide 5) → one solution slide per objective (slides 6–9) → live system (slides 10–11) → methodology.

Before you start: open the deck in presenter view, and have the dashboard already running and loaded
(`..\.venv\Scripts\python.exe -m uvicorn vandrishti.api:app --port 8000` from `backend`) on Chandrapur Forest
Block A in a second window or a second monitor, ready to switch to at slide 5. Keep `3_sample_outputs/` open as
a backup in case the network or the demo machine has trouble.

---

---

---

## Slide 1: Cover (30 s)

Good morning, respected members of the jury. We are the team from the Indian Institute of Information
Technology, Nagpur. *[Each member says their name, or the lead introduces everyone.]*

Our problem statement, from WCL, is an AI/ML-based GIS model for tree enumeration, species identification,
tree height and canopy density estimation.

Our solution is called **Van-drishti AI**. "Van" means forest and "drishti" means vision: seeing the forest,
tree by tree.

In the next few minutes we will show you what it does, how it works, and how WCL can start using it. And we
won't just tell you — we'll show you the actual system running, right now.

---

## Slide 2: Conceptualization (1 min)

*[Point to the yellow box.]*
Before any forest land is diverted for coal mining, every tree in the block has to be recorded: its location,
species, height, crown, and the density of the forest.

Today this is done by field teams walking through the forest with tapes and notebooks. It is slow. It can be
unsafe in rugged terrain. And two teams can come back with different numbers for the same block.

The scale is large. One of our sample blocks near Chandrapur is 121 hectares, and it holds an estimated
18,000 to 44,000 trees.

*[Point to the green box.]*
Our idea is simple. The user uploads the boundary of the block as a KML file, the same file they already have
from the lease or diversion map. The system gives back a georeferenced tree inventory, maps and a report.

*[Point to 1, 2, 3.]*
Boundary in, AI and GIS processing, inventory out. And this isn't a concept on a slide — **we have already
built it**. First, what it has to achieve.

---

## Slide 3: Objectives (45 s)

The problem statement gives us four objectives, and everything we built maps to them.

*[Point to the four cards.]*
**Tree enumeration**: count and locate every tree in the block. **Species identification**: name each tree's
species. **Tree height**: measure the height and crown of every tree. **Canopy density**: classify the forest in
Forest Survey of India density classes.

*[Bottom box.]*
And all of it has to come out as something WCL can use directly: a georeferenced tree inventory, maps, a PDF
report and GIS files, for the forest-clearance proposal.

---

## Slide 4: Two modes, satellite and drone (45 s)

We give WCL two ways to run the same analysis. *[Left card.]* **Satellite mode** needs only the block boundary.
It uses free satellite maps and gives a result in about a minute, so every block can be screened.
*[Right card.]* **Drone mode** adds a drone flight. From the drone photos we find every single crown, measure its
height, and name its species. *[Bottom.]* Satellite for every block first, drone where a tree-by-tree record is needed.

---

## Slide 5: Proposed Solution (1 min)

**(core)** Here is how we meet each objective. One upload, and two modes.

*[Point to the table, row by row.]*
- **Tree enumeration**: in satellite mode, tree tops are found in a 1-metre canopy height map; in drone mode,
  DeepForest AI finds every individual crown.
- **Species identification**: satellite mode gives the likely species for the site from its climate and soil;
  drone mode names the species of each tree, and says Unknown when it is not sure.
- **Tree height**: from the global canopy height map, or from the drone's own height model.
- **Canopy density**: both modes classify every 25-metre cell into FSI density classes.

*[Bottom box.]*
The result: a tree inventory, maps and a report for any block, in about a minute. The link on the right opens the live system. Let us show you it running.

---

## Slide 6: Proposed Solution, tree enumeration (45 s)

We start from a height map: the 1-metre satellite canopy height map, or the drone's own height model. Tree tops are the local high points; in drone mode the DeepForest AI draws a box on every crown. Each crown is outlined, duplicates are merged, bushes and trees outside the boundary are dropped. *[Point to the table.]* In Chandrapur Block A that gives a GPS point for every tree we can see. Where crowns merge, we say so and give a range; the drone resolves every crown.

---

## Slide 7: Site-aware species prediction (45 s)

A tree species can only grow where the climate and soil suit it. So before we look at a single crown, we ask:
which trees can grow at this site?

*[Point to the four steps.]*
We take the site's climate, soil and land cover, match it against records for hundreds of tree species, and find
the closest match.

*[Left table.]*
For Chandrapur Block A it recognises the Central Deccan Plateau dry deciduous forest and lists kullu, lendia,
kutaj, palash, rohan and their associates. In satellite mode, this is the species list WCL gets for free, before
any field visit.

**(core)** The site tells us which species can be there; the drone and field plots tell us how many actually are.

*[Transition.]* That is the solution. Now, how it works under the hood.

---

## Slide 8: Proposed Solution, tree height and crown (45 s)

Height is simply the top of the tree minus the ground below it. The top surface comes from the satellite height map or the drone's surface model; the bare ground comes from the drone's terrain model, from photogrammetry or LiDAR. The tallest point in each crown is the tree's height, and the crown outline gives its width and area. *[Point to the table.]* These are real measured values.

---

## Slide 9: Proposed Solution, canopy density (45 s)

We divide the block into 25-metre cells and measure what share of each cell is under tree canopy. Each cell gets a Forest Survey of India class: very dense, moderately dense, open or scrub. *[Point to the table.]* For Block A you get the hectares in each class, ready for the clearance form.

---

## Slide 10: This is already built and running — satellite mode (1 min)

*[Switch to the live dashboard now if you can; the slide is the fallback. This is the moment to say clearly:
this is a real, working website, not a mockup.]*

This is our dashboard after a satellite run on Chandrapur Forest Block A. It is live right now, and you're
welcome to open it yourselves after the talk.

*[Point left.]*
On the left, the eight processing steps it just ran, each with its result and duration.

*[Point to the map.]*
In the middle, every detected tree on a satellite basemap, in 3D, coloured by height. You can click any tree
to see its height, crown size and location, or switch on the density-class layer.

*[Point to the numbers on the right.]*
121.5 hectares. 4,846 trees mapped individually. 77 % canopy cover, mostly very dense forest. And the whole
run took under a minute.

From here the user downloads the PDF report, the tree list as CSV, a KMZ for Google Earth, or a Shapefile for
GIS — all real files, generated by this real run.

---

## Slide 11: Drone survey mode, live (45 s)

The same live system, now in drone survey mode, on a benchmark plot.

*[Point to the image.]*
Each green circle is a tree crown detected by DeepForest on 10-centimetre imagery, with its height measured
from the survey's canopy height model.

*[Point to the statistics.]*
20 trees, median height 15.3 metres, and the species breakdown. 18 trees are marked Unknown because the model
was less than 50 % sure. We would rather send those to a field botanist than put a wrong species in a
government record.

*[Point to the yellow card. Say this clearly.]*
To be transparent: we have not flown a drone on a WCL block yet. This data is from an aerial survey by NEON in
the US: 10 cm imagery plus LiDAR, the same files a drone survey delivers. The next step is a pilot flight on a
WCL block — everything else is already built and waiting for that data.

*[Transition.]* One more part of the solution: how we identify species.

---

## Slide 12: Proposed Methodology, pipeline (1 min 15 s)

This is the complete pipeline behind what you just saw. *[Point left to right.]*

The only input is the KML boundary. From there, there are two modes.

**Satellite mode** needs nothing else. It pulls four free datasets through Google Earth Engine: Meta's 1-metre
global canopy height map, Sentinel-2 imagery, the Copernicus elevation model and ESA land cover.

**Drone survey mode** also takes a drone orthophoto and the surface and terrain models from the survey.

Both modes go through the same processing and produce the same outputs: tree inventory, 2D and 3D map, PDF
report, and GIS files.

*[Point to the three cards at the bottom.]*
Three core methods:

- **Tree detection.** From satellite data, we find tree tops as local peaks in the canopy height model and grow
  each crown with a watershed algorithm. From drone images, we use DeepForest, a deep-learning detector
  (RetinaNet), on 10-centimetre imagery.
- **Height and density.** Height is the top of each crown in the canopy height model, which is surface minus
  terrain. Density is canopy cover on a 25-metre grid, classified into Forest Survey of India classes: very
  dense, moderately dense and open forest.
- **Species.** A Random Forest model trained on field-labelled trees of that region. If it is less than 50 %
  sure, it says **Unknown** instead of guessing.

---

## Slide 13: Methodology, the eight steps (45 s)

**(core)** This is what one run looks like: eight steps, and each one reports its result live on screen — the
same steps you just saw run on Block A.

*[Walk quickly across the top row.]*
It reads and checks the boundary, fetches canopy height, fetches satellite and terrain data, and detects the
trees.

*[Point to step 4.]*
Step 4 is where the honesty matters. In dense forest, 1-metre satellite data cannot separate touching crowns.
So instead of pretending, we report the trees we could map one by one, plus an estimated range for the rest.

*[Bottom row.]*
Then density, vegetation health, quality checks, and finally the inventory and reports.

*[Point to the strip at the bottom.]*
Drone mode adds two steps: checking the survey files, and classifying species. And everything is measured in
metres on the block's own UTM zone, so areas and crown sizes are correct.

---

## Slide 14: Scope, objective and generalization (45 s)

Our objective is a first-pass tree inventory for any forest-diversion block, with an honest accuracy statement
for every output.

*[Point to the four cards.]*
Four things: enumerate the trees, identify species, measure height and crown, and classify canopy density.

*[Point to the table.]*
The two modes cover different needs. Satellite mode is free and takes minutes, but it gives a stand-level
forest class, not species. Drone mode gives individual crowns, measured heights and species, at the cost of a
flight.

*[Point to Generalization.]*
It works for any block in India: the system picks the right map projection automatically. And for a new
region, a few hundred field-labelled trees are enough to train its species model.

---

## Slide 15: Positive impact (45 s)

*[Point to the four numbers.]*
About one minute for a satellite first pass of a 1.2 square-kilometre block on a laptop. Zero rupees in data
or licence cost per satellite run. Six output formats that open in tools WCL already uses. And every figure can
be traced back to its inputs.

*[Left box.]*
For WCL and CMPDI: Stage-I estimates and density maps for every block before anyone goes to the field. Field
teams then go only to the trees the system flags, which means less time in unsafe terrain. And one consistent
method across all areas.

*[Right box.]*
For the forest and the public record: a georeferenced record of what stood there before diversion, density maps
for compensatory afforestation planning, and uncertainty that is stated, never hidden.

---

## Slide 16: Proposed Deployment Architecture (45 s)

**(core)** The architecture is deliberately simple. *[Point left to right.]*

A browser dashboard, where the user uploads the boundary and watches the steps — the same dashboard you saw
running. An API service that checks the upload and creates the job. A pipeline worker that runs the stages. It
calls Google Earth Engine for data, the DeepForest model for crowns, and the regional species models.

*[Point down.]*
Every job is stored as a folder: inputs, results, reports and the event log. From there, results go into
existing systems: Google Earth, QGIS or ArcGIS, spreadsheets, or directly through the REST API.

*[Bottom cards.]*
The whole thing runs on one office PC for a pilot, and the same code scales to a server.

---

## Slide 17: Handling of rare events (1 min)

In real forests, things go wrong: clouds, dense canopy, unknown species, missing data. Our rule is that a problem
is detected, logged with the action taken, and never silently ignored.

*[Point to the table, pick three rows.]*
- If clouds cover the imagery in the chosen season, the system automatically widens the date window and logs
  it.
- If a species is uncertain or very rare, the tree is marked Unknown and flagged for field identification. It
  is never guessed.
- If a drone survey has no terrain model or does not cover the whole block, heights fall back to satellite data
  and every affected tree is flagged.

*[If time, open the event log in the live dashboard.]*
This is a real run on Chandrapur Block A. The warning says 80 % of the canopy could not be split into individual
crowns at 1-metre resolution. So the system says: the 4,846 mapped trees are a lower bound, the estimated total
is 18,235 to 44,310, and a drone survey would resolve individual crowns.

Recoverable problems never stop a run. And each event code has an action in our Standard Operating Procedure
for WCL staff.

---

## Slide 18: Suggested hardware for inference (30 s)

**(core)** No GPU is needed.

*[Top row.]*
A normal laptop or workstation with 16 GB of RAM is enough for a pilot and for one area office. A server is
only needed when many users run large drone mosaics.

*[Bottom left.]*
Measured on a laptop CPU: under a minute for a satellite run on one block, and about a minute for a drone plot.

*[Bottom right.]*
For drone mode, any RGB survey drone with RTK positioning works. A LiDAR payload gives the best heights under
dense canopy, and a multispectral camera improves species separation.

---

## Slide 19: Software and/or Hardware (30 s)

**(core)** The whole software stack is open source, so there are no licence fees.

*[Point across the cards.]*
The dashboard is React with MapLibre for maps — what you saw running earlier. The API is FastAPI in Python. The
geo-processing uses standard scientific libraries: rasterio, shapely, NumPy. The AI models are DeepForest and
scikit-learn. Data comes from Google Earth Engine, free.

*[Right card.]*
On the hardware side: an office PC, a survey drone, optionally LiDAR, and GPS for field plots. For drone
photogrammetry, OpenDroneMap is free.

---

## Slide 20: Data quality, the quality loop (45 s)

**(core)** Quality is checked at every step, not only at the end. *[Walk the five boxes.]*

One: inputs are checked. The boundary must be a proper polygon of the right size, and drone files must be
georeferenced and cover the block.
Two: data is cleaned. Cloudy pixels are masked, and all layers are put on the same metric grid.
Three: every output gets a confidence rating, High, Medium or Low, with the reason.
Four: flagged trees become the field verification list.
Five: the verified field labels go back into training.

*[Point to the strip.]*
So it is a loop: every survey makes the next one better.

*[Bottom cards.]*
Every job keeps a full audit trail, and every problem is recorded with the action taken.

---

## Slide 21: Operational Readiness (45 s)

*[Point to the arrow.]*
We are at stage one: the prototype is built, and — as you saw at the start — it already runs end to end.

*[Left list.]*
What is ready today: the web application running both modes end to end, tested on Chandrapur blocks and survey
data. A Standard Operating Procedure for WCL staff, a drone data specification for contractors, exports into
WCL's GIS tools, offline operation for blocks already processed, and secured file uploads.

*[Right box.]*
What we need before production: a pilot drone flight over one WCL block, field plots to train the species
model, and multi-user access.

---

## Slide 22: Implementation in the coal sector (45 s)

This is how it fits into WCL's clearance process. *[Walk the five boxes.]*

The boundary comes from the existing lease or diversion map. **Every** block gets a free satellite screening:
Stage-I estimates and density maps. **Only** blocks going to Stage-II, or needing species, get a drone survey,
flown to our specification. Field teams verify only the flagged trees and sample plots. And results go straight
into WCL records: the PDF on file, the Shapefile in GIS, the KMZ for review meetings.

*[Bottom cards.]*
Area environment and survey staff run it using the SOP, HQ and CMPDI GIS teams review and integrate, and
contractors deliver drone data to spec. We start at one WCL area, expand to all WCL areas, and then to other
Coal India subsidiaries.

---

## Slide 23: Work plan (45 s)

This is a six-month pilot plan. *[Walk the bars top to bottom.]*

Month one: select the pilot block and install the system on a WCL computer. Months one to three, shown in
orange: the drone survey and field plots, timed for the October–January leaf-on season. Months two to four: train
the regional species model. Months three to five: check it against field data. Months four and five:
integration and staff training. Months five and six: rollout to more blocks and the final report.

*[Bottom box.]*
The deliverables are a working system on WCL hardware, a trained regional species model, and trained staff.

---

## Slide 24: Innovation and differentiating factors, and close (1 min)

To close, six things make Van-drishti AI different. *[Point to each card briefly.]*

1. **KML in, inventory out.** One upload. No GIS expertise needed.
2. **Two modes, one pipeline.** Free screening for every block, paid drone detail only where it is needed.
3. **Honest uncertainty.** Every output carries its confidence and reason. Ranges instead of false precision.
   Unknown instead of a guessed species.
4. **Region-locked species models.** A model trained in Chandrapur is never silently used in another forest.
5. **Every step is visible.** Live progress, a rare-event log with actions, and a full audit trail.
6. **Open and reproducible.** Built on open, testable methods, not a black box.

*[Pause. Look at the jury.]*
Van-drishti AI does not replace the forest survey. It tells the survey team exactly where to go, and gives WCL a
faster, safer and auditable first pass for every block. And unlike a lot of what you'll see today, this one is
already running — we showed you at the start, and we're happy to show it again.

Thank you. We are happy to show a live run, or take your questions.

---

## Likely questions: short answers

Full answers are in `docs/FAQ.md`. The five most likely:

- **"Can it identify Indian species today?"** Not from satellite data. With drone imagery plus field-labelled
  trees from the region, yes; that is the pilot.
- **"Have you flown a drone?"** Not yet. Drone-mode results use NEON aerial survey data with the same file types.
- **"Why can't satellite mode count every tree in dense forest?"** 1 m data cannot separate touching crowns.
  That is why satellite mode reports a range and is used for screening, not enumeration.
- **"What about girth (GBH)?"** It cannot be measured from above. It needs field plots or height–crown–girth
  formulas calibrated on them, which is in the work plan.
- **"What if the internet or Earth Engine is down?"** Blocks already processed work offline from the cache; calls
  are retried; optional layers are skipped with a warning.

## Delivery tips

- Point at the slide while you speak; the jury follows your hand.
- Slides 10–11 are your strongest moment: a real, running website, in the first minute. If you can, actually
  switch to the browser live — it lands much harder than a screenshot.
- Say the limitations yourself (slides 7 and 11). It builds trust and pre-empts the hardest questions.
- If the live demo stalls, say "let me show the same run from the slide" and continue on slide 10.
- Rehearse the handovers between speakers at least twice with a timer.
