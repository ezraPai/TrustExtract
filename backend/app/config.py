"""Centralized filesystem configuration for the backend."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(environment_name: str, default: Path) -> Path:
    """Use an environment override when supplied, otherwise a project path."""

    value = os.getenv(environment_name)
    return Path(value).expanduser().resolve() if value else default.resolve()


DATABASE_PATH = project_path("TRUSTEXTRACT_DATABASE_PATH", PROJECT_ROOT / "data" / "trustextract.db")
UPLOADS_DIR = project_path("TRUSTEXTRACT_UPLOADS_DIR", PROJECT_ROOT / "data" / "uploads")
OCR_CACHE_DIR = project_path("TRUSTEXTRACT_OCR_CACHE_DIR", PROJECT_ROOT / "artifacts" / "ocr")
POLICY_FILE = project_path(
    "TRUSTEXTRACT_POLICY_FILE",
    PROJECT_ROOT / "artifacts" / "phase6_calibrated_policy.json",
)

