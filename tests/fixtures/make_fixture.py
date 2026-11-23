"""Write small Overture-shaped parquet files from plain Python dicts (shared by all tests).

Purpose: let any test, including the independent contract tests, build
synthetic releases without knowing pipeline internals. Format: docs/data_contract.md §10.

Place dict keys (all optional except id):
    id, lon, lat, name, category, basic_category, confidence
    wkt              -> overrides lon/lat with any WKT geometry (e.g. a LINESTRING)
    geometry=None    -> a NULL geometry
    sources          -> list of (dataset, license); default [("meta", "CDLA-Permissive-2.0")]
    operating_status -> e.g. "open", "permanently_closed"
    addresses        -> list of dicts with freeform/locality/postcode/region/country
    phones, websites, emails, socials -> lists of str
    brand_name       -> str (written as brand.names.primary)
Pass `minimal=True` to write only the required columns (tests optional-column handling).

Changelog dict keys: id, change_type, columns_changed (list of str).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

_ADDR = "STRUCT(freeform VARCHAR, locality VARCHAR, postcode VARCHAR, region VARCHAR, country VARCHAR)[]"


def _q(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def write_places(path: Path, places: list[dict[str, Any]], minimal: bool = False) -> Path:
    """Write an Overture-shaped places parquet file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
        # lon/lat are stored as numbers and turned into a point with ST_Point, so special values such
        # as NaN can be written (WKT text cannot express NaN). `wkt` overrides them for other shapes.
        con.execute(f"""CREATE TABLE f (
            id VARCHAR, wkt VARCHAR, lon DOUBLE, lat DOUBLE, name VARCHAR, category VARCHAR, basic_category VARCHAR,
            confidence DOUBLE, src_dataset VARCHAR[], src_license VARCHAR[], operating_status VARCHAR,
            addresses {_ADDR}, phones VARCHAR[], websites VARCHAR[], emails VARCHAR[],
            socials VARCHAR[], brand_name VARCHAR)""")
        for p in places:
            wkt, lon, lat = None, None, None
            if "wkt" in p:
                wkt = p["wkt"]
            elif not ("geometry" in p and p["geometry"] is None):
                lon, lat = p["lon"], p["lat"]
            sources = p.get("sources", [("meta", "CDLA-Permissive-2.0")])
            con.execute(
                f"""INSERT INTO f VALUES ($id, $wkt, $lon, $lat, $name, $cat, $basic, $conf, $ds, $lic,
                    $status, CAST($addr AS JSON)::{_ADDR}, $phones, $websites, $emails, $socials, $brand)""",
                {
                    "id": p.get("id"),
                    "wkt": wkt,
                    "lon": lon,
                    "lat": lat,
                    "name": p.get("name"),
                    "cat": p.get("category"),
                    "basic": p.get("basic_category"),
                    "conf": p.get("confidence", 0.9),
                    "ds": [s[0] for s in sources],
                    "lic": [s[1] for s in sources],
                    "status": p.get("operating_status"),
                    "addr": json.dumps(p["addresses"]) if p.get("addresses") is not None else None,
                    "phones": p.get("phones"),
                    "websites": p.get("websites"),
                    "emails": p.get("emails"),
                    "socials": p.get("socials"),
                    "brand": p.get("brand_name"),
                },
            )
        optional = (
            ""
            if minimal
            else """,
            operating_status, addresses, phones, websites, emails, socials,
            CASE WHEN brand_name IS NULL THEN NULL
                 ELSE struct_pack(names := struct_pack("primary" := brand_name)) END AS brand"""
        )
        con.execute(f"""
            COPY (
                SELECT
                    id,
                    ST_AsWKB(CASE WHEN wkt IS NOT NULL THEN ST_GeomFromText(wkt)
                                  WHEN lon IS NOT NULL THEN ST_Point(lon, lat) END)::BLOB AS geometry,
                    struct_pack("primary" := name) AS names,
                    struct_pack("primary" := category) AS taxonomy,
                    basic_category,
                    confidence,
                    list_transform(list_zip(src_dataset, src_license),
                                   x -> struct_pack(dataset := x[1], license := x[2])) AS sources
                    {optional}
                FROM f
            ) TO '{_q(path)}' (FORMAT parquet)
        """)  # noqa: S608 - test-controlled path
    finally:
        con.close()
    return path


def write_changelog(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write a changelog parquet file (id, change_type, columns_changed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE c (id VARCHAR, change_type VARCHAR, columns_changed VARCHAR[])")
        for r in rows:
            con.execute(
                "INSERT INTO c VALUES ($id, $t, $cols)",
                {"id": r["id"], "t": r["change_type"], "cols": r.get("columns_changed")},
            )
        con.execute(f"COPY c TO '{_q(path)}' (FORMAT parquet)")  # noqa: S608
    finally:
        con.close()
    return path
