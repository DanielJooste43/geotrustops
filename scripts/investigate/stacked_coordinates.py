"""Investigation I-1: why do many places share an exact coordinate?

Method and thresholds are pre-registered in docs/investigation_backlog.md (I-1) and must not be tuned
after seeing results. Stage A uses only fields in the place records:

  H2 shared address point: >= 50% of a stack's places share the most common base address
  H1 shared complex:       >= 50% carry a unit designator, or a strong complex anchor (name or address)
                           is present and <= 10% of categories would not fit inside a complex
  H0 unexplained:          neither (goes to stage B)

Outcome: explained if H1 + H2 cover >= 80% of stacked places and >= 8 of the 10 largest stacks.

Usage: python scripts/investigate/stacked_coordinates.py [--csv out.csv]
Reads the pinned November extract in data/raw (run `geotrustops fetch` first).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from geotrustops.config import load_config  # noqa: E402
from geotrustops.extract import release_path, verify_manifest  # noqa: E402

# Regular expressions (DuckDB RE2, case-insensitive via (?i)). Pre-registered vocabulary.
UNIT = (
    r"(?i)\b(?:(?:shop|unit|suite|office|store|stall|kiosk|flat|room|floor|level|block)"
    r"\s*(?:no\.?|number|#)?\s*[a-z]?\d+[a-z]?"
    r"|(?:ground|first|second|third|\d+(?:st|nd|rd|th))\s+floor"
    r"|stall|kiosk)\b"
)
STRONG = (
    r"(?i)\b(?:mall|shopping\s+(?:centre|center|complex)|retail\s+(?:park|centre|center|block)"
    r"|plaza|arcade|business\s+park|office\s+park|complex|towers?)\b"
)
WEAK = r"(?i)\b(?:centre|center|building|house|court|square)\b"
UNFIT = [
    "beach",
    "lake",
    "mountain",
    "river",
    "nature_reserve",
    "national_park",
    "airport",
    "train_station",
    "farm",
    "campground",
]

UNIT_SHARE = 0.5
BASE_SHARE = 0.5
UNFIT_MAX = 0.10
COVER_MIN = 0.80
TOP_N, TOP_MIN = 10, 8
LARGE = 10

SQL = """
WITH p AS (
    SELECT id,
           ST_X(ST_GeomFromWKB(geometry)) AS lon,
           ST_Y(ST_GeomFromWKB(geometry)) AS lat,
           names."primary" AS name,
           coalesce(addresses[1].freeform, '') AS addr,
           basic_category AS cat,
           taxonomy.hierarchy[1] AS top_cat,
           list_transform(sources, s -> s.dataset) AS datasets
    FROM read_parquet($path)
),
study AS (
    SELECT * FROM p
    WHERE lon BETWEEN $west AND $east AND lat BETWEEN $south AND $north
),
stacked AS (
    SELECT *, count(*) OVER (PARTITION BY lon, lat) AS stack_size
    FROM study
),
feat AS (
    SELECT *,
        regexp_matches(addr || ' ' || coalesce(name, ''), $unit) AS has_unit,
        nullif(trim(regexp_replace(regexp_replace(lower(regexp_replace(addr, $unit, ' ', 'g')),
            '[^a-z0-9 ]', ' ', 'g'), '\\s+', ' ', 'g')), '') AS base_addr,
        regexp_matches(coalesce(name, '') || ' ' || addr, $strong) AS strong,
        regexp_matches(coalesce(name, '') || ' ' || addr, $weak) AS weak,
        (cat IN (SELECT unnest($unfit::VARCHAR[])) OR top_cat = 'geographic_entities') AS unfit
    FROM stacked WHERE stack_size >= 2
),
modal AS (
    SELECT lon, lat, max(n) AS modal_n FROM (
        SELECT lon, lat, base_addr, count(*) AS n FROM feat
        WHERE base_addr IS NOT NULL GROUP BY ALL
    ) GROUP BY ALL
),
src AS (  -- source mix per stack (descriptive only); separate so it cannot duplicate place rows
    SELECT lon, lat, list(DISTINCT d ORDER BY d) AS datasets
    FROM (SELECT lon, lat, unnest(datasets) AS d FROM feat) GROUP BY ALL
),
agg AS (
    SELECT lon, lat, count(*) AS size,
           avg(has_unit::INT) AS unit_share,
           bool_or(strong) AS strong_anchor,
           bool_or(weak) AS weak_anchor,
           avg(unfit::INT) AS unfit_share,
           count(*) FILTER (WHERE addr = '') AS no_address,
           list(name ORDER BY name)[1:6] AS sample_names
    FROM feat GROUP BY lon, lat
)
SELECT a.lon, a.lat, a.size, a.unit_share,
       coalesce(m.modal_n, 0) / a.size AS base_share,
       a.strong_anchor, a.weak_anchor, a.unfit_share, a.no_address,
       coalesce(s.datasets, []) AS datasets, a.sample_names
