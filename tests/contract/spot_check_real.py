"""Independently check five seeded, stratified random changes against raw parquet.

Inputs: existing out/ exports and their pinned raw releases. Output: JSON evidence
on stdout; assertions fail on disagreement. No pipeline imports. One record per
exported class, seed 20261123; this is a spot-check, not exhaustive validation.
"""

import hashlib
import json
import math
from pathlib import Path
import random

import duckdb


def distance(a, b):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat, dlon = lat2 - lat1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def main():
    root = Path(__file__).resolve().parents[2]
    summary = json.loads((root / "out/summary.json").read_text(encoding="utf-8"))
    features = json.loads((root / "out/changes.geojson").read_text(encoding="utf-8"))["features"]
    rng = random.Random(20261123)
    sample = [
        rng.choice(
            sorted(
                [f for f in features if f["properties"]["change_type"] == kind],
                key=lambda f: f["properties"]["id"],
            )
        )
        for kind in ("added", "removed", "moved", "attribute_changed", "shifted")
    ]
    con = duckdb.connect()
    con.execute("LOAD spatial")
    raw = {}
    for side, release in summary["releases"].items():
        path = root / "data/raw/releases" / release / "places.parquet"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == summary["inputs_sha256"][side]
        # Grain: one raw source row per selected id (asserted below).
        query = """SELECT id, names.primary AS name, taxonomy.primary AS category,
                   basic_category, ST_X(ST_GeomFromWKB(geometry)) AS lon,
                   ST_Y(ST_GeomFromWKB(geometry)) AS lat
                   FROM read_parquet($path) WHERE id IN (SELECT unnest($ids))"""
        result = con.execute(
            query, {"path": path.as_posix(), "ids": [f["properties"]["id"] for f in sample]}
        )
        columns = [d[0] for d in result.description]
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        assert len(rows) == len({r["id"] for r in rows})
        raw[side] = {r["id"]: r for r in rows}
    con.close()
    checks = []
    aoi = summary["aoi"]

    def inside(row):
        return (
            row is not None
            and aoi["west"] <= row["lon"] <= aoi["east"]
            and aoi["south"] <= row["lat"] <= aoi["north"]
        )

    for feature in sample:
        prop = feature["properties"]
        old, new = (raw[side].get(prop["id"]) for side in ("prev", "curr"))
        assert inside(old) or inside(new)
        metres = distance(old, new) if old and new else None
        if old is None:
            expected = "added"
        elif new is None:
            expected = "removed"
        elif metres > summary["thresholds_m"]["move"]:
            expected = "moved"
        elif any(
            (old[k] or None) != (new[k] or None) for k in ("name", "category", "basic_category")
        ):
            expected = "attribute_changed"
        elif metres > summary["thresholds_m"]["minor_move"]:
            expected = "shifted"
        else:
            expected = "unchanged"
        assert prop["change_type"] == expected
        location = old if expected == "removed" else new
        assert feature["geometry"]["coordinates"] == [
            round(location["lon"], 6),
            round(location["lat"], 6),
        ]
        for side, row in (("prev", old), ("curr", new)):
            for key in ("name", "category", "basic_category", "lon", "lat"):
                value = row[key] if row else None
                if value is not None and key in ("lon", "lat"):
                    value = round(value, 6)
                assert prop[f"{side}_{key}"] == value
        if metres is not None:
            assert prop["distance_m"] == round(metres, 1)
            assert prop["crossed_aoi_boundary"] == (inside(old) != inside(new))
        checks.append(
            {
                "id": prop["id"],
                "expected": expected,
                "exported": prop["change_type"],
                "raw_distance_m": metres,
                "prev": old,
                "curr": new,
                "agrees": True,
            }
        )
    print(
        json.dumps(
            {
                "seed": 20261123,
                "sampling": "one random record per exported class",
                "input_hashes_verified": True,
                "checks": checks,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
