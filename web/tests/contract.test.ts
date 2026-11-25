// Tests for the contract adapter: synthetic fixtures for each rule, plus the real exported files.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CHANGE_TYPES, ContractError, checkSameRun, checkTimelineMatchesRun, checkTriageMatchesRun, parseChanges, parseSummary,
  historyRuns, parseTimeline, parseTriage, positions, reconciliationHolds, recordHistory,
  type ChangeProperties,
} from "../src/contract";

const props = (over: Partial<ChangeProperties> = {}): ChangeProperties => ({
  id: "a", change_type: "moved", distance_m: 30.1, move_band: "material",
  prev_name: "X", curr_name: "X", prev_category: "c", curr_category: "c",
  prev_basic_category: "b", curr_basic_category: "b",
  prev_lon: 28.18, prev_lat: -25.74, curr_lon: 28.1803, curr_lat: -25.7402,
  prev_operating_status: null, curr_operating_status: null, prev_confidence: 0.9, curr_confidence: 0.9,
  name_changed: false, name_change_kind: null, category_changed: false, basic_category_changed: false,
  status_changed: false, confidence_to_zero: false, crossed_aoi_boundary: false,
  enrichment_changed: "", format_only_changed: "", ...over,
});

const meta = {
  interpretation: "i", releases: { prev: "p", curr: "c" }, pipeline_version: "0.5.0", contract_version: "0.4",
  inputs_sha256: { prev: "h1", curr: "h2" }, changelog_sha256: null, attribution: "a",
};

const collection = (features: unknown[], m: object = meta) => ({ type: "FeatureCollection", geotrustops: m, features });
const feature = (p: ChangeProperties, coords: unknown = [p.curr_lon, p.curr_lat]) =>
  ({ type: "Feature", id: p.id, geometry: { type: "Point", coordinates: coords }, properties: p });

describe("parseChanges", () => {
  it("accepts a valid collection", () => {
    expect(parseChanges(collection([feature(props())])).features).toHaveLength(1);
  });
  it("rejects an unsupported contract version", () => {
    expect(() => parseChanges(collection([], { ...meta, contract_version: "0.5" }))).toThrow(ContractError);
  });
  it("rejects an unknown change type (e.g. unchanged is never exported)", () => {
    expect(() => parseChanges(collection([feature(props({ change_type: "unchanged" as never }))]))).toThrow(/change_type/);
  });
  it("rejects duplicate ids", () => {
    expect(() => parseChanges(collection([feature(props()), feature(props())]))).toThrow(/duplicate/);
  });
  it("rejects a mismatched feature id", () => {
    const f = { ...feature(props()), id: "other" };
    expect(() => parseChanges(collection([f]))).toThrow(/id/);
  });
  it("rejects out-of-range coordinates", () => {
    expect(() => parseChanges(collection([feature(props(), [200, 0])]))).toThrow(/range/);
  });
  it("rejects a wrongly typed field instead of reading it silently", () => {
    expect(() => parseChanges(collection([feature(props({ distance_m: "30" as never }))]))).toThrow(/distance_m/);
  });
});

describe("positions", () => {
  it("removed records have no current position; added records no previous one", () => {
    expect(positions(props({ curr_lon: null, curr_lat: null })).curr).toBeNull();
    expect(positions(props({ prev_lon: null, prev_lat: null })).prev).toBeNull();
  });
});

describe("real exported files", () => {
  const read = (name: string) =>
    JSON.parse(readFileSync(fileURLToPath(new URL(`../../out/${name}`, import.meta.url)), "utf8")) as unknown;
  const changes = parseChanges(read("changes.geojson"));
  const summary = parseSummary(read("summary.json"));

  it("both files describe the same run", () => {
    expect(() => checkSameRun(changes, summary)).not.toThrow();
  });
  it("feature counts per change type equal summary.json (the map shows summary numbers only)", () => {
    for (const t of CHANGE_TYPES) {
      const n = changes.features.filter((f) => f.properties.change_type === t).length;
      expect(n, t).toBe(summary.change_counts[t]);
    }
  });
  it("every reconciliation identity holds", () => {
    expect(reconciliationHolds(summary)).toBe(true);
  });
  it("removed records are placed at their previous position, others at the current one (contract §5)", () => {
    for (const f of changes.features) {
      const { prev, curr } = positions(f.properties);
      const expected = f.properties.change_type === "removed" ? prev : curr;
      expect(f.geometry.coordinates, f.properties.id).toEqual(expected);
    }
  });
});

