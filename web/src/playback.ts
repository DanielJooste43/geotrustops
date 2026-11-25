// Release-history playback and movement trails (data contract §12).
// Inputs: the validated timeline (out_timeline/timeline.json). Every count shown comes from its per-release rows;
// the browser only selects which events to draw for the chosen release (ADR 0004).
// Honesty rules: timing is per release, so a moved record steps from its last-seen position to its new one; the
// short ease between them is drawn as motion between two release positions, never as an observed path, and is
// skipped when reduced motion is requested. Releases without published changes are marked, not shown as zero.
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
import { TIMELINE_KINDS, type Timeline, type TimelineEvent } from "./contract";

export const HISTORY_LAYERS = ["tl-trail", "tl-glow", "tl-core"];
/** Marker layers that can be clicked; each feature carries `rid`, the record's index into timeline.ids. */
export const HISTORY_CLICKABLE = ["tl-core", "tl-glow"];
const GLOW = "#e879f9";
const TRAIL = "#fbbf24";
const FADE = [0.34, 0.16, 0.07]; // glow opacity by age in releases: the current release, then the two before
const STEP_MS = 1400; // time per release while playing
const EASE_MS = 900; // a moved record eases from its last-seen to its new position
const MOVED = TIMELINE_KINDS.indexOf("position_changed");

const fmt = new Intl.NumberFormat("en-ZA");
const empty = (): FeatureCollection => ({ type: "FeatureCollection", features: [] });

export interface PlaybackDom {
  panel: HTMLElement;
  play: HTMLButtonElement;
  prev: HTMLButtonElement;
  next: HTMLButtonElement;
  slider: HTMLInputElement;
  label: HTMLElement;
  note: HTMLElement;
  bars: SVGSVGElement;
  trails: HTMLInputElement;
}

export class Playback {
  private frame: number;
  private timer: number | null = null;
  private anim: number | null = null;
  private readonly byRelease: TimelineEvent[][];

  constructor(
    private readonly map: MapLibreMap,
    private readonly tl: Timeline,
    private readonly dom: PlaybackDom,
    private readonly reducedMotion: boolean,
  ) {
    this.byRelease = tl.releases.map(() => []);
    for (const e of tl.events) this.byRelease[e[0]]!.push(e);
    this.frame = tl.releases.length - 1;
    this.addLayers();
    this.renderBars();
    const last = String(tl.releases.length - 1);
    dom.slider.min = "0";
    dom.slider.max = last;
    dom.slider.step = "1";
    dom.slider.addEventListener("input", () => { this.stop(); this.show(Number(dom.slider.value), false); });
    dom.prev.addEventListener("click", () => { this.stop(); this.show(Math.max(0, this.frame - 1), true); });
    dom.next.addEventListener("click", () => { this.stop(); this.show(Math.min(tl.releases.length - 1, this.frame + 1), true); });
    dom.play.addEventListener("click", () => (this.timer === null ? this.start() : this.stop()));
    dom.trails.addEventListener("change", () => this.show(this.frame, false));
    this.show(this.frame, false);
  }

