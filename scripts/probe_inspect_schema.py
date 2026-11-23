"""Feasibility probe, step 1: print the real Overture places schema for both releases.

Purpose: never hardcode a field we have not looked at. This reads only Parquet
footers (metadata) from the public S3 bucket, not the data itself.
Output: column names and types per release, and whether the two schemas match.
"""

from __future__ import annotations

import sys

import duckdb

BASE = "s3://overturemaps-us-west-2/release"
RELEASES = sys.argv[1:] or ["2026-10-21.0", "2026-11-18.0"]

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region = 'us-west-2';")

schemas: dict[str, list[tuple[str, str]]] = {}
for rel in RELEASES:
    uri = f"{BASE}/{rel}/theme=places/type=place/*.parquet"
    rows = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{uri}') LIMIT 0").fetchall()  # noqa: S608
    schemas[rel] = [(r[0], r[1]) for r in rows]
    print(f"\n=== {rel}: {len(rows)} columns")
    for name, dtype in schemas[rel]:
        print(f"  {name}: {dtype}")

if len(schemas) == 2:
    a, b = (dict(s) for s in schemas.values())
    print("\n=== schema diff between releases")
    print("  only in first :", sorted(set(a) - set(b)))
    print("  only in second:", sorted(set(b) - set(a)))
    print("  type changed  :", sorted(k for k in set(a) & set(b) if a[k] != b[k]))
