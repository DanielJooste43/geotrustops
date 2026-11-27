// Typed view of the pipeline's exported files (docs/data_contract.md §5, contract v0.4).
// Purpose: the one place where the map learns the output contract, so a contract change fails loudly here
// (a thrown ContractError) instead of the map silently misreading a field.
// Inputs: parsed JSON of out/changes.geojson and out/summary.json. Outputs: validated, typed objects.
// Rule (ADR 0004): nothing here computes a classification or a displayed count; numbers shown come from summary.json.
// Counting features is allowed only as a check against summary.json (checkSameRun).

export const SUPPORTED_CONTRACT = "0.4";

/** Change types that appear as features in changes.geojson, in contract priority order. */
export const CHANGE_TYPES = ["added", "removed", "moved", "attribute_changed", "shifted"] as const;
export type ChangeType = (typeof CHANGE_TYPES)[number];

export const MOVE_BANDS = ["stable", "minor", "material", "major"] as const;
export type MoveBand = (typeof MOVE_BANDS)[number];

export interface ChangeProperties {
  id: string;
  change_type: ChangeType;
  distance_m: number | null;
  move_band: MoveBand | null;
  prev_name: string | null;
  curr_name: string | null;
  prev_category: string | null;
  curr_category: string | null;
  prev_basic_category: string | null;
  curr_basic_category: string | null;
  prev_lon: number | null;
  prev_lat: number | null;
  curr_lon: number | null;
  curr_lat: number | null;
  prev_operating_status: string | null;
  curr_operating_status: string | null;
  prev_confidence: number | null;
  curr_confidence: number | null;
  name_changed: boolean | null;
  name_change_kind: string | null;
  category_changed: boolean | null;
  basic_category_changed: boolean | null;
  status_changed: boolean | null;
  confidence_to_zero: boolean | null;
  crossed_aoi_boundary: boolean | null;
  enrichment_changed: string | null;
  format_only_changed: string | null;
}

export interface ChangeFeature {
  type: "Feature";
  id: string;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: ChangeProperties;
}

export interface Provenance {
  interpretation: string;
  releases: { prev: string; curr: string };
  pipeline_version: string;
  contract_version: string;
  inputs_sha256: { prev: string; curr: string };
  changelog_sha256: string | null;
  attribution: string;
}

export interface Changes {
  type: "FeatureCollection";
  geotrustops: Provenance;
  features: ChangeFeature[];
}

export interface ReconciliationIdentity {
  identity: string;
  lhs: number;
  rhs: number;
  holds: boolean;
}

export interface Summary {
  pipeline_version: string;
  contract_version: string;
  releases: { prev: string; curr: string };
  aoi: { west: number; south: number; east: number; north: number };
  thresholds_m: { minor_move: number; move: number; major_move: number };
  inputs_sha256: { prev: string; curr: string };
  change_counts: Record<ChangeType | "excluded" | "unchanged", number>;
  move_band_counts: Record<MoveBand, number>;
  flag_counts: Record<string, number>;
  reconciliation: Record<string, ReconciliationIdentity>;
  interpretation: string;
  changelog_check: {
    changelog_sha256: string | null;
    rules: Record<string, { checked: number; mismatches: number }>;
    /** Overture's own changelog type for each considered id (e.g. data_changed); optional in older summaries. */
    changelog_types_for_considered_ids?: Record<string, number>;
  } | null;
}

export class ContractError extends Error {
  override name = "ContractError";
}

type Json = Record<string, unknown>;