  private addLayers(): void {
    const m = this.map;
    m.addSource("tl-events", { type: "geojson", data: empty() });
    m.addSource("tl-trails", { type: "geojson", data: empty() });
    m.addLayer({
      id: "tl-trail", type: "line", source: "tl-trails", layout: { visibility: "none", "line-cap": "round" },
      paint: {
        "line-color": TRAIL,
        "line-width": ["case", ["==", ["get", "age"], 0], 2, 1],
        "line-opacity": ["match", ["get", "age"], 0, 0.9, 1, 0.35, 0.15],
      },
    });
    m.addLayer({
      id: "tl-glow", type: "circle", source: "tl-events", layout: { visibility: "none" },
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 7, 15, 13, 18, 26],
        "circle-color": GLOW,
        "circle-opacity": ["match", ["get", "age"], 0, FADE[0]!, 1, FADE[1]!, FADE[2]!],
        "circle-blur": 1,
      },
    });
    m.addLayer({
      id: "tl-core", type: "circle", source: "tl-events", layout: { visibility: "none" },
      filter: ["==", ["get", "age"], 0],
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 1.6, 15, 2.6, 18, 4.5],
        "circle-color": ["case", ["get", "moved"], TRAIL, "#fdf4ff"],
        "circle-opacity": 0.95,
      },
    });
  }

  setVisible(on: boolean): void {
    for (const l of HISTORY_LAYERS) {
      const vis = on && (l !== "tl-trail" || this.dom.trails.checked);
      this.map.setLayoutProperty(l, "visibility", vis ? "visible" : "none");
    }
    this.dom.panel.hidden = !on;
    if (!on) this.stop();
  }

  private start(): void {
    if (this.frame >= this.tl.releases.length - 1) this.show(0, false);
    this.dom.play.textContent = "Pause";
    this.dom.play.setAttribute("aria-pressed", "true");
    this.timer = window.setInterval(() => {
      if (this.frame >= this.tl.releases.length - 1) return this.stop();
      this.show(this.frame + 1, true);
    }, STEP_MS);
  }

  stop(): void {
    if (this.timer !== null) window.clearInterval(this.timer);
    this.timer = null;
    this.dom.play.textContent = "Play";
    this.dom.play.setAttribute("aria-pressed", "false");
  }

  /** Draws release i: its events and moves are brightest, those of the two releases before fade out. */
  private show(i: number, animate: boolean): void {
    this.frame = i;
    this.dom.slider.value = String(i);
    if (this.anim !== null) cancelAnimationFrame(this.anim);
    const trailsOn = this.dom.trails.checked;
    const points = (t: number): FeatureCollection => {
      const features: Feature[] = [];
      for (let age = 2; age >= 0; age--) {
        for (const e of this.byRelease[i - age] ?? []) {
          const moved = e[1] === MOVED;
          let lon = e[3];
          let lat = e[4];
          if (age === 0 && moved && t < 1 && e[6] !== null && e[7] !== null) {
            lon = e[6] + (e[3] - e[6]) * t;
            lat = e[7] + (e[4] - e[7]) * t;
          }
          features.push({
            type: "Feature", properties: { age, moved, rid: e[2] }, geometry: { type: "Point", coordinates: [lon, lat] },
          });
        }
      }
      return { type: "FeatureCollection", features };
    };
    const trails: Feature[] = [];
    if (trailsOn) {
      for (let r = Math.max(0, i - 2); r <= i; r++) { // same fade window as the glow; a record's full trail is in its details
        for (const e of this.byRelease[r]!) {
          if (e[1] !== MOVED || e[6] === null || e[7] === null) continue;
          trails.push({
            type: "Feature", properties: { age: i - r },
            geometry: { type: "LineString", coordinates: [[e[6], e[7]], [e[3], e[4]]] },
          });
        }
      }
    }
    this.map.getSource<GeoJSONSource>("tl-trails")?.setData({ type: "FeatureCollection", features: trails });
    this.map.setLayoutProperty("tl-trail", "visibility", trailsOn && !this.dom.panel.hidden ? "visible" : "none");
    const src = this.map.getSource<GeoJSONSource>("tl-events");
    if (animate && trailsOn && !this.reducedMotion && this.byRelease[i]!.some((e) => e[1] === MOVED)) {
      const t0 = performance.now();
      let lastDraw = 0;
      const tick = (now: number) => {
        const t = Math.min(1, (now - t0) / EASE_MS);
        if (now - lastDraw > 50 || t === 1) { // ~20 updates per second keeps large releases smooth enough
          src?.setData(points(1 - (1 - t) * (1 - t)));
          lastDraw = now;
        }
        this.anim = t < 1 ? requestAnimationFrame(tick) : null;
      };
      this.anim = requestAnimationFrame(tick);
    } else {
      src?.setData(points(1));
    }
    this.renderLabel();
    this.highlightBar();
  }

  private renderLabel(): void {
    const r = this.tl.releases[this.frame]!;
    this.dom.slider.setAttribute("aria-valuetext", `Release ${r.release}`);
    this.dom.label.replaceChildren();
    const strong = document.createElement("strong");
    strong.textContent = r.release;
    this.dom.label.append(
      strong,
      r.changes_published // zeros from an unpublished change set are not counts, so none are shown
        ? ` · ${fmt.format(r.added)} added · ${fmt.format(r.removed)} removed · ${fmt.format(r.position_changed)} moved`
        : " · no changes published",
    );
    const notes: string[] = [];
    if (!r.changes_published) notes.push("Overture published no added, removed or edited records for this release: not evidence of no change.");
    if (r.first_seen_without_added > 0) {
      notes.push(`${fmt.format(r.first_seen_without_added)} records first appear here without an added row (the changelog before this release is missing).`);
    }
    if (this.frame === 0) notes.push("First release in the series: moves need an earlier position, so none are shown.");
    this.dom.note.textContent = notes.join(" ");
    this.dom.note.hidden = notes.length === 0;
  }

  private renderBars(): void {
    const svg = this.dom.bars;
    const ns = "http://www.w3.org/2000/svg";
    const n = this.tl.releases.length;
    const totals = this.tl.releases.map((r) => r.added + r.removed + r.position_changed);
    const max = Math.max(...totals, 1);
    svg.setAttribute("viewBox", `0 0 ${n * 10} 40`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.replaceChildren();
    this.tl.releases.forEach((r, i) => {
      if (!r.changes_published) {
        const tick = document.createElementNS(ns, "rect"); // a marker, not a zero bar
        tick.setAttribute("x", String(i * 10 + 3)); tick.setAttribute("y", "36");
        tick.setAttribute("width", "4"); tick.setAttribute("height", "4");
        tick.setAttribute("class", "unpublished");
        svg.append(tick);
        return;
      }
      const h = Math.max(1, (totals[i]! / max) * 36);
      const bar = document.createElementNS(ns, "rect");
      bar.setAttribute("x", String(i * 10 + 1)); bar.setAttribute("y", String(40 - h));
      bar.setAttribute("width", "8"); bar.setAttribute("height", String(h));
      svg.append(bar);
    });
  }

  private highlightBar(): void {
    [...this.dom.bars.children].forEach((b, i) => b.classList.toggle("current", i === this.frame));
  }
}
