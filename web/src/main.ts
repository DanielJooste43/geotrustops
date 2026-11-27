// GeoTrustOps web map: shows the pipeline's exported change records on a dark basemap.
// Inputs: data/changes.geojson, data/summary.json (copied from out/); data/stack_causes.json (quality flags) and
// data/timeline.json (release history, loaded on first use). Every number shown comes from those files (ADR 0004);
// the browser filters what is drawn but never computes a count or a classification.
import {
  AttributionControl, GeoJSONSource, Map as MapLibreMap, NavigationControl, ScaleControl, setWorkerUrl,
  type ExpressionSpecification, type FilterSpecification, type MapGeoJSONFeature, type StyleSpecification,
} from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
// MapLibre v6 runs tile parsing in a module worker loaded from its own file; let Vite emit it as an asset.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";
import {
  CHANGE_TYPES, ContractError, checkSameRun, checkTimelineMatchesRun, checkTriageMatchesRun, parseChanges, parseSummary,
  historyRuns, parseTimeline, parseTriage, positions, reconciliationHolds, recordHistory,
  type ChangeFeature, type ChangeProperties, type ChangeType, type Changes, type StackCluster, type Summary,
  type Timeline, type Triage,
} from "./contract";
import { HISTORY_CLICKABLE, Playback } from "./playback";
import { SWIPE_AFTER_LAYER, Swipe, type SymbolImages } from "./swipe";
import { SELECTION_LAYERS, SELECTION_SOURCES, type SelectionSource } from "./selection";
import { drawSymbol, symbolSvg, symbolsFor, type Symbol } from "./symbols";

const STYLE_URL = "https://tiles.openfreemap.org/styles/dark";
// The basemap's TileJSON supplies "OpenFreeMap © OpenMapTiles Data from OpenStreetMap" (linked); we add only the
// credits it does not cover. Without the basemap (fallback), only the data credit applies.
const DATA_ATTRIBUTION = '<a href="https://overturemaps.org/" target="_blank" rel="noopener">Overture Maps Foundation</a>';
const BASEMAP_TIMEOUT_MS = 8000;
const OVERALL = "#e879f9"; // one colour for every changed record in the overall view
const TYPE_LAYERS = ["changes-halo", "changes"];
const OVERALL_LAYERS = ["overall-glow", "overall-core"];
const CHANGE_CLICKABLE = ["changes", "overall-core", "overall-glow", SWIPE_AFTER_LAYER];
const FLAG = "#a78bfa";
// Quality rings per view. In the glow views the violet ring sits next to the magenta glow, two close hues, so the
// rings become a thin, dim outline there and the glow carries the colour.
const RING_STYLE = {
  types: { fill: 0.06, width: 1.25, stroke: 0.6 },
  glow: { fill: 0, width: 1, stroke: 0.35 },
} as const;
setWorkerUrl(workerUrl);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const $ = <T extends HTMLElement>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el as T;
};

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text; // always text, never HTML: names come from source data
  return e;
}

const fmt = new Intl.NumberFormat("en-ZA");

async function loadJson(url: string): Promise<unknown> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

/** Fetches the basemap style; resolves to a plain dark style if the provider is unreachable. */
async function loadStyle(): Promise<{ style: StyleSpecification | string; basemap: boolean }> {
  const fallback: StyleSpecification = {
    version: 8,
    sources: {},
    layers: [{ id: "background", type: "background", paint: { "background-color": "#080f19" } }],
  };
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), BASEMAP_TIMEOUT_MS);
    const r = await fetch(STYLE_URL, { signal: ctrl.signal });
    clearTimeout(t);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return { style: (await r.json()) as StyleSpecification, basemap: true };
  } catch {
    return { style: fallback, basemap: false };
  }
}

function showNotice(text: string): void {
  const n = $("notice");
  n.textContent = text;
  n.hidden = false;
}

// ---------- header, counts, legend ----------

function renderHeader(summary: Summary): void {
  const r = $("releases");
  r.replaceChildren(
    "Overture places ",
    Object.assign(el("strong"), { textContent: summary.releases.prev }),
    " → ",
    Object.assign(el("strong"), { textContent: summary.releases.curr }),
    Object.assign(el("span", "wide-only"), { textContent: " · central Pretoria study area" }),
  );
  $("interpretation").textContent = summary.interpretation.replace(/!=/g, "≠");
  // The headline finding, stated where a visitor lands: every number is read from summary.json, none is computed.
  const flagged = summary.changelog_check?.changelog_types_for_considered_ids?.data_changed;
  const h = $("headline");
  if (flagged === undefined) { h.hidden = true; return; }
  const c = summary.change_counts;
  h.replaceChildren(
    "Overture's changelog marks ", Object.assign(el("strong"), { textContent: fmt.format(flagged) }),
    " places here as changed; this comparison finds ", Object.assign(el("strong"), { textContent: fmt.format(c.moved) }),
    ` moved more than ${summary.thresholds_m.move} m and `, Object.assign(el("strong"), { textContent: fmt.format(c.attribute_changed) }),
    " renamed or recategorised.",
  );
}

