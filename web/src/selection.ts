// Selection markers: the chosen record's previous and current positions (joined by a dashed line) and its trail by
// release. Shared by the main map and the swipe view's earlier-release map, so a record chosen on either side of the
// divider is marked on both.
import type { LayerSpecification } from "maplibre-gl";

export type SelectionSource = "selection" | "sel-trail";
export const SELECTION_SOURCES: SelectionSource[] = ["selection", "sel-trail"];

export const SELECTION_LAYERS: LayerSpecification[] = [
  {
    id: "sel-line", type: "line", source: "selection", filter: ["==", ["geometry-type"], "LineString"],
    paint: { "line-color": "#f1f5f9", "line-width": 1.5, "line-dasharray": [2, 2] },
  },
  {
    id: "sel-trail-line", type: "line", source: "sel-trail",
    filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString"]]],
    paint: { "line-color": "#fbbf24", "line-width": 1.5, "line-dasharray": [1, 2], "line-opacity": 0.9 },
  },
  {
    id: "sel-trail-points", type: "circle", source: "sel-trail", filter: ["==", ["geometry-type"], "Point"],
    paint: { "circle-radius": 3, "circle-color": "#fbbf24", "circle-stroke-color": "#080f19", "circle-stroke-width": 1 },
  },
  {
    id: "sel-points", type: "circle", source: "selection", filter: ["==", ["geometry-type"], "Point"],
    paint: {
      "circle-radius": 9, "circle-stroke-width": 2, "circle-stroke-color": "#f1f5f9",
      "circle-color": ["case", ["==", ["get", "which"], "prev"], "rgba(0,0,0,0)", "rgba(241,245,249,0.25)"],
    },
  },
];
