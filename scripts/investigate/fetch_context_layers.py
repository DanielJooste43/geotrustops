"""Download the Overture context layers used by the stacked-coordinates cascade (investigation I-1).

Divisions (points), buildings and transportation (connectors, segments), for the extraction bbox only, from the
same pinned releases as the places. ODbL (© OpenStreetMap contributors, Overture Maps Foundation); used for
internal analysis only and not redistributed. Each file gets a manifest with its source URI and SHA-256.

Usage: python scripts/investigate/fetch_context_layers.py [release ...]   (default: both configured releases)
Output: data/raw/context/<release>/<type>/data.parquet (+ manifest.json; git-ignored)
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from geotrustops.config import load_config  # noqa: E402
from geotrustops.extract import ExtractError, download  # noqa: E402

URI = "s3://overturemaps-us-west-2/release/{release}/theme={theme}/type={type}/*.parquet"
LAYERS = [
    ("divisions", "division", 'id, geometry, subtype, names."primary" AS name, bbox'),
    (
        "buildings",
        "building",
        'id, geometry, height, num_floors, class, subtype, names."primary" AS name, bbox',
    ),
    ("transportation", "connector", "id, geometry, bbox"),
    ("transportation", "segment", 'id, geometry, subtype, class, names."primary" AS name, bbox'),
]


def main(argv: list[str]) -> int:
    cfg = load_config(ROOT / "config" / "study_area.json")
    releases = argv or [cfg.prev_release, cfg.curr_release]
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region = $r", {"r": cfg.s3_region})
    try:
        for release in releases:
            for theme, typ, select in LAYERS:
                out = ROOT / "data" / "raw" / "context" / release / typ / "data.parquet"
                if out.exists():
                    print(f"skip: {out.relative_to(ROOT)} exists")
                    continue
                uri = URI.format(release=release, theme=theme, type=typ)
                meta = {"kind": f"context:{typ}", "release": release, "licence": "ODbL-1.0"}
                m = download(con, uri, select, cfg.extraction_bbox, out, meta)
                print(f"{release} {typ}: {m['row_count']} rows, {m['bytes']} B")
    except ExtractError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
