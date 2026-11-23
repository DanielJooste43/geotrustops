"""Feasibility probe, step 3: observed QA and candidate-change feasibility on real extracts.

Purpose: decide go/no-go from real numbers, before any pipeline or UI work.
Inputs:  data/raw/places_<rel>.parquet from probe_extract.py
Output:  printed metrics, and docs/feasibility_probe.json (machine-readable copy)

Row grain of every per-release query: one Overture place record (id).
Candidate change semantics follow the brief (illustrative 25 m move threshold,
NULL-safe attribute comparison). This is a feasibility probe, not the final
pipeline: `src/geotrustops` rebuilds it with tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
PREV, CURR = "2026-10-21.0", "2026-11-18.0"
MOVE_M = 25.0

con = duckdb.connect()
con.execute("INSTALL spatial; LOAD spatial;")


def raw(rel: str) -> str:
    return (ROOT / "data" / "raw" / f"places_{rel}.parquet").as_posix()


# Normalized view per release. ST_GeomFromWKB parses the WKB blob; we keep the
# geometry type so non-points are visible rather than silently coerced.
for alias, rel in (("p", PREV), ("c", CURR)):
    con.execute(f"""
        CREATE TABLE {alias} AS
        SELECT
            id,
            ST_GeometryType(ST_GeomFromWKB(geometry))::VARCHAR AS geom_type,
            ST_X(ST_GeomFromWKB(geometry)) AS lon,
            ST_Y(ST_GeomFromWKB(geometry)) AS lat,
            names."primary"      AS name,
            taxonomy."primary"   AS category,
            basic_category,
            operating_status,
            confidence,
            "version"            AS rec_version,
            sources
        FROM read_parquet('{raw(rel)}')
    """)  # noqa: S608


def one(sql: str) -> object:
    row = con.execute(sql).fetchone()
    return row[0] if row else None


def rows(sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


out: dict[str, object] = {}
for alias, rel in (("p", PREV), ("c", CURR)):
    q = {
        "rows": one(f"SELECT count(*) FROM {alias}"),
        "distinct_ids": one(f"SELECT count(DISTINCT id) FROM {alias}"),
        "null_or_empty_ids": one(f"SELECT count(*) FROM {alias} WHERE coalesce(id,'')=''"),
        "geometry_types": dict(rows(f"SELECT geom_type, count(*) FROM {alias} GROUP BY 1")),
        "null_coords": one(f"SELECT count(*) FROM {alias} WHERE lon IS NULL OR lat IS NULL"),
        "outside_bbox": one(
            f"SELECT count(*) FROM {alias} WHERE NOT (lon BETWEEN 28.168 AND 28.205 "
            f"AND lat BETWEEN -25.758 AND -25.732)"
        ),
        "null_name": one(f"SELECT count(*) FROM {alias} WHERE coalesce(name,'')=''"),
        "null_category": one(f"SELECT count(*) FROM {alias} WHERE category IS NULL"),
        "null_basic_category": one(f"SELECT count(*) FROM {alias} WHERE basic_category IS NULL"),
        "operating_status": dict(
            rows(f"SELECT operating_status, count(*) FROM {alias} GROUP BY 1")
        ),
        "source_licences": dict(
            rows(
                f"SELECT s.license, count(*) FROM {alias}, UNNEST(sources) AS t(s) GROUP BY 1 ORDER BY 2 DESC"
            )
        ),
        "source_datasets": dict(
            rows(
                f"SELECT s.dataset, count(*) FROM {alias}, UNNEST(sources) AS t(s) GROUP BY 1 ORDER BY 2 DESC"
            )
        ),
        "top_categories": rows(
            f"SELECT category, count(*) FROM {alias} GROUP BY 1 ORDER BY 2 DESC LIMIT 8"
        ),
    }
    out[rel] = q

# Candidate changes. Grain: one id from the union of both releases.
con.execute(f"""
    CREATE TABLE j AS
    SELECT
        coalesce(c.id, p.id) AS id,
        p.id IS NULL AS is_new,
        c.id IS NULL AS is_gone,
        2 * 6371000 * asin(sqrt(
            pow(sin(radians(c.lat - p.lat) / 2), 2)
            + cos(radians(p.lat)) * cos(radians(c.lat)) * pow(sin(radians(c.lon - p.lon) / 2), 2)
        )) AS dist_m,
        c.name IS DISTINCT FROM p.name AS name_diff,
        c.category IS DISTINCT FROM p.category AS cat_diff,
        c.basic_category IS DISTINCT FROM p.basic_category AS basic_diff,
        c.operating_status IS DISTINCT FROM p.operating_status AS status_diff,
        c.rec_version IS DISTINCT FROM p.rec_version AS version_diff,
        p.name AS old_name, c.name AS new_name, p.category AS old_cat, c.category AS new_cat
    FROM c FULL OUTER JOIN p ON c.id = p.id
