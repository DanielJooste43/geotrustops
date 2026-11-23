"""Load and validate config/study_area.json (contract §10).

Every rule parameter (releases, AOI, buffer, threshold, failure share) lives in the
config file, so changing a rule never means editing code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """The config file is missing a key or has an impossible value."""


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def expanded(self, deg: float) -> BBox:
        return BBox(self.west - deg, self.south - deg, self.east + deg, self.north + deg)

    def as_dict(self) -> dict[str, float]:
        return {"west": self.west, "south": self.south, "east": self.east, "north": self.north}


@dataclass(frozen=True)
class Config:
    prev_release: str
    curr_release: str
    aoi: BBox
    buffer_deg: float
    move_threshold_m: float
    minor_move_m: float
    major_move_m: float
    max_excluded_share: float
    release_uri: str
    changelog_uri: str
    s3_region: str
    out_dir: str | None
    raw: dict[str, Any]  # the parsed file, hashed into the calibration-log key

    @property
    def extraction_bbox(self) -> BBox:
        """AOI plus buffer: what is downloaded, so edge-crossing places are in both extracts."""
        return self.aoi.expanded(self.buffer_deg)


def load_config(path: Path) -> Config:
    try:
        # utf-8-sig also accepts a byte-order mark, which Windows editors/PowerShell often add.
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        aoi = BBox(**{k: float(raw["aoi"][k]) for k in ("west", "south", "east", "north")})
        source = raw.get("source", {})
        cfg = Config(
            prev_release=str(raw["releases"]["prev"]),
            curr_release=str(raw["releases"]["curr"]),
            aoi=aoi,
            buffer_deg=float(raw["buffer_deg"]),
            move_threshold_m=float(raw["move_threshold_m"]),
            minor_move_m=float(raw["minor_move_m"]),
            major_move_m=float(raw["major_move_m"]),
            max_excluded_share=float(raw["max_excluded_share"]),
            release_uri=str(source.get("release_uri", "")),
            changelog_uri=str(source.get("changelog_uri", "")),
            s3_region=str(source.get("s3_region", "us-west-2")),
            out_dir=raw.get("out_dir"),
            raw=raw,
        )
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise ConfigError(f"invalid config {path}: {exc}") from exc
    if not (aoi.west < aoi.east and aoi.south < aoi.north):
        raise ConfigError(f"AOI is empty or inverted: {aoi}")
    if cfg.buffer_deg < 0 or not 0 <= cfg.max_excluded_share <= 1:
        raise ConfigError("need buffer_deg >= 0 and 0 <= max_excluded_share <= 1")
    if not 0 < cfg.minor_move_m < cfg.move_threshold_m < cfg.major_move_m:
        raise ConfigError("need 0 < minor_move_m < move_threshold_m < major_move_m")
    return cfg
