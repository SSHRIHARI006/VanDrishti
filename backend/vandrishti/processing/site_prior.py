"""Site species prior: which trees can grow here, from climate, soil and worldwide records.

training/build_species_niches.py stores, for every candidate tree species, the
climate and soil at its worldwide GBIF records, and for every Indian record its
climate, soil and land cover. For an Indian site we find the reference records
from the most similar places in India (climate + soil, re-weighted to the site's
land-cover mix, so town gardens don't count at a forest site) and take each
species' share of them. Outside India, or for a species model's own classes, the
same nearest-records share is taken over the species' worldwide records.
GBIF records show where species are seen, not how many trees there are: the
shares rank likely species, they are not stem counts. In drone mode it rules out labels for
species that cannot occur at the site.

This is a predicted likelihood of occurrence, never a tree count.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..sources.gee import ENV_VARS

LOG_VARS = ["bio12", "bio17", "soc"]
LOCAL_BOOST = 1.5
REF_K = 1500     # nearest Indian reference records used for an Indian site
NICHE_K = 400    # nearest worldwide niche points used elsewhere and for a model's classes
MIN_SHARE_PCT = 0.1
PLANTED_BUILT_SHARE = 0.25  # a quarter or more of a species' Indian records on built-up land: often planted
HABITAT_GROUPS = {"forest": [10, 95], "shrub_grass": [20, 30], "cropland": [40], "built": [50],
                  "other": [60, 70, 80, 90, 100]}

# Common names used in central India (Hindi / Marathi), for display only.
LOCAL_NAMES = {
    "Tectona grandis": "Sagwan / Sag",
    "Madhuca longifolia": "Mahua / Moha",
    "Diospyros melanoxylon": "Tendu / Tembhurni",
    "Terminalia elliptica": "Saja / Ain",
    "Terminalia tomentosa": "Saja / Ain",
    "Anogeissus latifolia": "Dhaura / Dhavda",
    "Lagerstroemia parviflora": "Lendia / Lendi",
    "Buchanania cochinchinensis": "Chironji / Charoli",
    "Buchanania lanzan": "Chironji / Charoli",
    "Butea monosperma": "Palash / Palas",
    "Boswellia serrata": "Salai",
    "Pterocarpus marsupium": "Bija / Bibla",
    "Dalbergia latifolia": "Shisham / Shisav",
    "Dalbergia sissoo": "Shisham / Shisav",
    "Terminalia arjuna": "Arjun",
    "Terminalia bellirica": "Baheda / Behda",
    "Terminalia chebula": "Harad / Hirda",
    "Syzygium cumini": "Jamun / Jambhul",
    "Mangifera indica": "Aam / Amba",
    "Azadirachta indica": "Neem / Kadulimb",
    "Ficus benghalensis": "Bargad / Vad",
    "Ficus religiosa": "Peepal / Pimpal",
    "Ficus racemosa": "Gular / Umbar",
    "Vachellia nilotica": "Babul / Babhul",
    "Acacia nilotica": "Babul / Babhul",
    "Senegalia catechu": "Khair",
    "Acacia catechu": "Khair",
    "Aegle marmelos": "Bel",
    "Phyllanthus emblica": "Amla / Avla",
    "Cassia fistula": "Amaltas / Bahava",
    "Gmelina arborea": "Gamhar / Shivan",
    "Schleichera oleosa": "Kusum",
    "Haldina cordifolia": "Haldu / Hed",
    "Bombax ceiba": "Semal / Katesavar",
    "Albizia lebbeck": "Siris / Shirish",
    "Hardwickia binata": "Anjan",
    "Soymida febrifuga": "Rohan",
    "Pongamia pinnata": "Karanj",
    "Millettia pinnata": "Karanj",
    "Tamarindus indica": "Imli / Chinch",
    "Shorea robusta": "Sal",
    "Ziziphus mauritiana": "Ber / Bor",
    "Limonia acidissima": "Kaith / Kavath",
    "Grewia tiliifolia": "Dhaman",
    "Semecarpus anacardium": "Bhilawa / Bibba",
    "Leucaena leucocephala": "Subabul",
    "Eucalyptus camaldulensis": "Nilgiri",
    "Eucalyptus tereticornis": "Nilgiri",
    "Holoptelea integrifolia": "Chilbil / Vavla",
    "Cordia dichotoma": "Lasora / Bhokar",
    "Lannea coromandelica": "Jhingan / Moi",
    "Conocarpus latifolius": "Dhaura / Dhavda",
    "Anogeissus latifolia": "Dhaura / Dhavda",
    "Ougeinia oojeinensis": "Tinsa / Tiwas",
    "Mitragyna parvifolia": "Kaim",
    "Chloroxylon swietenia": "Bhirra",
    "Garuga pinnata": "Kekar",
    "Holarrhena pubescens": "Kutaj / Kuda",
    "Albizia procera": "Safed siris / Kinhai",
    "Sterculia urens": "Kullu / Karai",
    "Madhuca indica": "Mahua / Moha",
    "Terminalia anogeissiana": "Dhaura / Dhavda",
}


def local_species_keys(lon: float, lat: float, cache_dir: Path, radius_km: int = 50) -> set[int] | None:
    """GBIF species keys of plants recorded within radius_km of the site (cached). None if GBIF is unreachable."""
    path = cache_dir / f"gbif_local_{lat:.3f}_{lon:.3f}_{radius_km}.json"
    if path.exists():
        return set(json.loads(path.read_text()))
    url = ("https://api.gbif.org/v1/occurrence/search?" + urllib.parse.urlencode({
        "geo_distance": f"{lat:.5f},{lon:.5f},{radius_km}km", "kingdomKey": 6, "limit": 0,
        "facet": "speciesKey", "facetLimit": 3000}))
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            facets = json.load(r)["facets"]
    except (OSError, ValueError, KeyError):
        return None
    keys = [int(c["name"]) for c in (facets[0]["counts"] if facets else [])]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys))
    return set(keys)


def niche_features(raw: np.ndarray) -> np.ndarray:
    """Rows of ENV_VARS values -> niche feature space (rainfall and carbon log-scaled)."""
    x = np.asarray(raw, dtype=float).copy()
    for v in LOG_VARS:
        i = ENV_VARS.index(v)
        x[:, i] = np.log1p(np.clip(x[:, i], 0, None))
    return x


@lru_cache(maxsize=4)
def load_niches(path: Path) -> dict | None:
    if not path.exists():
        return None
    table = json.loads(path.read_text(encoding="utf-8"))
    if "points_file" not in table or not path.with_name(table["points_file"]).exists():
        return None  # table from an older builder version: rebuild with training/build_species_niches.py
    arrays = np.load(path.with_name(table["points_file"]))
    if "ref_z" not in arrays:
        return None
    table["_pts"] = arrays["points"]
    table["_pts_taxon"] = np.repeat(np.arange(len(table["taxa"])), [t["points_count"] for t in table["taxa"]])
    table["_ref_z"], table["_ref_taxon"], table["_ref_hab"] = arrays["ref_z"], arrays["ref_taxon"], arrays["ref_hab"]
    return table


def habitat_shares(worldcover_classes: np.ndarray) -> dict[str, float] | None:
    """Share of the boundary in each habitat group, from ESA WorldCover class codes."""
    v = worldcover_classes[np.isfinite(worldcover_classes)].astype(int)
    if not v.size:
        return None
    return {g: float(np.isin(v, codes).mean()) for g, codes in HABITAT_GROUPS.items()}


def site_vector(env: dict, table: dict) -> np.ndarray:
    raw = np.array([[env[v] for v in table["variables"]]], dtype=float)
    return ((niche_features(raw) - table["scaler"]["mean"]) / table["scaler"]["std"])[0]


def _nearest_shares(points: np.ndarray, labels: np.ndarray, n_labels: int, z: np.ndarray, k: int,
                    weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Each label's share of the k records nearest to z (Gaussian kernel, bandwidth = median distance)."""
    d = np.sqrt(((points - z) ** 2).sum(axis=1))
    k = min(k, len(d))
    idx = np.argpartition(d, k - 1)[:k]
    w = np.exp(-0.5 * (d[idx] / max(float(np.median(d[idx])), 1e-3)) ** 2)
    if weights is not None:
        w = w * weights[idx]
    shares = np.bincount(labels[idx], weights=w, minlength=n_labels)
    counts = np.bincount(labels[idx], minlength=n_labels)
    return shares / max(shares.sum(), 1e-12), counts


