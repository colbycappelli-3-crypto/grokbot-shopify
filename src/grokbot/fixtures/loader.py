"""Load TEST/MOCK opportunity fixtures shipped with the package."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..resources import FIXTURES_DIR, RESEARCH_PACKETS_DIR
from ..validation import iter_spec_files, load_and_validate


class FixtureError(ValueError):
    pass


def load_fixture(name: str, directory: Optional[Path] = None) -> dict:
    directory = directory or FIXTURES_DIR
    path = Path(name)
    if not path.suffix:
        path = directory / f"{name}.yaml"
    elif not path.is_absolute():
        path = directory / path
    data = load_and_validate(path, "opportunity_fixture")
    blob = f"{data.get('banner', '')} {data.get('data_classification', '')}".upper()
    if "MOCK" not in blob and "TEST" not in blob:
        raise FixtureError(f"{path}: fixture must be explicitly marked TEST or MOCK.")
    return data


def load_all_fixtures(directory: Optional[Path] = None) -> List[dict]:
    directory = directory or FIXTURES_DIR
    return [load_fixture(path.name, directory) for path in iter_spec_files(directory)]


def load_research_packet(name: str, directory: Optional[Path] = None) -> dict:
    directory = directory or RESEARCH_PACKETS_DIR
    path = Path(name)
    if not path.suffix:
        path = directory / f"{name}.yaml"
    elif not path.is_absolute():
        path = directory / path
    data = load_and_validate(path, "research_packet")
    blob = f"{data.get('banner', '')} {data.get('data_classification', '')}".upper()
    if "MOCK" not in blob and "TEST" not in blob:
        raise FixtureError(f"{path}: research packet must be explicitly marked TEST or MOCK.")
    return data


def load_all_research_packets(directory: Optional[Path] = None) -> List[dict]:
    directory = directory or RESEARCH_PACKETS_DIR
    return [load_research_packet(path.name, directory) for path in iter_spec_files(directory)]
