"""The comparison pipeline: data-contract stages A-C, reconciliation (§4) and changelog oracle (§9).

Inputs:  two Overture-shaped places parquet files (prev, curr), optional changelog parquet, Config.
Output:  a `Result` (classified ids, summary, QA lists). Nothing is written here: export.py writes
         files only after every gate has passed.

One in-memory DuckDB database, a chain of tables:

    norm        grain: one source row per release           Stage A (flatten + normalize)
    rows        grain: one source row per release           Stage B (exclusion reason, in_aoi)
    ids         grain: one distinct non-empty id            Stage C (match, classify, flags)
    changelog   grain: one changelog row                    §9 oracle (optional)

Adapted from the diff step of an earlier, unpublished prototype by the same author (FULL OUTER JOIN,
IS DISTINCT FROM, haversine). Values are passed as *named* parameters ($name): the original positional `?` binding
failed on DuckDB 1.1.3 and 1.4.2 (binding-order and parse errors).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from geotrustops import CONTRACT_VERSION, __version__
from geotrustops.config import Config
from geotrustops.extract import sha256

CHANGE_TYPES = [
    "excluded",
    "added",
    "removed",
    "moved",
    "attribute_changed",
    "shifted",
    "unchanged",
]
EXPORTED_TYPES = ["added", "removed", "moved", "attribute_changed", "shifted"]
MOVE_BANDS = ["stable", "minor", "material", "major"]
NAME_CHANGE_KINDS = [
    "added",
    "removed",
    "case_or_spacing",
    "punctuation",
    "expanded_or_trimmed",
    "different",
]
ENRICH_FIELDS = ["addresses", "brand", "emails", "phones", "socials", "websites"]  # sorted
EXCLUSION_REASONS = [
    "missing_id",
    "duplicate_id",
    "missing_geometry",
    "non_point_geometry",
    "invalid_coordinates",
]
REQUIRED_COLUMNS = {
    "id",
    "geometry",
    "names",
    "taxonomy",
    "basic_category",
    "confidence",
    "sources",
}
OPTIONAL_COLUMNS = {
    "operating_status",
    "addresses",
    "phones",
    "websites",
    "emails",
    "socials",
    "brand",
}

# ISO 3166-2 code -> the upper-cased spellings of each South African province seen in the
# source (codes and names). Contract §1 "Address normalisation". Constant data, not user input.
_ZA_REGIONS = {
    "ZA-GP": ["GP", "GAUTENG"],
    "ZA-WC": ["WC", "WESTERN CAPE"],
    "ZA-KZN": ["KZN", "KWAZULU NATAL", "KWAZULU-NATAL"],
    "ZA-NW": ["NW", "NORTH WEST"],
    "ZA-MP": ["MP", "MPUMALANGA"],
    "ZA-LP": ["LP", "LIMPOPO"],
    "ZA-EC": ["EC", "EASTERN CAPE"],
    "ZA-FS": ["FS", "FREE STATE"],
    "ZA-NC": ["NC", "NORTHERN CAPE"],
}


def _region_case(expr: str) -> str:
    """SQL CASE mapping a region value to its ISO code; unknown values pass through unchanged."""
    key = f"upper(trim({expr}))"
    whens = " ".join(
        f"WHEN {key} IN ({', '.join(repr(s) for s in spellings)}) THEN '{iso}'"
        for iso, spellings in _ZA_REGIONS.items()
    )
    return f"CASE WHEN {key} LIKE 'ZA-%' THEN {key} {whens} ELSE {expr} END"


class PipelineError(RuntimeError):
    """A quality gate (contract §6) failed; the run must stop and write nothing."""


@dataclass
class Result:
    summary: dict[str, Any]
    changes: list[dict[str, Any]] = field(default_factory=list)  # one per exported id
    excluded_rows: list[dict[str, Any]] = field(default_factory=list)
    top_moves: list[dict[str, Any]] = field(default_factory=list)
    renames: list[dict[str, Any]] = field(default_factory=list)
    lifecycle: list[dict[str, Any]] = field(default_factory=list)
    changelog_mismatches: list[dict[str, Any]] = field(default_factory=list)
    # every id in the extraction -> its change_type, or 'not_in_study' (tests / lookups)
    classification: dict[str, str] = field(default_factory=dict)


# --- Stage A: normalize (grain: one row per source row) -------------------------------------
# Nested Overture fields become flat columns. {geom_expr} and the optional-column expressions are
# chosen per file in Python (see _select_exprs): absent optional columns become NULL.
# TRY(...) turns an unparsable WKB value into NULL (-> `missing_geometry`) instead of failing.
_NORMALIZE = """
INSERT INTO norm
WITH src AS (
    SELECT row_number() OVER () AS src_row, * FROM read_parquet($path)
), parsed AS (
    SELECT
        src_row,
        NULLIF(id, '')     AS id,
        {geom_expr}        AS geom,
        names."primary"    AS raw_name,
        taxonomy."primary" AS category,
        basic_category,
        confidence,
        sources,
        {operating_status} AS operating_status,
        {addresses_raw}    AS addresses_raw,
        {addresses_norm}   AS addresses_norm,
        {phones}           AS phones,
        {phones_norm}      AS phones_norm,
        {websites}         AS websites,
        {emails}           AS emails,
        {socials}          AS socials,
        {brand}            AS brand,
        {brand_name}       AS brand_name
    FROM src
), typed AS (
    SELECT *, ST_GeometryType(geom)::VARCHAR AS geom_type FROM parsed
)
SELECT
    $side AS side, src_row, id, geom_type,
    -- ST_X/ST_Y are only defined for points; other shapes get NULL coordinates.
    -- The guard is INSIDE the call on purpose: `CASE WHEN point THEN ST_X(geom) END` still let
    -- DuckDB evaluate ST_X on a LINESTRING when many rows shared identical coordinates (likely
    -- dictionary-encoded vectors; regression test in tests/). Here ST_X only receives a point or NULL.
    ST_X(CASE WHEN geom_type = 'POINT' THEN geom END) AS lon,
    ST_Y(CASE WHEN geom_type = 'POINT' THEN geom END) AS lat,
    NULLIF(raw_name, '') AS name, category, basic_category, confidence, operating_status,
    addresses_raw, addresses_norm, phones, phones_norm, websites, emails, socials, brand, brand_name,
    -- sorted + distinct, so the text does not depend on the source's list order
    array_to_string(list_sort(list_distinct(list_transform(sources, s -> s.dataset))), ';')
        AS source_datasets,
    array_to_string(list_sort(list_distinct(list_transform(sources, s -> s.license))), ';')
        AS source_licences
