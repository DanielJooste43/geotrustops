"""Download pinned Overture extracts (releases + changelog) and verify them later.

Purpose: get small, unmodified, provenance-tracked local copies for the extraction bbox
(AOI + buffer). Adapted from open-map-quality-lake/src/omql/ingest/overture.py:
bbox-overlap filter with Parquet predicate pushdown, temp file + rename, 0 rows = error.

Layout (data/raw is git-ignored):
    data/raw/releases/<release>/places.parquet (+ manifest.json)
    data/raw/changelog/<release>/places_changelog.parquet (+ manifest.json)

The spatial extension is deliberately NOT loaded here, so `geometry` is stored as plain
WKB bytes exactly as delivered; the pipeline decodes it (it accepts BLOB or GEOMETRY).

Archive fallback: Overture keeps a release on S3 for at most 60 days. `data/archive.json`
(committed) lists every pinned extract with its SHA-256; the files themselves sit in a
private archive (GitHub release assets). When S3 no longer serves a release, `fetch`
restores the file from that archive and accepts it only if size and SHA-256 match the
committed manifest. Repository and token come from the environment, never from files.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import duckdb

from geotrustops.config import BBox, Config

ARCHIVE_REPO_ENV = "GEOTRUSTOPS_ARCHIVE_REPO"  # "<account>/<repo>" of the private archive
ARCHIVE_TOKEN_ENV = "GEOTRUSTOPS_ARCHIVE_TOKEN"  # noqa: S105 - variable name, not a secret
Source = Literal["auto", "s3", "archive"]
# Downloads one archive asset (by name) to the given path.
AssetFetcher = Callable[[str, Path], None]


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


def download(
    con: duckdb.DuckDBPyConnection,
    uri: str,
    select: str,
    bbox: BBox,
    out: Path,
    meta: dict[str, Any],
) -> dict[str, Any]:
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


def s3_connection(cfg: Config) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection that can read Overture's public bucket (anonymous, httpfs)."""
    c = duckdb.connect()
    try:
        c.execute("INSTALL httpfs; LOAD httpfs;")
        c.execute("SET s3_region = $r", {"r": cfg.s3_region})
    except duckdb.Error as exc:  # e.g. offline: the extension cannot be installed
        c.close()
        raise ExtractError(f"cannot prepare S3 access: {exc}") from exc
    return c


