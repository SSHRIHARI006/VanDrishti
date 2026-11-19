# IDTReeS validation — 2026-09-24

Benchmark: IDTReeS 2020 (NEON OSBS, MLBS, TALL), 393 plots of 20 m × 20 m. Matching: one-to-one, IoU ≥ 0.4.

## 1. Crown detection

| Method (mode) | Plots | Labelled crowns | Predictions | Recall | Precision (lower bound) | Mean IoU |
|---|---|---|---|---|---|---|
| DeepForest RGB, score ≥ 0.1 (survey mode) | 393 | 1765 | 5214 | **0.517** | 0.175 | 0.617 |
| DeepForest RGB, score ≥ 0.2 (survey mode) | 393 | 1765 | 3588 | **0.493** | 0.242 | 0.62 |
| DeepForest RGB, score ≥ 0.3 (survey mode) | 393 | 1765 | 2653 | **0.455** | 0.303 | 0.625 |
| CHM watershed on LiDAR (survey CHM) | 393 | 1765 | 2782 | **0.343** | 0.217 | 0.561 |
| CHM watershed on Meta 1 m (satellite mode) | 393 | 1765 | 1341 | **0.136** | 0.179 | 0.546 |

Recall by site: DeepForest RGB, score ≥ 0.1 (survey mode): {'MLBS': 0.475, 'OSBS': 0.501, 'TALL': 0.745}; DeepForest RGB, score ≥ 0.2 (survey mode): {'MLBS': 0.452, 'OSBS': 0.472, 'TALL': 0.74}; DeepForest RGB, score ≥ 0.3 (survey mode): {'MLBS': 0.402, 'OSBS': 0.444, 'TALL': 0.709}; CHM watershed on LiDAR (survey CHM): {'MLBS': 0.268, 'OSBS': 0.373, 'TALL': 0.515}; CHM watershed on Meta 1 m (satellite mode): {'MLBS': 0.09, 'OSBS': 0.166, 'TALL': 0.199}

## 2. Tree height vs field measurement

| Source | n | MAE (m) | RMSE (m) | Bias (m) | R² |
|---|---|---|---|---|---|
| LiDAR CHM (survey) | 1057 | 2.7 | 4.12 | 1.93 | 0.444 |
| Meta 1 m CHM (satellite) | 1057 | 4.89 | 6.2 | -3.24 | -0.258 |

## 3. Species classification (5-fold CV grouped by plot)

| Features | Samples | Classes | Accuracy | Macro F1 | Weighted F1 |
|---|---|---|---|---|---|
| RGB + height (drone-equivalent) | 1109 | 12 | 0.41 | 0.255 | 0.41 |
| RGB + height + hyperspectral (PCA 20) | 1109 | 12 | 0.532 | 0.41 | 0.53 |

Per-species results (RGB + height + hyperspectral (PCA 20)):

| Species | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| PIPA2 | 0.856 | 0.894 | 0.875 | 312 |
| QURU | 0.48 | 0.409 | 0.442 | 176 |
| ACRU | 0.469 | 0.42 | 0.443 | 143 |
| QUAL | 0.51 | 0.491 | 0.5 | 106 |
| Other | 0.328 | 0.2 | 0.248 | 95 |
| QULA2 | 0.586 | 0.689 | 0.634 | 74 |
| QUCO2 | 0.18 | 0.186 | 0.183 | 59 |
| AMLA | 0.157 | 0.234 | 0.188 | 47 |
| NYSY | 0.194 | 0.298 | 0.235 | 47 |
| QUGE2 | 0.75 | 0.167 | 0.273 | 18 |
| LITU | 0.591 | 0.765 | 0.667 | 17 |
| MAGNO | 0.172 | 0.333 | 0.227 | 15 |

Unknown threshold (uncertain trees are reported as Unknown instead of guessed). The survey pipeline deploys the RGB + height model (drones give RGB) with threshold 0.5:

| Threshold | RGB + height (drone-equivalent): share assigned / accuracy | RGB + height + hyperspectral (PCA 20): share assigned / accuracy |
|---|---|---|
| 0.0 | 1.0 / 0.41 | 1.0 / 0.532 |
| 0.3 | 0.701 / 0.507 | 0.547 / 0.697 |
| 0.4 | 0.456 / 0.579 | 0.349 / 0.819 |
| 0.5 | 0.301 / 0.68 | 0.197 / 0.89 |
| 0.6 | 0.208 / 0.766 | 0.097 / 0.898 |
| 0.7 | 0.13 / 0.785 | 0.033 / 0.946 |

## Caveats

- IDTReeS crowns cover field-surveyed trees only, so unmatched predictions are not necessarily false: precision is a lower bound; recall is the reliable detection metric.
- DeepForest was pretrained on NEON imagery that may include these sites; its recall may be optimistic.
- Species are US species; an Indian deployment trains the same model on local field labels.
- Species with fewer than 15 labels are grouped as 'Other'.
