"""Runtime settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    gee_project: str = os.environ.get("GEE_PROJECT", "")
    data_dir: Path = Path(os.environ.get("VANDRISHTI_DATA_DIR", REPO_ROOT / "data"))
    max_aoi_km2: float = float(os.environ.get("VANDRISHTI_MAX_AOI_KM2", "10"))
    warn_aoi_km2: float = float(os.environ.get("VANDRISHTI_WARN_AOI_KM2", "5"))
    max_upload_mb: int = int(os.environ.get("VANDRISHTI_MAX_UPLOAD_MB", "20"))
    max_survey_upload_mb: int = int(os.environ.get("VANDRISHTI_MAX_SURVEY_UPLOAD_MB", "2048"))
    cors_origins: list[str] = field(
        default_factory=lambda: os.environ.get(
            "VANDRISHTI_CORS_ORIGINS", "http://localhost:5173"
        ).split(",")
    )

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def models_dir(self) -> Path:
        return REPO_ROOT / "models"

    @property
    def samples_dir(self) -> Path:
        return REPO_ROOT / "samples"


settings = Settings()
