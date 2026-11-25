// Change-type symbols: colour AND shape, so status is never conveyed by colour alone.
// Drawn on a canvas at runtime (original artwork, no icon set to license).
import type { ChangeType } from "./contract";

export interface Symbol {
  label: string;
  color: string;
  shape: "circle" | "cross" | "diamond" | "diamond-outline" | "square";
}

export function symbolsFor(thresholds: { minor_move: number; move: number }): Record<ChangeType, Symbol> {
  return {
    added: { label: "Added", color: "#2dd4bf", shape: "circle" },
    removed: { label: "Removed", color: "#fb7185", shape: "cross" },
    moved: { label: `Moved (> ${thresholds.move} m)`, color: "#fbbf24", shape: "diamond" },
    attribute_changed: { label: "Name or category changed", color: "#60a5fa", shape: "square" },
    shifted: {
      label: `Shifted (${thresholds.minor_move}–${thresholds.move} m)`, color: "#fde68a", shape: "diamond-outline",
    },
  };
}

const SIZE = 48; // drawn at 2x for sharp rendering; registered with pixelRatio 2 (24 css px)

/** Draws one symbol; returns RGBA pixels for map.addImage. */
export function drawSymbol(s: Symbol, size = SIZE): ImageData {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable");
  const c = size / 2;
  const r = size * 0.3;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.strokeStyle = "#080f19"; // dark outline keeps light symbols readable on light basemap features
  ctx.fillStyle = s.color;
  ctx.lineWidth = size * 0.06;

  const path = new Path2D();
  switch (s.shape) {
    case "circle":
      path.arc(c, c, r, 0, Math.PI * 2);
      break;
    case "square":
      path.rect(c - r * 0.85, c - r * 0.85, r * 1.7, r * 1.7);
      break;
    case "diamond":
    case "diamond-outline":
      path.moveTo(c, c - r * 1.15);
      path.lineTo(c + r * 1.15, c);
      path.lineTo(c, c + r * 1.15);
      path.lineTo(c - r * 1.15, c);
      path.closePath();
      break;
    case "cross":
      break;
  }

  if (s.shape === "cross") {
    const d = r * 0.85;
    const x = new Path2D();
    x.moveTo(c - d, c - d);
    x.lineTo(c + d, c + d);
    x.moveTo(c + d, c - d);
    x.lineTo(c - d, c + d);
    ctx.lineWidth = size * 0.2;
    ctx.stroke(x); // dark halo
    ctx.strokeStyle = s.color;
    ctx.lineWidth = size * 0.11;
    ctx.stroke(x);
  } else if (s.shape === "diamond-outline") {
    ctx.lineWidth = size * 0.16;
    ctx.stroke(path);
    ctx.strokeStyle = s.color;
    ctx.lineWidth = size * 0.08;
    ctx.stroke(path);
  } else {
    ctx.fill(path);
    ctx.stroke(path);
  }
  return ctx.getImageData(0, 0, size, size);
}

/** Small inline SVG of a symbol for the legend and inspector (same shapes as the map). */
export function symbolSvg(s: Symbol): SVGSVGElement {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("swatch");
  let el: SVGElement;
  switch (s.shape) {
    case "circle":
      el = document.createElementNS(ns, "circle");
      el.setAttribute("cx", "12"); el.setAttribute("cy", "12"); el.setAttribute("r", "7");
      el.setAttribute("fill", s.color);
      break;
    case "square":
      el = document.createElementNS(ns, "rect");
      el.setAttribute("x", "6"); el.setAttribute("y", "6"); el.setAttribute("width", "12"); el.setAttribute("height", "12");
      el.setAttribute("fill", s.color);
      break;
    case "cross":
      el = document.createElementNS(ns, "path");
      el.setAttribute("d", "M6 6L18 18M18 6L6 18");
      el.setAttribute("stroke", s.color); el.setAttribute("stroke-width", "3"); el.setAttribute("stroke-linecap", "round");
      break;
    default:
      el = document.createElementNS(ns, "path");
      el.setAttribute("d", "M12 3L21 12L12 21L3 12Z");
      if (s.shape === "diamond") el.setAttribute("fill", s.color);
      else {
        el.setAttribute("fill", "none"); el.setAttribute("stroke", s.color); el.setAttribute("stroke-width", "2.5");
      }
  }
  svg.appendChild(el);
  return svg;
}