FROM typed
"""

_NORM_COLUMNS = """side VARCHAR, src_row BIGINT, id VARCHAR, geom_type VARCHAR, lon DOUBLE, lat DOUBLE,
    name VARCHAR, category VARCHAR, basic_category VARCHAR, confidence DOUBLE, operating_status VARCHAR,
    addresses_raw VARCHAR, addresses_norm VARCHAR, phones VARCHAR, phones_norm VARCHAR,
    websites VARCHAR, emails VARCHAR,
    socials VARCHAR, brand VARCHAR, brand_name VARCHAR, source_datasets VARCHAR, source_licences VARCHAR"""

# --- Stage B: exclusion + AOI membership (grain unchanged) ----------------------------------
# First failing rule wins (contract §2). count(*) OVER (PARTITION BY side, id) = copies of an id.
_EXCLUDE = """
CREATE TABLE rows AS
WITH flagged AS (
    SELECT *,
        CASE
            WHEN id IS NULL THEN 'missing_id'
            WHEN count(*) OVER (PARTITION BY side, id) > 1 THEN 'duplicate_id'
            WHEN geom_type IS NULL THEN 'missing_geometry'
            WHEN geom_type <> 'POINT' THEN 'non_point_geometry'
            WHEN lon IS NULL OR lat IS NULL OR isnan(lon) OR isnan(lat)
                 OR lon NOT BETWEEN -180 AND 180 OR lat NOT BETWEEN -90 AND 90
                THEN 'invalid_coordinates'
        END AS exclusion_reason,
        -- point inside the AOI (inclusive); NULL = location UNKNOWN whenever the coordinates are not a
        -- valid WGS84 position (none, NaN, out of range), whatever the exclusion reason. Without this,
        -- NaN or lon 181 compared as "outside" and an invalid record silently left the study.
        CASE WHEN lon IS NOT NULL AND lat IS NOT NULL AND NOT isnan(lon) AND NOT isnan(lat)
                  AND lon BETWEEN -180 AND 180 AND lat BETWEEN -90 AND 90
             THEN lon BETWEEN $west AND $east AND lat BETWEEN $south AND $north
        END AS point_in_aoi
    FROM norm
)
SELECT *, (exclusion_reason IS NULL AND coalesce(point_in_aoi, false)) AS in_aoi
FROM flagged
"""

# --- Stage C: match + classify (grain: one row per distinct non-empty id) --------------------
# p / c = the single *valid* row of an id in prev / curr (valid ids are unique per release).
_CLASSIFY = """
CREATE TABLE ids AS
WITH p AS (SELECT * FROM rows WHERE side = 'prev' AND exclusion_reason IS NULL),
     c AS (SELECT * FROM rows WHERE side = 'curr' AND exclusion_reason IS NULL),
