"""Shared test helpers: a config writer and a one-call build runner."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from geotrustops.cli import main
from tests.fixtures.make_fixture import write_changelog, write_places

ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG = ROOT / "config" / "study_area.json"
RAW = ROOT / "data" / "raw"

# AOI used by synthetic tests: the real study AOI, so coordinates look familiar.
INSIDE = (28.18, -25.74)  # a point well inside the AOI
OUTSIDE = (28.30, -25.74)  # east of the AOI (east edge 28.205): outside the study area
METRES_PER_DEG_LAT = 6371000 * 3.141592653589793 / 180  # ~111,195 m on the haversine sphere


def write_config(path: Path, **overrides: Any) -> Path:
    cfg = json.loads(REAL_CONFIG.read_text(encoding="utf-8"))
    cfg.update(overrides)
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


@pytest.fixture
def build(tmp_path: Path) -> Callable[..., tuple[int, Path]]:
    """build(prev_places, curr_places, changelog=None, **config_overrides) -> (exit_code, out_dir)."""

    def _build(
        prev: list[dict], curr: list[dict], changelog: list[dict] | None = None, **cfg: Any
    ) -> tuple[int, Path]:
        cfg.setdefault("max_excluded_share", 1.0)  # most tests exclude rows on purpose
        args = [
            "build",
            "--config",
            str(write_config(tmp_path / "cfg.json", **cfg)),
            "--prev",
            str(write_places(tmp_path / "prev.parquet", prev)),
            "--curr",
            str(write_places(tmp_path / "curr.parquet", curr)),
            "--out",
            str(tmp_path / "out"),
            "--no-history",
        ]
        if changelog is not None:
            args += ["--changelog", str(write_changelog(tmp_path / "cl.parquet", changelog))]
        return main(args), tmp_path / "out"

    return _build


def summary(out: Path) -> dict:
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


def features(out: Path) -> dict[str, dict]:
    fc = json.loads((out / "changes.geojson").read_text(encoding="utf-8"))
    return {f["id"]: f for f in fc["features"]}


def place(id_: str, lon: float = INSIDE[0], lat: float = INSIDE[1], **kw: Any) -> dict:
    return {"id": id_, "lon": lon, "lat": lat, "name": kw.pop("name", f"Place {id_}"), **kw}
