"""Filesystem resource resolution for schemas, specs, and configuration.

Schemas and shipped example specs live inside the package so they travel with
it. Owner-editable configuration lives in the repository ``config/`` directory,
resolved by walking up from this file to the project root.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMAS_DIR = PACKAGE_DIR / "schemas"
AGENT_SPECS_DIR = PACKAGE_DIR / "specs" / "agents"
WORKFLOW_SPECS_DIR = PACKAGE_DIR / "specs" / "workflows"


def repo_root(start: Optional[Path] = None) -> Path:
    """Return the project root (the directory containing ``pyproject.toml``)."""
    here = (start or PACKAGE_DIR).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    # Fall back to the directory above ``src/``.
    return PACKAGE_DIR.parents[1]


def config_dir() -> Path:
    return repo_root() / "config"


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    """Load a JSON schema by bare name (``agent_spec``) or filename."""
    path = SCHEMAS_DIR / name
    if not path.suffix:
        path = SCHEMAS_DIR / f"{name}.schema.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)