ex AS (
    -- grain: one row per id with at least one excluded row
    SELECT id,
        NULLIF(array_to_string(list_sort(list_distinct(
            list(exclusion_reason) FILTER (WHERE side = 'prev'))), ';'), '') AS prev_exclusion,
        NULLIF(array_to_string(list_sort(list_distinct(
            list(exclusion_reason) FILTER (WHERE side = 'curr'))), ';'), '') AS curr_exclusion,
        bool_or(coalesce(point_in_aoi, true)) AS ex_in_aoi_or_unlocated
    FROM rows WHERE exclusion_reason IS NOT NULL AND id IS NOT NULL GROUP BY id
),
any_row AS (SELECT id, bool_or(coalesce(point_in_aoi, false)) AS any_point_in_aoi
            FROM rows WHERE id IS NOT NULL GROUP BY id),
joined AS (
    SELECT
        coalesce(c.id, p.id, ex.id) AS id,
        p.id IS NOT NULL AS prev_valid,
        c.id IS NOT NULL AS curr_valid,
        ex.id IS NOT NULL AS has_exclusion,
        ex.prev_exclusion, ex.curr_exclusion,
        coalesce(p.in_aoi, false) OR coalesce(c.in_aoi, false) AS in_study,
        coalesce(ex.ex_in_aoi_or_unlocated, false) OR coalesce(a.any_point_in_aoi, false) AS excluded_in_aoi,
        p.lon AS prev_lon, p.lat AS prev_lat, c.lon AS curr_lon, c.lat AS curr_lat,
        p.name AS prev_name, c.name AS curr_name,
        p.category AS prev_category, c.category AS curr_category,
        p.basic_category AS prev_basic_category, c.basic_category AS curr_basic_category,
        p.operating_status AS prev_operating_status, c.operating_status AS curr_operating_status,
        p.confidence AS prev_confidence, c.confidence AS curr_confidence,
        c.brand_name AS curr_brand_name,
        p.in_aoi AS prev_in_aoi, c.in_aoi AS curr_in_aoi,
        -- fields whose raw text differs but whose normalised form is equal (format migration)
        concat_ws(';',
            CASE WHEN p.addresses_raw IS DISTINCT FROM c.addresses_raw
                  AND p.addresses_norm IS NOT DISTINCT FROM c.addresses_norm THEN 'addresses' END,
            CASE WHEN p.phones IS DISTINCT FROM c.phones
                  AND p.phones_norm IS NOT DISTINCT FROM c.phones_norm THEN 'phones' END) AS format_diff,
        -- enrichment fields that differ (normalised where defined), sorted, ';'-joined; '' if none
        concat_ws(';',
            CASE WHEN p.addresses_norm IS DISTINCT FROM c.addresses_norm THEN 'addresses' END,
            CASE WHEN p.brand IS DISTINCT FROM c.brand THEN 'brand' END,
            CASE WHEN p.emails IS DISTINCT FROM c.emails THEN 'emails' END,
            CASE WHEN p.phones_norm IS DISTINCT FROM c.phones_norm THEN 'phones' END,
            CASE WHEN p.socials IS DISTINCT FROM c.socials THEN 'socials' END,
            CASE WHEN p.websites IS DISTINCT FROM c.websites THEN 'websites' END) AS enrich_diff,
        coalesce(c.source_datasets, p.source_datasets) AS source_datasets,
        coalesce(c.source_licences, p.source_licences) AS source_licences,
        -- haversine distance in metres (radius 6371000 m); NULL unless matched
        2 * 6371000 * asin(sqrt(
            pow(sin(radians(c.lat - p.lat) / 2), 2)
            + cos(radians(p.lat)) * cos(radians(c.lat)) * pow(sin(radians(c.lon - p.lon) / 2), 2)
        )) AS distance_m
    FROM p
    FULL OUTER JOIN c ON c.id = p.id
    FULL OUTER JOIN ex ON ex.id = coalesce(c.id, p.id)
    LEFT JOIN any_row a ON a.id = coalesce(c.id, p.id, ex.id)
),
flags AS (
    SELECT *,
        prev_valid AND curr_valid AS matched,
        (in_study OR (has_exclusion AND excluded_in_aoi)) AS considered,
        prev_name IS DISTINCT FROM curr_name AS name_diff,
        (prev_name IS DISTINCT FROM curr_name
         OR prev_category IS DISTINCT FROM curr_category
         OR prev_basic_category IS DISTINCT FROM curr_basic_category) AS attr_diff
    FROM joined
)
SELECT *,
    -- Exactly one change type, first match wins (contract §3).
    CASE
        WHEN has_exclusion THEN 'excluded'
        WHEN curr_valid AND NOT prev_valid THEN 'added'
        WHEN prev_valid AND NOT curr_valid THEN 'removed'
        WHEN distance_m > $threshold THEN 'moved'
        WHEN attr_diff THEN 'attribute_changed'
        WHEN distance_m > $minor THEN 'shifted'
        ELSE 'unchanged'
    END AS change_type,
    CASE WHEN matched THEN CASE
        WHEN distance_m <= $minor THEN 'stable'
        WHEN distance_m <= $threshold THEN 'minor'
        WHEN distance_m <= $major THEN 'material'
        ELSE 'major' END END AS move_band,
    CASE WHEN matched THEN name_diff END AS name_changed,
    CASE WHEN matched AND name_diff THEN CASE
        WHEN prev_name IS NULL THEN 'added'
        WHEN curr_name IS NULL THEN 'removed'
        WHEN lower(trim(regexp_replace(prev_name, '\\s+', ' ', 'g')))
           = lower(trim(regexp_replace(curr_name, '\\s+', ' ', 'g'))) THEN 'case_or_spacing'
        -- \\p{{L}}\\p{{N}} = any Unicode letter or digit, so accented names are handled correctly
        WHEN regexp_replace(lower(prev_name), '[^\\p{{L}}\\p{{N}}]', '', 'g')
           = regexp_replace(lower(curr_name), '[^\\p{{L}}\\p{{N}}]', '', 'g') THEN 'punctuation'
        WHEN contains(lower(curr_name), lower(prev_name))
          OR contains(lower(prev_name), lower(curr_name)) THEN 'expanded_or_trimmed'
        ELSE 'different' END END AS name_change_kind,
    -- true/false for every matched id (§3): a missing name or brand compares as NULL, which is "no match".
    CASE WHEN matched THEN coalesce(name_diff AND lower(curr_name) = lower(curr_brand_name), false) END
        AS name_matches_brand,
    CASE WHEN matched THEN prev_category IS DISTINCT FROM curr_category END AS category_changed,
    CASE WHEN matched THEN prev_basic_category IS DISTINCT FROM curr_basic_category END
        AS basic_category_changed,
    CASE WHEN matched THEN prev_operating_status IS DISTINCT FROM curr_operating_status END
        AS status_changed,
    CASE WHEN matched THEN coalesce(curr_confidence = 0 AND prev_confidence IS DISTINCT FROM 0, false) END
        AS confidence_to_zero,
    CASE WHEN matched THEN enrich_diff END AS enrichment_changed,
    CASE WHEN matched THEN format_diff END AS format_only_changed,
    CASE WHEN matched THEN prev_in_aoi IS DISTINCT FROM curr_in_aoi END AS crossed_aoi_boundary
