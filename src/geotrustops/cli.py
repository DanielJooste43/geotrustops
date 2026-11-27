"""Command line: `geotrustops fetch`, `geotrustops build` (contract §10) and `geotrustops timeline` (§12).

Exit codes: 0 success; 2 the run failed (bad config, missing, altered or unreadable input, QA or reconciliation
failure, an output that could not be put in place) and no output was replaced. One exception (contract §6): if the
run history cannot be read, the new outputs stay in place and the history is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import duckdb

from geotrustops import __version__
from geotrustops.config import Config, ConfigError, load_config
from geotrustops.export import ExportError, write_outputs
from geotrustops.extract import ExtractError, changelog_path, fetch, release_path, verify_manifest
from geotrustops.pipeline import PipelineError, Result, run
from geotrustops.timeline import (
    TimelineError,
    build_timeline,
    fetch_timeline,
    load_inputs,
    load_timeline_config,
    write_timeline,
)

ROOT = Path.cwd()
HISTORY = ROOT / "runs" / "history.jsonl"
ARCHIVE = ROOT / "data" / "archive.json"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="geotrustops", description=__doc__.splitlines()[0])
    p.add_argument("--config", type=Path, default=ROOT / "config" / "study_area.json")
    p.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="download pinned extracts into --raw-dir")
    f.add_argument("--force", action="store_true", help="re-download even if files exist")
    f.add_argument(
        "--source",
        choices=["auto", "s3", "archive"],
        default="auto",
        help="auto: Overture S3, falling back to the private archive (default); "
        "s3 or archive: only that source",
    )
    f.add_argument("--archive", type=Path, default=ARCHIVE, help=argparse.SUPPRESS)
    b = sub.add_parser("build", help="compare releases and write outputs")
    b.add_argument("--prev", type=Path, help="explicit prev parquet (skips manifest checks)")
    b.add_argument("--curr", type=Path, help="explicit curr parquet (skips manifest checks)")
    b.add_argument("--changelog", type=Path, help="explicit changelog parquet")
    b.add_argument("--no-changelog", action="store_true", help="skip the §9 cross-check")
    b.add_argument("--out", type=Path, help="output folder (default: config out_dir, else out/)")
    b.add_argument("--no-history", action="store_true", help="do not update runs/history.jsonl")
    b.add_argument("--history", type=Path, default=HISTORY, help=argparse.SUPPRESS)
    t = sub.add_parser(
        "timeline", help="build the release timeline from the changelog of every release"
    )
    t.add_argument("--fetch", action="store_true", help="download missing changelog extracts first")
    t.add_argument("--force", action="store_true", help="with --fetch: re-download all extracts")
    t.add_argument("--timeline-config", type=Path, default=ROOT / "config" / "timeline.json")
    t.add_argument("--out", type=Path, help="output folder (default: timeline config out_dir)")
    return p


def _hoist_globals(argv: list[str]) -> list[str]:
    """Allow `build --config X` as well as `--config X build` (contract §10 shows the former)."""
    out, rest, i = [], [], 0
    while i < len(argv):
        if argv[i] in ("--config", "--raw-dir") and i + 1 < len(argv):
            out += argv[i : i + 2]
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    return out + rest


def _record_history(result: Result, cfg: Config, path: Path) -> None:
    """Upsert one calibration-log line per distinct (inputs, config, version) (contract §5).

    No timestamps: rerunning the same inputs replaces its own line, so the file is stable.
    """
    s = result.summary
    # The changelog is part of the run's identity: re-checking the same snapshots against a different
    # changelog (or none) is different evidence and must not overwrite the earlier line.
    changelog_sha = (s["changelog_check"] or {}).get("changelog_sha256")
    key_src = json.dumps(
        {
            "inputs": s["inputs_sha256"],
            "changelog": changelog_sha,
            "config": cfg.raw,
            "version": __version__,
        },
        sort_keys=True,
    )
    key = hashlib.sha256(key_src.encode()).hexdigest()[:16]
    share = {
        side: {
            r: round(n / s["input_rows"][side], 6) if s["input_rows"][side] else None
            for r, n in s["excluded_rows_by_reason"][side].items()
        }
        for side in ("prev", "curr")
    }
    entry = {
        "key": key,
        "releases": s["releases"],
        "pipeline_version": __version__,
        "contract_version": s["contract_version"],
        "inputs_sha256": s["inputs_sha256"],
        "changelog_sha256": changelog_sha,
        "input_rows": s["input_rows"],
        "excluded_share_by_reason": share,
        "change_counts": s["change_counts"],
        "changelog_mismatches": (s["changelog_check"] or {}).get("total_mismatches"),
        "interpretation": s["interpretation"],
    }
    lines = {}
    if path.exists():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                try:
                    lines[json.loads(line)["key"]] = line
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ExportError(
                        f"{path}:{n}: unreadable run-history line ({exc}); outputs were written, history not updated"
                    ) from exc
    lines[key] = json.dumps(entry, ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write a temporary file and replace it: an interrupted write never truncates the existing history.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(lines[k] + "\n" for k in sorted(lines)), encoding="utf-8", newline="\n")
    tmp.replace(path)


def _timeline(args: argparse.Namespace, cfg: Config) -> int:
    tcfg = load_timeline_config(args.timeline_config)
    if args.fetch:
        fetch_timeline(cfg, tcfg, args.raw_dir, force=args.force)
    doc = build_timeline(cfg, load_inputs(cfg, tcfg, args.raw_dir), tcfg.min_step_m)
    path = write_timeline(doc, args.out or ROOT / tcfg.out_dir)
    print(f"ok: {doc['event_count']} events over {len(doc['releases'])} releases -> {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(_hoist_globals(list(sys.argv[1:] if argv is None else argv)))
    try:
        cfg = load_config(args.config)
        if args.command == "fetch":
            fetch(cfg, args.raw_dir, force=args.force, source=args.source, archive=args.archive)
            return 0
        if args.command == "timeline":
            return _timeline(args, cfg)
        if (args.prev is None) != (args.curr is None):
            raise PipelineError("give both --prev and --curr, or neither")
        if args.prev is not None:
            prev, curr = args.prev, args.curr
            changelog = None if args.no_changelog else args.changelog
        else:
            prev = release_path(args.raw_dir, cfg.prev_release)
            curr = release_path(args.raw_dir, cfg.curr_release)
            verify_manifest(prev, cfg, "release", cfg.prev_release)
            verify_manifest(curr, cfg, "release", cfg.curr_release)
            changelog = None
            if not args.no_changelog:
                changelog = args.changelog or changelog_path(args.raw_dir, cfg.curr_release)
                if args.changelog is None:
                    verify_manifest(changelog, cfg, "changelog", cfg.curr_release)
        out = args.out or (ROOT / cfg.out_dir if cfg.out_dir else ROOT / "out")
        result = run(prev, curr, changelog, cfg)
        write_outputs(result, out)
        if not args.no_history:
            _record_history(result, cfg, args.history)
    except (ConfigError, ExportError, ExtractError, PipelineError, TimelineError) as exc:
        print(f"geotrustops: FAILED: {exc}", file=sys.stderr)
        return 2
    except (duckdb.Error, OSError, json.JSONDecodeError) as exc:
        # Not a named gate, but still a failed run: an unreadable or wrongly typed input file, a corrupt manifest,
        # a full disk. Same exit code and one line instead of a traceback.
        print(f"geotrustops: FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    s = result.summary
    print(f"ok: {s['considered_ids']} ids in study -> {out}")
    print("   " + ", ".join(f"{k} {v}" for k, v in s["change_counts"].items()))
    if s["changelog_check"] is not None:
        print(f"   changelog cross-check mismatches: {s['changelog_check']['total_mismatches']}")
    return 0


def main_entry() -> None:
    raise SystemExit(main())
