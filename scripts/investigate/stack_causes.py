# ruff: noqa: S608 - f-strings insert only the UTM constant and internal filters, never user input
"""Investigation I-1, stage C: assign each stacked cluster a *likely cause* from simple checks.

The cascade, thresholds and order are pre-registered in docs/investigation_backlog.md (I-1, stage C); first match
wins and every cluster is flagged for manual inspection. Overture data only:
places plus divisions, buildings and transportation for the same release (fetch_context_layers.py).

Amended cascade (2026-11-24, recorded before the October run; see the backlog for the reasoning):

  0 cluster: places within 2 m (single-linkage)
  1 duplicates >= 50% (same normalised name or phone)          -> duplicate records (stop)
  2 >= 50% share a base street address with a street number    -> shared address point (+ "unit numbers recorded")
  3 >= 50% postal-box addresses: >= 50% share the same box     -> one institution, shared postal box
                                 otherwise                     -> postal address, no street
  4 10+ places and centre within 50 m of a division point       -> near a town point (likely town-level geocode)
  5 >= 50% town-only addresses                                  -> town-only address
  6 >= 50% of points have <= 4 decimals in lon and lat          -> rounded coordinates
  7 centre inside a building: footprint >= 10,000 m2            -> large building (mall-like), else compact building
  8 centre within 2 m of a connector                            -> intersection geocode
  9 centre within 2 m of a road segment                         -> street-centreline geocode
  otherwise                                                     -> unknown: manual inspection

Usage: python scripts/investigate/stack_causes.py [release]   (default: the configured current release)
"""

from __future__ import annotations

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stacked_coordinates import UNIT  # noqa: E402  (same unit-designator vocabulary as stage A)

from geotrustops.config import load_config  # noqa: E402
from geotrustops.extract import release_path, verify_manifest  # noqa: E402

NEAR_M = 2.0
SHARE = 0.5
TOWN_M, TOWN_MIN_SIZE = (
    50.0,
    10,
)  # suppliers' town points differ by tens of metres; fallbacks gather many places
MALL_M2 = 10_000.0  # floor counts are mostly missing, so footprint area alone stands in for "many entrances"
TOWN_SUBTYPES = ["locality", "localadmin", "borough", "macrohood", "neighborhood", "microhood"]
POSTAL = (
    r"(?i)\b(?:private\s+ba[gy]|p\.?\s?o\.?\s+box|po\s?box|postnet\s+suite|posbus|privaatsak)\b"
)
CORNER = r"(?i)\b(?:cnr|corner)\b"
# Box identity = box type + number, e.g. "Private Bag X680" -> "privatebag x680", "P.O. Box 123" -> "pobox 123".
BOX = (
    r"(?i)\b(private\s+ba[gy]|p\.?\s?o\.?\s+box|po\s?box|postnet\s+suite|posbus|privaatsak)"
    r"\s*(?:no\.?\s*)?([a-z]?\s?\d+)"
)
UTM = "EPSG:32735"  # UTM zone 35S covers the study area; metres for areas and distances
M_PER_DEG_LAT = 110_574.0


def decimals(x: float) -> int:
    """Digits after the decimal point in the shortest repr of the stored double."""
    r = repr(x)
    return len(r.split(".")[1]) if "." in r and "e" not in r else 0


