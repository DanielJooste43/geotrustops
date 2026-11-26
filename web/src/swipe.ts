// Before/after swipe: the earlier release's positions on the left of a divider, the later release's on the right.
// The right side is the main map; the left side is a second, non-interactive map clipped at the divider. Only the
// main map is ever moved by the user, and the second map follows it, so the two cameras cannot drive each other.
import { Map as MapLibreMap, type FilterSpecification, type StyleSpecification } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import { CHANGE_TYPES, positions, type ChangeType, type Changes, type Summary } from "./contract";

export type Side = "before" | "after";

/** Points for one side: each changed record at its position in that release (records absent there are left out). */
export function sideFeatures(changes: Changes, side: Side): FeatureCollection {
  const features: FeatureCollection["features"] = [];
  for (const f of changes.features) {
    const { prev, curr } = positions(f.properties);
    const at = side === "before" ? prev : curr;
    if (!at) continue;
    features.push({
      type: "Feature", id: f.properties.id,
      properties: { id: f.properties.id, change_type: f.properties.change_type },
      geometry: { type: "Point", coordinates: at },
    });
  }
  return { type: "FeatureCollection", features };
}

/** Expected number of records on each side, from the pipeline's summary: added records exist only in the later
 * release and removed records only in the earlier one; every other change class exists in both. */
export function sideCounts(summary: Summary): Record<Side, number> {
  const c = summary.change_counts;
  const both = c.moved + c.shifted + c.attribute_changed;
  return { before: both + c.removed, after: both + c.added };
}

/** Minimal camera surface used by the follower (lets the sync be tested without a WebGL map). */
export interface CameraSource {
  on(type: "move", fn: () => void): unknown;
  off(type: "move", fn: () => void): unknown;
  getCenter(): { lng: number; lat: number };
  getZoom(): number;
  getBearing(): number;
  getPitch(): number;
}
export interface CameraTarget {
  jumpTo(o: { center: [number, number]; zoom: number; bearing: number; pitch: number }): unknown;
}

/** One-way camera sync: the follower copies the leader on every move. Nothing listens to the follower, so there is
 * no feedback loop. Returns a function that stops following. */
export function followCamera(leader: CameraSource, follower: CameraTarget): () => void {
  const copy = () => {
    const c = leader.getCenter();
    follower.jumpTo({ center: [c.lng, c.lat], zoom: leader.getZoom(), bearing: leader.getBearing(), pitch: leader.getPitch() });
  };
  leader.on("move", copy);
  copy();
  return () => leader.off("move", copy);
}

/** Divider position after a key press (percent of the map width), or null for keys the slider does not handle. */
export function keyStep(key: string, at: number, big: boolean): number | null {
  const step = big ? 10 : 2;
  const next = key === "ArrowLeft" || key === "ArrowDown" ? at - step
    : key === "ArrowRight" || key === "ArrowUp" ? at + step
    : key === "PageDown" ? at - 10
    : key === "PageUp" ? at + 10
    : key === "Home" ? 0
    : key === "End" ? 100
    : null;
  return next === null ? null : Math.min(100, Math.max(0, next));
}

const SYMBOL_LAYOUT = {
  "icon-image": ["concat", "sym-", ["get", "change_type"]],
  "icon-size": ["interpolate", ["linear"], ["zoom"], 12, 0.45, 15, 0.7, 18, 1],
  "icon-allow-overlap": true,
  "icon-ignore-placement": true,
  "symbol-sort-key": ["match", ["get", "change_type"], "shifted", 1, "attribute_changed", 2, "moved", 3, "removed", 4, 5],
} as const;

const LABEL_ROOM_PX = 120;

export const SWIPE_AFTER_LAYER = "swipe-after";
export const SWIPE_BEFORE_LAYER = "swipe-before";

interface SwipeElements {
  overlay: HTMLElement; // divider line, grip (role=slider) and the two release labels
  grip: HTMLElement;
  labelBefore: HTMLElement;
  labelAfter: HTMLElement;
}

/** Symbol images keyed by change type, already drawn for the main map. */
export type SymbolImages = Record<ChangeType, { width: number; height: number; data: Uint8Array }>;

export class Swipe {
  private before: MapLibreMap | null = null;
  private container: HTMLDivElement | null = null;
  private unfollow: (() => void) | null = null;
  private at = 50; // divider position, percent of the map width
  private shown: ChangeType[] = [...CHANGE_TYPES];
  private visible = false;

  constructor(
    private readonly map: MapLibreMap,
    private readonly style: StyleSpecification | string,
    private readonly changes: Changes,
    private readonly summary: Summary,
    private readonly images: SymbolImages,
    private readonly els: SwipeElements,
  ) {
    els.labelBefore.textContent = summary.releases.prev;
    els.labelAfter.textContent = summary.releases.curr;
    map.addSource(SWIPE_AFTER_LAYER, { type: "geojson", data: sideFeatures(changes, "after") });
    // Under the selection markers, so a chosen record's previous and current positions draw on top.
    map.addLayer(
      { id: SWIPE_AFTER_LAYER, type: "symbol", source: SWIPE_AFTER_LAYER, layout: { ...SYMBOL_LAYOUT, visibility: "none" } as never },
      map.getLayer("sel-line") ? "sel-line" : undefined,
    );
    this.bindGrip();
    map.on("resize", () => { this.before?.resize(); this.render(); });
  }