describe("parseTriage", () => {
  const cluster = { size: 2, lon: 28.19, lat: -25.75, likely_cause: "one compact building", also_duplicates: false,
    manual_inspection: true, ids: ["a", "b"] };
  const doc = (over: object = {}) => ({ schema_version: 1, release: "r", method: "m", cluster_rule_m: 2,
    places_in_aoi: 10, inputs_sha256: { places: "h2" }, cluster_count: 1, clustered_places: 2, licence: "ODbL-1.0",
    licence_uri: "https://opendatacommons.org/licenses/odbl/1-0/", attribution: "a", interpretation: "i",
    clusters: [cluster], ...over });

  it("accepts a valid file", () => { expect(parseTriage(doc()).clusters).toHaveLength(1); });
  it("requires the ODbL notice (ODbL 4.2)", () => {
    expect(() => parseTriage(doc({ licence: "CC0-1.0" }))).toThrow(/ODbL/);
  });
  it("requires the manual-inspection flag on every cluster", () => {
    expect(() => parseTriage(doc({ clusters: [{ ...cluster, manual_inspection: false }] }))).toThrow(/manual/);
  });
  it("rejects a size that does not match its ids", () => {
    expect(() => parseTriage(doc({ clusters: [{ ...cluster, size: 3 }], clustered_places: 3 }))).toThrow(/size/);
  });
  it("is accepted only with the change run it was computed for (same release and places input)", () => {
    const run = { releases: { prev: "p", curr: "r" }, inputs_sha256: { prev: "h1", curr: "h2" } } as never;
    expect(() => checkTriageMatchesRun(parseTriage(doc()), run)).not.toThrow();
    expect(() => checkTriageMatchesRun(parseTriage(doc({ release: "older" })), run)).toThrow(/release/);
    expect(() => checkTriageMatchesRun(parseTriage(doc({ inputs_sha256: { places: "x" } })), run)).toThrow(/extract/);
  });
  it("rejects totals that do not match the clusters", () => {
    expect(() => parseTriage(doc({ clustered_places: 5 }))).toThrow(/clustered_places/);
  });
});