""")
con.execute(f"""
    CREATE TABLE k AS SELECT *, CASE
        WHEN is_new THEN 'added' WHEN is_gone THEN 'removed'
        WHEN dist_m > {MOVE_M} THEN 'moved'
        WHEN name_diff OR cat_diff OR basic_diff THEN 'attribute_changed'
        ELSE 'unchanged' END AS change_type FROM j
""")
classes = dict(rows("SELECT change_type, count(*) FROM k GROUP BY 1 ORDER BY 1"))
both = one("SELECT count(*) FROM k WHERE NOT is_new AND NOT is_gone")
out["comparison"] = {
    "union_ids": one("SELECT count(*) FROM k"),
    "ids_in_both": both,
    "classes": classes,
    "reconciles": (
        classes.get("added", 0) + both == out[CURR]["rows"]  # type: ignore[index]
        and classes.get("removed", 0) + both == out[PREV]["rows"]  # type: ignore[index]
    ),
    "matched_secondary_flags": dict(
        zip(
            [
                "name_diff",
                "cat_diff",
                "basic_diff",
                "status_diff",
                "version_diff",
                "moved_gt_0_1m",
                "moved_gt_5m",
                "moved_gt_25m",
                "moved_gt_100m",
            ],
            rows("""SELECT count_if(name_diff), count_if(cat_diff), count_if(basic_diff),
                count_if(status_diff), count_if(version_diff),
                count_if(dist_m > 0.1), count_if(dist_m > 5), count_if(dist_m > 25),
                count_if(dist_m > 100)
                FROM k WHERE NOT is_new AND NOT is_gone""")[0],
        )
    ),
    # ID churn probe: a removed record and an added record with the same name
    # within 50 m are probably the same place re-issued under a new id.
    "removed_added_same_name_within_50m": one(f"""
        SELECT count(*) FROM
          (SELECT p.* FROM p JOIN k ON k.id = p.id AND k.change_type = 'removed') r
          JOIN (SELECT c.* FROM c JOIN k ON k.id = c.id AND k.change_type = 'added') a
          ON lower(r.name) = lower(a.name)
         AND 2 * 6371000 * asin(sqrt(pow(sin(radians(a.lat - r.lat) / 2), 2)
             + cos(radians(r.lat)) * cos(radians(a.lat)) * pow(sin(radians(a.lon - r.lon) / 2), 2))) < 50
    """),
    "sample_attribute_changes": rows("""
        SELECT id, old_name, new_name, old_cat, new_cat FROM k
        WHERE change_type = 'attribute_changed' ORDER BY id LIMIT 6"""),
    "sample_moves": rows("""
        SELECT id, old_name, new_name, round(dist_m, 1) FROM k
        WHERE change_type = 'moved' ORDER BY dist_m DESC LIMIT 6"""),
}

print(json.dumps(out, indent=2, default=str))
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "feasibility_probe.json").write_text(
    json.dumps(out, indent=2, default=str), "utf-8"
)
