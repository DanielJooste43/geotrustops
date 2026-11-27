# Feasibility probes (historical)

One-off scripts run before the pipeline existed, to check that Overture's places data for the study area could
support a release-to-release comparison at all (a go/no-go check: row counts, stable ids, how many records change
and how). They are kept as a record of how the project started; they are **not** part of the pipeline, its tests
or its outputs. The pipeline is `src/geotrustops/` and is run with the `geotrustops` command (see the README).

| Script | What it checked |
|---|---|
| `probe_extract.py` | extract one release for the study area bounding box (later became `geotrustops fetch`) |
| `probe_inspect_schema.py` | the columns and types Overture publishes for places |
| `probe_feasibility.py` | first counts of added, removed, moved and renamed records; writes `docs/history/feasibility_probe.json` |

The figures in `docs/history/feasibility_probe.json` are from that first probe and differ slightly from the current
outputs, which use the finished rules in `docs/data_contract.md`.