describe("real triage file", () => {
  const triage = parseTriage(JSON.parse(readFileSync(
    fileURLToPath(new URL("../../out_triage/stack_causes.json", import.meta.url)), "utf8")) as unknown);
  const summary = parseSummary(JSON.parse(readFileSync(
    fileURLToPath(new URL("../../out/summary.json", import.meta.url)), "utf8")) as unknown);

  it("matches the committed change run (release and places input)", () => {
    expect(() => checkTriageMatchesRun(triage, summary)).not.toThrow();
  });
  it("places every cluster centre inside the study area", () => {
    const { west, south, east, north } = summary.aoi;
    for (const c of triage.clusters) {
      expect(c.lon >= west && c.lon <= east && c.lat >= south && c.lat <= north, `${c.lon},${c.lat}`).toBe(true);
    }
  });
  it("lists each place in at most one cluster", () => {
    const ids = triage.clusters.flatMap((c) => c.ids);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("parseTimeline", () => {
  const rel = (release: string, over: object = {}) => ({
    release, change_type_partitions: ["added", "data_changed", "removed", "unchanged"], changes_published: true,
    added: 0, removed: 0, position_changed: 0, position_changed_labelled_unchanged: 0, first_seen_without_added: 0,
    ...over,
  });
  const tl = (over: object = {}) => ({
    schema_version: 1, aoi: { west: 0, south: 0, east: 1, north: 1 }, min_step_m: 1, method: "m",
    interpretation: ["per release"], kinds: ["added", "removed", "position_changed"],
    event_fields: ["release_index", "kind_index", "id_index", "lon", "lat", "from_release_index", "from_lon", "from_lat", "distance_m"],
    releases: [rel("2026-01-01.0", { added: 1 }), rel("2026-02-01.0", { position_changed: 1 })],
    ids: ["a"],
    events: [[0, 0, 0, 0.5, 0.5, null, null, null, null], [1, 2, 0, 0.6, 0.5, 0, 0.5, 0.5, 10.1]],
    event_count: 2, inputs_sha256: { "2026-01-01.0": "x", "2026-02-01.0": "cl" },
    licences: ["CDLA-Permissive-2.0", "Apache-2.0", "CC0-1.0"], attribution: "© Overture Maps Foundation",
    ...over,
  });

  it("accepts a valid file", () => {
    expect(parseTimeline(tl()).events).toHaveLength(2);
  });
  it("requires the three places licences and an attribution", () => {
    expect(() => parseTimeline(tl({ licences: ["CC0-1.0"] }))).toThrow(/licences/);
    expect(() => parseTimeline(tl({ attribution: "" }))).toThrow(/attribution/);
  });
  it("rejects counts that do not add up to the events", () => {
    expect(() => parseTimeline(tl({ releases: [rel("2026-01-01.0", { added: 2 }), rel("2026-02-01.0", { position_changed: 1 })] })))
      .toThrow(/add up/);
    expect(() => parseTimeline(tl({ event_count: 3 }))).toThrow(/event_count/);
  });
  it("rejects releases out of order and indexes out of range", () => {
    expect(() => parseTimeline(tl({ releases: [rel("2026-02-01.0", { added: 1 }), rel("2026-01-01.0", { position_changed: 1 })] })))
      .toThrow(/oldest first/);
    expect(() => parseTimeline(tl({ events: [[0, 0, 5, 0.5, 0.5, null, null, null, null], [1, 2, 0, 0.6, 0.5, 0, 0.5, 0.5, 10.1]] })))
      .toThrow(/id out of range/);
  });
  it("requires a from position on moves only", () => {
    expect(() => parseTimeline(tl({ events: [[0, 0, 0, 0.5, 0.5, null, null, null, null], [1, 2, 0, 0.6, 0.5, null, null, null, null]] })))
      .toThrow(/from position/);
    expect(() => parseTimeline(tl({ events: [[0, 0, 0, 0.5, 0.5, 0, 0.5, 0.5, 1], [1, 2, 0, 0.6, 0.5, 0, 0.5, 0.5, 10.1]] })))
      .toThrow(/only position changes/);
  });
  it("is accepted only with the change run whose changelog it ends with", () => {
    const run = (curr: string, sha: string) => ({ geotrustops: { releases: { prev: "p", curr }, changelog_sha256: sha } }) as never;
    expect(() => checkTimelineMatchesRun(parseTimeline(tl()), run("2026-02-01.0", "cl"))).not.toThrow();
    expect(() => checkTimelineMatchesRun(parseTimeline(tl()), run("2026-03-01.0", "cl"))).toThrow(/current release/);
    expect(() => checkTimelineMatchesRun(parseTimeline(tl()), run("2026-02-01.0", "other"))).toThrow(/changelog/);
  });
  it("lists a record's positions by release, starting from where its first move began", () => {
    const steps = recordHistory(parseTimeline(tl()), "a");
    expect(steps.map((s) => [s.release, s.kind])).toEqual([["2026-01-01.0", "added"], ["2026-02-01.0", "position_changed"]]);
    expect(recordHistory(parseTimeline(tl()), "missing")).toEqual([]);
    const moveOnly = tl({ releases: [rel("2026-01-01.0"), rel("2026-02-01.0", { position_changed: 1 })],
      events: [[1, 2, 0, 0.6, 0.5, 0, 0.5, 0.5, 10.1]], event_count: 1 });
    expect(recordHistory(parseTimeline(moveOnly), "a").map((s) => s.kind)).toEqual(["seen", "position_changed"]);
  });
  it("lists a move's own origin when steps outside the study area are missing, and never joins across a removal", () => {
    // a: removed at P in release 1; re-added and moved outside the study area (not in the file); in release 3 it
    // moves back in from Q. The trail must start at Q, not at the removal point P.
    const gap = tl({
      releases: [rel("2026-01-01.0", { added: 1 }), rel("2026-02-01.0", { removed: 1 }), rel("2026-03-01.0"),
        rel("2026-04-01.0", { position_changed: 1 })],
      events: [[0, 0, 0, 0.5, 0.5, null, null, null, null], [1, 1, 0, 0.5, 0.5, null, null, null, null],
        [3, 2, 0, 0.6, 0.5, 2, 0.9, 0.9, 50]],
      event_count: 3, inputs_sha256: { "2026-04-01.0": "cl" },
    });
    const steps = recordHistory(parseTimeline(gap), "a");
    expect(steps.map((s) => [s.release, s.kind, s.joined])).toEqual([
      ["2026-01-01.0", "added", false], ["2026-02-01.0", "removed", false],
      ["2026-03-01.0", "seen", false], ["2026-04-01.0", "position_changed", true],
    ]);
    expect(historyRuns(steps)).toEqual([[[0.9, 0.9], [0.6, 0.5]]]);
  });
});

describe("real timeline file", () => {
  const read = (p: string) => JSON.parse(readFileSync(fileURLToPath(new URL(p, import.meta.url)), "utf8")) as unknown;
  const timeline = parseTimeline(read("../../out_timeline/timeline.json"));
  const changes = parseChanges(read("../../out/changes.geojson"));

  it("ends at the committed change run and uses its changelog", () => {
    expect(() => checkTimelineMatchesRun(timeline, changes)).not.toThrow();
  });
  it("draws every recorded move from its own from position", () => {
    for (const id of timeline.ids.slice(0, 4000)) {
      const steps = recordHistory(timeline, id);
      steps.forEach((s, i) => {
        if (s.kind === "position_changed") expect(steps[i - 1]?.kind === "removed", id).toBe(false);
      });
    }
    const steps = recordHistory(timeline, "4a277dd5-7b99-4a6f-aae8-97719e2345b4"); // moves back in from outside
    const i = steps.findIndex((s) => s.release === "2026-09-23.1");
    expect(steps[i - 1]).toMatchObject({ release: "2026-08-19.0", kind: "seen", lon: 28.179478, lat: -25.758072 });
  });
  it("gives every moved record of the change run a position history ending at its current position", () => {
    for (const f of changes.features.filter((x) => x.properties.change_type === "moved")) {
      const steps = recordHistory(timeline, f.properties.id);
      const last = steps[steps.length - 1];
      expect(last, f.properties.id).toBeDefined();
      expect(last!.lon).toBeCloseTo(f.geometry.coordinates[0], 5);
      expect(last!.lat).toBeCloseTo(f.geometry.coordinates[1], 5);
    }
  });
});
