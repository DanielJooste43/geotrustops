// Tests for the contract adapter: synthetic fixtures for each rule, plus the real exported files.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CHANGE_TYPES, ContractError, checkSameRun, parseChanges, parseSummary, positions, reconciliationHolds,
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