function renderCounts(summary: Summary, symbols: Record<ChangeType, Symbol>): void {
  const strip = $("counts");
  strip.replaceChildren();
  for (const t of CHANGE_TYPES) {
    const c = el("div", "count");
    c.append(symbolSvg(symbols[t]), el("span", "n", fmt.format(summary.change_counts[t])), el("span", "label", symbols[t].label));
    strip.append(c);
  }
  // Context, not change counts: drawn quieter and grouped at the end so the five change classes lead.
  const meta = el("div", "count-meta");
  const unchanged = el("span", "meta-item");
  unchanged.append(el("span", "n", fmt.format(summary.change_counts.unchanged)), " unchanged (not drawn)");
  const ok = reconciliationHolds(summary);
  const rec = el("span", `meta-item ${ok ? "ok" : "bad"}`);
  rec.append(el("span", "mark-ok", ok ? "✓" : "✗"), ok ? " Counts reconcile" : " Reconciliation failed");
  meta.append(unchanged, rec);
  strip.append(meta);
}

function renderFilters(summary: Summary, symbols: Record<ChangeType, Symbol>, onChange: (shown: ChangeType[]) => void): void {
  const list = $("filter-list");
  list.replaceChildren();
  const boxes: HTMLInputElement[] = [];
  for (const t of CHANGE_TYPES) {
    const label = el("label", "filter");
    const box = el("input");
    box.type = "checkbox";
    box.checked = true;
    box.value = t;
    boxes.push(box);
    label.append(box, symbolSvg(symbols[t]), el("span", "name", symbols[t].label), el("span", "n", fmt.format(summary.change_counts[t])));
    list.append(label);
  }
  list.addEventListener("change", () => onChange(boxes.filter((b) => b.checked).map((b) => b.value as ChangeType)));
}

// ---------- provenance panel ----------

function renderProvenance(summary: Summary, changes: Changes): void {
  const body = $("provenance-body");
  body.replaceChildren();
  const kv = el("dl", "kv");
  const row = (k: string, v: string, mono = false) => {
    kv.append(el("dt", undefined, k));
    const dd = el("dd", mono ? "mono" : undefined, v);
    kv.append(dd);
  };
  row("Releases", `${summary.releases.prev} → ${summary.releases.curr}`);
  row("Study area", `${summary.aoi.west}, ${summary.aoi.south}, ${summary.aoi.east}, ${summary.aoi.north} (WGS84)`);
  row("Pipeline", `v${summary.pipeline_version}, data contract v${summary.contract_version}`);
  row("Thresholds", `shifted > ${summary.thresholds_m.minor_move} m, moved > ${summary.thresholds_m.move} m`);
  row("Input prev (SHA-256)", summary.inputs_sha256.prev, true);
  row("Input curr (SHA-256)", summary.inputs_sha256.curr, true);
  row("Changelog (SHA-256)", changes.geotrustops.changelog_sha256 ?? "not used", true);
  body.append(kv);

  body.append(el("h3", undefined, "Reconciliation identities (all must hold, or the run fails)"));
  for (const r of Object.values(summary.reconciliation)) {
    const line = el("div", "identity");
    line.append(el("span", r.holds ? "tick" : "cross", r.holds ? "✓" : "✗"), el("span", undefined, `${r.identity}: ${fmt.format(r.lhs)} = ${fmt.format(r.rhs)}`));
    body.append(line);
  }
  if (summary.changelog_check) {
    body.append(el("h3", undefined, "Independent check against Overture's changelog"));
    for (const [rule, v] of Object.entries(summary.changelog_check.rules)) {
      const line = el("div", "identity");
      const ok = v.mismatches === 0;
      line.append(el("span", ok ? "tick" : "cross", ok ? "✓" : "✗"), el("span", undefined, `${rule.replace(/_/g, " ")}: ${fmt.format(v.checked)} checked, ${fmt.format(v.mismatches)} mismatches`));
      body.append(line);
    }
  }
  const p = el("p", "note", "Outputs are deterministic for these inputs: rebuilding from the same releases gives byte-identical files.");
  body.append(p);
}

// ---------- inspector ----------

const show = (v: string | number | null | undefined): string => (v === null || v === undefined || v === "" ? "—" : String(v));

