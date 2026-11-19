# Deploying Van-drishti AI on a VPS

The whole app runs as two containers:

| Container | Role |
|---|---|
| `app` | FastAPI backend + the built React dashboard on port 8000 (internal only) |
| `caddy` | TLS termination, gzip, 2 GB upload limit, reverse proxy on 80/443 |

State that must survive restarts lives in the named volume `vandrishti_data`
(`/app/data` in the container: `jobs/`, `cache/`, `users.json`).

## 1. Server prerequisites

- Linux VPS (Ubuntu 22.04/24.04 or Debian 12), **2 vCPU / 4 GB RAM / 40 GB disk** minimum.
  Drone survey mode (DeepForest + PyTorch) is CPU-only and peaks around 2 GB RAM per job.
  Add disk if you run many blocks: cached rasters in `data/cache/` are the bulk of the growth.
- Inbound ports **80** and **443** open in the firewall/security group.
- Docker Engine 24+ with the Compose v2 plugin (`docker compose version` should print v2.24 or newer,
  which is needed for the optional `env_file`).

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # then log out and back in
```

## 2. Get the code and configure it

```bash
git clone <this-repo> vandrishti && cd vandrishti
cp .env.example .env
```

Edit `.env` — the values that matter on a server:

| Variable | Why |
|---|---|
| `GEE_PROJECT` | Google Cloud project registered for Earth Engine. Required, or every satellite job fails at stage 2. |
| `GEE_SERVICE_ACCOUNT_KEY` | The service-account JSON key on **one line**. There is no browser to run `earthengine authenticate`. |
| `VANDRISHTI_ADMIN_PASSWORD` | Turns sign-in on. Without it anyone who finds the URL can create jobs and read results. |
| `VANDRISHTI_SECRET_KEY` | Any long random string. Keeps sessions valid across restarts; otherwise every restart logs everyone out. |
| `SITE_ADDRESS` | Your domain (e.g. `vandrishti.example.org`) for automatic HTTPS. Omit to test on `http://<ip>` first. |
| `INSTALL_DEEPFOREST` | `1` (default) builds drone survey support. Set `0` for a much smaller, faster image if you only need satellite mode. |

### Earth Engine service account

1. In the Google Cloud console: create a service account in the project you set as `GEE_PROJECT`.
2. Create a JSON key for it and download the file.
3. Register the service-account email for Earth Engine (Earth Engine console → *Register a project*, or
   `earthengine authenticate` on a workstation and use the same project).
4. Make the key a single line and paste it into `.env`:

```bash
jq -c . ~/Downloads/vandrishti-gee.json
# {"type":"service_account","project_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...","client_email":"..."}
```

```dotenv
GEE_SERVICE_ACCOUNT_KEY={"type":"service_account",...}
```

The key file is git-ignored by pattern (`*-service-account*.json`) — never commit it. `.env` itself is
git-ignored too, but keep it `chmod 600`.

## 3. Start it

```bash
docker compose up -d --build
docker compose ps            # app should become "healthy"
docker compose logs -f app   # watch the first start
```

First build takes a while (frontend build + Python wheels + torch/DeepForest). Later builds reuse the
dependency layers.

Once `app` is healthy, open `http://<server-ip>/` — you should get the sign-in screen (if
`VANDRISHTI_ADMIN_PASSWORD` is set) and `/api/health` should return
`{"status":"ok","gee_project_configured":true}`.

Smoke test a real satellite run from the UI: *New assessment → sample boundary*
(`chandrapur_forest_block_a.kml`). If the canopy-height stage fails, the service-account key or the project
registration is the usual cause — `docker compose logs app` shows the `GEEError` text.

## 4. Turn on HTTPS

1. Point an `A` (and `AAAA`, if you have IPv6) record at the VPS IP.
2. Set the domain and restart the proxy:

```bash
sed -i 's/^# SITE_ADDRESS=.*/SITE_ADDRESS=vandrishti.example.org/' .env
grep SITE_ADDRESS .env
docker compose up -d caddy
docker compose logs -f caddy   # waiting for certificate / certificate obtained
```

