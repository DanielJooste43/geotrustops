// Tests for the before/after swipe: which records and positions each side draws, the one-way camera sync, and the
// divider's keyboard steps. The real exported files check that each side's count matches the pipeline's summary.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseChanges, parseSummary, type ChangeProperties, type Changes } from "../src/contract";
import { followCamera, keyStep, sideCounts, sideFeatures, type CameraSource } from "../src/swipe";

const props = (over: Partial<ChangeProperties>): ChangeProperties => ({
  id: "a", change_type: "moved", distance_m: 30, move_band: "material",
  prev_name: "X", curr_name: "X", prev_category: "c", curr_category: "c",
  prev_basic_category: "b", curr_basic_category: "b",
  prev_lon: 28.18, prev_lat: -25.74, curr_lon: 28.181, curr_lat: -25.741,
  prev_operating_status: null, curr_operating_status: null, prev_confidence: 0.9, curr_confidence: 0.9,
  name_changed: false, name_change_kind: null, category_changed: false, basic_category_changed: false,
  status_changed: false, confidence_to_zero: false, crossed_aoi_boundary: false,
  enrichment_changed: "", format_only_changed: "", ...over,
});
const changesOf = (ps: ChangeProperties[]): Changes => ({
  type: "FeatureCollection",
  features: ps.map((p) => ({
    type: "Feature", id: p.id, properties: p,
    geometry: { type: "Point", coordinates: [p.curr_lon ?? p.prev_lon!, p.curr_lat ?? p.prev_lat!] },
  })),
} as unknown as Changes);

describe("sideFeatures", () => {
  const changes = changesOf([
    props({ id: "m" }),
    props({ id: "r", change_type: "removed", curr_lon: null, curr_lat: null }),
    props({ id: "n", change_type: "added", prev_lon: null, prev_lat: null }),
  ]);
  const ids = (side: "before" | "after") => sideFeatures(changes, side).features.map((f) => f.id);
  const at = (side: "before" | "after", id: string) =>
    (sideFeatures(changes, side).features.find((f) => f.id === id)!.geometry as { coordinates: number[] }).coordinates;

  it("draws removed records only before and added records only after", () => {
    expect(ids("before")).toEqual(["m", "r"]);
    expect(ids("after")).toEqual(["m", "n"]);
  });
  it("draws a moved record at its earlier position before and its later position after", () => {
    expect(at("before", "m")).toEqual([28.18, -25.74]);
    expect(at("after", "m")).toEqual([28.181, -25.741]);
  });
  it("keeps the change type for the symbols and filters", () => {
    expect(sideFeatures(changes, "before").features[1]!.properties).toEqual({ id: "r", change_type: "removed" });
  });
});

describe("real exported files", () => {
  const read = (name: string) =>
    JSON.parse(readFileSync(fileURLToPath(new URL(`../../out/${name}`, import.meta.url)), "utf8")) as unknown;
  const changes = parseChanges(read("changes.geojson"));
  const summary = parseSummary(read("summary.json"));
  it("each side draws exactly the records the summary counts for that release", () => {
    const expected = sideCounts(summary);
    expect(sideFeatures(changes, "before").features).toHaveLength(expected.before);
    expect(sideFeatures(changes, "after").features).toHaveLength(expected.after);
  });
});

describe("followCamera", () => {
  const fakeLeader = () => {
    const listeners = new Set<() => void>();
    const cam = { center: { lng: 28.18, lat: -25.74 }, zoom: 14, bearing: 0, pitch: 0 };
    const leader: CameraSource & { move(): void; listeners: Set<() => void>; cam: typeof cam } = {
      listeners, cam,
      on: (_t, fn) => listeners.add(fn), off: (_t, fn) => listeners.delete(fn),
      getCenter: () => cam.center, getZoom: () => cam.zoom, getBearing: () => cam.bearing, getPitch: () => cam.pitch,
      move: () => { for (const fn of listeners) fn(); },
    };
    return leader;
  };

  it("copies the leader's camera at once and on every move", () => {
    const leader = fakeLeader();
    const jumps: unknown[] = [];
    followCamera(leader, { jumpTo: (o) => jumps.push(o) });
    leader.cam.zoom = 16;
    leader.move();
    expect(jumps).toEqual([
      { center: [28.18, -25.74], zoom: 14, bearing: 0, pitch: 0 },
      { center: [28.18, -25.74], zoom: 16, bearing: 0, pitch: 0 },
    ]);
  });
  it("never moves the leader: the follower has no listener, so there is no feedback loop", () => {
    const leader = fakeLeader();
    let followerMoves = 0;
    followCamera(leader, { jumpTo: () => { followerMoves++; } });
    for (let i = 0; i < 3; i++) leader.move();
    expect(followerMoves).toBe(4); // one initial copy + one per leader move, never more
    expect(leader.listeners.size).toBe(1);
  });
  it("stops following when switched off", () => {
    const leader = fakeLeader();
    let n = 0;
    const stop = followCamera(leader, { jumpTo: () => { n++; } });
    stop();
    leader.move();
    expect(n).toBe(1);
    expect(leader.listeners.size).toBe(0);
  });
});

describe("keyStep", () => {
  it("moves by small and large steps and clamps to the map edges", () => {
    expect(keyStep("ArrowLeft", 50, false)).toBe(48);
    expect(keyStep("ArrowRight", 50, true)).toBe(60);
    expect(keyStep("ArrowLeft", 1, false)).toBe(0);
    expect(keyStep("End", 20, false)).toBe(100);
    expect(keyStep("Home", 80, false)).toBe(0);
  });
  it("ignores other keys so Tab and Escape keep working", () => {
    expect(keyStep("Tab", 50, false)).toBeNull();
    expect(keyStep("Escape", 50, false)).toBeNull();
  });
});