function diffRow(dl: HTMLElement, label: string, prev: string | number | null, curr: string | number | null): void {
  dl.append(el("dt", undefined, label));
  const dd = el("dd");
  const changed = show(prev) !== show(curr);
  if (!changed) dd.textContent = show(curr);
  else {
    const d = el("div", "diff");
    d.append(el("span", "was", show(prev)), el("span", "arrow", "→"), el("span", "changed", show(curr)));
    dd.append(d);
  }
  dl.append(dd);
}

function renderInspector(p: ChangeProperties, s: Symbol, summary: Summary): void {
  const body = $("inspector-body");
  body.replaceChildren();
  $("inspector-title").textContent = p.curr_name ?? p.prev_name ?? "(no name)";
  const badge = el("span", "badge");
  badge.style.color = s.color;
  badge.append(symbolSvg(s), s.label);
  body.append(badge);

  const kv = el("dl", "kv");
  const oneSide = p.change_type === "added" || p.change_type === "removed";
  if (oneSide) {
    // Added records exist only in the current release, removed ones only in the previous: show that side's values.
    const side = p.change_type === "added" ? "curr" : "prev";
    const release = side === "curr" ? summary.releases.curr : summary.releases.prev;
    kv.append(el("dt", undefined, "Present in"), el("dd", undefined, `${release} only`));
    const v = (k: "name" | "category" | "basic_category" | "operating_status") => p[`${side}_${k}`];
    kv.append(el("dt", undefined, "Name"), el("dd", undefined, show(v("name"))));
    kv.append(el("dt", undefined, "Category"), el("dd", undefined, show(v("category"))));
    kv.append(el("dt", undefined, "Basic category"), el("dd", undefined, show(v("basic_category"))));
    kv.append(el("dt", undefined, "Status"), el("dd", undefined, show(v("operating_status"))));
    kv.append(el("dt", undefined, "Confidence"), el("dd", undefined, show(p[`${side}_confidence`]?.toFixed(2))));
  } else {
    diffRow(kv, "Name", p.prev_name, p.curr_name);
    diffRow(kv, "Category", p.prev_category, p.curr_category);
    diffRow(kv, "Basic category", p.prev_basic_category, p.curr_basic_category);
    diffRow(kv, "Status", p.prev_operating_status, p.curr_operating_status);
    diffRow(kv, "Confidence", p.prev_confidence?.toFixed(2) ?? null, p.curr_confidence?.toFixed(2) ?? null);
  }
  if (p.distance_m !== null) {
    kv.append(el("dt", undefined, "Position change"), el("dd", undefined, `${p.distance_m} m (${show(p.move_band)})`));
  }
  const flags: string[] = [];
  if (p.name_change_kind) flags.push(`rename: ${p.name_change_kind.replace(/_/g, " ")}`);
  if (p.crossed_aoi_boundary) flags.push("crossed the study-area boundary");
  if (p.status_changed) flags.push("operating status changed");
  if (p.confidence_to_zero) flags.push("confidence dropped to 0");
  if (p.enrichment_changed) flags.push(`contact/address fields changed: ${p.enrichment_changed.replace(/;/g, ", ")}`);
  if (p.format_only_changed) flags.push(`format-only change: ${p.format_only_changed.replace(/;/g, ", ")}`);
  if (flags.length) kv.append(el("dt", undefined, "Also"), el("dd", undefined, flags.join("; ")));
  kv.append(el("dt", undefined, "Releases"), el("dd", undefined, `${summary.releases.prev} → ${summary.releases.curr}`));
  kv.append(el("dt", undefined, "Record ID"), el("dd", "mono", p.id));
  body.append(kv);
  body.append(el("p", "note small", "A change to the map record, not proof of a real-world opening, closure or move."));
}

function renderClusterInspector(c: StackCluster, triage: Triage): void {
  const body = $("inspector-body");
  body.replaceChildren();
  $("inspector-title").textContent = `${c.size} places stacked within ${triage.cluster_rule_m} m`;
  body.append(el("span", "badge flag", "Quality flag · manual inspection"));
  const kv = el("dl", "kv");
  kv.append(el("dt", undefined, "Likely cause"), el("dd", undefined, c.likely_cause));
  if (c.also_duplicates) kv.append(el("dt", undefined, "Also"), el("dd", undefined, "contains duplicate records"));
  kv.append(el("dt", undefined, "Release"), el("dd", undefined, triage.release));
  kv.append(el("dt", undefined, "Position"), el("dd", "mono", `lon ${c.lon.toFixed(6)}, lat ${c.lat.toFixed(6)}`));
  body.append(kv);
  body.append(el("h3", undefined, `Place IDs (${c.size})`));
  const list = el("ul", "ids mono");
  for (const id of c.ids.slice(0, 8)) list.append(el("li", undefined, id));
  if (c.size > 8) list.append(el("li", undefined, `and ${c.size - 8} more (in the downloadable database)`));
  body.append(list);
  body.append(el("p", "note small", triage.interpretation));
  const notice = el("p", "note small");
  const a = el("a", undefined, "Open Database License (ODbL)");
  a.href = triage.licence_uri;
  a.rel = "noopener";
  notice.append(`Derived from data ${triage.attribution}; made available under the `, a, ".");
  body.append(notice);
}

