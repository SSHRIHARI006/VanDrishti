"""Hugging Face Space entry point: serves the Van-drishti AI API and web app through a Gradio server."""

import os
import sys
from pathlib import Path

try:
    import spaces  # must be imported before torch on ZeroGPU hardware
except ImportError:  # local runs
    spaces = None

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("VANDRISHTI_MAX_SURVEY_UPLOAD_MB", "200")
os.environ.setdefault("VANDRISHTI_DEEPFOREST_ACCELERATOR", "cpu")

from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from gradio import Server  # noqa: E402

from vandrishti.api import app as api_app  # noqa: E402

DIST = ROOT / "frontend" / "dist"

if spaces is not None:
    @spaces.GPU(duration=1)
    def _noop():  # ZeroGPU needs one decorated function; all processing runs on CPU
        pass

app = Server(title="Van-drishti AI")
api_routes = [r for r in api_app.router.routes if getattr(r, "path", "").startswith("/api/")]
if not any(r.path == "/api/auth/login" for r in api_routes) or not any(r.path == "/api/jobs" for r in api_routes):
    raise RuntimeError("API routes were not picked up from vandrishti.api")
app.router.routes.extend(api_routes)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(DIST / "index.html")


@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(DIST / "favicon.svg")


for sub in ("assets", "maplibre"):
    app.mount(f"/{sub}", StaticFiles(directory=DIST / sub), name=sub)

demo = app
if __name__ == "__main__":
    demo.launch(ssr_mode=False)
