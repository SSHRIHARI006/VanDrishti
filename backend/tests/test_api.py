import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from vandrishti import config, jobs

    settings = config.Settings(data_dir=tmp_path)
    monkeypatch.setattr(config, "settings", settings)
    monkeypatch.setattr(jobs, "settings", settings)
    from vandrishti import api

    monkeypatch.setattr(api, "settings", settings)
    return TestClient(api.app)


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_rejects_unsupported_upload(client):
    r = client.post("/api/jobs", files={"file": ("payload.exe", b"MZ")})
    assert r.status_code == 400


def test_unknown_job_and_unsafe_names(client):
    assert client.get("/api/jobs/not-a-job").status_code == 404
    assert client.get("/api/jobs/abcdefabcdef/files/job.json").status_code == 404
    assert client.post("/api/jobs/from-sample/..%2F.env").status_code in (404, 405)
    assert client.post("/api/jobs/from-survey-sample/..%2F..").status_code in (404, 405)


def test_only_registered_outputs_are_served(client, tmp_path):
    from vandrishti.jobs import Job

    job = Job.create("t", "satellite", [{"id": "aoi", "name": "a"}], {})
    (job.dir / "trees.geojson").write_text("{}")
    (job.dir / "secret.txt").write_text("x")
    job.set_layer("trees", "trees.geojson", "Trees")
    assert client.get(f"/api/jobs/{job.id}/files/trees.geojson").status_code == 200
    assert client.get(f"/api/jobs/{job.id}/files/secret.txt").status_code == 404
    assert client.get(f"/api/jobs/{job.id}/files/job.json").status_code == 404


def test_survey_upload_validation(client):
    kml = ("b.kml", b"<kml/>")
    r = client.post("/api/jobs/survey", files={"boundary": kml, "ortho": ("ortho.jpg", b"x")})
    assert r.status_code == 400
    r = client.post("/api/jobs/survey", files={"boundary": ("b.exe", b"x"), "ortho": ("o.tif", b"x")})
    assert r.status_code == 400
    r = client.post("/api/jobs/survey", files={"boundary": kml})
    assert r.status_code == 422  # orthophoto is required
