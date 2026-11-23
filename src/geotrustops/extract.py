"""Download pinned Overture extracts (releases + changelog) and verify them later.

Purpose: get small, unmodified, provenance-tracked local copies for the extraction bbox
(AOI + buffer). Adapted from open-map-quality-lake/src/omql/ingest/overture.py:
bbox-overlap filter with Parquet predicate pushdown, temp file + rename, 0 rows = error.

Layout (data/raw is git-ignored):
    data/raw/releases/<release>/places.parquet (+ manifest.json)
    data/raw/changelog/<release>/places_changelog.parquet (+ manifest.json)

The spatial extension is deliberately NOT loaded here, so `geometry` is stored as plain
WKB bytes exactly as delivered; the pipeline decodes it (it accepts BLOB or GEOMETRY).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import duckdb

from geotrustops.config import BBox, Config


class ExtractError(RuntimeError):
    """A download produced no rows, failed, or a manifest does not match its file."""


def release_path(raw_dir: Path, release: str) -> Path:
    return raw_dir / "releases" / release / "places.parquet"


def changelog_path(raw_dir: Path, release: str) -> Path:
    return raw_dir / "changelog" / release / "places_changelog.parquet"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest_path(data_file: Path) -> Path:
    return data_file.parent / "manifest.json"


def _bbox_where(b: BBox) -> str:
    # Floats come from the validated config, not user SQL; repr() keeps full precision.
    return (
        f"bbox.xmin <= {b.east!r} AND bbox.xmax >= {b.west!r} "
        f"AND bbox.ymin <= {b.north!r} AND bbox.ymax >= {b.south!r}"
    )


def _download(
    con: duckdb.DuckDBPyConnection, uri: str, select: str, bbox: BBox, out: Path, meta: dict
) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    started = dt.datetime.now(dt.UTC)
    # Both the source URI and the COPY target are *named* bound parameters, so paths containing
    # quotes cannot break or inject into the SQL (DuckDB 1.4.2 binds COPY targets; positional `?`
    # on 1.1.3 did not parse). `select` and the bbox floats are internal constants, never user text.
    try:
        con.execute(
            f"COPY (SELECT {select} FROM read_parquet($uri, hive_partitioning = true) "  # noqa: S608
            f"WHERE {_bbox_where(bbox)} ORDER BY id) TO $dest (FORMAT parquet, COMPRESSION zstd)",
            {"uri": uri, "dest": tmp.as_posix()},
        )
        row = con.execute("SELECT count(*) FROM read_parquet($p)", {"p": tmp.as_posix()}).fetchone()
    except duckdb.Error as exc:
        tmp.unlink(missing_ok=True)
        raise ExtractError(f"could not read {uri}: {exc}") from exc
    rows = int(row[0]) if row else 0
    if rows == 0:
        tmp.unlink(missing_ok=True)
        raise ExtractError(f"0 rows from {uri} for {bbox}: treated as failure, not empty success")
    tmp.replace(out)
    manifest = {
        **meta,
        "source_uri": uri,
        "extraction_bbox": bbox.as_dict(),
        "filter": "Overture bbox struct overlaps extraction_bbox",
        "row_count": rows,
        "file": out.name,
        "sha256": sha256(out),
        "bytes": out.stat().st_size,
        "extracted_utc": started.isoformat(timespec="seconds"),
        "duckdb_version": duckdb.__version__,
    }
    _manifest_path(out).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def fetch(cfg: Config, raw_dir: Path, force: bool = False) -> list[dict]:
    """Download both releases and the curr changelog unless already present."""
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region = $r", {"r": cfg.s3_region})
    bbox = cfg.extraction_bbox
    jobs = [
        (
            release_path(raw_dir, rel),
            cfg.release_uri.format(release=rel),
            "*",
            {"kind": "release", "release": rel},
        )
        for rel in (cfg.prev_release, cfg.curr_release)
    ]
    jobs.append(
        (
            changelog_path(raw_dir, cfg.curr_release),
            cfg.changelog_uri.format(release=cfg.curr_release),
            "id, change_type, columns_changed, bbox",
            {"kind": "changelog", "release": cfg.curr_release},
        )
    )
    results = []
    try:
        for out, uri, select, meta in jobs:
            if out.exists() and not force:
                print(f"skip: {out} exists (use --force to re-download)")
                results.append(json.loads(_manifest_path(out).read_text(encoding="utf-8")))
                continue
            m = _download(con, uri, select, bbox, out, meta)
            print(f"{meta['kind']} {meta['release']}: {m['row_count']} rows -> {out}")
            results.append(m)
    finally:
        con.close()
    return results


def verify_manifest(data_file: Path, cfg: Config, kind: str, release: str) -> dict:
    """Fail if the file is missing, altered, or was extracted for another release/bbox."""
    mpath = _manifest_path(data_file)
    if not data_file.exists() or not mpath.exists():
        raise ExtractError(f"missing input or manifest: {data_file} (run `geotrustops fetch`)")
    m = json.loads(mpath.read_text(encoding="utf-8"))
    problems = []
    if m.get("kind") != kind or m.get("release") != release:
        problems.append(f"manifest is for {m.get('kind')} {m.get('release')}")
    if m.get("extraction_bbox") != cfg.extraction_bbox.as_dict():
        problems.append("extraction bbox differs from config (stale extract?)")
    if sha256(data_file) != m.get("sha256"):
        problems.append("sha256 differs from manifest (file changed since download)")
    if problems:
        raise ExtractError(f"{data_file}: " + "; ".join(problems))
    return m
