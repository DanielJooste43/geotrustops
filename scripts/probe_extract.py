"""Feasibility probe, step 2: clip both pinned Overture places releases to the study bbox.

Purpose: get a small, real, unmodified local copy of each release for the AOI.
Inputs:  public s3://overturemaps-us-west-2/release/<rel>/theme=places/type=place/
Outputs: data/raw/places_<rel>.parquet  (all source columns, as delivered)
         data/raw/places_<rel>.manifest.json  (uri, bbox, rows, sha256, time)

Adapted from open-map-quality-lake/src/omql/ingest/overture.py (bbox overlap
filter with Parquet predicate pushdown, temp-file + rename, zero rows = error).

Filter rule: a place is kept when its *point* lies inside the bbox (inclusive).
For points, bbox.xmin == xmax, so the overlap test equals point-in-box.
The same rule is applied to both releases, so the AOI is identical.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import duckdb

BASE = "s3://overturemaps-us-west-2/release"
RELEASES = ["2026-10-21.0", "2026-11-18.0"]
# WGS84 lon/lat: west, south, east, north (central Pretoria, from the project brief)
WEST, SOUTH, EAST, NORTH = 28.168, -25.758, 28.205, -25.732
OUT = Path(__file__).resolve().parents[1] / "data" / "raw"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract(con: duckdb.DuckDBPyConnection, release: str) -> None:
    uri = f"{BASE}/{release}/theme=places/type=place/*.parquet"
    final = OUT / f"places_{release}.parquet"
    tmp = final.with_suffix(".parquet.tmp")
    if final.exists():
        print(f"skip {release}: {final.name} already exists (delete it to re-extract)")
        return
    # Floats are module constants, not user input, so f-string interpolation is safe.
    sql = f"""
        COPY (
            SELECT * FROM read_parquet('{uri}')
            WHERE bbox.xmin <= {EAST} AND bbox.xmax >= {WEST}
              AND bbox.ymin <= {NORTH} AND bbox.ymax >= {SOUTH}
            ORDER BY id
        ) TO '{tmp.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """  # noqa: S608
    started = dt.datetime.now(dt.UTC)
    try:
        con.execute(sql)
    except duckdb.Error:
        tmp.unlink(missing_ok=True)
        raise
    row = con.execute("SELECT count(*) FROM read_parquet($p)", {"p": tmp.as_posix()}).fetchone()
    rows = int(row[0]) if row else 0
    if rows == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"0 rows for {release} in bbox: treat as failure, not empty success")
    tmp.replace(final)
    manifest = {
        "release": release,
        "source_uri": uri,
        "bbox_wgs84": {"west": WEST, "south": SOUTH, "east": EAST, "north": NORTH},
        "filter": "bbox overlap on Overture bbox struct (point-in-box for points)",
        "row_count": rows,
        "file": final.name,
        "sha256": sha256(final),
        "bytes": final.stat().st_size,
        "extracted_utc": started.isoformat(timespec="seconds"),
        "duckdb_version": duckdb.__version__,
    }
    final.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    print(f"{release}: {rows} rows -> {final.name} ({final.stat().st_size / 1024:.0f} KB)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region = 'us-west-2';")
    for release in RELEASES:
        extract(con, release)
    con.close()


if __name__ == "__main__":
    main()