Caddy obtains and renews the certificate automatically; certificates live in the `caddy_data` volume, so
they survive restarts. Port 80 must stay open for the ACME challenge.

## 5. Optional: drone survey species models

Species classification only runs when a trained model's bbox covers the site. Bundles are git-ignored, so
copy them to the server:

```bash
scp models/species/*.joblib you@server:/srv/vandrishti/models/species/
docker compose restart app
```

Mount them at build time instead if you prefer a self-contained image (uncomment nothing — just copy the
files into `models/species/` **before** `docker compose build`; `.dockerignore` excludes `*.joblib`, so for
baked-in models remove that line). Without a model, survey jobs still run and label every tree `Unknown`.

Species bundles are pickled scikit-learn objects: the image installs `scikit-learn>=1.5`, so a model trained
with a much newer sklearn may fail to unpickle. If it does, rebuild with the matching version.

## 6. Operations

```bash
docker compose logs -f app                  # application + pipeline events
docker compose exec app ls data/jobs       # job folders (job.json, events.jsonl, outputs)
docker compose restart app                 # queued/running jobs are marked failed on restart (by design)
docker compose pull && docker compose up -d --build   # after a git pull, to redeploy
```

**Backups** — everything persistent is in two volumes:

```bash
docker run --rm -v vandrishti_vandrishti_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/vandrishti-data-$(date +%F).tar.gz -C /data .
# restore: same command with `tar xzf`, into a stack that is stopped
```

**Disk growth** — `data/cache/` keeps downloaded rasters per AOI with no eviction, and jobs are kept
forever. Prune deliberately:

```bash
# old finished jobs (dry run first)
docker compose exec app find data/jobs -maxdepth 1 -mindepth 1 -type d -mtime +30
docker compose exec app find data/jobs -maxdepth 1 -mindepth 1 -type d -mtime +30 -exec rm -rf {} +
# cached rasters for areas you no longer assess
docker compose exec app du -sh data/cache && docker compose exec app rm -rf data/cache/*
```

**Resource limits** — a single small VPS can be constrained by adding to the `app` service:

```yaml
    deploy:
      resources:
        limits:
          memory: 3g
```

## 7. Scaling notes and limits

- **Run exactly one `app` replica.** Jobs execute in an in-process `ThreadPoolExecutor(max_workers=2)` and
  progress is written to local files; a second replica would ignore the first one's jobs, and `users.json`
  would diverge. To handle more load, raise the box size, not the replica count.
- **No queue service or cancellation.** A restart marks in-flight jobs failed (`JOB_INTERRUPTED`).
- **Two concurrent jobs** per instance; extra submissions queue in the executor.
- **Uploads**: boundaries 20 MB, survey rasters 200 MB each (`VANDRISHTI_MAX_SURVEY_UPLOAD_MB` to change).
  Caddy allows up to 2 GB per request — raise both if you lift the app limits.
- **Auth without a hosted user store**: users added in the app are saved to `data/users.json` in the volume.
  Leave `VANDRISHTI_USERS_REPO`/`VANDRISHTI_USERS_TOKEN` empty unless you also want the Hugging Face dataset
  mirror.
- **Everything is HTTP behind Caddy.** Do not publish port 8000 directly to the internet.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `gee_project_configured: false` in `/api/health` | `GEE_PROJECT` missing from `.env`, or the container was not recreated after editing it (`docker compose up -d`). |
| Satellite job fails at *Canopy height* | Bad/expired service-account key, project not registered for Earth Engine, or the service account lacks Earth Engine access. Check `docker compose logs app`. |
| Survey job says `ORTHO_MISSING` / `SURVEY_FILE_INVALID` | The orthophoto must be a georeferenced GeoTIFF with ≥3 bands and ≤1 m resolution. |
| Survey trees all `Unknown` | No species model covers the site — expected outside the trained region. |
| `413` on upload | Request bigger than the Caddy `max_size`, or above `VANDRISHTI_MAX_SURVEY_UPLOAD_MB`. |
| Caddy loops on certificates | DNS not pointing at the VPS yet, or port 80 blocked. |
| App container restarts repeatedly | Check `docker compose logs app`; the healthcheck only fails if the API stops answering `/api/health`. |
