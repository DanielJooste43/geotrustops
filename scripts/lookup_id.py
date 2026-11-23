"""Show one Overture place id in the prev and curr releases of a config, side by side.

Usage: .venv\\Scripts\\python.exe scripts\\lookup_id.py <id> [--config config\\study_area.json]
Use it to hand-check any change the pipeline reports (and to fill golden records).
It reads the raw extracts directly and shares no classification code with the pipeline.

Prints, for prev then curr: every row with that id (more than one row = duplicate id),
or "(absent)"; name, taxonomy category, basic_category, lon/lat, inside_aoi; then the
haversine distance prev -> curr when the id has exactly one row in each.
Independent cross-check for distance: QGIS > Measure Line between the two coordinates.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]

# TRY + the POINT guard inside ST_X/ST_Y: invalid or non-point geometries print as
# unavailable instead of crashing, so excluded records can be inspected.
SQL = """
    WITH g AS (
        SELECT names."primary" AS name, taxonomy."primary" AS category, basic_category,
               TRY(ST_GeomFromWKB(geometry)) AS geom
        FROM read_parquet($path) WHERE id = $id
    )
    SELECT name, category, basic_category, ST_GeometryType(geom)::VARCHAR AS geom_type,
           ST_X(CASE WHEN ST_GeometryType(geom)::VARCHAR = 'POINT' THEN geom END) AS lon,
           ST_Y(CASE WHEN ST_GeometryType(geom)::VARCHAR = 'POINT' THEN geom END) AS lat
    FROM g
"""


def _fmt(v: float | None) -> str:
    return "unavailable" if v is None else f"{v:.6f}"


def _valid(lon: float | None, lat: float | None) -> bool:
    """A usable WGS84 position: present, finite and in range (contract §2)."""
    return (
        lon is not None
        and lat is not None
        and math.isfinite(lon)
        and math.isfinite(lat)
        and -180 <= lon <= 180
        and -90 <= lat <= 90
    )


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371000 * math.asin(math.sqrt(a))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--config", type=Path, default=ROOT / "config" / "study_area.json")
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8-sig"))
    aoi = cfg["aoi"]
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    found = {}
    for role in ("prev", "curr"):
        release = cfg["releases"][role]
        path = args.raw_dir / "releases" / release / "places.parquet"
        rows = con.execute(SQL, {"path": path.as_posix(), "id": args.id}).fetchall()
        found[role] = rows
        print(f"{role} {release}:")
        if not rows:
            print("    (absent: id not in this release's extraction)")
        if len(rows) > 1:
            print(f"    WARNING: {len(rows)} rows with this id (duplicate)")
        for name, category, basic, geom_type, lon, lat in rows:
            # unknown (not False) when the position is invalid, matching contract §2
            inside = (
                (aoi["west"] <= lon <= aoi["east"] and aoi["south"] <= lat <= aoi["north"])
                if _valid(lon, lat)
                else "unknown (invalid position)"
            )
            print(f"    name={name!r} | category={category} | basic={basic}")
            print(
                f"    geometry={geom_type or 'missing/unparsable'} lon={_fmt(lon)} lat={_fmt(lat)}"
                f" | inside_aoi={inside}"
            )
    if len(found["prev"]) == 1 and len(found["curr"]) == 1:
        (*_, lon1, lat1), (*_, lon2, lat2) = found["prev"][0], found["curr"][0]
        if not (_valid(lon1, lat1) and _valid(lon2, lat2)):
            print("distance prev -> curr: not computable (a release has no valid WGS84 point)")
        else:
            print(f"distance prev -> curr: {haversine_m(lon1, lat1, lon2, lat2):.2f} m")


if __name__ == "__main__":
    main()
