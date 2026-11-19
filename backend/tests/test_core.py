import io
import json
import zipfile

import numpy as np
import pytest

from vandrishti.aoi import AOIError, load_aoi
from vandrishti.processing.density import density_grid, fsi_class
from vandrishti.processing.trees import SURVEY_PARAMS, detect_trees

SQUARE_KML = b"""<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Test block</name>
<Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>
79.30,20.00,0 79.31,20.00,0 79.31,20.01,0 79.30,20.01,0 79.30,20.00,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>"""


def kmz(payload: bytes, name: str = "doc.kml") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, payload)
    return buf.getvalue()


def test_kml_parsed_with_area_and_utm():
    aoi = load_aoi("block.kml", SQUARE_KML, 10, 5)
    assert aoi.name == "Test block"
    assert aoi.utm_epsg == 32644
    assert 1.1 < aoi.area_km2 < 1.25  # ~1.05 km x 1.11 km


def test_kmz_and_geojson_equivalent():
    a = load_aoi("b.kmz", kmz(SQUARE_KML), 10, 5)
    gj = {"type": "Feature", "properties": {"name": "g"}, "geometry": {"type": "Polygon", "coordinates": [
        [[79.30, 20.00], [79.31, 20.00], [79.31, 20.01], [79.30, 20.01], [79.30, 20.00]]]}}
    b = load_aoi("b.geojson", json.dumps(gj).encode(), 10, 5)
    assert abs(a.area_km2 - b.area_km2) < 1e-6


@pytest.mark.parametrize("filename,data,msg", [
    ("x.kml", b"<kml><Point><coordinates>79,20</coordinates></Point></kml>", "No polygon"),
    ("x.kml", b"not xml", "Could not read KML"),
    ("x.kmz", b"not a zip", "not a valid zip"),
    ("x.kmz", kmz(b"<kml/>", "readme.txt"), "does not contain a .kml"),
    ("x.shp", b"", "Unsupported file type"),
])
def test_bad_inputs_rejected(filename, data, msg):
    with pytest.raises(AOIError, match=msg):
        load_aoi(filename, data, 10, 5)


def test_xml_entity_attack_blocked():
    evil = b"""<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<kml><Placemark><name>&x;</name></Placemark></kml>"""
    with pytest.raises(AOIError):
        load_aoi("evil.kml", evil, 10, 5)


def test_area_limits():
    big = SQUARE_KML.replace(b"79.31", b"79.40").replace(b"20.01", b"20.10")
    with pytest.raises(AOIError, match="above the"):
        load_aoi("big.kml", big, 10, 5)
    assert load_aoi("big.kml", big, 200, 5).warnings  # allowed, but warned


def synthetic_forest(n_side=4, spacing=12.0, res=0.5):
    """Grid of cone-shaped trees of known count on a 0.5 m raster."""
    size = int(n_side * spacing / res)
    yy, xx = np.mgrid[0:size, 0:size] * res
    chm = np.zeros((size, size), np.float32)
    for i in range(n_side):
        for j in range(n_side):
            cx, cy = (i + 0.5) * spacing, (j + 0.5) * spacing
            h = 12 + (i + j) % 3 * 3
            cone = h - 2.2 * np.hypot(xx - cx, yy - cy)
            chm = np.maximum(chm, cone)
    return np.clip(chm, 0, None), res


def test_detects_known_number_of_trees():
    chm, res = synthetic_forest()
    out = detect_trees(chm, res, np.ones(chm.shape, bool), SURVEY_PARAMS)
    assert out["count"] == 16
    assert set(np.round(out["height_m"]).astype(int)) <= {12, 15, 18}
    assert (out["crown_area_m2"] > 10).all()


def test_no_trees_on_bare_ground():
    out = detect_trees(np.zeros((50, 50), np.float32), 1.0, np.ones((50, 50), bool), SURVEY_PARAMS)
    assert out["count"] == 0


def test_fsi_classes_and_density_grid():
    assert [fsi_class(v) for v in (85, 55, 20, 5)] == ["VDF", "MDF", "OF", "NF"]
    chm = np.zeros((50, 50), np.float32)
    chm[:25, :] = 10  # top half canopy
    d = density_grid(chm, 1.0, np.ones(chm.shape, bool), np.array([5]), np.array([5]), np.array([10.0]), 25, 5)
    covers = sorted(c["canopy_cover_pct"] for c in d["cells"])
    assert covers == [0.0, 0.0, 100.0, 100.0]
    assert sum(c["detected_trees"] for c in d["cells"]) == 1


def _niche_table():
    from vandrishti.sources.gee import ENV_VARS

    k = len(ENV_VARS)
    rng = np.random.default_rng(0)
    groups = ["forest", "shrub_grass", "cropland", "built", "other"]
    # teak: records near the site climate, mostly in forest; duranta: same climate, mostly in towns;
    # acer: a far-away climate
    centres = [np.zeros(k), np.zeros(k), np.full(k, 4.0)]
    habs = [0, 3, 0]
    ref_z = np.vstack([c + 0.2 * rng.standard_normal((60, k)) for c in centres])
    ref_taxon = np.repeat(np.arange(3), 60)
    ref_hab = np.repeat(habs, 60)
    table = {"variables": ENV_VARS, "scaler": {"mean": np.zeros(k), "std": np.ones(k)},
             "habitat_groups": groups,
             "habitat_baseline": {"forest": 0.5, "shrub_grass": 0.1, "cropland": 0.1, "built": 0.25, "other": 0.05},
             "taxa": [{"key": i, "name": n, "rank": "SPECIES"} for i, n in
                      enumerate(["Tectona grandis", "Duranta erecta", "Acer rubrum"])],
             "_ref_z": ref_z, "_ref_taxon": ref_taxon, "_ref_hab": ref_hab,
             "_pts": ref_z, "_pts_taxon": ref_taxon}
    return table, dict.fromkeys(ENV_VARS, 0.0)