def canonical(name: str) -> str:
    """'Acer rubrum L.' -> 'Acer rubrum'; 'Magnolia sp.' -> 'Magnolia'."""
    words = re.findall(r"[A-Za-z-]+", name or "")
    if len(words) >= 2 and words[1].islower() and words[1] not in ("sp", "spp", "L"):
        return f"{words[0]} {words[1]}"
    return words[0] if words else ""


def _built(t: dict) -> float | None:
    return t["habitat"]["built"] if t.get("habitat") else None


def planted_discount(taxa: list[dict], site_built: float, base_built: float) -> np.ndarray:
    """Species recorded mostly in towns are planted or ornamental; many of their 'forest' records are leafy gardens.
    At a natural site scale each species by its odds of being recorded outside built-up land, relative to an
    average species; at a town site (site_built -> 1) leave it alone."""
    def odds(b: float) -> float:
        b = min(max(b, 0.02), 0.98)
        return (1 - b) / b

    natural = np.array([np.clip(odds(b) / odds(base_built), 0.1, 5.0) if b is not None else 1.0
                        for b in map(_built, taxa)])
    return (1 - site_built) * natural + site_built


def score_species(env: dict, table: dict, in_india: bool, local_keys: set[int] | None = None,
                  site_habitat: dict[str, float] | None = None) -> list[dict]:
    """Each tree species' share of the records from places most like this site, best first."""
    z = site_vector(env, table)
    taxa = table["taxa"]
    if in_india:
        hw = None
        if site_habitat:
            base, eps = table["habitat_baseline"], 0.02
            ratio = np.array([(site_habitat[g] + eps) / (base[g] + eps) for g in table["habitat_groups"]])
            hw = ratio[table["_ref_hab"]]
        shares, counts = _nearest_shares(table["_ref_z"], table["_ref_taxon"], len(taxa), z, REF_K, hw)
    else:
        shares, counts = _nearest_shares(table["_pts"], table["_pts_taxon"], len(taxa), z, NICHE_K)
    if in_india and site_habitat:
        shares = shares * planted_discount(taxa, site_habitat["built"], table["habitat_baseline"]["built"])
    recorded = np.array([bool(local_keys and t["key"] in local_keys) for t in taxa])
    shares = shares * np.where(recorded, LOCAL_BOOST, 1.0)
    shares = 100 * shares / max(shares.sum(), 1e-12)
    out = [{"key": t["key"], "name": t["name"], "rank": t["rank"], "family": t.get("family"),
            "english_name": t.get("english_name"), "local_name": LOCAL_NAMES.get(t["name"]),
            "share_pct": round(float(shares[i]), 1), "similar_site_records": int(counts[i]),
            "recorded_nearby": bool(recorded[i]), "often_planted": (_built(t) or 0) >= PLANTED_BUILT_SHARE}
           for i, t in enumerate(taxa) if shares[i] >= MIN_SHARE_PCT]
    return sorted(out, key=lambda s: -s["share_pct"])


