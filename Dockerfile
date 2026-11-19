# syntax=docker/dockerfile:1
# Van-drishti AI — single image that serves the FastAPI backend and the built dashboard
# (backend/vandrishti/api.py mounts frontend/dist at "/").

# ---------- 1. build the React dashboard ----------
FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. python runtime ----------
# Bookworm (not the newest slim tag) keeps the glibc/system libraries aligned with the geospatial wheels.
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    VANDRISHTI_DATA_DIR=/app/data

# libgomp1 is needed by scikit-learn / numpy wheels, libexpat1 by the bundled GDAL inside the rasterio
# wheel; curl is handy for troubleshooting.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libexpat1 curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so the layer is cached across source edits.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

# Drone survey mode only. The CPU torch index keeps the image ~1 GB smaller than the CUDA wheels.
ARG INSTALL_DEEPFOREST=1
RUN if [ "$INSTALL_DEEPFOREST" = "1" ]; then \
      pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
      && pip install deepforest==2.1.0 ; \
    fi

COPY backend/ backend/
COPY --from=frontend /src/frontend/dist frontend/dist
COPY models/ models/
COPY samples/ samples/

# Non-root runtime user; the data dir and the model caches must be writable.
# lightning_logs is needed because DeepForest's predict_tile() starts a PyTorch-Lightning trainer
# that writes its logs relative to the working directory (/app).
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /app/data /app/lightning_logs /home/app/.cache \
 && chown -R app:app /app/data /app/lightning_logs /home/app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

# One worker on purpose: jobs run in an in-process ThreadPoolExecutor and job state lives on disk.
CMD ["uvicorn", "vandrishti.api:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
