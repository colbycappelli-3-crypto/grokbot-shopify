"""Load owner-editable validation gate defaults."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..resources import config_dir
from ..validation import load_and_validate

GATES_FILENAME = "validation_gates.yaml"


def load_validation_gates(path: Optional[Path] = None) -> dict:
    path = Path(path) if path else config_dir() / GATES_FILENAME
    return load_and_validate(path, "validation_gates")
