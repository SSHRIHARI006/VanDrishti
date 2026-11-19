"""HTTP API: create assessments from a KML/KMZ, follow their progress, fetch results."""

from __future__ import annotations

import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from .config import REPO_ROOT, settings
from .jobs import Job, is_valid_job_id, list_jobs
from .pipeline import SATELLITE_STAGES, merged_options, run_satellite_job
from .pipeline_survey import SURVEY_FILES, SURVEY_STAGES, run_survey_job

AOI_EXTENSIONS = (".kml", ".kmz", ".geojson", ".json")
RASTER_EXTENSIONS = (".tif", ".tiff")
FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")

app = FastAPI(title="Vandrishti AI", version="0.1.0", dependencies=[Depends(auth.require_user)])
auth.register(app)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
executor = ThreadPoolExecutor(max_workers=2)


@app.on_event("startup")
def recover_interrupted_jobs() -> None:
    for j in list_jobs():
        if j["status"] in ("queued", "running"):
            job = Job.load(j["id"])
            job.event("error", "JOB_INTERRUPTED", "The server restarted while this assessment was running",
                      action="Start the assessment again")
            job.set_status("failed")


def _load(job_id: str) -> Job:
    if not is_valid_job_id(job_id):
        raise HTTPException(404, "Assessment not found")
    try:
        return Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Assessment not found") from None


def _start(filename: str, data: bytes, name: str | None, options: dict) -> dict:
    job = Job.create(name or filename.rsplit(".", 1)[0], "satellite", SATELLITE_STAGES, merged_options(options))
    job.update("auto_name", not name)
    (job.dir / "input").mkdir(exist_ok=True)
    (job.dir / "input" / Path(filename).name).write_bytes(data)
    executor.submit(run_satellite_job, job, filename, data)
    return {"id": job.id}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "gee_project_configured": bool(settings.gee_project)}


@app.get("/api/samples")
def samples() -> list[dict]:
    if not settings.samples_dir.exists():
        return []
    return [
        {"filename": p.name, "name": p.stem.replace("_", " ").title()}
        for p in sorted(settings.samples_dir.iterdir())
        if p.suffix.lower() in AOI_EXTENSIONS
    ]


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    options: str | None = Form(None),
) -> dict:
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(AOI_EXTENSIONS):
        raise HTTPException(400, "Upload a .kml, .kmz or .geojson boundary file")
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB")
    return _start(filename, data, name, _parse_options(options))


@app.post("/api/jobs/from-sample/{filename}")
def create_job_from_sample(filename: str) -> dict:
    if not FILENAME_RE.fullmatch(filename):
        raise HTTPException(404, "Sample not found")
    path = settings.samples_dir / filename
    if not path.is_file() or path.suffix.lower() not in AOI_EXTENSIONS:
        raise HTTPException(404, "Sample not found")
    return _start(filename, path.read_bytes(), None, {})


async def _save_upload(upload: UploadFile, dest: Path, limit_mb: int) -> None:
    limit, size = limit_mb * 1024 * 1024, 0
    with dest.open("wb") as f:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, f"{upload.filename} is larger than {limit_mb} MB")
            f.write(chunk)


def _parse_options(options: str | None) -> dict:
    try:
        return json.loads(options) if options else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "options must be JSON") from None


@app.post("/api/jobs/survey")
async def create_survey_job(
    boundary: UploadFile = File(...),
    ortho: UploadFile = File(...),
    dsm: UploadFile | None = File(None),
    dtm: UploadFile | None = File(None),
    chm: UploadFile | None = File(None),
    name: str | None = Form(None),
    options: str | None = Form(None),
) -> dict:
    bname = Path(boundary.filename or "").name
    if not bname.lower().endswith(AOI_EXTENSIONS):
        raise HTTPException(400, "Upload a .kml, .kmz or .geojson boundary file")
    uploads = {k: u for k, u in zip(SURVEY_FILES, (ortho, dsm, dtm, chm)) if u is not None and u.filename}
    for kind, u in uploads.items():
        if not u.filename.lower().endswith(RASTER_EXTENSIONS):
            raise HTTPException(400, f"The {kind.upper()} must be a GeoTIFF (.tif)")
    bdata = await boundary.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(bdata) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Boundary file is larger than {settings.max_upload_mb} MB")

    job = Job.create(name or bname.rsplit(".", 1)[0], "survey", SURVEY_STAGES, merged_options(_parse_options(options)))
    job.update("auto_name", not name)
    inputs = job.dir / "input"
    inputs.mkdir(exist_ok=True)
    files = {}
    try:
        for kind, u in uploads.items():
            files[kind] = inputs / f"{kind}.tif"
            await _save_upload(u, files[kind], settings.max_survey_upload_mb)
    except HTTPException:
        shutil.rmtree(job.dir, ignore_errors=True)
        raise
    (inputs / bname).write_bytes(bdata)
    executor.submit(run_survey_job, job, bname, bdata, files)
    return {"id": job.id}


def _survey_samples() -> dict[str, Path]:
    root = settings.samples_dir / "survey"
    if not root.exists():
        return {}
    return {d.name: d for d in sorted(root.iterdir()) if (d / "sample.json").exists() and (d / "ortho.tif").exists()}


@app.get("/api/samples/survey")
def survey_samples() -> list[dict]:
    out = []
    for sid, d in _survey_samples().items():
        meta = json.loads((d / "sample.json").read_text(encoding="utf-8"))
        out.append({"id": sid, **meta, "inputs": [k for k in SURVEY_FILES if (d / f"{k}.tif").exists()]})
    return out


@app.post("/api/jobs/from-survey-sample/{sample_id}")
def create_job_from_survey_sample(sample_id: str) -> dict:
    d = _survey_samples().get(sample_id)
    if d is None:
        raise HTTPException(404, "Sample not found")
    kml = d / "boundary.kml"
    job = Job.create(sample_id, "survey", SURVEY_STAGES, merged_options({}))
    job.update("auto_name", True)
    inputs = job.dir / "input"
    inputs.mkdir(exist_ok=True)
    files = {}
    for kind in SURVEY_FILES:
        if (d / f"{kind}.tif").exists():
            files[kind] = inputs / f"{kind}.tif"
            shutil.copy(d / f"{kind}.tif", files[kind])
    executor.submit(run_survey_job, job, kml.name, kml.read_bytes(), files)
    return {"id": job.id}


@app.get("/api/jobs")
def jobs() -> list[dict]:
    return list_jobs()


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str) -> dict:
    job = _load(job_id)
    return {**job.state, "events": job.events()}


def _allowed_files(state: dict) -> set[str]:
    out = state["outputs"]
    names = {v["file"] for group in ("layers", "rasters", "exports") for v in out[group].values()}
    names |= {s["preview"] for s in state["stages"] if s.get("preview")}
    return names


@app.get("/api/jobs/{job_id}/files/{filename}")
def job_file(job_id: str, filename: str, download: bool = False):
    job = _load(job_id)
    if not FILENAME_RE.fullmatch(filename) or filename not in _allowed_files(job.state):
        raise HTTPException(404, "File not found")
    path = job.path(filename)
    if not path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=filename if download else None)


_dist = REPO_ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