function isObject(v: unknown): v is Json {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function need(cond: boolean, what: string): asserts cond {
  if (!cond) throw new ContractError(what);
}

const NUMBER_OR_NULL = [
  "distance_m", "prev_lon", "prev_lat", "curr_lon", "curr_lat", "prev_confidence", "curr_confidence",
] as const;
const STRING_OR_NULL = [
  "prev_name", "curr_name", "prev_category", "curr_category", "prev_basic_category", "curr_basic_category",
  "prev_operating_status", "curr_operating_status", "name_change_kind", "enrichment_changed", "format_only_changed",
] as const;
const BOOL_OR_NULL = [
  "name_changed", "category_changed", "basic_category_changed", "status_changed", "confidence_to_zero",
  "crossed_aoi_boundary",
] as const;

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isCount = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 0;
const isText = (v: unknown): v is string => typeof v === "string" && v.length > 0;
const isLonLat = (lon: unknown, lat: unknown): boolean =>
  isNum(lon) && isNum(lat) && lon >= -180 && lon <= 180 && lat >= -90 && lat <= 90;

function checkFeature(f: unknown, i: number): ChangeFeature {
  const at = `features[${i}]`;
  need(isObject(f) && f.type === "Feature", `${at}: not a Feature`);
  const g = f.geometry;
  need(isObject(g) && g.type === "Point" && Array.isArray(g.coordinates), `${at}: geometry must be a Point`);
  const [lon, lat] = g.coordinates as unknown[];
  need(isNum(lon) && isNum(lat), `${at}: coordinates must be finite numbers`);
  need(isLonLat(lon, lat), `${at}: coordinates out of range`);
  const p = f.properties;
  need(isObject(p), `${at}: properties missing`);
  need(typeof p.id === "string" && p.id.length > 0, `${at}: id must be a non-empty string`);
  need(f.id === p.id, `${at}: feature id and properties.id differ`);
  need(CHANGE_TYPES.includes(p.change_type as ChangeType), `${at}: unknown change_type ${String(p.change_type)}`);
  need(p.move_band === null || MOVE_BANDS.includes(p.move_band as MoveBand), `${at}: unknown move_band`);
  for (const k of NUMBER_OR_NULL) need(p[k] === null || isNum(p[k]), `${at}: ${k} must be a finite number or null`);
  for (const k of STRING_OR_NULL) need(p[k] === null || typeof p[k] === "string", `${at}: ${k} must be string|null`);
  for (const k of BOOL_OR_NULL) need(p[k] === null || typeof p[k] === "boolean", `${at}: ${k} must be boolean|null`);
  // Which positions exist follows from the change type (§5): added records have no previous position, removed
  // records no current one, every other class both. The point sits at prev for removed, else at curr.
  const hasPrev = p.prev_lon !== null || p.prev_lat !== null;
  const hasCurr = p.curr_lon !== null || p.curr_lat !== null;
  need(!hasPrev || isLonLat(p.prev_lon, p.prev_lat), `${at}: previous position incomplete or out of range`);
  need(!hasCurr || isLonLat(p.curr_lon, p.curr_lat), `${at}: current position incomplete or out of range`);
  need(hasPrev === (p.change_type !== "added") && hasCurr === (p.change_type !== "removed"),
    `${at}: positions present do not fit change_type ${String(p.change_type)}`);
  // distance_m and move_band exist for every matched id and only for them (§3): null for added and removed.
  const matched = p.change_type !== "added" && p.change_type !== "removed";
  need((p.distance_m !== null) === matched && (p.move_band !== null) === matched,
    `${at}: distance_m and move_band must be set exactly for matched records`);
  need(p.distance_m === null || (p.distance_m as number) >= 0, `${at}: distance_m must not be negative`);
  const [sideLon, sideLat] = p.change_type === "removed" ? [p.prev_lon, p.prev_lat] : [p.curr_lon, p.curr_lat];
  need(lon === sideLon && lat === sideLat, `${at}: point is not at the position its change type is drawn at`);
  return f as unknown as ChangeFeature;
}

/** Validates changes.geojson against contract §5; throws ContractError on the first violation. */
export function parseChanges(raw: unknown): Changes {
  need(isObject(raw) && raw.type === "FeatureCollection", "changes: not a FeatureCollection");
  const meta = raw.geotrustops;
  need(isObject(meta), "changes: foreign member 'geotrustops' missing");
  need(meta.contract_version === SUPPORTED_CONTRACT,
    `changes: contract ${String(meta.contract_version)}, map supports ${SUPPORTED_CONTRACT}`);
  need(isObject(meta.releases) && typeof meta.releases.prev === "string" && typeof meta.releases.curr === "string",
    "changes: releases missing");
  need(isObject(meta.inputs_sha256) && isText(meta.inputs_sha256.prev) && isText(meta.inputs_sha256.curr),
    "changes: inputs_sha256 missing");
  need(meta.changelog_sha256 === null || isText(meta.changelog_sha256), "changes: changelog_sha256 must be text or null");
  need(Array.isArray(raw.features), "changes: features missing");
  const features = raw.features.map(checkFeature);
  const ids = new Set(features.map((f) => f.properties.id));
  need(ids.size === features.length, "changes: duplicate ids");
  return raw as unknown as Changes;
}

/** Validates every summary.json field the map reads or displays; throws ContractError on the first violation. */
export function parseSummary(raw: unknown): Summary {
  need(isObject(raw), "summary: not an object");
  need(raw.contract_version === SUPPORTED_CONTRACT,
    `summary: contract ${String(raw.contract_version)}, map supports ${SUPPORTED_CONTRACT}`);
  need(isText(raw.pipeline_version), "summary: pipeline_version missing");
  need(isText(raw.interpretation), "summary: interpretation missing");
  const { releases, inputs_sha256: sha, aoi, thresholds_m: th } = raw;
  need(isObject(releases) && isText(releases.prev) && isText(releases.curr), "summary: releases missing");
  need(isObject(sha) && isText(sha.prev) && isText(sha.curr), "summary: inputs_sha256 missing");
  need(isObject(aoi) && isLonLat(aoi.west, aoi.south) && isLonLat(aoi.east, aoi.north)
    && (aoi.west as number) < (aoi.east as number) && (aoi.south as number) < (aoi.north as number),
    "summary: aoi must be a WGS84 box with west < east and south < north");
  need(isObject(th) && isNum(th.minor_move) && isNum(th.move) && isNum(th.major_move)
    && th.minor_move > 0 && th.minor_move < th.move && th.move < th.major_move,
    "summary: thresholds_m must be positive and ordered minor_move < move < major_move");
  need(isObject(raw.change_counts), "summary: change_counts missing");
  for (const t of [...CHANGE_TYPES, "excluded", "unchanged"]) {
    need(isCount(raw.change_counts[t]), `summary: change_counts.${t} must be a count`);
  }
  // "Counts reconcile" is shown when every identity holds, so an empty or malformed section must not pass as true.
  const rec = raw.reconciliation;
  need(isObject(rec) && Object.keys(rec).length > 0, "summary: reconciliation has no identities");
  for (const [k, r] of Object.entries(rec)) {
    need(isObject(r) && isText(r.identity) && isNum(r.lhs) && isNum(r.rhs) && typeof r.holds === "boolean",
      `summary: reconciliation.${k} needs identity, lhs, rhs and a boolean holds`);
  }
  const cc = raw.changelog_check;
  if (cc !== null) {
    need(isObject(cc) && (cc.changelog_sha256 === null || isText(cc.changelog_sha256)) && isObject(cc.rules),
      "summary: changelog_check must be null or carry changelog_sha256 and rules");
    for (const [k, v] of Object.entries(cc.rules)) {
      need(isObject(v) && isCount(v.checked) && isCount(v.mismatches), `summary: changelog_check.rules.${k} needs counts`);
    }
    const types = cc.changelog_types_for_considered_ids;
    need(types === undefined || (isObject(types) && Object.values(types).every(isCount)),
      "summary: changelog_check.changelog_types_for_considered_ids must hold counts");
  }
  return raw as unknown as Summary;
}

/** Both files must describe the same run; otherwise the map would mix numbers from different builds. */
export function checkSameRun(changes: Changes, summary: Summary): void {
  const m = changes.geotrustops;
  need(m.releases.prev === summary.releases.prev && m.releases.curr === summary.releases.curr,
    "changes and summary describe different releases");
  need(m.inputs_sha256.prev === summary.inputs_sha256.prev && m.inputs_sha256.curr === summary.inputs_sha256.curr,
    "changes and summary come from different inputs");
  need(m.changelog_sha256 === (summary.changelog_check?.changelog_sha256 ?? null),
    "changes and summary were checked against different changelogs");
  // A check, not a displayed number: the map shows summary.json's counts, and the features must agree with them.
  for (const t of CHANGE_TYPES) {
    const drawn = changes.features.filter((f) => f.properties.change_type === t).length;
    need(drawn === summary.change_counts[t], `changes has ${drawn} ${t} records, summary counts ${summary.change_counts[t]}`);
  }
}

/** True when every reconciliation identity in summary.json holds. */
export function reconciliationHolds(summary: Summary): boolean {
  return Object.values(summary.reconciliation).every((r) => r.holds);
}

/** Previous and current positions of a record; null where the record has no position in that release. */
export function positions(p: ChangeProperties): { prev: [number, number] | null; curr: [number, number] | null } {
  const prev = p.prev_lon !== null && p.prev_lat !== null ? ([p.prev_lon, p.prev_lat] as [number, number]) : null;
  const curr = p.curr_lon !== null && p.curr_lat !== null ? ([p.curr_lon, p.curr_lat] as [number, number]) : null;
  return { prev, curr };
}

// ---------- quality triage file (out_triage/stack_causes.json, ODbL, schema_version 1) ----------

export interface StackCluster {
  size: number;
  lon: number;
  lat: number;
  likely_cause: string;
  also_duplicates: boolean;
  manual_inspection: true;
  ids: string[];
}

export interface Triage {
  schema_version: 1;
  release: string;
  method: string;
  cluster_rule_m: number;
  places_in_aoi: number;
  inputs_sha256: { places: string } & Record<string, string>;
  cluster_count: number;
  clustered_places: number;
  licence: "ODbL-1.0";
  licence_uri: string;
  attribution: string;
  interpretation: string;
  clusters: StackCluster[];
}

/** Validates the stacked-places triage file; throws ContractError on the first violation. */
export function parseTriage(raw: unknown): Triage {
  need(isObject(raw), "triage: not an object");
  need(raw.schema_version === 1, `triage: schema ${String(raw.schema_version)}, map supports 1`);
  // The licence link is used as a link target: only an https address is accepted.
  need(raw.licence === "ODbL-1.0" && typeof raw.licence_uri === "string" && raw.licence_uri.startsWith("https://"),
    "triage: ODbL licence notice missing");
  need(isText(raw.attribution) && isText(raw.release), "triage: attribution/release missing");
  need(isText(raw.interpretation), "triage: interpretation missing");
  need(isNum(raw.cluster_rule_m) && raw.cluster_rule_m > 0, "triage: cluster_rule_m must be a positive number");
  need(isObject(raw.inputs_sha256) && typeof raw.inputs_sha256.places === "string", "triage: inputs_sha256 missing");
  need(Array.isArray(raw.clusters), "triage: clusters missing");
  need(raw.cluster_count === raw.clusters.length, "triage: cluster_count does not match the clusters listed");
  let places = 0;
  raw.clusters.forEach((c: unknown, i: number) => {
    const at = `clusters[${i}]`;
    need(isObject(c), `${at}: not an object`);
    need(isLonLat(c.lon, c.lat), `${at}: centre missing or out of range`);
    need(typeof c.also_duplicates === "boolean", `${at}: also_duplicates must be boolean`);
    need(typeof c.likely_cause === "string" && c.likely_cause.length > 0, `${at}: likely_cause missing`);
    need(c.manual_inspection === true, `${at}: every cluster must be flagged for manual inspection`);
    need(Array.isArray(c.ids) && c.ids.every((x) => typeof x === "string"), `${at}: ids must be strings`);
    need(typeof c.size === "number" && c.size >= 2 && c.size === c.ids.length, `${at}: size must equal ids (>= 2)`);
    places += c.size;
  });
  need(places === raw.clustered_places, "triage: clustered_places does not match the clusters listed");
  return raw as unknown as Triage;
}

/** Quality flags describe one release; showing them with another change run would mislabel them (contract §11). */
export function checkTriageMatchesRun(triage: Triage, summary: Summary): void {
  need(triage.release === summary.releases.curr,
    `quality flags are for release ${triage.release}, the change run's current release is ${summary.releases.curr}`);
  need(triage.inputs_sha256.places === summary.inputs_sha256.curr,
    "quality flags were computed from a different places extract than the change run");
}

// ---------- release timeline (out_timeline/timeline.json, contract §12, schema_version 1) ----------

export const TIMELINE_KINDS = ["added", "removed", "position_changed"] as const;
export type TimelineKind = (typeof TIMELINE_KINDS)[number];
export const TIMELINE_FIELDS = [
  "release_index", "kind_index", "id_index", "lon", "lat", "from_release_index", "from_lon", "from_lat", "distance_m",
] as const;
export const TIMELINE_LICENCES = ["CDLA-Permissive-2.0", "Apache-2.0", "CC0-1.0"] as const;

/** One event: [release, kind, id, lon, lat, from release, from lon, from lat, distance m] (contract §12). */
export type TimelineEvent = [
  number, number, number, number, number, number | null, number | null, number | null, number | null,
];

export interface TimelineRelease {
  release: string;
  change_type_partitions: string[];
  changes_published: boolean;
  added: number;
  removed: number;
  position_changed: number;
  position_changed_labelled_unchanged: number;
  first_seen_without_added: number;
}

export interface Timeline {
  schema_version: 1;
  aoi: { west: number; south: number; east: number; north: number };
  min_step_m: number;
  method: string;
  interpretation: string[];
  kinds: TimelineKind[];
  event_fields: string[];
  releases: TimelineRelease[];
  ids: string[];
  events: TimelineEvent[];
  event_count: number;
  inputs_sha256: Record<string, string>;
  licences: string[];
  attribution: string;
}

const sameList = (a: unknown, b: readonly string[]) =>
  Array.isArray(a) && a.length === b.length && a.every((x, i) => x === b[i]);

/** Validates the release timeline; throws ContractError on the first violation. */
export function parseTimeline(raw: unknown): Timeline {
  need(isObject(raw), "timeline: not an object");
  need(raw.schema_version === 1, `timeline: schema ${String(raw.schema_version)}, map supports 1`);
  need(sameList(raw.kinds, TIMELINE_KINDS), "timeline: unexpected kinds");
  need(sameList(raw.event_fields, TIMELINE_FIELDS), "timeline: unexpected event_fields");
  need(sameList(raw.licences, TIMELINE_LICENCES) && typeof raw.attribution === "string" && raw.attribution.length > 0,
    "timeline: licences or attribution missing");
  need(Array.isArray(raw.interpretation) && raw.interpretation.length > 0, "timeline: interpretation missing");
  need(Array.isArray(raw.releases) && raw.releases.length >= 2, "timeline: releases missing");
  need(Array.isArray(raw.ids) && raw.ids.every((x) => typeof x === "string"), "timeline: ids must be strings");
  need(Array.isArray(raw.events) && raw.event_count === raw.events.length, "timeline: event_count does not match");
  need(isObject(raw.inputs_sha256), "timeline: inputs_sha256 missing");
  const releases = raw.releases as unknown[];
  let total = 0;
  releases.forEach((r, i) => {
    need(isObject(r) && typeof r.release === "string" && typeof r.changes_published === "boolean",
      `timeline releases[${i}]: release or changes_published missing`);
    for (const k of [...TIMELINE_KINDS, "first_seen_without_added"]) {
      need(isCount(r[k]), `timeline releases[${i}]: ${k} must be a count`);
    }
    for (const k of TIMELINE_KINDS) total += r[k] as number;
    need(i === 0 || (releases[i - 1] as { release: string }).release < r.release, "timeline: releases not oldest first");
  });
  need(total === raw.events.length, "timeline: per-release counts do not add up to the events listed");
  const nIds = (raw.ids as unknown[]).length;
  (raw.events as unknown[]).forEach((e, i) => {
    const at = `timeline events[${i}]`;
    need(Array.isArray(e) && e.length === TIMELINE_FIELDS.length, `${at}: wrong length`);
    const [rel, kind, id, lon, lat, fromRel, fromLon, fromLat, dist] = e as unknown[];
    need(Number.isInteger(rel) && (rel as number) >= 0 && (rel as number) < releases.length, `${at}: release out of range`);
    need(Number.isInteger(kind) && (kind as number) >= 0 && (kind as number) < TIMELINE_KINDS.length, `${at}: kind out of range`);
    need(Number.isInteger(id) && (id as number) >= 0 && (id as number) < nIds, `${at}: id out of range`);
    need(typeof lon === "number" && typeof lat === "number", `${at}: position missing`);
    const moved = TIMELINE_KINDS[kind as number] === "position_changed";
    if (moved) {
      need(Number.isInteger(fromRel) && (fromRel as number) >= 0 && (fromRel as number) < (rel as number) && typeof fromLon === "number"
        && typeof fromLat === "number" && typeof dist === "number", `${at}: a position change needs its from position`);
    } else {
      need(fromRel === null && fromLon === null && fromLat === null && dist === null, `${at}: only position changes have a from position`);
    }
  });
  // Each displayed per-release count must equal the events listed for that release and kind, not only in total.
  const perRelease = releases.map(() => TIMELINE_KINDS.map(() => 0));
  for (const e of raw.events as number[][]) perRelease[e[0]!]![e[1]!]! += 1;
  releases.forEach((r, i) => {
    TIMELINE_KINDS.forEach((k, j) => {
      need((r as Json)[k] === perRelease[i]![j], `timeline releases[${i}]: ${k} count does not match its events`);
    });
  });
  return raw as unknown as Timeline;
}

/** The timeline must end at the change run's current release and use the same changelog (contract §12). */
export function checkTimelineMatchesRun(timeline: Timeline, changes: Changes): void {
  const curr = changes.geotrustops.releases.curr;
  need(timeline.releases[timeline.releases.length - 1]?.release === curr,
    `the timeline does not end at the change run's current release ${curr}`);
  need(timeline.inputs_sha256[curr] === changes.geotrustops.changelog_sha256,
    "the timeline was built from a different changelog than the change run's cross-check");
}

export interface HistoryStep {
  release: string;
  /** "seen": the last-seen position a move started from, listed because no earlier step shows it. */
  kind: TimelineKind | "seen";
  lon: number;
  lat: number;
  distance_m: number | null;
  /** True when a line from the previous step to this one is a recorded move (contract §12); false starts a new run. */
  joined: boolean;
}

/**
 * A record's positions by release from the timeline. Each move is drawn from its own from position (the record's
 * last-seen position), which is listed when the previous step is elsewhere: events outside the study area are not
 * in the file, so consecutive events need not connect. Only a move joins two steps; an add, a removal or a listed
 * origin starts a new run, so unrelated positions are never connected.
 */
export function recordHistory(timeline: Timeline, id: string): HistoryStep[] {
  const idx = timeline.ids.indexOf(id);
  if (idx < 0) return [];
  const out: HistoryStep[] = [];
  for (const e of timeline.events) {
    if (e[2] !== idx) continue;
    const kind = TIMELINE_KINDS[e[1]]!;
    const release = timeline.releases[e[0]]!.release;
    if (kind === "position_changed" && e[5] !== null && e[6] !== null && e[7] !== null) {
      const prev = out[out.length - 1];
      const fromShown = prev !== undefined && prev.kind !== "removed" && prev.lon === e[6] && prev.lat === e[7];
      if (!fromShown) {
        out.push({ release: timeline.releases[e[5]]!.release, kind: "seen", lon: e[6], lat: e[7], distance_m: null, joined: false });
      }
      out.push({ release, kind, lon: e[3], lat: e[4], distance_m: e[8], joined: true });
    } else {
      out.push({ release, kind, lon: e[3], lat: e[4], distance_m: e[8], joined: false });
    }
  }
  return out;
}

/** The recorded moves of a history as line runs: consecutive steps joined by a move, never across a break. */
export function historyRuns(steps: HistoryStep[]): [number, number][][] {
  const runs: [number, number][][] = [];
  for (const s of steps) {
    const p: [number, number] = [s.lon, s.lat];
    const run = runs[runs.length - 1];
    if (s.joined && run) run.push(p);
    else runs.push([p]);
  }
  return runs.filter((r) => r.length >= 2);
}
