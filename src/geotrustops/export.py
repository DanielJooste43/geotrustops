"""Write out/changes.geojson, out/summary.json and out/qa_report.md (contract §5).

Determinism: rows sorted by id, coordinates already rounded in SQL, fixed key order, LF line
endings, no timestamps, so the same inputs give byte-identical files.
Safety: files are written to `<out>.staging/` and swapped in only when complete, so a failed
or interrupted run never replaces known-good outputs.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from geotrustops.pipeline import Result


class ExportError(RuntimeError):
    """Outputs could not be put in place; the previous outputs are kept."""


_PROPERTY_ORDER = [
    "id",
    "change_type",
    "distance_m",
    "move_band",
    "prev_name",
    "curr_name",
    "prev_category",
    "curr_category",
    "prev_basic_category",
    "curr_basic_category",
    "prev_lon",
    "prev_lat",
    "curr_lon",
    "curr_lat",
    "prev_operating_status",
    "curr_operating_status",
    "prev_confidence",
    "curr_confidence",
    "name_changed",
    "name_change_kind",
    "name_matches_brand",
    "category_changed",
    "basic_category_changed",
    "status_changed",
    "confidence_to_zero",
    "enrichment_changed",
    "format_only_changed",
    "crossed_aoi_boundary",
    "source_datasets",
    "source_licences",
]


def _feature(rec: dict[str, Any]) -> dict[str, Any]:
    # Removed places are drawn where they used to be; everything else at its current position.
    if rec["change_type"] == "removed":
        coords = [rec["prev_lon"], rec["prev_lat"]]
    else:
        coords = [rec["curr_lon"], rec["curr_lat"]]
    return {
        "type": "Feature",
        "id": rec["id"],
        "geometry": {"type": "Point", "coordinates": coords},
        "properties": {k: rec[k] for k in _PROPERTY_ORDER},
    }


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _qa_report(result: Result) -> str:
    s = result.summary
    t = s["thresholds_m"]
    lines = [
        "# GeoTrustOps QA report",
        "",
        f"Releases: `{s['releases']['prev']}` → `{s['releases']['curr']}` · "
        f"shifted > {t['minor_move']} m · moved > {t['move']} m · major > {t['major_move']} m · "
        f"contract v{s['contract_version']}",
        "",
        f"> {s['interpretation']}",
        "",
        "## Provenance",
        "",
        f"- Pipeline `{s['pipeline_version']}` · contract `v{s['contract_version']}`",
        f"- AOI: {s['aoi']}",
        f"- Extraction bbox (AOI + buffer): {s['extraction_bbox']}",
        f"- Input sha256: prev `{s['inputs_sha256']['prev']}` · curr `{s['inputs_sha256']['curr']}`",
        *(
            [f"- Changelog sha256: `{s['changelog_check']['changelog_sha256']}`"]
            if s.get("changelog_check")
            else []
        ),
        "",
        "## Inputs",
        "",
        "| | prev | curr |",
        "|---|---|---|",
        f"| rows in extraction (AOI + buffer) | {s['input_rows']['prev']} | {s['input_rows']['curr']} |",
        f"| valid rows | {s['valid_rows']['prev']} | {s['valid_rows']['curr']} |",
    ]
    for reason, n in s["excluded_rows_by_reason"]["prev"].items():
        lines.append(
            f"| excluded: `{reason}` | {n} | {s['excluded_rows_by_reason']['curr'][reason]} |"
        )
    lines += [
        "",
        f"Ids: {s['union_ids']} in extraction, {s['considered_ids']} in study, "
        f"{s['buffer_only_ids']} buffer-only (ignored).",
        "",
        "## Change types (ids in study)",
        "",
        "| type | count |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in s["change_counts"].items()],
        "",
        "| move band (matched ids) | count |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in s["move_band_counts"].items()],
        "",
        "| flag | count |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in s["flag_counts"].items()],
        "",
        "| enrichment field changed (addresses after region normalisation) | count |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in s["enrichment_field_counts"].items()],
        "",
        "| format-only change (raw differs, normalised equal; not counted above) | count |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in s["format_only_field_counts"].items()],
        "",
        "## Renames by kind (kind describes the edit, not its quality)",
        "",
        "| kind | count |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in s["name_change_kind_counts"].items()],
        "",
        "| kind | id | previous | current | = brand |",
        "|---|---|---|---|---|",
        *[
            f"| {r['name_change_kind']} | `{r['id']}` | {r['prev_name']} | {r['curr_name']} | "
            f"{r['name_matches_brand']} |"
            for r in result.renames
        ],
        "",
        f"## Lifecycle changes ({len(result.lifecycle)})",
        "",
        *(
            [
                f"- `{r['id']}` {r['curr_name']}: status {r['prev_operating_status']} → "
                f"{r['curr_operating_status']}, confidence {r['prev_confidence']} → {r['curr_confidence']}"
                for r in result.lifecycle
            ]
            or ["None."]
        ),
        "",
        "## Reconciliation",
        "",
        *[
            f"- {'✔' if r['holds'] else '✘'} `{r['identity']}`: {r['lhs']} = {r['rhs']}"
            for r in s["reconciliation"].values()
        ],
        "",
        "## Changelog cross-check (contract §9)",
        "",
    ]
    cc = s.get("changelog_check")
    if cc is None:
        lines.append("Not run (no changelog supplied).")
    else:
        lines += ["| rule | checked | mismatches |", "|---|---|---|"]
        lines += [f"| {k} | {v['checked']} | {v['mismatches']} |" for k, v in cc["rules"].items()]
        lines += [
            "",
            "Changelog type of ids in study: "
            + ", ".join(f"{k} {v}" for k, v in cc["changelog_types_for_considered_ids"].items()),
        ]
        if result.changelog_mismatches:
            lines += [
                "",
                "| rule | id | GeoTrustOps | changelog | columns_changed |",
                "|---|---|---|---|---|",
            ]
            lines += [
                f"| {m['rule']} | `{m['id']}` | {m['geotrustops']} | {m['changelog']} | "
                f"{m['columns_changed']} |"
                for m in result.changelog_mismatches
            ]
    lines += [
        "",
        "## 10 largest moves",
        "",
        "| id | previous name | current name | m | crossed AOI edge |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| `{m['id']}` | {m['prev_name']} | {m['curr_name']} | {m['distance_m']} | "
        f"{m['crossed_aoi_boundary']} |"
        for m in result.top_moves
    ]
    lines += ["", f"## Excluded rows ({len(result.excluded_rows)})", ""]
    if result.excluded_rows:
        lines += ["| release | row | id | reason | geometry | name |", "|---|---|---|---|---|---|"]
        lines += [
            f"| {e['side']} | {e['src_row']} | `{e['id']}` | {e['exclusion_reason']} | "
            f"{e['geom_type']} | {e['name']} |"
            for e in result.excluded_rows
        ]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def write_outputs(result: Result, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    staging = out_dir.with_name(out_dir.name + ".staging")
    previous = out_dir.with_name(out_dir.name + ".previous")
    shutil.rmtree(staging, ignore_errors=True)  # leftover from an interrupted run; recreated below
    staging.mkdir(parents=True)
    s = result.summary
    geojson = {
        "type": "FeatureCollection",
        # RFC 7946 §6.1 "foreign member": provenance + interpretation limits travel with the data
        # (contract §5, §7). Deterministic: no timestamps.
        "geotrustops": {
            "interpretation": s["interpretation"],
            "releases": s["releases"],
            "pipeline_version": s["pipeline_version"],
            "contract_version": s["contract_version"],
            "inputs_sha256": s["inputs_sha256"],
            "changelog_sha256": (s.get("changelog_check") or {}).get("changelog_sha256"),
            "attribution": "© Overture Maps Foundation and its sources; licence per feature in source_licences",
        },
        "features": [_feature(r) for r in result.changes],
    }
    files = {
        "changes.geojson": _dump(geojson),
        "summary.json": _dump(result.summary),
        "qa_report.md": _qa_report(result),
    }
    for name, text in files.items():
        (staging / name).write_text(text, encoding="utf-8", newline="\n")
    _swap_into_place(staging, out_dir, previous)


def _swap_into_place(staging: Path, out_dir: Path, previous: Path) -> None:
    """Replace `out_dir` with `staging` so that a failure never leaves the outputs missing.

    current -> .previous, staging -> current, then .previous is dropped. If the second rename fails, the previous
    outputs are moved back before the error is raised (AGENTS.md: a failed run must not replace previous outputs).
    """
    try:
        if previous.exists():
            shutil.rmtree(
                previous
            )  # a stale copy that cannot be removed stops the run before anything moves
        had_outputs = out_dir.exists()
        if had_outputs:
            out_dir.rename(previous)
        try:
            staging.rename(out_dir)
        except OSError:
            if had_outputs:
                previous.rename(out_dir)
            raise
    except OSError as exc:
        raise ExportError(
            f"could not put the new outputs in place at {out_dir}: {exc}; previous outputs kept"
        ) from exc
    shutil.rmtree(
        previous, ignore_errors=True
    )  # cleanup after success; a leftover is removed by the next run
