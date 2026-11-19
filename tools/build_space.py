"""Assemble the Hugging Face Space folder (deploy/space/build) from the repo.

Usage:  python tools/build_space.py [job_id ...]
Build the frontend first (cd frontend && npm run build). The listed finished jobs are bundled as sample runs.
Upload the folder with:
    hf upload <user>/<space> deploy/space/build . --repo-type space
"""

from __future__ import annotations

import shutil
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deploy" / "space" / "build"
SEED_JOBS = sys.argv[1:] or ["28c7761ac343", "f5186ceaffd3"]
# gradio, spaces and torch are provided by the Space runtime; the rest are test-only.
SKIP = {"pytest", "httpx"}
# Pinned so the pickled species models load; everything else keeps the backend's minimum versions.
PINNED = ["scikit-learn", "deepforest"]
EXTRA = ["pandas", "torchvision"]


def requirements() -> str:
    out = []
    for line in (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        name = line.split(">=")[0].split("[")[0]
        if line and name not in SKIP and name not in PINNED:
            out.append(line)
    out += [f"{name}=={version(name)}" for name in PINNED] + EXTRA
    return "\n".join(out) + "\n"


def main() -> None:
    dist = ROOT / "frontend" / "dist"
    if not (dist / "index.html").exists():
        sys.exit("frontend/dist is missing: run 'npm run build' in frontend/ first")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "lightning_logs", "tests")
    shutil.copytree(ROOT / "backend", OUT / "backend", ignore=ignore)
    shutil.copytree(dist, OUT / "frontend" / "dist")
    shutil.copytree(ROOT / "models", OUT / "models")
    shutil.copytree(ROOT / "samples", OUT / "samples")
    for job in SEED_JOBS:
        shutil.copytree(ROOT / "data" / "jobs" / job, OUT / "data" / "jobs" / job)
    for name in ("app.py", "README.md"):
        shutil.copy(ROOT / "deploy" / "space" / name, OUT / name)
    (OUT / "requirements.txt").write_text(requirements(), encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e6
    print(f"Space folder ready: {OUT}  ({size:.0f} MB)")


if __name__ == "__main__":
    main()
