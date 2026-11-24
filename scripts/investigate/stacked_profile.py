# ruff: noqa: S608, E501 - f-strings insert only internal table names, the fixed AOI filter and the group order;
# every value (file paths, regexes, category lists) is a named parameter.
"""I-1 exploratory profile of stack groups (descriptive only; no thresholds depend on it).

Run from the repo root: python scripts/investigate/stacked_profile.py
"""

import sys

import duckdb

sys.path.insert(0, "scripts/investigate")
sys.path.insert(0, "src")
import stacked_coordinates as sc  # noqa: E402

P_NOV = "data/raw/releases/2026-11-18.0/places.parquet"
P_OCT = "data/raw/releases/2026-10-21.0/places.parquet"
AOI = "lon BETWEEN 28.168 AND 28.205 AND lat BETWEEN -25.758 AND -25.732"

c = duckdb.connect()
c.execute("LOAD spatial")


def base(path: str, name: str) -> None:
    c.execute(
        f"""CREATE OR REPLACE TABLE {name} AS
      SELECT id, ST_X(ST_GeomFromWKB(geometry)) AS lon, ST_Y(ST_GeomFromWKB(geometry)) AS lat,
             names."primary" AS name, coalesce(addresses[1].freeform, '') AS addr,
             addresses[1].locality AS locality, addresses[1].postcode AS postcode,
             basic_category AS cat, taxonomy.hierarchy[1] AS top_cat, confidence, operating_status,
             coalesce(len(websites),0) AS n_web, coalesce(len(phones),0) AS n_phone, coalesce(len(emails),0) AS n_email, coalesce(len(socials),0) AS n_social,
             brand.names."primary" AS brand_name,
             list_transform(sources, s -> s.dataset) AS datasets,
             list_transform(sources, s -> s.update_time) AS updates,
             CAST(geometry AS BLOB) AS wkb
      FROM read_parquet($path)""",
        {"path": path},
    )
    c.execute(f"DELETE FROM {name} WHERE NOT ({AOI})")


base(P_NOV, "nov")
base(P_OCT, "octo")

# Stage A class per stack (same rules as the committed script).
c.execute(
    """CREATE TABLE s AS
  WITH st AS (SELECT *, count(*) OVER (PARTITION BY lon, lat) AS size FROM nov),
  f AS (SELECT *, regexp_matches(addr || ' ' || coalesce(name, ''), $u) AS has_unit,
          nullif(trim(regexp_replace(regexp_replace(lower(regexp_replace(addr, $u, ' ', 'g')), '[^a-z0-9 ]', ' ', 'g'),
                 '\\s+', ' ', 'g')), '') AS base_addr,
          regexp_matches(coalesce(name, '') || ' ' || addr, $s) AS strong,
          coalesce(cat IN (SELECT unnest($unfit::VARCHAR[])) OR top_cat = 'geographic_entities', false) AS unfit
        FROM st),
  m AS (SELECT lon, lat, max(n) AS modal_n FROM (SELECT lon, lat, base_addr, count(*) n FROM f
        WHERE base_addr IS NOT NULL AND size >= 2 GROUP BY ALL) GROUP BY ALL),
  a AS (SELECT lon, lat, any_value(size) AS size, avg(has_unit::INT) AS us, bool_or(strong) AS sa,
          avg(unfit::INT) AS uf FROM f WHERE size >= 2 GROUP BY lon, lat)
  SELECT a.lon, a.lat, a.size,
    CASE WHEN coalesce(m.modal_n, 0) / a.size >= 0.5 THEN 'H2'
         WHEN a.us >= 0.5 OR (a.sa AND a.uf <= 0.1) THEN 'H1' ELSE 'H0' END AS cls
  FROM a LEFT JOIN m USING (lon, lat)""",
    {"u": sc.UNIT, "s": sc.STRONG, "unfit": sc.UNFIT},
)
c.execute("""CREATE TABLE g AS
  SELECT n.*, coalesce(s.cls, 'single') AS grp, coalesce(s.size, 1) AS size,
    CASE WHEN n.addr = '' THEN 'none'
         WHEN NOT regexp_matches(n.addr, '\\d') THEN 'no number (town/suburb only)'
         ELSE 'has a number' END AS addr_form,
    length(split_part(CAST(round(n.lon, 8) AS VARCHAR), '.', 2)) AS lon_dp,
    length(split_part(CAST(round(n.lat, 8) AS VARCHAR), '.', 2)) AS lat_dp
  FROM nov n LEFT JOIN s USING (lon, lat)""")

GROUPS = "CASE grp WHEN 'H2' THEN 1 WHEN 'H1' THEN 2 WHEN 'H0' THEN 3 ELSE 4 END"


def show(title: str, sql: str) -> None:
    print(f"\n== {title}")
    cur = c.execute(sql)
    cols = [d[0] for d in cur.description]
    print("  " + " | ".join(cols))
    for r in cur.fetchall():
        print("  " + " | ".join(f"{v:.2f}" if isinstance(v, float) else str(v) for v in r))


