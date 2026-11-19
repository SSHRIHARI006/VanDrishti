"""Does the site species prior improve species identification? Test on IDTReeS.

Same cross-validation as validation/idtrees_validation.py (class-balanced Random
Forest on RGB + height features, 5-fold grouped by plot, rare species -> Other),
so the "image only" row reproduces the published 41 % accuracy. Each held-out
tree's probabilities are then combined with the site prior for its plot's
location (climate + soil niche match, training/build_species_niches.py).
OSBS (Florida) and MLBS (Virginia) have very different climates.

Usage:
    python training/eval_site_prior.py [--data "../idtrees datset"]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from shapely.geometry import Point
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "validation"))

from idtrees_validation import MIN_SPECIES_SAMPLES, load_plots, species_samples, taxon_names  # noqa: E402
from vandrishti.config import settings  # noqa: E402
from vandrishti.processing import site_prior  # noqa: E402
from vandrishti.sources import gee  # noqa: E402

OUT = ROOT / "results" / "idtrees"
THRESHOLD = 0.5


def metrics(y: np.ndarray, proba: np.ndarray, classes: np.ndarray) -> dict:
    pred = classes[proba.argmax(axis=1)]
    conf = proba.max(axis=1)
    sel = conf >= THRESHOLD
    return {
        "accuracy": round(float(accuracy_score(y, pred)), 3),
        "macro_f1": round(float(f1_score(y, pred, average="macro", zero_division=0)), 3),
        "assigned_share": round(float(sel.mean()), 3),
        "accuracy_on_assigned": round(float((pred[sel] == y[sel]).mean()), 3) if sel.any() else None,
    }


def estimate_composition(p: np.ndarray, prior: np.ndarray, strength: float = 10.0, iters: int = 200) -> np.ndarray:
    """EM label-shift estimate of class proportions (Saerens et al. 2002) with a weak Dirichlet prior."""
    pi = prior.copy()
    for _ in range(iters):
        q = p * pi[None, :]
        q /= q.sum(axis=1, keepdims=True)
        new = (q.sum(axis=0) + strength * prior) / (len(p) + strength)
        if np.abs(new - pi).max() < 1e-6:
            return new
        pi = new
    return pi


def composition_error(y, proba, classes, groups, prior_rows, use_em: bool) -> float:
    """Mean absolute error (percentage points) of each plot's species shares, plots with >= 8 labelled trees."""
    errs = []
    for g in sorted(set(groups)):
        idx = np.array([i for i, x in enumerate(groups) if x == g])
        if len(idx) < 8:
            continue
        truth = np.array([(y[idx] == c).mean() for c in classes])
        if use_em:
            est = estimate_composition(proba[idx], prior_rows[idx[0]])
        else:
            pred = classes[proba[idx].argmax(axis=1)]
            est = np.array([(pred == c).mean() for c in classes])
        errs.append(np.abs(est - truth).sum() / 2 * 100)  # total variation distance, in % of trees
    return round(float(np.mean(errs)), 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT.parent / "idtrees datset")
    args = ap.parse_args()

    table = site_prior.load_niches(settings.models_dir / "niches" / "tree_niches.json")
    if table is None:
        sys.exit("Build the niche table first: python training/build_species_niches.py")
    plots = {k: v for k, v in load_plots(args.data).items() if v["split"] == "train"}
    X, _, y, groups, lonlat = species_samples(plots)
    counts = Counter(y)
    y = np.array([s if counts[s] >= MIN_SPECIES_SAMPLES else "Other" for s in y])
    X = np.where(np.isfinite(X), X, np.nanmedian(X, axis=0))
    classes = np.unique(y)

    proba = np.zeros((len(y), len(classes)))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(X, y, groups):
        rf = RandomForestClassifier(n_estimators=400, max_depth=14, class_weight="balanced", random_state=0, n_jobs=-1)
        rf.fit(X[tr], y[tr])
        proba[np.ix_(te, np.searchsorted(classes, rf.classes_))] = rf.predict_proba(X[te])

    # one site prior per NEON site, from that site's location (climate + soil + nearby records)
    names = taxon_names(args.data)
    sites = sorted({g.split("_")[0] for g in groups})
    priors, site_info = {}, {}
    for site in sites:
        pts = np.array([ll for ll, g in zip(lonlat, groups) if g.startswith(site + "_")])
        lon, lat = pts.mean(axis=0)
        env = gee.fetch_site_environment(Point(lon, lat).buffer(0.01))
        local = site_prior.local_species_keys(lon, lat, settings.cache_dir)
        scored = site_prior.score_species(env["env"], table, in_india=False, local_keys=local)
        priors[site] = site_prior.prior_for_classes(env["env"], table, list(classes), names)
        site_info[site] = {"ecoregion": env["ecoregion"], "lonlat": [round(lon, 4), round(lat, 4)],
                           "prior": {c: round(float(p), 3) for c, p in zip(classes, priors[site])},
                           "top_species": [(s["name"], s["share_pct"]) for s in scored[:8]]}
    prior_rows = np.array([priors[g.split("_")[0]] for g in groups])
    # presence-only use of the prior: a species either can occur here (>= 2 % share) or not; no abundance guess
    gate_rows = np.where(prior_rows >= 0.02, 1.0, 0.0)
    # oracle: the species truly recorded at each site (upper bound on what location alone can add)
    site_of = np.array([g.split("_")[0] for g in groups])
    truth_sets = {st: set(y[site_of == st]) for st in sites}
    oracle_rows = np.array([[1.0 if c in truth_sets[st] else 0.0 for c in classes] for st in site_of])

    pred0 = classes[proba.argmax(axis=1)]
    wrong = pred0 != y
    cross = np.array([p not in truth_sets[st] for p, st in zip(pred0, site_of)])

    results = {"samples": int(len(y)), "classes": classes.tolist(), "sites": site_info, "runs": {}}
    results["errors"] = {"image_only_errors": int(wrong.sum()),
                         "cross_site_errors": int((wrong & cross).sum()),
                         "cross_site_share_of_errors": round(float((wrong & cross).sum() / max(wrong.sum(), 1)), 3)}
    results["runs"]["Image only (RF)"] = {**metrics(y, proba, classes),
                                          "composition_error_pp": composition_error(y, proba, classes, groups, prior_rows, False)}
    for tau in (0.25, 0.5, 1.0):
        adj = np.vstack([site_prior.adjust_probabilities(proba[i:i + 1], prior_rows[i], tau=tau) for i in range(len(y))])
        results["runs"][f"Image + site prior (tau {tau})"] = {
            **metrics(y, adj, classes),
            "composition_error_pp": composition_error(y, proba, classes, groups, prior_rows, True) if tau == 0.5 else None,
        }
    for label, rows in (("Image + presence gate (site prior)", gate_rows), ("Image + presence gate (oracle site list)", oracle_rows)):
        adj = np.vstack([site_prior.adjust_probabilities(proba[i:i + 1], rows[i], tau=1.0) for i in range(len(y))])
        results["runs"][label] = {**metrics(y, adj, classes), "composition_error_pp": None}
    uniform = np.full_like(prior_rows, 1 / len(classes))
    results["runs"]["Image only (RF)"]["composition_error_em_pp"] = composition_error(y, proba, classes, groups, uniform, True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "site_prior.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = ["# Site species prior on IDTReeS", "",
             f"{len(y)} field-labelled crowns, {len(classes)} classes, 5-fold cross-validation grouped by plot "
             "(same split as validation.md). The prior comes only from each site's location: climate and soil "
             "matched against the worldwide records of the model's species (nearest-records share).", "",
             "| Method | Accuracy | Macro-F1 | Share assigned (≥0.5) | Accuracy when assigned | Plot composition error |",
             "|---|---|---|---|---|---|"]
    for k, r in results["runs"].items():
        ce = f"{r['composition_error_pp']} pp" if r["composition_error_pp"] is not None else "–"
        lines.append(f"| {k} | {r['accuracy']:.0%} | {r['macro_f1']:.3f} | {r['assigned_share']:.0%} | "
                     f"{(r['accuracy_on_assigned'] or 0):.0%} | {ce} |")
    lines += ["", "Composition error: share of trees that would have to change species for the estimated plot mix "
              "to equal the true mix (plots with ≥ 8 labelled trees). Image only = counting argmax labels; "
              "site prior = EM estimate (τ = 0.5 row).", ""]
    e = results["errors"]
    lines += [f"Of the image-only model's {e['image_only_errors']} errors, {e['cross_site_errors']} "
              f"({e['cross_site_share_of_errors']:.0%}) predict a species that does not occur at that site: this is "
              "the most any location-based prior can fix. The oracle row uses the true site species lists.",
              f"EM composition without any prior: {results['runs']['Image only (RF)']['composition_error_em_pp']} pp.", ""]
    for site, info in site_info.items():
        lines.append(f"- **{site}** ({info['ecoregion']}): top species by niche match "
                     + ", ".join(f"{n} {p}%" for n, p in info["top_species"][:5]))
    (OUT / "site_prior.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