def load_archive(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Read the committed archive manifest: (release tag, file entries)."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return str(doc["archive_tag"]), list(doc["files"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ExtractError(f"cannot read archive manifest {path}: {exc}") from exc


def _request(url: str, token: str, accept: str) -> urllib.request.Request:
    if not url.startswith("https://"):
        raise ExtractError(f"refusing non-HTTPS archive URL: {url}")
    headers = {"Accept": accept, "User-Agent": "geotrustops"}
    req = urllib.request.Request(url, headers=headers)  # noqa: S310 - scheme checked above
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    # Unredirected: asset downloads redirect to a pre-signed storage URL, which must not receive
    # the token (it would leak it, and the storage service rejects a second credential).
    req.add_unredirected_header("Authorization", f"Bearer {token}")
    return req


def github_asset_fetcher(repo: str, tag: str, token: str) -> AssetFetcher:
    """Fetch assets of release `tag` in the (private) GitHub repository `repo`."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ExtractError(f"{ARCHIVE_REPO_ENV} must look like <account>/<repo>, got {repo!r}")
    assets: dict[str, str] = {}

    def _get(name: str, dest: Path) -> None:
        try:
            if not assets:
                api = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
                listing = _request(api, token, "application/vnd.github+json")
                with urllib.request.urlopen(listing) as r:  # noqa: S310 - HTTPS checked in _request
                    assets.update({a["name"]: a["url"] for a in json.load(r)["assets"]})
            if name not in assets:
                raise ExtractError(f"archive release {tag} has no asset {name}")
            download = _request(assets[name], token, "application/octet-stream")
            with urllib.request.urlopen(download) as r, dest.open("wb") as f:  # noqa: S310
                shutil.copyfileobj(r, f)
        except urllib.error.HTTPError as exc:  # the message never contains the token
            raise ExtractError(f"archive download of {name} failed: HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ExtractError(f"archive download of {name} failed: {exc}") from exc

    return _get


def _fetcher_from_env(tag: str) -> AssetFetcher:
    repo, token = os.environ.get(ARCHIVE_REPO_ENV), os.environ.get(ARCHIVE_TOKEN_ENV)
    if not repo or not token:
        raise ExtractError(
            f"the archive needs {ARCHIVE_REPO_ENV} and {ARCHIVE_TOKEN_ENV}; "
            "access is available on request (README, Reproducibility)"
        )
    return github_asset_fetcher(repo, tag, token)


def restore_from_archive(
    entry: dict[str, Any], tag: str, bbox: BBox, out: Path, fetch_asset: AssetFetcher
) -> dict[str, Any]:
    """Download one archived extract; keep it only if size and SHA-256 match the manifest."""
    if entry.get("extraction_bbox") != bbox.as_dict():
        raise ExtractError(f"archived {entry['asset']} was extracted for another bbox")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    try:
        fetch_asset(entry["asset"], tmp)
        size, digest = tmp.stat().st_size, sha256(tmp)
        if size != entry["bytes"] or digest != entry["sha256"]:
            raise ExtractError(
                f"archived {entry['asset']} does not match data/archive.json "
                f"({size} B, sha256 {digest[:12]}...): rejected"
            )
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out)
    manifest = {
        **{k: v for k, v in entry.items() if k != "asset"},
        "file": out.name,
        "restored_from": f"archive release {tag}, asset {entry['asset']}",
    }
    _manifest_path(out).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def fetch(
    cfg: Config,
    raw_dir: Path,
    force: bool = False,
    source: Source = "auto",
    archive: Path | None = None,
    fetch_asset: AssetFetcher | None = None,
) -> list[dict[str, Any]]:
    """Get both releases and the curr changelog unless already present.

    source: "s3" reads Overture only; "archive" restores from the archive only; "auto" reads
    S3 and falls back to the archive for any file S3 cannot provide.
    """
    bbox = cfg.extraction_bbox
    archive_tag: str | None = None
    archive_files: list[dict[str, Any]] = []

    def from_archive(out: Path, kind: str, release: str) -> dict[str, Any]:
        nonlocal archive_tag, archive_files, fetch_asset
        if archive_tag is None:
            archive_tag, archive_files = load_archive(
                archive or Path.cwd() / "data" / "archive.json"
            )
        entry = next(
            (e for e in archive_files if e.get("kind") == kind and e.get("release") == release),
            None,
        )
        if entry is None:
            raise ExtractError(f"no archived {kind} for release {release} in the archive manifest")
        if fetch_asset is None:
            fetch_asset = _fetcher_from_env(archive_tag)
        return restore_from_archive(entry, archive_tag, bbox, out, fetch_asset)

    con: duckdb.DuckDBPyConnection | None = None

    def connect() -> duckdb.DuckDBPyConnection:
        nonlocal con
        if con is None:
            con = s3_connection(cfg)
        return con

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
            kind, release = meta["kind"], meta["release"]
            if source == "archive":
                m = from_archive(out, kind, release)
            else:
                try:
                    m = download(connect(), uri, select, bbox, out, meta)
                except ExtractError as exc:
                    if source == "s3":
                        raise
                    print(f"S3 could not provide {kind} {release} ({exc}); trying the archive")
                    m = from_archive(out, kind, release)
            print(f"{kind} {release}: {m['row_count']} rows -> {out}")
            results.append(m)
    finally:
        if con is not None:
            con.close()
    return results


def verify_manifest(data_file: Path, cfg: Config, kind: str, release: str) -> dict[str, Any]:
    """Fail if the file is missing, altered, or was extracted for another release/bbox."""
    mpath = _manifest_path(data_file)
    if not data_file.exists() or not mpath.exists():
        raise ExtractError(f"missing input or manifest: {data_file} (run `geotrustops fetch`)")
    m: dict[str, Any] = json.loads(mpath.read_text(encoding="utf-8"))
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