/** Appends a record's positions by release (from the timeline) to the open inspector; returns its trail for the map. */
function renderHistorySection(tl: Timeline, id: string): { points: [number, number][]; runs: [number, number][][] } {
  const steps = recordHistory(tl, id);
  if (steps.length === 0) return { points: [], runs: [] };
  const body = $("inspector-body");
  body.append(el("h3", undefined, "Position by release"));
  const list = el("ul", "history-list");
  const label = { seen: "last-seen position", added: "added", removed: "removed (last position)", position_changed: "moved" };
  for (const s of steps) {
    const li = el("li");
    const what = s.distance_m !== null ? `${label[s.kind]} ${s.distance_m} m` : label[s.kind];
    li.append(el("span", "mono", s.release), el("span", undefined, what),
      el("span"), el("span", "meta mono", `lon ${s.lon.toFixed(6)}, lat ${s.lat.toFixed(6)}`));
    list.append(li);
  }
  body.append(list);
  body.append(el("p", "note small",
    "From Overture's changelogs: positions per release, not dates within it. Dotted lines join a record's recorded "
    + "moves only; steps outside the study area are not listed, so a move may start from a last-seen position."));
  return { points: steps.map((s) => [s.lon, s.lat] as [number, number]), runs: historyRuns(steps) };
}

// ---------- map ----------