def clusters(points: list[tuple[str, float, float]]) -> dict[str, int]:
    """Single-linkage clusters of points within NEAR_M metres (union-find over a sorted sweep)."""
    parent = list(range(len(points)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(len(points)), key=lambda i: points[i][2])
    dlat = NEAR_M / M_PER_DEG_LAT
    for a, i in enumerate(order):
        _, lon_i, lat_i = points[i]
        m_lon = 111_320.0 * math.cos(math.radians(lat_i))
        for j in order[a + 1 :]:
            _, lon_j, lat_j = points[j]
            if lat_j - lat_i > dlat:
                break
            if math.hypot((lon_j - lon_i) * m_lon, (lat_j - lat_i) * M_PER_DEG_LAT) <= NEAR_M:
                parent[find(i)] = find(j)
    return {points[i][0]: find(i) for i in range(len(points))}


def main(argv: list[str]) -> int:
    cfg = load_config(ROOT / "config" / "study_area.json")
    release = argv[0] if argv else cfg.curr_release
    places = release_path(ROOT / "data" / "raw", release)
    verify_manifest(places, cfg, "release", release)
    ctx = ROOT / "data" / "raw" / "context" / release
    aoi = cfg.raw["aoi"]

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute(
        """CREATE TABLE p AS SELECT id, ST_X(ST_GeomFromWKB(geometry)) AS lon, ST_Y(ST_GeomFromWKB(geometry)) AS lat,
             names."primary" AS name, coalesce(addresses[1].freeform, '') AS addr,
             right(regexp_replace(coalesce(phones[1], ''), '[^0-9]', '', 'g'), 9) AS phone
           FROM read_parquet($path)""",
        {"path": places.as_posix()},
    )
    con.execute(
        "DELETE FROM p WHERE NOT (lon BETWEEN $west AND $east AND lat BETWEEN $south AND $north)",
        {k: float(aoi[k]) for k in ("west", "south", "east", "north")},
    )
    rows = con.execute("SELECT id, lon, lat FROM p ORDER BY id").fetchall()
    cid = clusters(rows)
    con.execute("CREATE TABLE c (id VARCHAR, cluster INTEGER)")
    con.executemany("INSERT INTO c VALUES (?, ?)", list(cid.items()))

    # Per-place features; clusters of 2+ places only.
    con.execute(
        """CREATE TABLE f AS
      WITH j AS (SELECT p.*, c.cluster, count(*) OVER (PARTITION BY c.cluster) AS size FROM p JOIN c USING (id))
      SELECT *,
        nullif(regexp_replace(lower(coalesce(name, '')), '[^a-z0-9]', '', 'g'), '') AS norm_name,
        nullif(phone, '') AS norm_phone,
        regexp_matches(addr || ' ' || coalesce(name, ''), $unit) AS has_unit,
        regexp_matches(addr, $postal) AS postal,
        (addr <> '' AND NOT regexp_matches(addr, '[0-9]')) AS town_only,
        regexp_matches(addr, $corner) AS corner,
        CASE WHEN regexp_matches(addr, $box) THEN
          replace(regexp_replace(lower(regexp_extract(addr, $box, 1)), '[^a-z]', '', 'g'),
                  'privatebay', 'privatebag') || ' '
          || regexp_replace(lower(regexp_extract(addr, $box, 2)), '\\s', '', 'g') END AS box_id,
        nullif(trim(regexp_replace(regexp_replace(lower(regexp_replace(addr, $unit, ' ', 'g')),
               '[^a-z0-9 ]', ' ', 'g'), '\\s+', ' ', 'g')), '') AS base_addr
      FROM j WHERE size >= 2""",
        {"unit": UNIT, "postal": POSTAL, "corner": CORNER, "box": BOX},
    )
    # Step 1: a place is a duplicate if its name or phone occurs more than once in its cluster.
    con.execute(
        """CREATE TABLE d AS SELECT cluster, avg(dup::INT) AS dup_share, bool_or(dup) AS any_dup FROM (
         SELECT cluster, (count(norm_name) OVER (PARTITION BY cluster, norm_name) > 1
                          OR count(norm_phone) OVER (PARTITION BY cluster, norm_phone) > 1) AS dup FROM f)
         GROUP BY cluster"""
    )
    # Step 2: most common base address; a postal-box number is not a street number, so postal bases do not count.
    con.execute(
        """CREATE TABLE b AS SELECT cluster, max(n) AS modal_n FROM (
         SELECT cluster, base_addr, count(*) AS n FROM f
         WHERE base_addr IS NOT NULL AND regexp_matches(base_addr, '[0-9]') AND NOT postal GROUP BY ALL)
         GROUP BY cluster"""
    )
    # Step 3: share of the cluster on its most common postal box (same box = one institution).
    con.execute(
        """CREATE TABLE bx AS SELECT cluster, max(n) AS box_n FROM (
         SELECT cluster, box_id, count(*) AS n FROM f WHERE box_id IS NOT NULL GROUP BY ALL) GROUP BY cluster"""
    )
    con.execute(
        """CREATE TABLE k AS SELECT cluster, count(*) AS size, avg(lon) AS clon, avg(lat) AS clat,
         avg(has_unit::INT) AS unit_share, avg(postal::INT) AS postal_share, avg(town_only::INT) AS town_share,
         bool_or(corner) AS corner, list(lon) AS lons, list(lat) AS lats, list(name ORDER BY name)[1:5] AS names
         FROM f GROUP BY cluster"""
    )

    def ctx_path(t: str) -> str:
        path = ctx / t / "data.parquet"
        if not path.exists():
            raise SystemExit(
                f"missing context layer {path} (run fetch_context_layers.py {release})"
            )
        return path.as_posix()

    con.execute(
        f"""CREATE TABLE kc AS SELECT *,
           ST_Transform(ST_Point(clon, clat), 'EPSG:4326', '{UTM}', always_xy := true) AS g
         FROM k"""
    )
    town = dict(
        con.execute(
            f"""SELECT k.cluster, min(ST_Distance(k.g, ST_Transform(ST_GeomFromWKB(v.geometry), 'EPSG:4326', '{UTM}',
                always_xy := true))) FROM kc k, read_parquet($p) v WHERE v.subtype IN (SELECT unnest($s::VARCHAR[]))
                GROUP BY k.cluster""",
            {"p": ctx_path("division"), "s": TOWN_SUBTYPES},
        ).fetchall()
    )
    bld = {
        r[0]: (r[1], r[2])
        for r in con.execute(
            f"""SELECT k.cluster, max(ST_Area(ST_Transform(ST_GeomFromWKB(b.geometry), 'EPSG:4326', '{UTM}',
                always_xy := true))) AS area, max(b.num_floors) AS floors
                FROM kc k, read_parquet($p) b
                WHERE ST_Contains(ST_GeomFromWKB(b.geometry), ST_Point(k.clon, k.clat)) GROUP BY k.cluster""",
            {"p": ctx_path("building")},
        ).fetchall()
    }

    def nearest(table: str, where: str = "") -> dict[int, float]:
        # Prefilter by a small degree window, then measure in metres.
        return dict(
            con.execute(
                f"""SELECT k.cluster, min(ST_Distance(k.g, ST_Transform(ST_GeomFromWKB(x.geometry), 'EPSG:4326',
                    '{UTM}', always_xy := true)))
                    FROM kc k, read_parquet($p) x
                    WHERE x.bbox.xmin <= k.clon + 0.0005 AND x.bbox.xmax >= k.clon - 0.0005
                      AND x.bbox.ymin <= k.clat + 0.0005 AND x.bbox.ymax >= k.clat - 0.0005 {where}
                    GROUP BY k.cluster""",
                {"p": ctx_path(table)},
            ).fetchall()
        )

    conn = nearest("connector")
    road = nearest("segment", "AND x.subtype = 'road'")

    ks = con.execute(
        """SELECT k.cluster, k.size, k.clon, k.clat, k.unit_share, k.postal_share, k.town_share, k.corner,
                  k.lons, k.lats, k.names, coalesce(b.modal_n, 0) / k.size AS base_share,
                  coalesce(bx.box_n, 0) / k.size AS box_share, d.dup_share, d.any_dup
           FROM k LEFT JOIN b USING (cluster) LEFT JOIN bx USING (cluster) LEFT JOIN d USING (cluster)
           ORDER BY k.size DESC, k.cluster"""
    ).fetchall()
    con.close()

    results = []
    floors_unknown = 0
    for (
        cl,
        size,
        clon,
        clat,
        unit_s,
        postal_s,
        town_s,
        corner,
        lons,
        lats,
        names,
        base_s,
        box_s,
        dup_s,
        any_dup,
    ) in ks:
        cause = None
        if dup_s >= SHARE:
            cause = "duplicate records"
        elif base_s >= SHARE:
            cause = "shared address point" + (" (unit numbers recorded)" if unit_s >= SHARE else "")
        elif postal_s >= SHARE:
            cause = (
                "one institution, shared postal box"
                if box_s >= SHARE
                else "postal address, no street"
            )
        elif size >= TOWN_MIN_SIZE and town.get(cl, math.inf) <= TOWN_M:
            cause = "near a town point (likely town-level geocode)"
        elif town_s >= SHARE:
            cause = "town-only address"
        elif (
            sum(decimals(x) <= 4 and decimals(y) <= 4 for x, y in zip(lons, lats, strict=True))
            >= SHARE * size
        ):
            cause = "rounded coordinates"
        elif cl in bld:
            area, floors = bld[cl]
            floors_unknown += floors is None
            cause = "large building (mall-like)" if area >= MALL_M2 else "one compact building"
        elif conn.get(cl, math.inf) <= NEAR_M:
            cause = "intersection geocode" + (" (address says corner)" if corner else "")
        elif road.get(cl, math.inf) <= NEAR_M:
            cause = "street-centreline geocode"
        else:
            cause = "unknown: manual inspection"
        results.append(
            (cl, size, clon, clat, cause, bool(any_dup) and cause != "duplicate records", names)
        )

    clusters_by = Counter(r[4] for r in results)
    places_by: defaultdict[str, int] = defaultdict(int)
    for r in results:
        places_by[r[4]] += r[1]
    total_places = sum(r[1] for r in results)
    print(
        f"release {release}: {len(rows)} places in AOI; {len(results)} clusters (>= 2 places within {NEAR_M:g} m) "
        f"holding {total_places} places"
    )
    print(
        "likely cause | clusters | places | % of clustered places   (all: manual inspection recommended)"
    )
    for cause, n in sorted(places_by.items(), key=lambda kv: -kv[1]):
        print(f"  {cause} | {clusters_by[cause]} | {n} | {n / total_places:.1%}")
    print(f"clusters that also contain duplicates: {sum(r[5] for r in results)}")
    n_bld = sum(
        1 for r in results if r[4] in ("large building (mall-like)", "one compact building")
    )
    print(f"building matches with unknown floors: {floors_unknown} of {n_bld}")
    print("10 largest clusters:")
    for _cl, size, clon, clat, cause, dup, names in results[:10]:
        flag = " +duplicates" if dup else ""
        print(
            f"  {size:>3} at ({clon:.6f}, {clat:.6f}): {cause}{flag}; e.g. {' | '.join(n or '' for n in names[:3])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