FROM flags
"""

_BOOL_FLAGS = [
    "name_changed",
    "name_matches_brand",
    "category_changed",
    "basic_category_changed",
    "status_changed",
    "confidence_to_zero",
    "crossed_aoi_boundary",
]
FORMAT_FIELDS = ["addresses", "phones"]

# Phone numbers: keep digits and '+'; a national number (leading 0) on a South African record
# (first address country 'ZA') becomes E.164 '+27…'. Contract §1 "Phone normalisation".
_PHONES_NORM = (
    "to_json(list_transform(list_filter(phones, v -> v IS NOT NULL AND v <> ''), v -> "
    "CASE WHEN regexp_replace(v, '[^0-9+]', '', 'g') LIKE '0%' AND {za} "
    "THEN '+27' || substr(regexp_replace(v, '[^0-9+]', '', 'g'), 2) "
    "ELSE regexp_replace(v, '[^0-9+]', '', 'g') END))::VARCHAR"
)


def _select_exprs(con: duckdb.DuckDBPyConnection, path: Path) -> dict[str, str]:
    """Per-file SQL expressions: geometry decoding, and NULL for absent optional columns."""
    cols = {
        r[0]: str(r[1])
        for r in con.execute(
            "SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_parquet($p))",
            {"p": path.as_posix()},
        ).fetchall()
    }
    missing = REQUIRED_COLUMNS - set(cols)
    if missing:
        raise PipelineError(f"{path}: required column(s) missing: {sorted(missing)}")
    has = set(cols) & OPTIONAL_COLUMNS
    null = "NULL::VARCHAR"
    as_json = {
        c: (f"to_json({c})::VARCHAR" if c in has else null)
        for c in ("phones", "websites", "emails", "socials", "brand")
    }
    region = _region_case("a.region")
    return {
        "geom_expr": (
            "geometry"
            if cols["geometry"].upper().startswith("GEOMETRY")
            else "TRY(ST_GeomFromWKB(geometry))"
        ),
        "operating_status": "operating_status" if "operating_status" in has else null,
        "addresses_raw": "to_json(addresses)::VARCHAR" if "addresses" in has else null,
        "addresses_norm": (
            "to_json(list_transform(addresses, a -> struct_pack("
            "freeform := a.freeform, locality := a.locality, postcode := a.postcode, "
            f"region := {region}, country := a.country)))::VARCHAR"
        )
        if "addresses" in has
        else null,
        "brand_name": 'brand.names."primary"' if "brand" in has else null,
        "phones_norm": _PHONES_NORM.format(
            za="coalesce(addresses[1].country = 'ZA', false)" if "addresses" in has else "false"
        )
        if "phones" in has
        else null,
        **as_json,
    }


def _rows(
    con: duckdb.DuckDBPyConnection, sql: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    cur = con.execute(sql, params or {})
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def _one_row(
    con: duckdb.DuckDBPyConnection, sql: str, params: dict[str, Any] | None = None
) -> tuple[Any, ...]:
    """Run a query that must return exactly one row (e.g. aggregate counts); fail clearly if it does not."""
    row = con.execute(sql, params or {}).fetchone()
    if row is None:
        raise PipelineError(f"query returned no row: {sql.strip().splitlines()[0][:80]}")
    return tuple(row)


def _scalar(con: duckdb.DuckDBPyConnection, sql: str, params: dict[str, Any] | None = None) -> Any:
    row = con.execute(sql, params or {}).fetchone()
    return row[0] if row else None


def run(prev: Path, curr: Path, changelog: Path | None, cfg: Config) -> Result:
    """Execute stages A-C, the gates and reconciliation. Raises PipelineError on any gate failure."""
    for p in (prev, curr):
        if not Path(p).exists():
            raise PipelineError(f"input file not found: {p}")
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
        con.execute(f"CREATE TABLE norm ({_NORM_COLUMNS})")
        for side, path in (("prev", Path(prev)), ("curr", Path(curr))):
            sql = _NORMALIZE.format(**_select_exprs(con, path))
            con.execute(sql, {"path": path.as_posix(), "side": side})
        a = cfg.aoi
        con.execute(_EXCLUDE, {"west": a.west, "east": a.east, "south": a.south, "north": a.north})
        con.execute(
            _CLASSIFY.format(),
            {
                "threshold": cfg.move_threshold_m,
                "minor": cfg.minor_move_m,
                "major": cfg.major_move_m,
            },
        )
        summary = _summarize(con, cfg, Path(prev), Path(curr))
        _gate(summary, cfg)
        result = Result(summary=summary)
        result.changes = _changes(con)
        result.classification = dict(
            con.execute(
                "SELECT id, CASE WHEN considered THEN change_type ELSE 'not_in_study' END "
                "FROM ids ORDER BY id"
            ).fetchall()
        )
        result.excluded_rows = _rows(
            con,
            """
            SELECT side, src_row, id, exclusion_reason, geom_type,
                   round(lon, 6) AS lon, round(lat, 6) AS lat, name
            FROM rows WHERE exclusion_reason IS NOT NULL ORDER BY side, id NULLS FIRST, src_row""",
        )
        result.top_moves = _rows(
            con,
            """
            SELECT id, prev_name, curr_name, round(distance_m, 1) AS distance_m, crossed_aoi_boundary
            FROM ids WHERE considered AND change_type = 'moved'
            ORDER BY distance_m DESC, id LIMIT 10""",
        )
        result.renames = _rows(
            con,
            """
            SELECT id, name_change_kind, prev_name, curr_name, name_matches_brand
            FROM ids WHERE considered AND name_changed ORDER BY name_change_kind, id""",
        )
        result.lifecycle = _rows(
            con,
            """
            SELECT id, curr_name, prev_operating_status, curr_operating_status,
                   prev_confidence, curr_confidence
            FROM ids WHERE considered AND (status_changed OR confidence_to_zero) ORDER BY id""",
        )
        if changelog is not None:
            summary["changelog_check"], result.changelog_mismatches = _changelog_check(
                con, Path(changelog)
            )
        else:
            summary["changelog_check"] = None
        return result
    finally:
        con.close()


def _counts(con: duckdb.DuckDBPyConnection, column: str, keys: list[str]) -> dict[str, int]:
    found = dict(
        con.execute(
            f"SELECT {column}, count(*) FROM ids WHERE considered AND {column} IS NOT NULL GROUP BY 1"  # noqa: S608 - internal column name
        ).fetchall()
    )
    return {k: int(found.get(k, 0)) for k in keys}


def _summarize(
    con: duckdb.DuckDBPyConnection, cfg: Config, prev: Path, curr: Path
) -> dict[str, Any]:
    input_rows, valid_rows, excluded_by_reason = {}, {}, {}
    for side in ("prev", "curr"):
        # R is counted from the source file itself, not from Stage B, so a row lost before Stage B (or a
        # normalisation that filters rows) fails identity 1 instead of shrinking both of its sides (contract §4).
        source = prev if side == "prev" else curr
        input_rows[side] = int(
            _scalar(con, "SELECT count(*) FROM read_parquet($p)", {"p": source.as_posix()})
        )
        valid_rows[side] = int(
            _scalar(
                con,
                "SELECT count(*) FROM rows WHERE side = $s AND exclusion_reason IS NULL",
                {"s": side},
            )
        )
        found = dict(
            con.execute(
                "SELECT exclusion_reason, count(*) FROM rows WHERE side = $s AND exclusion_reason IS NOT NULL "
                "GROUP BY 1",
                {"s": side},
            ).fetchall()
        )
        excluded_by_reason[side] = {r: int(found.get(r, 0)) for r in EXCLUSION_REASONS}

    change_counts = _counts(con, "change_type", CHANGE_TYPES)
    # coalesce(..., 0): count_if returns NULL (not 0) when every flag is NULL, e.g. no matched ids.
    flag_sql = ", ".join(f"coalesce(count_if({f}), 0)" for f in _BOOL_FLAGS)
    flag_sql_full = f"SELECT {flag_sql} FROM ids WHERE considered"  # noqa: S608 - internal column names
    flag_row = _one_row(con, flag_sql_full)
    flag_counts = dict(zip(_BOOL_FLAGS, (int(x) for x in flag_row), strict=True))

    def list_count(column: str, f: str) -> int:
        return int(
            _scalar(
                con,
                f"SELECT count(*) FROM ids WHERE considered "  # noqa: S608 - internal column name
                f"AND list_contains(string_split({column}, ';'), $f)",
                {"f": f},
            )
        )

    enrich_counts = {f: list_count("enrichment_changed", f) for f in ENRICH_FIELDS}
    format_counts = {f: list_count("format_only_changed", f) for f in FORMAT_FIELDS}
    # Stage C counts (what the classification produced). Rows AND distinct ids are both counted:
    # a substituted id (one id replaced by a copy of another) keeps the row count but not the distinct count.
    union_ids = int(_scalar(con, "SELECT count(*) FROM ids"))
    distinct_classified = int(_scalar(con, "SELECT count(DISTINCT id) FROM ids"))
    considered = int(_scalar(con, "SELECT count(*) FROM ids WHERE considered"))
    buffer_only = union_ids - considered
    matched = sum(change_counts[t] for t in ("moved", "attribute_changed", "shifted", "unchanged"))
    excl_rows = {s: sum(excluded_by_reason[s].values()) for s in ("prev", "curr")}
    # Independent baselines from Stage B rows only, using plain set operations and no Stage C
    # table: identities counted from the table they check would still pass if an id were dropped
    # (proven by the fault-injection tests). Grain of every set: one distinct id.
    baseline = _one_row(con, _BASELINE_SQL)
    src = dict(
        zip(
            ["union", "considered", "excluded", "c_curr", "c_prev", "matched"],
            (int(x) for x in baseline),
            strict=True,
        )
    )

    def identity(lhs: int, rhs: int, text: str) -> dict[str, Any]:
        return {"identity": text, "lhs": lhs, "rhs": rhs, "holds": lhs == rhs}

    reconciliation = {
        "rows_prev": identity(
            input_rows["prev"], valid_rows["prev"] + excl_rows["prev"], "R_prev = V_prev + X_prev"
        ),
        "rows_curr": identity(
            input_rows["curr"], valid_rows["curr"] + excl_rows["curr"], "R_curr = V_curr + X_curr"
        ),
        "ids_union": identity(
            src["union"],
            distinct_classified,
            "distinct source ids (Stage B) = distinct classified ids (Stage C)",
        ),
        "ids_unique": identity(
            union_ids,
            distinct_classified,
            "classified rows (Stage C) = distinct classified ids (one row per id)",
        ),
        "ids_considered": identity(
            src["considered"], considered, "study population (Stage B) = considered ids (Stage C)"
        ),
        "ids_partition": identity(
            src["considered"],
            sum(change_counts.values()),
            "study population (Stage B) = sum of change types",
        ),
        "excluded": identity(
            src["excluded"], change_counts["excluded"], "excluded ids in study (Stage B) = excluded"
        ),
        "matched": identity(
            src["matched"],
            matched,
            "valid in both, in study, not excluded (Stage B) = moved + attribute_changed + shifted + unchanged",
        ),
        "curr_side": identity(
            src["c_curr"], change_counts["added"] + matched, "C_curr (Stage B) = added + matched"
        ),
        "prev_side": identity(
            src["c_prev"],
            change_counts["removed"] + matched,
            "C_prev (Stage B) = removed + matched",
        ),
    }
    return {
        "pipeline_version": __version__,
        "contract_version": CONTRACT_VERSION,
        "releases": {"prev": cfg.prev_release, "curr": cfg.curr_release},
        "aoi": cfg.aoi.as_dict(),
        "extraction_bbox": cfg.extraction_bbox.as_dict(),
        "thresholds_m": {
            "minor_move": cfg.minor_move_m,
            "move": cfg.move_threshold_m,
            "major_move": cfg.major_move_m,
        },
        "inputs_sha256": {"prev": sha256(prev), "curr": sha256(curr)},
        "input_rows": input_rows,
        "valid_rows": valid_rows,
        "excluded_rows_by_reason": excluded_by_reason,
        "union_ids": union_ids,
        "considered_ids": considered,
        "buffer_only_ids": buffer_only,
        "change_counts": change_counts,
        "move_band_counts": _counts(con, "move_band", MOVE_BANDS),
        "name_change_kind_counts": _counts(con, "name_change_kind", NAME_CHANGE_KINDS),
        "flag_counts": flag_counts,
        "enrichment_field_counts": enrich_counts,
        "format_only_field_counts": format_counts,
        "reconciliation": reconciliation,
        "interpretation": (
            "Map-record changes between two Overture releases. added != opened, removed != closed, "
            "moved/shifted != the earlier position was wrong, a rename kind != better or worse."
        ),
    }


def _gate(summary: dict[str, Any], cfg: Config) -> None:
    """Contract §6 hard failures (missing files/columns are checked earlier)."""
    failures = []
    for side in ("prev", "curr"):
        rows = summary["input_rows"][side]
        if rows == 0:
            failures.append(f"{side}: 0 rows")
            continue
        share = sum(summary["excluded_rows_by_reason"][side].values()) / rows
        if share > cfg.max_excluded_share:
            failures.append(
                f"{side}: {share:.1%} rows excluded (limit {cfg.max_excluded_share:.0%})"
            )
    for name, ident in summary["reconciliation"].items():
        if not ident["holds"]:
            failures.append(f"reconciliation {name} failed: {ident['lhs']} != {ident['rhs']}")
    if failures:
        raise PipelineError("quality gate failed: " + "; ".join(failures))


def _changes(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """One record per exported id, sorted by id (contract §5)."""
    types = ", ".join(f"'{t}'" for t in EXPORTED_TYPES)
    return _rows(
        con,
        f"""
        SELECT id, change_type, round(distance_m, 1) AS distance_m, move_band,
            prev_name, curr_name, prev_category, curr_category,
            prev_basic_category, curr_basic_category,
            round(prev_lon, 6) AS prev_lon, round(prev_lat, 6) AS prev_lat,
            round(curr_lon, 6) AS curr_lon, round(curr_lat, 6) AS curr_lat,
            prev_operating_status, curr_operating_status, prev_confidence, curr_confidence,
            name_changed, name_change_kind, name_matches_brand, category_changed,
            basic_category_changed, status_changed, confidence_to_zero, enrichment_changed,
            format_only_changed, crossed_aoi_boundary, source_datasets, source_licences
        FROM ids WHERE considered AND change_type IN ({types}) ORDER BY id""",  # noqa: S608 - only the fixed EXPORTED_TYPES constant is interpolated
    )


# Independent Stage B baselines for contract §4 (grain of every CTE: one distinct id).
_BASELINE_SQL = """
        WITH ids_all  AS (SELECT DISTINCT id FROM rows WHERE id IS NOT NULL),
             ex       AS (SELECT DISTINCT id FROM rows WHERE id IS NOT NULL AND exclusion_reason IS NOT NULL),
             study    AS (SELECT DISTINCT id FROM rows WHERE in_aoi),
             ex_loc   AS (SELECT DISTINCT id FROM rows WHERE id IN (SELECT id FROM ex)
                            AND (point_in_aoi OR (exclusion_reason IS NOT NULL AND point_in_aoi IS NULL))),
             cons     AS (SELECT id FROM study UNION SELECT id FROM ex_loc),
             clean    AS (SELECT id FROM cons EXCEPT SELECT id FROM ex),
             v_curr   AS (SELECT DISTINCT id FROM rows WHERE side = 'curr' AND exclusion_reason IS NULL),
             v_prev   AS (SELECT DISTINCT id FROM rows WHERE side = 'prev' AND exclusion_reason IS NULL)
        SELECT (SELECT count(*) FROM ids_all),
               (SELECT count(*) FROM cons),
               (SELECT count(*) FROM (SELECT id FROM cons INTERSECT SELECT id FROM ex)),
               (SELECT count(*) FROM (SELECT id FROM clean INTERSECT SELECT id FROM v_curr)),
               (SELECT count(*) FROM (SELECT id FROM clean INTERSECT SELECT id FROM v_prev)),
               (SELECT count(*) FROM (SELECT id FROM clean INTERSECT SELECT id FROM v_curr
                                      INTERSECT SELECT id FROM v_prev))
        """


# --- §9 changelog oracle --------------------------------------------------------------------
# Each rule = (scope, expectation). Ids in scope are "checked"; checked ids where the expectation
# is not true are mismatches. `o` = GeoTrustOps ids, `cl` = changelog (NULL when the id is absent).
_ORACLE_RULES = {
    "added_is_changelog_added": ("o.change_type = 'added'", "cl.change_type = 'added'"),
    "removed_is_changelog_removed": ("o.change_type = 'removed'", "cl.change_type = 'removed'"),
    "moved_or_shifted_has_geometry_change": (
        "o.change_type IN ('moved', 'shifted')",
        "cl.change_type = 'data_changed' AND list_contains(cl.columns_changed, 'geometry')",
    ),
    "attribute_changed_has_attribute_change": (
        "o.change_type = 'attribute_changed'",
        "cl.change_type = 'data_changed' "
        "AND list_has_any(cl.columns_changed, ['names', 'taxonomy', 'basic_category'])",
    ),
    "changelog_unchanged_is_unchanged": (
        "cl.change_type = 'unchanged' AND o.change_type <> 'excluded'",
        "o.change_type = 'unchanged' AND o.enrichment_changed = '' AND NOT o.status_changed",
    ),
}


def _changelog_check(
    con: duckdb.DuckDBPyConnection, path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not path.exists():
        raise PipelineError(f"changelog file not found: {path}")
    con.execute(
        """CREATE OR REPLACE TABLE changelog AS
        SELECT id, change_type, columns_changed FROM read_parquet($p)""",
        {"p": path.as_posix()},
    )
    dup = int(_scalar(con, "SELECT count(*) - count(DISTINCT id) FROM changelog"))
    rules, mismatches = {}, []
    for name, (scope, expect) in _ORACLE_RULES.items():
        base = f"FROM ids o LEFT JOIN changelog cl USING (id) WHERE o.considered AND ({scope})"
        # coalesce(..., false): an absent changelog row makes the expectation NULL -> a mismatch
        found = _rows(
            con,
            f"""
            SELECT o.id, o.change_type AS geotrustops, cl.change_type AS changelog,
                   array_to_string(cl.columns_changed, ';') AS columns_changed
            {base} AND NOT coalesce({expect}, false) ORDER BY o.id""",
        )  # noqa: S608 - fixed rule text
        checked = int(_scalar(con, f"SELECT count(*) {base}"))  # noqa: S608 - fixed rule text
        rules[name] = {"checked": checked, "mismatches": len(found)}
        mismatches += [{"rule": name, **m} for m in found]
    changelog_types = dict(
        con.execute("""
        SELECT coalesce(cl.change_type, '(absent)'), count(*)
        FROM ids o LEFT JOIN changelog cl USING (id) WHERE o.considered GROUP BY 1 ORDER BY 1""").fetchall()
    )
    crosstab = _rows(
        con,
        """
        SELECT o.change_type AS geotrustops, coalesce(cl.change_type, '(absent)') AS changelog, count(*) AS n
        FROM ids o LEFT JOIN changelog cl USING (id) WHERE o.considered GROUP BY ALL ORDER BY 1, 2""",
    )
    return (
        {
            "changelog_sha256": sha256(path),
            "duplicate_ids_in_changelog": dup,
            "rules": rules,
            "total_mismatches": len(mismatches),
            "changelog_types_for_considered_ids": {k: int(v) for k, v in changelog_types.items()},
            "crosstab": crosstab,
        },
        mismatches,
    )
