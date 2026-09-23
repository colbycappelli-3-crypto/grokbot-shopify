"""Schema validation helpers shared across the package."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

import yaml
from jsonschema import Draft202012Validator

from .resources import load_schema


class SpecValidationError(ValueError):
    """Raised when an instance fails schema validation, with all errors."""

    def __init__(self, source: str, errors: List[str]):
        self.source = source
        self.errors = errors
        super().__init__(f"{source}: " + "; ".join(errors))


def validate(instance: Any, schema_name: str, *, source: str = "<instance>") -> None:
    schema = load_schema(schema_name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        messages = [
            f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
            for err in errors
        ]
        raise SpecValidationError(source, messages)


def load_yaml(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_and_validate(path: Path, schema_name: str) -> Any:
    data = load_yaml(path)
    validate(data, schema_name, source=str(path))
    return data


def iter_spec_files(directory: Path) -> List[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*.y*ml") if p.is_file())