async function main(): Promise<void> {
  let changes: Changes;
  let summary: Summary;
  try {
    [changes, summary] = await Promise.all([
      loadJson("./data/changes.geojson").then(parseChanges),
      loadJson("./data/summary.json").then(parseSummary),
    ]);
    checkSameRun(changes, summary);
  } catch (e) {
    const why = e instanceof ContractError ? `The exported files do not match the data contract: ${e.message}` : String(e);
    $("releases").textContent = "Data could not be loaded.";
    showNotice(why);
    return;
  }

  // The release timeline is optional and large: loaded on first use, and refused if it describes another run.
  let timelinePromise: Promise<Timeline> | null = null;
  let timelineReady: Timeline | null = null; // set once loaded, for synchronous use in the click handler
  const getTimeline = (): Promise<Timeline> =>
    (timelinePromise ??= loadJson("./data/timeline.json").then((raw) => {
      const t = parseTimeline(raw);
      checkTimelineMatchesRun(t, changes);
      timelineReady = t;
      return t;
    }));

  // The quality layer is optional: if its file is missing or invalid, the change map still works.
  let triage: Triage | null = null;
  try {
    const parsed = parseTriage(await loadJson("./data/stack_causes.json"));
    checkTriageMatchesRun(parsed, summary); // never show flags from another release under this run's label
    triage = parsed;
    $("quality-count").textContent =
      `${fmt.format(triage.cluster_count)} groups · ${fmt.format(triage.clustered_places)} places · larger ring, more places`;
  } catch (e) {
    $<HTMLInputElement>("quality").disabled = true;
    $("quality-count").textContent = e instanceof ContractError ? "not available for this release" : "unavailable";
    console.warn("quality flags not loaded:", e);
  }

  const symbols = symbolsFor(summary.thresholds_m);
  renderHeader(summary);
  renderCounts(summary, symbols);
  renderProvenance(summary, changes);

  const { style, basemap } = await loadStyle();
  if (!basemap) showNotice("The basemap could not be loaded. Changes are shown on a plain background.");

  const { west, south, east, north } = summary.aoi;
  const map = new MapLibreMap({
    container: "map",
    style,
    bounds: [[west, south], [east, north]],
    fitBoundsOptions: { padding: 40 },
    attributionControl: false,
    dragRotate: false,
    fadeDuration: reducedMotion ? 0 : 300,
    pitchWithRotate: false,
  });
  map.addControl(new AttributionControl({ compact: false, customAttribution: DATA_ATTRIBUTION }), "bottom-right");
  map.addControl(new NavigationControl({ showCompass: false }), "top-left");
  map.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
  map.touchZoomRotate.disableRotation();
  trackAttributionHeight();

  // The upstream Dark style references a pattern image its sprite does not contain; resolve it to a transparent
  // pixel so the console stays clean (the pattern is not needed for this map).
  map.setMissingStyleImageResolver((id) => {
    if (!map.hasImage(id)) map.addImage(id, { width: 1, height: 1, data: new Uint8Array(4) });
  });

  map.on("load", () => {
    const images = {} as SymbolImages;
    for (const t of CHANGE_TYPES) {
      const img = drawSymbol(symbols[t]);
      images[t] = { width: img.width, height: img.height, data: new Uint8Array(img.data.buffer) };
      map.addImage(`sym-${t}`, images[t], { pixelRatio: 2 });
    }

    // Study-area outline (from summary.json): context for edge effects.
    map.addSource("aoi", {
      type: "geojson",
      data: {
        type: "Feature", properties: {},
        geometry: { type: "Polygon", coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]] },
      },
    });
    map.addLayer({ id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": "#a8b8ca", "line-width": 1, "line-dasharray": [3, 3], "line-opacity": 0.6 } });

    if (triage) {
      const fc: FeatureCollection = {
        type: "FeatureCollection",
        features: triage.clusters.map((c, i) => ({
          type: "Feature", id: i, properties: { idx: i, size: c.size },
          geometry: { type: "Point", coordinates: [c.lon, c.lat] },
        })),
      };
      map.addSource("quality", { type: "geojson", data: fc });
      map.addLayer({
        id: "quality-ring", type: "circle", source: "quality",
        paint: {
          // Area grows with group size (radius ~ sqrt(size)), capped so the largest stacks do not cover whole
          // clusters. Drawn lighter than the change symbols: the flags support the change map, they do not lead it.
          "circle-radius": ["interpolate", ["linear"], ["zoom"],
            12, ["min", ["*", 2.4, ["sqrt", ["get", "size"]]], 18],
            16, ["min", ["*", 5, ["sqrt", ["get", "size"]]], 36]],
          "circle-color": FLAG,
          "circle-opacity": RING_STYLE.types.fill,
          "circle-stroke-color": FLAG,
          "circle-stroke-width": RING_STYLE.types.width,
          "circle-stroke-opacity": RING_STYLE.types.stroke,
        },
      });
    }

    map.addSource("changes", { type: "geojson", data: changes as unknown as FeatureCollection, promoteId: "id" });
    map.addLayer({
      id: "changes-halo", type: "circle", source: "changes",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 6, 16, 12, 19, 18],
        "circle-color": ["match", ["get", "change_type"], ...CHANGE_TYPES.flatMap((t) => [t, symbols[t].color]), "#ffffff"] as unknown as ExpressionSpecification,
        "circle-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 0.45, 0.14],
        "circle-blur": 0.6,
      },
    });
    map.addLayer({
      id: "changes", type: "symbol", source: "changes",
      layout: {
        "icon-image": ["concat", "sym-", ["get", "change_type"]],
        "icon-size": ["interpolate", ["linear"], ["zoom"], 12, 0.45, 15, 0.7, 18, 1],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
        "symbol-sort-key": ["match", ["get", "change_type"], "shifted", 1, "attribute_changed", 2, "moved", 3, "removed", 4, 5],
      },
    });

    // Overall view: every changed record as the same glowing point. Overlapping halos brighten where records
    // concentrate; nothing is aggregated or computed. The optional heatmap is a kernel-smoothed view of the same points.
    map.addLayer({
      id: "overall-heat", type: "heatmap", source: "changes", layout: { visibility: "none" },
      paint: {
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 12, 14, 15, 28, 18, 60],
        "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 12, 0.6, 16, 1.2],
        "heatmap-opacity": 0.8,
        "heatmap-color": [
          "interpolate", ["linear"], ["heatmap-density"],
          0, "rgba(217,70,239,0)", 0.15, "rgba(217,70,239,0.12)", 0.4, "rgba(217,70,239,0.32)",
          0.7, "rgba(232,121,249,0.55)", 1, "rgba(245,208,254,0.75)",
        ],
      },
    }, "changes-halo");
    map.addLayer({
      id: "overall-glow", type: "circle", source: "changes", layout: { visibility: "none" },
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 7, 15, 13, 18, 26],
        "circle-color": OVERALL,
        "circle-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 0.7, 0.28],
        "circle-blur": 1,
      },
    });
    map.addLayer({
      id: "overall-core", type: "circle", source: "changes", layout: { visibility: "none" },
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 1.6, 15, 2.6, 18, 4.5],
        "circle-color": "#fdf4ff",
        "circle-opacity": 0.95,
      },
    });

    // Selection: previous and current positions joined by a line, and the record's trail by release.
    for (const src of SELECTION_SOURCES) map.addSource(src, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    for (const l of SELECTION_LAYERS) map.addLayer(l);

    // Before/after swipe: the main map shows the later release's positions; a second map on the left of the
    // divider shows the earlier release's.
    const swipe = new Swipe(map, style, changes, summary, images, {
      overlay: $("swipe"), grip: $("swipe-grip"), labelBefore: $("swipe-label-before"), labelAfter: $("swipe-label-after"),
    });

    // Selection markers go to both maps: on the left of the swipe divider the earlier-release map covers the main one.
    const setSelection = (src: SelectionSource, data: FeatureCollection) => {
      map.getSource<GeoJSONSource>(src)?.setData(data);
      swipe.mirrorSelection(src, data);
    };
    const NONE: FeatureCollection = { type: "FeatureCollection", features: [] };

    let selected: string | null = null;
    const select = (f: ChangeFeature | null) => {
      if (selected) map.setFeatureState({ source: "changes", id: selected }, { selected: false });
      selected = f ? f.properties.id : null;
      timelineOnlyOpen = false;
      setSelection("sel-trail", NONE);
      if (!f) {
        setSelection("selection", NONE);
        $("inspector").hidden = true;
        return;
      }
      map.setFeatureState({ source: "changes", id: f.properties.id }, { selected: true });
      const { prev, curr } = positions(f.properties);
      const feats: Feature[] = [];
      if (prev) feats.push({ type: "Feature", properties: { which: "prev" }, geometry: { type: "Point", coordinates: prev } });
      if (curr) feats.push({ type: "Feature", properties: { which: "curr" }, geometry: { type: "Point", coordinates: curr } });
      if (prev && curr && f.properties.distance_m && f.properties.distance_m > 0) {
        feats.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [prev, curr] } });
      }
      setSelection("selection", { type: "FeatureCollection", features: feats });
      renderInspector(f.properties, symbols[f.properties.change_type], summary);
      $("inspector").hidden = false;
      const id = f.properties.id;
      getTimeline().then((tl) => {
        if (selected !== id) return; // another record was chosen meanwhile
        drawRecordHistory(tl, id);
      }).catch(() => { /* history is optional; the History view's status line explains a failure */ });
    };

    // A record's positions by release: listed in the open inspector and drawn as its trail.
    const drawRecordHistory = (tl: Timeline, id: string) => {
      const { points, runs } = renderHistorySection(tl, id);
      if (runs.length === 0) return;
      setSelection("sel-trail", {
        type: "FeatureCollection",
        features: [
          { type: "Feature", properties: {}, geometry: { type: "MultiLineString", coordinates: runs } },
          ...points.map((c): Feature => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: c } })),
        ],
      });
    };

    // History markers: a record in the current comparison opens its full details; any other timeline record opens
    // a timeline-only panel (its id and positions by release). Nothing here is computed beyond listing its events.
    let timelineOnlyOpen = false;
    const selectTimelineRecord = (tl: Timeline, id: string) => {
      const f = byId.get(id);
      if (f) return select(f);
      select(null);
      timelineOnlyOpen = true;
      $("inspector-title").textContent = `Record ${id.slice(0, 8)}`;
      const body = $("inspector-body");
      body.replaceChildren(el("span", "badge flag", "Release history only"));
      const kv = el("dl", "kv");
      kv.append(el("dt", undefined, "Record ID"), el("dd", "mono", id));
      body.append(kv);
      body.append(el("p", "note small", `Not among the changes between ${summary.releases.prev} and `
        + `${summary.releases.curr}, so only its timeline is shown: no names or other attributes are in that file.`));
      $("inspector").hidden = false;
      drawRecordHistory(tl, id);
    };

    const byId = new Map(changes.features.map((f) => [f.properties.id, f]));
    const visibleLayers = (ids: string[]) =>
      ids.filter((l) => map.getLayer(l) && map.getLayoutProperty(l, "visibility") !== "none");
    const selectCluster = (c: StackCluster, t: Triage) => {
      select(null);
      setSelection("selection", {
        type: "FeatureCollection",
        features: [{
          type: "Feature", properties: { which: "curr" }, geometry: { type: "Point", coordinates: [c.lon, c.lat] },
        }],
      });
      renderClusterInspector(c, t);
      $("inspector").hidden = false;
    };
    // One click handler: a change record wins over a quality ring underneath it.
    map.on("click", (e) => {
      // Left of the swipe divider the earlier-release map is on top: only its records can be chosen there.
      const left = swipe.beforeRecordAt(e.point);
      if (left !== undefined) return select(left ? byId.get(left) ?? null : null);
      const change = map.queryRenderedFeatures(e.point, { layers: visibleLayers(CHANGE_CLICKABLE) })[0] as
        MapGeoJSONFeature | undefined;
      const id = change?.properties?.id as string | undefined;
      if (id) return select(byId.get(id) ?? null);
      const marker = timelineReady
        ? map.queryRenderedFeatures(e.point, { layers: visibleLayers(HISTORY_CLICKABLE) })[0]
        : undefined;
      const rid = timelineReady && marker ? timelineReady.ids[Number(marker.properties?.rid)] : undefined;
      if (rid && timelineReady) {
        playback?.stop();
        return selectTimelineRecord(timelineReady, rid);
      }
      const ring = triage ? map.queryRenderedFeatures(e.point, { layers: visibleLayers(["quality-ring"]) })[0] : undefined;
      const c = ring && triage ? triage.clusters[Number(ring.properties?.idx)] : undefined;
      if (c && triage) return selectCluster(c, triage);
      select(null);
    });
    const hoverable = [...CHANGE_CLICKABLE, ...(triage ? ["quality-ring"] : [])]; // history markers: added with them
    map.on("mouseenter", hoverable, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", hoverable, () => { map.getCanvas().style.cursor = ""; });

    $<HTMLInputElement>("quality").addEventListener("change", (e) => {
      if (map.getLayer("quality-ring")) {
        const on = (e.target as HTMLInputElement).checked;
        map.setLayoutProperty("quality-ring", "visibility", on ? "visible" : "none");
      }
    });
    $("inspector-close").addEventListener("click", () => select(null));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") select(null); });

    // Records list: the keyboard path to individual records (map points are not reachable with Tab).
    let shownTypes: ChangeType[] = [...CHANGE_TYPES];
    const search = $<HTMLInputElement>("records-search");
    const sorted = [...changes.features].sort((a, b) =>
      (a.properties.curr_name ?? a.properties.prev_name ?? "").localeCompare(b.properties.curr_name ?? b.properties.prev_name ?? ""));
    const renderRecords = () => {
      const q = search.value.trim().toLowerCase();
      const list = $("records-list");
      list.replaceChildren();
      for (const f of sorted) {
        const p = f.properties;
        if (!shownTypes.includes(p.change_type)) continue;
        const name = p.curr_name ?? p.prev_name ?? "(no name)";
        const cat = p.curr_category ?? p.prev_category ?? "";
        if (q && !name.toLowerCase().includes(q) && !cat.toLowerCase().includes(q)) continue;
        const li = el("li");
        const b = el("button");
        b.type = "button";
        const text = el("span");
        text.append(el("span", undefined, name), el("br"), el("span", "meta", `${symbols[p.change_type].label}${cat ? ` · ${cat}` : ""} · id ${p.id.slice(0, 8)}`));
        b.append(symbolSvg(symbols[p.change_type]), text, el("span", "meta", p.distance_m !== null && p.distance_m > 0 ? `${p.distance_m} m` : ""));
        b.addEventListener("click", () => {
          $<HTMLDialogElement>("panel-records").close();
          select(f);
          const target = { center: f.geometry.coordinates, zoom: Math.max(map.getZoom(), 17) };
          if (reducedMotion) map.jumpTo(target);
          else map.easeTo({ ...target, duration: 600 });
          $("inspector-close").focus();
        });
        li.append(b);
        list.append(li);
      }
    };
    search.addEventListener("input", renderRecords);
    renderRecords();

    renderFilters(summary, symbols, (shown) => {
      shownTypes = shown;
      renderRecords();
      const filter: FilterSpecification = ["in", ["get", "change_type"], ["literal", shown]];
      for (const l of [...TYPE_LAYERS, ...OVERALL_LAYERS, "overall-heat"]) map.setFilter(l, filter);
      swipe.setFilter(shown);
      if (selected && !shown.includes(byId.get(selected)!.properties.change_type)) select(null);
    });

    // View switch: change types (shape + colour per class), overall change (one glow per record), or history
    // (release-by-release playback of the timeline, with movement trails).
    const density = $<HTMLInputElement>("density");
    const setVis = (ids: string[], on: boolean) => {
      for (const l of ids) map.setLayoutProperty(l, "visibility", on ? "visible" : "none");
    };
    let playback: Playback | null = null;
    const status = $("history-status");
    const applyView = () => {
      const view = document.querySelector<HTMLInputElement>('input[name="view"]:checked')?.value ?? "types";
      const overall = view === "overall";
      const history = view === "history";
      const swipeOn = view === "swipe";
      setVis(TYPE_LAYERS, view === "types");
      swipe.setVisible(swipeOn);
      $("swipe-legend").hidden = !swipeOn;
      setVis(OVERALL_LAYERS, overall);
      setVis(["overall-heat"], overall && density.checked);
      if (map.getLayer("quality-ring")) {
        const ring = view === "types" || swipeOn ? RING_STYLE.types : RING_STYLE.glow;
        map.setPaintProperty("quality-ring", "circle-opacity", ring.fill);
        map.setPaintProperty("quality-ring", "circle-stroke-width", ring.width);
        map.setPaintProperty("quality-ring", "circle-stroke-opacity", ring.stroke);
      }
      $("overall-legend").hidden = !overall;
      $("density-note").hidden = !(overall && density.checked);
      $("history-legend").hidden = !history;
      $("filters").hidden = history; // the change-type filters describe the two-release comparison only
      playback?.setVisible(history);
      if (!history && timelineOnlyOpen) select(null); // a timeline-only record has no place in the comparison views
      if (!history || playback) return;
      select(null);
      status.textContent = "Loading the release history…";
      getTimeline().then((tl) => {
        playback ??= new Playback(map, tl, {
          panel: $("playback"), play: $<HTMLButtonElement>("pb-play"), prev: $<HTMLButtonElement>("pb-prev"),
          next: $<HTMLButtonElement>("pb-next"), slider: $<HTMLInputElement>("pb-slider"), label: $("pb-label"),
          note: $("pb-note"), bars: document.getElementById("pb-bars") as unknown as SVGSVGElement,
          trails: $<HTMLInputElement>("trails"),
        }, reducedMotion);
        map.on("mouseenter", HISTORY_CLICKABLE, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", HISTORY_CLICKABLE, () => { map.getCanvas().style.cursor = ""; });
        const first = tl.releases[0]!.release;
        const last = tl.releases[tl.releases.length - 1]!.release;
        status.textContent = `${tl.releases.length} releases, ${first} to ${last}. A spike can reflect a change in `
          + "Overture's sources or schema rather than on the ground; releases marked with a hollow square published no "
          + "added, removed or edited records.";
        $("history-credit").textContent = `Data: ${tl.attribution} Licences: ${tl.licences.join(", ")}.`;
        applyView();
      }).catch((e: unknown) => {
        status.textContent = e instanceof ContractError
          ? `The release history does not match this map's data: ${e.message}`
          : "The release history could not be loaded.";
        console.warn("timeline not loaded:", e);
      });
    };
    for (const r of document.querySelectorAll<HTMLInputElement>('input[name="view"]')) r.addEventListener("change", applyView);
    density.addEventListener("change", applyView);
    $<HTMLInputElement>("trails").addEventListener("change", applyView);
  });

  map.on("error", (e) => {
    // Tile errors after a successful style load: keep the data visible, explain once.
    if (basemap && String(e.error?.message ?? "").match(/tile|fetch|network/i)) {
      showNotice("Some basemap tiles could not be loaded. The change records are unaffected.");
    }
  });

}

