# Site species prior on IDTReeS

1109 field-labelled crowns, 12 classes, 5-fold cross-validation grouped by plot (same split as validation.md). The prior comes only from each site's location: climate and soil matched against the worldwide records of the model's species (nearest-records share).

| Method | Accuracy | Macro-F1 | Share assigned (≥0.5) | Accuracy when assigned | Plot composition error |
|---|---|---|---|---|---|
| Image only (RF) | 41% | 0.255 | 30% | 68% | 39.1 pp |
| Image + site prior (tau 0.25) | 41% | 0.259 | 32% | 68% | – |
| Image + site prior (tau 0.5) | 40% | 0.250 | 34% | 68% | 43.7 pp |
| Image + site prior (tau 1.0) | 39% | 0.228 | 42% | 61% | – |
| Image + presence gate (site prior) | 42% | 0.265 | 35% | 68% | – |
| Image + presence gate (oracle site list) | 43% | 0.267 | 36% | 69% | – |

Composition error: share of trees that would have to change species for the estimated plot mix to equal the true mix (plots with ≥ 8 labelled trees). Image only = counting argmax labels; site prior = EM estimate (τ = 0.5 row).

Of the image-only model's 654 errors, 48 (7%) predict a species that does not occur at that site: this is the most any location-based prior can fix. The oracle row uses the true site species lists.
EM composition without any prior: 47.4 pp.

- **MLBS** (Appalachian-Blue Ridge forests): top species by niche match Amelanchier laevis 27.1%, Quercus coccinea 13.6%, Acer rubrum 13.2%, Pyrus pyrifolia 7.8%, Quercus rubra 7.5%
- **OSBS** (Southeast US conifer savannas): top species by niche match Quercus laevis 10.9%, Pinus palustris 10.3%, Quercus geminata 9.6%, Acalypha wilkesiana 8.1%, Moringa oleifera 5.6%