def prior_for_classes(env: dict, table: dict, classes: list[str], scientific_names: dict[str, str],
                      scored: list[dict] | None = None, in_india: bool = False) -> np.ndarray | None:
    """Prior over a species model's classes. In India it comes from the site's reference-record shares;
    otherwise from the nearest worldwide records of the model's own species. Unplaceable classes are neutral."""
    idx_of = {t["name"]: i for i, t in enumerate(table["taxa"])}
    mapped = {c: idx_of.get(canonical(scientific_names[c])) for c in classes if c in scientific_names}
    mapped = {c: i for c, i in mapped.items() if i is not None}
    if len(mapped) < 2:
        return None
    if in_india and scored:
        share = {s["name"]: s["share_pct"] for s in scored}
        w = {c: share.get(table["taxa"][i]["name"], 0.0) for c, i in mapped.items()}
    else:
        sel = np.isin(table["_pts_taxon"], list(mapped.values()))
        remap = {i: j for j, i in enumerate(mapped.values())}
        labels = np.array([remap[i] for i in table["_pts_taxon"][sel]])
        shares, _ = _nearest_shares(table["_pts"][sel], labels, len(mapped), site_vector(env, table), NICHE_K)
        w = {c: float(shares[remap[i]]) for c, i in mapped.items()}
    total = sum(w.values())
    if total <= 0:
        return None
    known = len(mapped) / len(classes)
    prior = np.array([w[c] / total * known if c in w else 1.0 / len(classes) for c in classes])
    return prior / prior.sum()


PRESENCE_MIN_SHARE = 0.02


def presence_gate(prior: np.ndarray, min_share: float = PRESENCE_MIN_SHARE) -> np.ndarray:
    """1 for species that can occur at the site, 0 otherwise. Record shares say where species are seen, not how
    common they are, so only presence is used to correct labels (IDTReeS: presence gate 41 -> 42 % accuracy;
    share-weighted prior 41 -> 40 %)."""
    return np.where(prior >= min_share, 1.0, 0.0)


def adjust_probabilities(p: np.ndarray, prior: np.ndarray, tau: float = 0.5, floor: float = 0.02) -> np.ndarray:
    """p' ∝ p · prior^tau. The model is class-balanced (uniform training prior), so this is Bayes' rule,
    tempered (tau < 1) so the site prior refines rather than overrules the image; the floor keeps rare
    species from being pushed to zero."""
    q = p * np.maximum(prior, floor)[None, :] ** tau
    return q / q.sum(axis=1, keepdims=True)
