# Satellite mode vs airborne LiDAR — 2026-09-24

529 IDTReeS plots (20 m × 20 m; NEON OSBS, MLBS, TALL). Reference: NEON airborne LiDAR canopy height model (IDTReeS). Satellite: Meta/WRI Global Canopy Height 1 m (as used by satellite mode). Canopy = height ≥ 5 m.

| Output | MAE | RMSE | Bias (satellite − LiDAR) | Correlation r |
|---|---|---|---|---|
| Canopy cover (percentage points) | 9.64 | 15.75 | -5.79 | 0.919 |
| Plot canopy height, 95th percentile (m) | 5.06 | 6.19 | -4.61 | 0.777 |

**Forest Survey of India density class:** same class as LiDAR on **77%** of plots; within one class on 97%.

Confusion (rows: LiDAR class, columns: satellite class):

| LiDAR \ Satellite | VDF | MDF | OF | NF |
|---|---|---|---|---|
| VDF | 306 | 23 | 6 | 2 |
| MDF | 15 | 42 | 53 | 8 |
| OF | 0 | 3 | 54 | 13 |
| NF | 0 | 0 | 0 | 4 |

By site:

| Site | Plots | Cover MAE (pp) | Cover bias (pp) | Height RMSE (m) | Height bias (m) | Class agreement |
|---|---|---|---|---|---|---|
| MLBS | 56 | 2.29 | -1.28 | 6.49 | -5.37 | 98% |
| OSBS | 321 | 14.02 | -10.43 | 4.34 | -2.93 | 64% |
| TALL | 152 | 3.09 | 2.35 | 8.83 | -7.89 | 97% |

Notes: a 20 m plot is smaller than the 25 m density cell used in the dashboard, so these are plot-scale comparisons; the LiDAR survey and the satellite imagery behind the Meta model are from different dates (2018–2020), so some differences are real change.
