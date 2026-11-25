// Typed view of the pipeline's exported files (docs/data_contract.md §5, contract v0.4).
// Purpose: the one place where the map learns the output contract, so a contract change fails loudly here
// (a thrown ContractError) instead of the map silently misreading a field.
// Inputs: parsed JSON of out/changes.geojson and out/summary.json. Outputs: validated, typed objects.
// Rule (ADR 0004): nothing here computes a classification or a count; numbers shown come from summary.json.

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

function checkFeature(f: unknown, i: number): ChangeFeature {
  const at = `features[${i}]`;
  need(isObject(f) && f.type === "Feature", `${at}: not a Feature`);
  const g = f.geometry;
  need(isObject(g) && g.type === "Point" && Array.isArray(g.coordinates), `${at}: geometry must be a Point`);
  const [lon, lat] = g.coordinates as unknown[];
  need(typeof lon === "number" && typeof lat === "number", `${at}: coordinates must be numbers`);
  need(lon >= -180 && lon <= 180 && lat >= -90 && lat <= 90, `${at}: coordinates out of range`);
  const p = f.properties;
  need(isObject(p), `${at}: properties missing`);
  need(typeof p.id === "string" && p.id.length > 0, `${at}: id must be a non-empty string`);
  need(f.id === p.id, `${at}: feature id and properties.id differ`);
  need(CHANGE_TYPES.includes(p.change_type as ChangeType), `${at}: unknown change_type ${String(p.change_type)}`);
  need(p.move_band === null || MOVE_BANDS.includes(p.move_band as MoveBand), `${at}: unknown move_band`);
  for (const k of NUMBER_OR_NULL) need(p[k] === null || typeof p[k] === "number", `${at}: ${k} must be number|null`);
  for (const k of STRING_OR_NULL) need(p[k] === null || typeof p[k] === "string", `${at}: ${k} must be string|null`);
  for (const k of BOOL_OR_NULL) need(p[k] === null || typeof p[k] === "boolean", `${at}: ${k} must be boolean|null`);
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
  need(Array.isArray(raw.features), "changes: features missing");
  const features = raw.features.map(checkFeature);
  const ids = new Set(features.map((f) => f.properties.id));
  need(ids.size === features.length, "changes: duplicate ids");
  return raw as unknown as Changes;
}

/** Validates summary.json fields the map displays; throws ContractError on the first violation. */
export function parseSummary(raw: unknown): Summary {
  need(isObject(raw), "summary: not an object");
  need(raw.contract_version === SUPPORTED_CONTRACT,
    `summary: contract ${String(raw.contract_version)}, map supports ${SUPPORTED_CONTRACT}`);
  need(isObject(raw.change_counts), "summary: change_counts missing");
  for (const t of [...CHANGE_TYPES, "excluded", "unchanged"]) {
    need(typeof raw.change_counts[t] === "number", `summary: change_counts.${t} missing`);
  }
  need(isObject(raw.reconciliation), "summary: reconciliation missing");
  need(isObject(raw.releases) && isObject(raw.aoi) && isObject(raw.inputs_sha256), "summary: provenance missing");
  return raw as unknown as Summary;
}

/** Both files must describe the same run; otherwise the map would mix numbers from different builds. */
export function checkSameRun(changes: Changes, summary: Summary): void {
  const m = changes.geotrustops;
  need(m.releases.prev === summary.releases.prev && m.releases.curr === summary.releases.curr,
    "changes and summary describe different releases");
  need(m.inputs_sha256.prev === summary.inputs_sha256.prev && m.inputs_sha256.curr === summary.inputs_sha256.curr,
    "changes and summary come from different inputs");
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
  need(raw.licence === "ODbL-1.0" && typeof raw.licence_uri === "string", "triage: ODbL licence notice missing");
  need(typeof raw.attribution === "string" && typeof raw.release === "string", "triage: attribution/release missing");
  need(isObject(raw.inputs_sha256) && typeof raw.inputs_sha256.places === "string", "triage: inputs_sha256 missing");
  need(Array.isArray(raw.clusters), "triage: clusters missing");
  need(raw.cluster_count === raw.clusters.length, "triage: cluster_count does not match the clusters listed");
  let places = 0;
  raw.clusters.forEach((c: unknown, i: number) => {
    const at = `clusters[${i}]`;
    need(isObject(c), `${at}: not an object`);
    need(typeof c.lon === "number" && typeof c.lat === "number", `${at}: centre missing`);
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