// The attribution line wraps to two lines on a phone. Its live height (and the filter sheet's, below the map) are
// exposed as --attrib-h and --sheet-h so the playback and record panels sit above the credit instead of covering it.
function trackAttributionHeight(): void {
  const layout = document.querySelector<HTMLElement>(".layout");
  const attrib = document.querySelector<HTMLElement>(".maplibregl-ctrl-attrib");
  const rail = $("rail");
  if (!layout || !attrib) return;
  const px = (e: HTMLElement) => `${Math.ceil(e.getBoundingClientRect().height)}px`;
  const update = () => {
    layout.style.setProperty("--attrib-h", px(attrib));
    layout.style.setProperty("--sheet-h", px(rail));
  };
  const observer = new ResizeObserver(update);
  observer.observe(attrib);
  observer.observe(rail);
  update();
}

// Category values such as "diagnostics_imaging_or_lab_service" are single long words: offer line breaks after
// each underscore (<wbr>, so copied text is unchanged) instead of breaking mid-word.
new MutationObserver(() => {
  for (const dd of document.querySelectorAll<HTMLElement>("#inspector-body dd")) {
    const text = dd.textContent ?? "";
    if (dd.childElementCount > 0 || !text.includes("_")) continue;
    dd.replaceChildren(...text.split("_").flatMap((part, i) => (i === 0 ? [part] : ["_", el("wbr"), part])));
  }
}).observe($("inspector-body"), { childList: true, subtree: true });

// Panels and mobile sheet
for (const b of document.querySelectorAll<HTMLButtonElement>("[data-panel]")) {
  b.addEventListener("click", () => document.querySelector<HTMLDialogElement>(`#panel-${b.dataset.panel}`)?.showModal());
}
for (const b of document.querySelectorAll<HTMLButtonElement>("[data-close]")) {
  b.addEventListener("click", () => b.closest("dialog")?.close());
}
$("sheet-handle").addEventListener("click", () => {
  const rail = $("rail");
  const open = rail.classList.toggle("open");
  $("sheet-handle").setAttribute("aria-expanded", String(open));
});

void main();