show(
    "groups",
    f"SELECT grp, count(DISTINCT (lon, lat)) AS points, count(*) AS places, median(size) AS med_size, max(size) AS max_size FROM g GROUP BY grp ORDER BY {GROUPS}",
)
show(
    "address form (% of group)",
    f"""SELECT grp, round(100*avg((addr_form='has a number')::INT),1) AS pct_number,
  round(100*avg((addr_form LIKE 'no number%')::INT),1) AS pct_town_only, round(100*avg((addr_form='none')::INT),1) AS pct_none,
  round(100*avg((postcode IS NULL)::INT),1) AS pct_no_postcode FROM g GROUP BY grp ORDER BY {GROUPS}""",
)
show(
    "coordinate precision: share of places with <= 5 decimals in both lon and lat",
    f"""SELECT grp,
  round(100*avg((lon_dp <= 5 AND lat_dp <= 5)::INT),1) AS pct_le5dp, round(100*avg((lon_dp <= 4 AND lat_dp <= 4)::INT),1) AS pct_le4dp,
  median(greatest(lon_dp, lat_dp)) AS med_dp FROM g GROUP BY grp ORDER BY {GROUPS}""",
)
show(
    "source datasets (% of group's places that include each)",
    f"""SELECT grp,
  round(100*avg(list_contains(datasets,'meta')::INT),1) AS meta, round(100*avg(list_contains(datasets,'Foursquare')::INT),1) AS foursquare,
  round(100*avg(list_contains(datasets,'Microsoft')::INT),1) AS microsoft, round(100*avg(list_contains(datasets,'AllThePlaces')::INT),1) AS alltheplaces,
  round(100*avg((len(list_filter(datasets, d -> d NOT IN ('Overture'))) >= 2)::INT),1) AS multi_source
  FROM g GROUP BY grp ORDER BY {GROUPS}""",
)
show(
    "confidence and completeness",
    f"""SELECT grp, round(median(confidence),2) AS med_conf, round(100*avg((confidence < 0.5)::INT),1) AS pct_conf_lt_05,
  round(100*avg((n_web > 0)::INT),1) AS pct_web, round(100*avg((n_phone > 0)::INT),1) AS pct_phone,
  round(100*avg((n_social > 0)::INT),1) AS pct_social, round(100*avg((brand_name IS NOT NULL)::INT),1) AS pct_brand
  FROM g GROUP BY grp ORDER BY {GROUPS}""",
)
show(
    "top-level category (% of group)",
    """PIVOT (SELECT grp, coalesce(top_cat,'(none)') AS tc FROM g) ON grp USING count(*) GROUP BY tc ORDER BY "H0" DESC NULLS LAST""",
)
show(
    "most common basic categories in stacked groups",
    """SELECT grp, list(cat || ' ' || n ORDER BY n DESC)[1:6] AS top_categories FROM
  (SELECT grp, coalesce(cat,'(none)') AS cat, count(*) n FROM g WHERE grp <> 'single' GROUP BY ALL) GROUP BY grp ORDER BY grp""",
)
show(
    "source record recency (latest source update year)",
    f"""SELECT grp, list(y || ':' || n ORDER BY y) AS by_year FROM
  (SELECT grp, substr(list_max(updates), 1, 4) AS y, count(*) n FROM g GROUP BY ALL) GROUP BY grp ORDER BY {GROUPS}""",
)
show(
    "persistence: were these places at the same point in October?",
    f"""SELECT g.grp, count(*) AS places,
  round(100*avg((o.id IS NOT NULL)::INT),1) AS pct_in_oct,
  round(100*avg((o.lon = g.lon AND o.lat = g.lat)::INT),1) AS pct_same_point,
  round(100*avg((o.id IS NULL)::INT),1) AS pct_new_in_nov
  FROM g LEFT JOIN octo o USING (id) GROUP BY g.grp ORDER BY {GROUPS.replace("grp", "g.grp")}""",
)

show(
    "duplicates and missing category",
    f"""WITH d AS (SELECT *, count(*) OVER (PARTITION BY lon, lat, lower(trim(name))) AS same_name_here FROM g)
  SELECT grp, round(100*avg((same_name_here > 1)::INT),1) AS pct_dup_name_same_point,
  round(100*avg((cat IS NULL)::INT),1) AS pct_no_category, round(100*avg((n_email > 0)::INT),1) AS pct_email
  FROM d GROUP BY grp ORDER BY {GROUPS}""",
)
show(
    "libraries in stacks: names",
    """SELECT grp, size, list(name ORDER BY name)[1:8] AS names FROM g
  WHERE cat = 'library' AND grp <> 'single' GROUP BY grp, size, lon, lat ORDER BY size DESC LIMIT 4""",
)

POSTAL = r"(?i)\b(private\s+ba[gy]|p\.?\s?o\.?\s+box|po\s?box|postnet\s+suite|posbus|privaatsak)\b"
show(
    "postal-box addresses (cannot be geocoded to a street)",
    f"""SELECT grp, count(*) AS places,
  count(*) FILTER (WHERE regexp_matches(addr, '{POSTAL}')) AS n_postal,
  round(100*avg(regexp_matches(addr, '{POSTAL}')::INT),1) AS pct_postal FROM g GROUP BY grp ORDER BY {GROUPS}""",
)
show(
    "largest stacks: postal / town-only / street-number shares",
    """SELECT round(lon,6) lon, round(lat,6) lat, any_value(size) size, any_value(grp) grp,
  round(100*avg(regexp_matches(addr, '"""
    + POSTAL
    + """')::INT)) pct_postal,
  round(100*avg((addr_form LIKE 'no number%')::INT)) pct_town_only, round(100*avg((addr_form='has a number')::INT)) pct_number,
  round(100*avg((lon_dp<=4 AND lat_dp<=4)::INT)) pct_4dp,
  list_filter(list_distinct(flatten(list(datasets))), d -> d <> 'Overture') sources
  FROM g WHERE size >= 10 GROUP BY lon, lat ORDER BY size DESC""",
)
