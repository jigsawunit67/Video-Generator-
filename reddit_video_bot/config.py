from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | os.PathLike | None = None) -> dict[str, Any]:
    if load_dotenv:
        load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg


def resolve(path: str) -> Path:
    """Relative Pfade aus der Config relativ zum Projekt-Root auflösen."""
    p = Path(path)
    return p if p.is_absolute() else ROOT / p
