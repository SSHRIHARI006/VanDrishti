# Drone survey data specification

What to fly and what to deliver so a block can be processed in **drone survey mode** (per-tree crowns,
measured heights, species). Audience: survey contractors and the WCL survey team.

## Deliverables (per block)

| File | Format | Required | Notes |
|---|---|---|---|
| Block boundary | KML / KMZ | Yes | Same boundary used for the assessment |
| Orthophoto | GeoTIFF, RGB, 8-bit | Yes | 2–10 cm ground sampling distance (GSD); the system resamples to 10 cm |
| Digital Surface Model (DSM) | GeoTIFF, float, metres | Recommended | Top of canopy / structures |
| Digital Terrain Model (DTM) | GeoTIFF, float, metres | Recommended | Bare ground, from the same processing |
| Canopy Height Model (CHM) | GeoTIFF, float, metres | Alternative | If supplied, DSM/DTM are not needed |
| Field plot labels | GeoJSON (points or crown polygons) | For species | `species` attribute per tree; see SOP section 6 |

All rasters must be **georeferenced** (embedded coordinate system, e.g. WGS 84 / UTM 44N, EPSG:32644 for
Chandrapur–Nagpur) and cover the whole boundary; the system reports coverage below 95 % and rejects files
covering less than 20 %.

## Flight parameters

| Parameter | Value |
|---|---|
| Season | **Post-monsoon, October–January** (full leaf, low cloud). Avoid March–June: teak and many dry-deciduous species are leafless |
| Time of day | 10:00–14:00 to limit long shadows |
| Altitude | 80–120 m above ground |
| GSD | 3–5 cm (RGB) |
| Overlap | 75–80 % forward, 65–70 % side (dense canopy needs high overlap for a good DSM) |
| Georeferencing | RTK/PPK drone, or at least 5 ground control points per block |
| Wind | < 8 m/s (moving crowns blur and break photogrammetry) |

**Optional sensors.** A LiDAR payload gives the best DTM under dense canopy and the most accurate heights.
A multispectral camera (red-edge, NIR) improves species separation; hyperspectral data improved species
accuracy markedly in the IDTReeS validation but is costly to acquire.

## Processing to deliverables

Photogrammetry in OpenDroneMap (free), Pix4D or Agisoft Metashape:

1. Align images with GCP / RTK positions.
2. Dense point cloud → classify ground points.
3. Export orthophoto (GeoTIFF), DSM (all points) and DTM (ground points), all in the same coordinate system.

## Permissions and safety

- Drone registration and flight permission through DGCA Digital Sky; check airspace zones.
- Mine safety clearance for flights over or near active workings; coordinate with the mine manager.
- Survey data belongs to WCL; store it with the job records.

## Field plots for species (first survey in a region)

20–30 plots of 0.1 ha across the forest density classes, recording per tree: GPS position (sub-metre GNSS
preferred), species (local and botanical name), height, GBH. About 150–300 labelled trees give a usable first
model; the model improves as more plots are added. Rare species are reported as *Unknown* until enough labels
exist.
