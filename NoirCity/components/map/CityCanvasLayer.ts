import L from "leaflet";
import type { City, CityLocation, Point } from "@/lib/engine/citySchema";
import { MAP_COLORS, ROAD_WIDTH } from "@/lib/city/palette";

/**
 * Draws the whole city onto one canvas rather than handing Leaflet ~3,700
 * individual vector objects. At this scale a single canvas redraw per frame is
 * far cheaper than Leaflet's per-path SVG/canvas bookkeeping, and it lets the
 * road hierarchy fade in and out by zoom the way a real map does.
 *
 * Interaction is handled by hit-testing city coordinates, not by DOM events on
 * markers, which keeps 1,200 locations essentially free.
 */

export interface CityLayerState {
  /** Location ids the team has been to. Drawn cold. */
  visited: Set<string>;
  /** Where the team is now. */
  hereId: string | null;
  /** Highlighted for the current action, e.g. a travel preview. */
  focusedId: string | null;
}

const EMPTY_STATE: CityLayerState = {
  visited: new Set(),
  hereId: null,
  focusedId: null,
};

export class CityCanvasLayer extends L.Layer {
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private frame = 0;

  constructor(
    private city: City,
    private state: CityLayerState = EMPTY_STATE,
  ) {
    super();
  }

  setState(next: CityLayerState) {
    this.state = next;
    this.redraw();
  }

  onAdd(map: L.Map): this {
    const canvas = L.DomUtil.create("canvas", "citymap-canvas");
    canvas.style.position = "absolute";
    canvas.style.pointerEvents = "none";
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    map.getPanes().overlayPane?.appendChild(canvas);

    map.on("move zoom viewreset resize zoomanim", this.reposition, this);
    this.reposition();
    return this;
  }

  onRemove(map: L.Map): this {
    map.off("move zoom viewreset resize zoomanim", this.reposition, this);
    this.canvas?.remove();
    this.canvas = null;
    this.ctx = null;
    return this;
  }

  private reposition = () => {
    const map = this._map;
    if (!map || !this.canvas) return;
    const size = map.getSize();
    const dpr = window.devicePixelRatio || 1;

    if (this.canvas.width !== size.x * dpr || this.canvas.height !== size.y * dpr) {
      this.canvas.width = size.x * dpr;
      this.canvas.height = size.y * dpr;
      this.canvas.style.width = `${size.x}px`;
      this.canvas.style.height = `${size.y}px`;
    }
    // The canvas covers the viewport, so it has to be pinned back to the
    // top-left of the container every time Leaflet shifts the layer pane.
    L.DomUtil.setPosition(this.canvas, map.containerPointToLayerPoint([0, 0]));
    this.redraw();
  };

