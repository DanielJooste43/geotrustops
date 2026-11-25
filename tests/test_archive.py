"""Archive fallback for pinned extracts that Overture no longer serves (S3 keeps 60 days).

Offline: the archive is a local folder behind a stand-in fetcher; no network, no token.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from geotrustops.cli import main
from geotrustops.config import Config, load_config
from geotrustops.extract import (
    ARCHIVE_REPO_ENV,
    ARCHIVE_TOKEN_ENV,
    ExtractError,
    _request,
    changelog_path,
    fetch,
    load_archive,
    release_path,
    sha256,
    verify_manifest,
)
from tests.conftest import RAW, ROOT, place, write_config
from tests.fixtures.make_fixture import write_changelog, write_places

ARCHIVE_JSON = ROOT / "data" / "archive.json"


def _jobs(cfg: Config) -> list[tuple[str, str, str]]:
    """(kind, release, asset name) for every file `fetch` needs for this config."""
    return [
        ("release", cfg.prev_release, f"places_{cfg.prev_release}.parquet"),
        ("release", cfg.curr_release, f"places_{cfg.curr_release}.parquet"),
        ("changelog", cfg.curr_release, f"places_changelog_{cfg.curr_release}.parquet"),
    ]


@pytest.fixture
def archive(tmp_path: Path) -> tuple[Config, Path, Path]:
    """A config whose S3 URIs do not exist, plus a local archive and its manifest."""
    cfg = load_config(
        write_config(
            tmp_path / "cfg.json",
            source={
                "release_uri": (tmp_path / "gone" / "{release}" / "*.parquet").as_posix(),
                "changelog_uri": (tmp_path / "gone" / "cl-{release}" / "*.parquet").as_posix(),
            },
        )
    )
    store = tmp_path / "store"
    files: list[dict[str, Any]] = []
    for kind, rel, asset in _jobs(cfg):
        if kind == "release":
            write_places(store / asset, [place("a"), place("b")])
        else:
            write_changelog(store / asset, [{"id": "a", "change_type": "unchanged"}])
        files.append(
            {
                "asset": asset,
                "kind": kind,
                "release": rel,
                "extraction_bbox": cfg.extraction_bbox.as_dict(),
                "row_count": 2 if kind == "release" else 1,
                "sha256": sha256(store / asset),
                "bytes": (store / asset).stat().st_size,
            }
        )
    manifest = tmp_path / "archive.json"
    manifest.write_text(json.dumps({"archive_tag": "t1", "files": files}), encoding="utf-8")
    return cfg, store, manifest


def _local(store: Path, calls: list[str] | None = None):
    def get(name: str, dest: Path) -> None:
        if calls is not None:
            calls.append(name)
        shutil.copyfile(store / name, dest)

    return get


def test_auto_falls_back_to_the_archive_when_s3_has_no_files(tmp_path: Path, archive):
    cfg, store, manifest = archive
    raw = tmp_path / "raw"
    calls: list[str] = []
    out = fetch(cfg, raw, archive=manifest, fetch_asset=_local(store, calls))
    assert calls == [asset for _, _, asset in _jobs(cfg)]
    assert all("restored_from" in m for m in out)
    # The restored files pass the same manifest gate as an S3 download.
    verify_manifest(release_path(raw, cfg.prev_release), cfg, "release", cfg.prev_release)
    verify_manifest(release_path(raw, cfg.curr_release), cfg, "release", cfg.curr_release)
    verify_manifest(changelog_path(raw, cfg.curr_release), cfg, "changelog", cfg.curr_release)


def test_a_file_that_differs_from_the_manifest_is_rejected_and_not_kept(tmp_path: Path, archive):
    cfg, store, manifest = archive
    target = store / f"places_{cfg.prev_release}.parquet"
    target.write_bytes(target.read_bytes()[:-1] + b"\x00")  # same size, different bytes
    raw = tmp_path / "raw"
    with pytest.raises(ExtractError, match="does not match"):
        fetch(cfg, raw, source="archive", archive=manifest, fetch_asset=_local(store))
    out = release_path(raw, cfg.prev_release)
    assert not out.exists()
    assert not out.with_suffix(".parquet.tmp").exists()
    assert not (out.parent / "manifest.json").exists()


def test_archive_entry_for_another_bbox_is_rejected(tmp_path: Path, archive):
    cfg, store, manifest = archive
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["files"][0]["extraction_bbox"]["west"] -= 0.5
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ExtractError, match="another bbox"):
        fetch(cfg, tmp_path / "raw", source="archive", archive=manifest, fetch_asset=_local(store))


def test_s3_only_does_not_touch_the_archive(tmp_path: Path, archive):
    cfg, store, manifest = archive
    calls: list[str] = []
    with pytest.raises(ExtractError, match="could not read"):
        fetch(
            cfg, tmp_path / "raw", source="s3", archive=manifest, fetch_asset=_local(store, calls)
        )
    assert calls == []


def test_archive_without_credentials_fails_with_a_clear_message(
    tmp_path: Path, archive, monkeypatch: pytest.MonkeyPatch
):
    cfg, _, manifest = archive
    monkeypatch.delenv(ARCHIVE_REPO_ENV, raising=False)
    monkeypatch.delenv(ARCHIVE_TOKEN_ENV, raising=False)
    with pytest.raises(ExtractError, match=ARCHIVE_TOKEN_ENV):
        fetch(cfg, tmp_path / "raw", source="archive", archive=manifest)


def test_cli_reports_a_missing_archive_release_as_a_gate_failure(tmp_path: Path, archive):
    cfg_path = tmp_path / "cfg.json"
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"archive_tag": "t1", "files": []}), encoding="utf-8")
    args = ["fetch", "--source", "archive", "--archive", str(empty)]
    assert main(["--config", str(cfg_path), "--raw-dir", str(tmp_path / "raw"), *args]) == 2


def test_token_is_not_forwarded_on_redirect():
    req = _request("https://api.github.com/x", "secret-token", "application/octet-stream")
    assert req.unredirected_hdrs.get("Authorization") == "Bearer secret-token"
    assert "Authorization" not in req.headers  # urllib copies only these to the redirect target
    with pytest.raises(ExtractError, match="non-HTTPS"):
        _request("http://example.org/x", "t", "*/*")


# --- the committed manifest -------------------------------------------------------------------


def test_committed_manifest_covers_every_configured_pair():
    _, files = load_archive(ARCHIVE_JSON)
    have = {(f["kind"], f["release"]) for f in files}
    for cfg_file in sorted((ROOT / "config").glob("*.json")):
        if (
            cfg_file.name == "timeline.json"
        ):  # changelog list, not a release pair; Overture keeps changelogs
            continue
        cfg = load_config(cfg_file)
        for kind, rel, asset in _jobs(cfg):
            assert (kind, rel) in have, f"{cfg_file.name}: {kind} {rel} not archived"
            entry = next(f for f in files if (f["kind"], f["release"]) == (kind, rel))
            assert entry["asset"] == asset
            assert entry["extraction_bbox"] == cfg.extraction_bbox.as_dict()
            assert len(entry["sha256"]) == 64 and entry["bytes"] > 0


@pytest.mark.realdata
def test_committed_manifest_matches_the_local_extracts():
    # A plain `geotrustops fetch` gets only the primary pair, so check whichever extracts exist.
    _, files = load_archive(ARCHIVE_JSON)
    checked = 0
    for f in files:
        sub = "releases" if f["kind"] == "release" else "changelog"
        name = "places.parquet" if f["kind"] == "release" else "places_changelog.parquet"
        path = RAW / sub / f["release"] / name
        if path.exists():
            assert sha256(path) == f["sha256"], path
            checked += 1
    if checked == 0:
        pytest.skip("no pinned extracts present in data/raw")