def test_site_prior_uses_climate_and_habitat(monkeypatch):
    from vandrishti.processing import site_prior

    table, env = _niche_table()
    monkeypatch.setattr(site_prior, "niche_features", lambda raw: np.asarray(raw, float))
    monkeypatch.setattr(site_prior, "REF_K", 100)
    forest_site = {"forest": 0.9, "shrub_grass": 0.05, "cropland": 0.05, "built": 0.0, "other": 0.0}
    scored = site_prior.score_species(env, table, in_india=True, site_habitat=forest_site)
    assert scored[0]["name"] == "Tectona grandis"
    assert "Acer rubrum" not in [s["name"] for s in scored]  # far climate: none of its records are near
    town_site = {"forest": 0.0, "shrub_grass": 0.0, "cropland": 0.1, "built": 0.9, "other": 0.0}
    assert site_prior.score_species(env, table, True, site_habitat=town_site)[0]["name"] == "Duranta erecta"
    prior = site_prior.prior_for_classes(env, table, ["TEGR", "ACRU", "Other"],
                                         {"TEGR": "Tectona grandis L.f.", "ACRU": "Acer rubrum L."})
    assert prior[0] > prior[1] and abs(prior.sum() - 1) < 1e-9 and abs(prior[2] - 1 / 3) < 1e-9


def test_prior_adjustment_is_normalised_and_floored():
    from vandrishti.processing.site_prior import adjust_probabilities

    p = np.array([[0.6, 0.3, 0.1], [0.2, 0.2, 0.6]])
    q = adjust_probabilities(p, np.array([0.0, 0.5, 0.5]))
    assert np.allclose(q.sum(axis=1), 1)
    assert (q[:, 0] > 0).all()  # floor keeps a zero-prior species possible


def test_presence_gate():
    from vandrishti.processing.site_prior import adjust_probabilities, presence_gate

    gate = presence_gate(np.array([0.5, 0.001, 0.3]))
    assert gate.tolist() == [1.0, 0.0, 1.0]
    q = adjust_probabilities(np.array([[0.3, 0.6, 0.1]]), gate, tau=1.0)
    assert q.argmax() == 0 and q[0, 1] > 0  # the unlikely species is down-weighted, not removed


def test_leaf_fall_separates_evergreen_from_deciduous():
    from vandrishti.processing import vegetation as veg

    on = np.array([[0.8, 0.8, 0.8, 0.2]], np.float32)
    dry = np.array([[0.75, 0.55, 0.3, 0.1]], np.float32)
    drop = veg.leaf_fall(on, dry)
    assert np.isnan(drop[0, 3])  # not vegetated in the leaf-on season
    assert veg.leaf_habit_classes(np.nan_to_num(drop, nan=-1.0)).tolist() == [[1, 2, 3, 0]]
    summary = veg.leaf_fall_summary(drop, np.ones(on.shape, bool))
    assert summary["class_pct"] == {"evergreen": 33.3, "semi_deciduous": 33.3, "deciduous": 33.3}
    assert summary["tree_area_pct"] == 75.0


def test_sign_in_and_admin_user_management(tmp_path, monkeypatch):
    import importlib

    from fastapi.testclient import TestClient

    monkeypatch.setenv("VANDRISHTI_ADMIN_PASSWORD", "admin-secret-1")
    from vandrishti import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "_path", lambda: tmp_path / "users.json")
    from vandrishti import api
    importlib.reload(api)
    try:
        c = TestClient(api.app)
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/jobs").status_code == 401
        assert c.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
        admin = {"Authorization": "Bearer " + c.post(
            "/api/auth/login", json={"username": "admin", "password": "admin-secret-1"}).json()["token"]}
        assert c.get("/api/jobs", headers=admin).status_code == 200
        assert c.post("/api/auth/users", headers=admin, json={"username": "ravi", "password": "short"}).status_code == 400
        assert c.post("/api/auth/users", headers=admin,
                      json={"username": "ravi", "password": "forest-walk-9"}).status_code == 200
        assert "forest-walk-9" not in (tmp_path / "users.json").read_text()
        user = {"Authorization": "Bearer " + c.post(
            "/api/auth/login", json={"username": "ravi", "password": "forest-walk-9"}).json()["token"]}
        assert c.get("/api/jobs", headers=user).status_code == 200
        assert c.get("/api/auth/users", headers=user).status_code == 403
        assert c.post("/api/auth/users", headers=user, json={"username": "eve", "password": "12345678"}).status_code == 403
        assert c.delete("/api/auth/users/ravi", headers=admin).status_code == 200
        assert c.get("/api/jobs", headers=user).status_code == 401  # removed users lose access at once
        assert c.get("/api/jobs", headers={"Authorization": user["Authorization"] + "x"}).status_code == 401
    finally:
        monkeypatch.delenv("VANDRISHTI_ADMIN_PASSWORD")
        importlib.reload(auth)
        importlib.reload(api)