FROM agg a
LEFT JOIN modal m USING (lon, lat)
LEFT JOIN src s USING (lon, lat)
ORDER BY a.size DESC, a.lon, a.lat
"""


def classify(row: dict) -> str:
    if row["base_share"] >= BASE_SHARE:
        return "H2"
    if row["unit_share"] >= UNIT_SHARE or (
        row["strong_anchor"] and row["unfit_share"] <= UNFIT_MAX
    ):
        return "H1"
    return "H0"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, help="write the per-stack table here")
    args = ap.parse_args()

    cfg = load_config(ROOT / "config" / "study_area.json")
    path = release_path(ROOT / "data" / "raw", cfg.curr_release)
    verify_manifest(path, cfg, "release", cfg.curr_release)
    aoi = cfg.raw["aoi"]

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    params = {
        "path": path.as_posix(),
        **{k: float(aoi[k]) for k in ("west", "south", "east", "north")},
        "unit": UNIT,
        "strong": STRONG,
        "weak": WEAK,
        "unfit": UNFIT,
    }
    cur = con.execute(SQL, params)
    cols = [d[0] for d in cur.description]
    stacks = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    study_n = con.execute(
        "SELECT count(*) FROM read_parquet($path) WHERE ST_X(ST_GeomFromWKB(geometry)) BETWEEN $west AND $east "
        "AND ST_Y(ST_GeomFromWKB(geometry)) BETWEEN $south AND $north",
        {k: params[k] for k in ("path", "west", "south", "east", "north")},
    ).fetchone()[0]
    con.close()

    for s in stacks:
        s["class"] = classify(s)

    stacked_n = sum(s["size"] for s in stacks)
    by_class = {c: sum(s["size"] for s in stacks if s["class"] == c) for c in ("H1", "H2", "H0")}
    stacks_by_class = {c: sum(1 for s in stacks if s["class"] == c) for c in ("H1", "H2", "H0")}
    covered = (by_class["H1"] + by_class["H2"]) / stacked_n if stacked_n else 0.0
    top = stacks[:TOP_N]
    top_explained = sum(1 for s in top if s["class"] != "H0")
    explained = covered >= COVER_MIN and top_explained >= TOP_MIN

    print(f"release {cfg.curr_release}; places in study AOI: {study_n}")
    print(
        f"stacks (>=2 places): {len(stacks)}; stacked places: {stacked_n} ({stacked_n / study_n:.1%})"
    )
    print(f"large stacks (>={LARGE}): {sum(1 for s in stacks if s['size'] >= LARGE)}")
    for c in ("H2", "H1", "H0"):
        print(
            f"  {c}: {stacks_by_class[c]} stacks, {by_class[c]} places ({by_class[c] / stacked_n:.1%})"
        )
    print(
        f"coverage H1+H2: {covered:.1%} (need >= {COVER_MIN:.0%}); "
        f"top {TOP_N} explained: {top_explained} (need >= {TOP_MIN})"
    )
    print(f"OUTCOME: {'explained' if explained else 'inconclusive -> stage B for H0 stacks'}")
    print()
    print("top stacks:")
    for s in top:
        print(
            f"  {s['class']} size={s['size']:>3} unit={s['unit_share']:.2f} base={s['base_share']:.2f} "
            f"strong={s['strong_anchor']!s:5} weak={s['weak_anchor']!s:5} unfit={s['unfit_share']:.2f} "
            f"noaddr={s['no_address']} src={','.join(s['datasets'])} at ({s['lon']:.6f}, {s['lat']:.6f})"
        )
        print(f"      e.g. {' | '.join(n or '' for n in s['sample_names'])}")

    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            keys = [
                "lon",
                "lat",
                "size",
                "class",
                "unit_share",
                "base_share",
                "strong_anchor",
                "weak_anchor",
                "unfit_share",
                "no_address",
                "datasets",
                "sample_names",
            ]
            w.writerow(keys)
            for s in stacks:
                w.writerow(
                    [";".join(map(str, s[k])) if isinstance(s[k], list) else s[k] for k in keys]
                )
        print(f"\nper-stack table -> {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