  setVisible(on: boolean): void {
    this.visible = on;
    this.els.overlay.hidden = !on;
    this.map.setLayoutProperty(SWIPE_AFTER_LAYER, "visibility", on ? "visible" : "none");
    if (on && !this.before) this.createBefore();
    if (this.container) this.container.hidden = !on;
    if (on && this.before && !this.unfollow) this.unfollow = followCamera(this.map, this.before);
    if (!on && this.unfollow) { this.unfollow(); this.unfollow = null; } // no work while the view is off
    this.render();
  }

  setFilter(shown: ChangeType[]): void {
    this.shown = shown;
    const filter: FilterSpecification = ["in", ["get", "change_type"], ["literal", shown]];
    this.map.setFilter(SWIPE_AFTER_LAYER, filter);
    if (this.before?.getLayer(SWIPE_BEFORE_LAYER)) this.before.setFilter(SWIPE_BEFORE_LAYER, filter);
  }

  /** The record id under a screen point on the left of the divider, or null (right side: use the main map). */
  beforeRecordAt(point: { x: number; y: number }): string | null | undefined {
    if (!this.visible || !this.before) return undefined;
    if (point.x >= this.dividerPx()) return undefined;
    const hit = this.before.queryRenderedFeatures([point.x, point.y], { layers: [SWIPE_BEFORE_LAYER] })[0];
    return (hit?.properties?.id as string | undefined) ?? null;
  }

  private dividerPx(): number {
    return (this.map.getContainer().clientWidth * this.at) / 100;
  }

  private createBefore(): void {
    // Inside the main map's container, just after its canvas: above the after-map, below its controls and
    // attribution, so the credit line stays visible on both sides.
    const div = document.createElement("div");
    div.className = "swipe-before";
    div.setAttribute("aria-hidden", "true");
    this.map.getCanvasContainer().after(div);
    this.container = div;
    const before = new MapLibreMap({
      container: div,
      style: typeof this.style === "string" ? this.style : structuredClone(this.style),
      interactive: false,
      attributionControl: false,
      center: this.map.getCenter(),
      zoom: this.map.getZoom(),
      fadeDuration: 0,
    });
    before.setMissingStyleImageResolver((id) => {
      if (!before.hasImage(id)) before.addImage(id, { width: 1, height: 1, data: new Uint8Array(4) });
    });
    before.on("load", () => {
      for (const t of CHANGE_TYPES) before.addImage(`sym-${t}`, this.images[t], { pixelRatio: 2 });
      // The same study-area outline as the main map, so both sides share the frame of reference.
      const { west, south, east, north } = this.summary.aoi;
      before.addSource("aoi", {
        type: "geojson",
        data: { type: "Feature", properties: {}, geometry: { type: "Polygon",
          coordinates: [[[west, south], [east, south], [east, north], [west, north], [west, south]]] } },
      });
      before.addLayer({ id: "aoi-line", type: "line", source: "aoi",
        paint: { "line-color": "#a8b8ca", "line-width": 1, "line-dasharray": [3, 3], "line-opacity": 0.6 } });
      before.addSource(SWIPE_BEFORE_LAYER, { type: "geojson", data: sideFeatures(this.changes, "before") });
      before.addLayer({ id: SWIPE_BEFORE_LAYER, type: "symbol", source: SWIPE_BEFORE_LAYER, layout: SYMBOL_LAYOUT as never });
      this.setFilter(this.shown);
    });
    this.before = before;
  }

  private render(): void {
    const w = this.map.getContainer().clientWidth;
    const x = this.dividerPx();
    if (this.container) this.container.style.clipPath = `inset(0 ${Math.max(0, w - x)}px 0 0)`;
    this.els.overlay.style.setProperty("--x", `${x}px`);
    // A label needs room beside the divider; hide it when its side is too narrow to show it whole.
    this.els.labelBefore.hidden = x < LABEL_ROOM_PX;
    this.els.labelAfter.hidden = w - x < LABEL_ROOM_PX;
    const g = this.els.grip;
    g.setAttribute("aria-valuenow", String(Math.round(this.at)));
    g.setAttribute("aria-valuetext",
      `${Math.round(this.at)}% of the map shows ${this.summary.releases.prev}; the rest shows ${this.summary.releases.curr}`);
  }

  private bindGrip(): void {
    const g = this.els.grip;
    const moveTo = (clientX: number) => {
      const r = this.map.getContainer().getBoundingClientRect();
      this.at = Math.min(100, Math.max(0, ((clientX - r.left) / r.width) * 100));
      this.render();
    };
    g.addEventListener("pointerdown", (e) => { g.setPointerCapture(e.pointerId); moveTo(e.clientX); e.preventDefault(); });
    g.addEventListener("pointermove", (e) => { if (g.hasPointerCapture(e.pointerId)) moveTo(e.clientX); });
    g.addEventListener("keydown", (e) => {
      const next = keyStep(e.key, this.at, e.shiftKey);
      if (next === null) return;
      e.preventDefault();
      this.at = next;
      this.render();
    });
  }
}