  private redraw() {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.draw();
    });
  }

  /**
   * CRS.Simple is affine, so two probe points give us the whole transform and
   * we avoid ~15,000 latLngToContainerPoint calls per frame.
   */
  private transform() {
    const map = this._map;
    const a = map.latLngToContainerPoint(L.latLng(0, 0));
    const b = map.latLngToContainerPoint(L.latLng(1000, 1000));
    const sx = (b.x - a.x) / 1000;
    const sy = (b.y - a.y) / 1000;
    return {
      x: (cx: number) => a.x + cx * sx,
      y: (cy: number) => a.y + cy * sy,
      scale: Math.abs(sx),
    };
  }

  private draw() {
    const map = this._map;
    const ctx = this.ctx;
    if (!map || !ctx || !this.canvas) return;

    const dpr = window.devicePixelRatio || 1;
    const size = map.getSize();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size.x, size.y);
    ctx.fillStyle = MAP_COLORS.ink;
    ctx.fillRect(0, 0, size.x, size.y);

    const t = this.transform();
    const { scale } = t;
    const { city } = this;

    const trace = (pts: Point[]) => {
      ctx.beginPath();
      ctx.moveTo(t.x(pts[0][0]), t.y(pts[0][1]));
      for (let i = 1; i < pts.length; i++) {
        ctx.lineTo(t.x(pts[i][0]), t.y(pts[i][1]));
      }
    };

    // Cheap viewport rejection. Blocks are small, so their first point is a
    // good enough proxy for the whole shape.
    const pad = 120;
    const visible = (p: Point) => {
      const sx = t.x(p[0]);
      const sy = t.y(p[1]);
      return sx > -pad && sx < size.x + pad && sy > -pad && sy < size.y + pad;
    };

    // --- blocks -----------------------------------------------------------
    const showBlockEdges = scale > 0.08;
    const fills = {
      built: MAP_COLORS.blockBuilt,
      park: MAP_COLORS.blockPark,
      yard: MAP_COLORS.blockYard,
    };
    const edges = {
      built: MAP_COLORS.blockBuiltEdge,
      park: MAP_COLORS.blockParkEdge,
      yard: MAP_COLORS.blockYardEdge,
    };
    ctx.lineWidth = 0.6;
    for (const block of city.blocks) {
      if (!visible(block.polygon[0])) continue;
      trace(block.polygon);
      ctx.closePath();
      ctx.fillStyle = fills[block.kind];
      ctx.fill();
      if (showBlockEdges) {
        ctx.strokeStyle = edges[block.kind];
        ctx.stroke();
      }
    }

    // --- water ------------------------------------------------------------
    trace(city.river.polygon);
    ctx.closePath();
    ctx.fillStyle = MAP_COLORS.water;
    ctx.fill();
    ctx.strokeStyle = MAP_COLORS.waterEdge;
    ctx.lineWidth = 1;
    ctx.stroke();

    // --- railways ---------------------------------------------------------
    ctx.strokeStyle = MAP_COLORS.rail;
    ctx.lineWidth = Math.max(1, 2.4 * Math.min(1, scale * 4));
    ctx.setLineDash([7, 5]);
    for (const rw of city.railways) {
      trace(rw.points);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    // --- streets ----------------------------------------------------------
    // Lanes vanish when zoomed out, so the hierarchy stays legible.
    const roadPx = (kind: keyof typeof ROAD_WIDTH) =>
      Math.max(ROAD_WIDTH[kind].minPx, ROAD_WIDTH[kind].metres * scale);
    const order: Array<keyof typeof ROAD_WIDTH> = ["lane", "street", "avenue"];
    const colors = {
      lane: MAP_COLORS.lane,
      street: MAP_COLORS.street,
      avenue: MAP_COLORS.avenue,
    };
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const kind of order) {
      if (kind === "lane" && scale < 0.075) continue;
      if (kind === "street" && scale < 0.045) continue;
      ctx.strokeStyle = colors[kind];
      ctx.lineWidth = roadPx(kind);
      for (const s of city.streets) {
        if (s.kind !== kind) continue;
        if (!visible(s.points[0]) && !visible(s.points[s.points.length - 1])) continue;
        trace(s.points);
        ctx.stroke();
      }
    }

    // --- crossings --------------------------------------------------------
    ctx.strokeStyle = MAP_COLORS.bridge;
    for (const br of city.bridges) {
      ctx.lineWidth = Math.max(2.2, (br.kind === "bridge" ? 34 : 16) * scale);
      ctx.setLineDash(br.kind === "ferry" ? [6, 6] : []);
      trace(br.points);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    // --- street names -----------------------------------------------------
    // Only close in, and only on roads long enough to carry the label.
    const streetLabels: Array<[number, number, number, number]> = [];
    if (scale > 0.5) {
      ctx.font = '500 11px Georgia, "Times New Roman", serif';
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = MAP_COLORS.boroughLabel;
      for (const s of city.streets) {
        if (s.kind === "lane" && scale < 0.9) continue;
        const mid = Math.floor((s.points.length - 1) / 2);
        const [x0, y0] = s.points[mid];
        const [x1, y1] = s.points[mid + 1] ?? s.points[mid];
        const ax = t.x(x0);
        const ay = t.y(y0);
        if (ax < 0 || ax > size.x || ay < 0 || ay > size.y) continue;
        const bx = t.x(x1);
        const by = t.y(y1);
        const width = ctx.measureText(s.name).width;
        if (Math.hypot(bx - ax, by - ay) < width * 0.5) continue;

        // Reject overlaps against an axis-aligned box round the label. Rough for
        // rotated text, but it stops the pile-ups at busy intersections.
        const cx = (ax + bx) / 2;
        const cy = (ay + by) / 2;
        const r = Math.max(width, 14) / 2;
        const box: [number, number, number, number] = [cx - r, cy - 7, cx + r, cy + 7];
        if (
          streetLabels.some(
            (c) => box[0] < c[2] && box[2] > c[0] && box[1] < c[3] && box[3] > c[1],
          )
        ) {
          continue;
        }
        streetLabels.push(box);

        let angle = Math.atan2(by - ay, bx - ax);
        if (angle > Math.PI / 2) angle -= Math.PI;
        if (angle < -Math.PI / 2) angle += Math.PI;
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(angle);
        ctx.fillText(s.name, 0, 0);
        ctx.restore();
      }
      ctx.textBaseline = "alphabetic";
    }

    // --- locations --------------------------------------------------------
    // Small and dim at city zoom: 1,200 pins would otherwise bury the streets
    // they are supposed to sit on.
    const pinRadius = Math.max(0.9, Math.min(3.6, scale * 12));
    for (const loc of city.locations) {
      if (loc.isLandmark) continue;
      const sx = t.x(loc.x);
      const sy = t.y(loc.y);
      if (sx < -pad || sx > size.x + pad || sy < -pad || sy > size.y + pad) continue;
      const seen = this.state.visited.has(loc.id);
      ctx.beginPath();
      ctx.arc(sx, sy, pinRadius, 0, Math.PI * 2);
      ctx.fillStyle = seen ? MAP_COLORS.pinVisited : MAP_COLORS.pin;
      ctx.globalAlpha = seen ? 0.9 : Math.min(0.72, 0.28 + scale * 2.4);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    // --- landmarks --------------------------------------------------------
    // Names only once there is room for them; the civic quarter alone has five
    // landmarks inside 400 metres.
    const showLandmarkLabels = scale > 0.19;
    const claimed: Array<[number, number, number, number]> = [];
    ctx.font = '11px Georgia, "Times New Roman", serif';
    ctx.textAlign = "center";
    ctx.textBaseline = "alphabetic";
    for (const loc of city.locations) {
      if (!loc.isLandmark) continue;
      const sx = t.x(loc.x);
      const sy = t.y(loc.y);
      if (sx < -pad || sx > size.x + pad || sy < -pad || sy > size.y + pad) continue;
      ctx.beginPath();
      ctx.arc(sx, sy, pinRadius + 1.8, 0, Math.PI * 2);
      ctx.fillStyle = MAP_COLORS.landmark;
      ctx.fill();

      if (!showLandmarkLabels) continue;
      const half = ctx.measureText(loc.name).width / 2 + 3;
      const ly = sy - pinRadius - 6;
      const box: [number, number, number, number] = [sx - half, ly - 11, sx + half, ly + 3];
      const overlaps = claimed.some(
        (c) => box[0] < c[2] && box[2] > c[0] && box[1] < c[3] && box[3] > c[1],
      );
      if (overlaps) continue;
      claimed.push(box);
      ctx.fillStyle = MAP_COLORS.ink;
      ctx.globalAlpha = 0.65;
      ctx.fillRect(box[0], box[1], box[2] - box[0], box[3] - box[1]);
      ctx.globalAlpha = 1;
      ctx.fillStyle = MAP_COLORS.landmarkLabel;
      ctx.fillText(loc.name, sx, ly);
    }

    // --- where the team is ------------------------------------------------
    const here = this.state.hereId
      ? city.locations.find((l) => l.id === this.state.hereId)
      : null;
    if (here) this.drawMarker(ctx, t.x(here.x), t.y(here.y), MAP_COLORS.here, here.name, true);

    const focused =
      this.state.focusedId && this.state.focusedId !== this.state.hereId
        ? city.locations.find((l) => l.id === this.state.focusedId)
        : null;
    if (focused) {
      this.drawMarker(ctx, t.x(focused.x), t.y(focused.y), MAP_COLORS.landmark, focused.name, false);
    }

    // --- borough names ----------------------------------------------------
    ctx.font = '600 13px Georgia, "Times New Roman", serif';
    ctx.textAlign = "center";
    ctx.shadowColor = MAP_COLORS.ink;
    ctx.shadowBlur = 6;
    ctx.fillStyle = MAP_COLORS.boroughLabel;
    for (const b of city.boroughs) {
      let cx = 0;
      let cy = 0;
      for (const p of b.polygon) {
        cx += p[0];
        cy += p[1];
      }
      cx /= b.polygon.length;
      cy /= b.polygon.length;
      const sx = t.x(cx);
      const sy = t.y(cy);
      if (sx < 0 || sx > size.x || sy < 0 || sy > size.y) continue;
      ctx.fillText(b.name.toUpperCase().split("").join(" "), sx, sy);
    }
    ctx.shadowBlur = 0;
  }

  private drawMarker(
    ctx: CanvasRenderingContext2D,
    sx: number,
    sy: number,
    color: string,
    label: string,
    pulse: boolean,
  ) {
    ctx.beginPath();
    ctx.arc(sx, sy, 8, 0, Math.PI * 2);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    ctx.stroke();
    if (pulse) {
      ctx.beginPath();
      ctx.arc(sx, sy, 13, 0, Math.PI * 2);
      ctx.globalAlpha = 0.35;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    ctx.beginPath();
    ctx.arc(sx, sy, 3.4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.font = '600 12px Georgia, "Times New Roman", serif';
    ctx.textAlign = "center";
    ctx.fillText(label, sx, sy - 17);
  }
}

/** Nearest location to a click, within a screen-pixel radius. */
export function hitTest(
  city: City,
  map: L.Map,
  containerPoint: L.Point,
  radiusPx = 16,
): CityLocation | null {
  let best: CityLocation | null = null;
  let bestD = radiusPx;
  for (const loc of city.locations) {
    const p = map.latLngToContainerPoint(L.latLng(loc.y, loc.x));
    const d = Math.hypot(p.x - containerPoint.x, p.y - containerPoint.y);
    // Landmarks win ties so a big name is never blocked by a filler pin.
    if (d < bestD || (d < radiusPx && loc.isLandmark && d <= bestD + 4)) {
      bestD = d;
      best = loc;
    }
  }
  return best;
}
