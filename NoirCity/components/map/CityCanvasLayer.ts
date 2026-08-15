import L from "leaflet";
import type { City, CityLocation, Point } from "@/lib/engine/citySchema";
import { MAP_COLORS, ROAD_WIDTH } from "@/lib/city/palette";
import { drawGlyph, glyphFamily } from "@/lib/city/glyphs";

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

/**
 * A drive in progress.
 *
 * Held apart from `CityLayerState` because it changes sixty times a second
 * while the rest changes once an action. Pushing it through `setState` would
 * mean rebuilding the visited Set on every frame of every journey.
 *
 * Coordinates are city metres, not pixels - the view can pan underneath a drive
 * and the line has to stay pinned to the streets rather than to the screen.
 */
export interface TravelState {
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  /** 0 at the kerb outside, 1 on arrival. */
  t: number;
}

const EMPTY_STATE: CityLayerState = {
  visited: new Set(),
  hereId: null,
  focusedId: null,
};

export class CityCanvasLayer extends L.Layer {
  /** What the user sees. Only ever written to by blitting the buffer. */
  private canvas: HTMLCanvasElement | null = null;
  private visibleCtx: CanvasRenderingContext2D | null = null;
  /**
   * Everything is drawn here first, then copied across in one operation.
   *
   * The reason is specific: assigning to `canvas.width` blanks a canvas
   * synchronously. With a single canvas, any resize left it empty until the next
   * frame drew - one guaranteed blank frame per resize, which is exactly what
   * made the map flash every time the panel moved. The buffer means the visible
   * canvas goes straight from the old picture to the new one.
   */
  private buffer: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private frame = 0;
  /**
   * While held, the buffer keeps updating but nothing reaches the screen.
   *
   * Re-fitting the view is several Leaflet operations - invalidateSize, then
   * fitBounds, then a min-zoom clamp - and each one fires events that ask us to
   * draw. Drawn mid-sequence the transform can put the whole city outside the
   * viewport, and every shape gets culled, leaving a flat background fill. That
   * is what the flicker actually was: not a cleared canvas, a correctly drawn
   * one containing nothing.
   *
   * Holding the blit means the last good picture stays up until the view settles.
   */
  private held = false;

  constructor(
    private city: City,
    private state: CityLayerState = EMPTY_STATE,
  ) {
    super();
  }

  private travel: TravelState | null = null;

  setState(next: CityLayerState) {
    this.state = next;
    this.redraw();
  }

  /**
   * Advances or clears the drive.
   *
   * `redraw` coalesces through one rAF, so being called every frame by the
   * animation and again by Leaflet's own pan on the same frame still costs a
   * single draw.
   */
  setTravel(next: TravelState | null) {
    this.travel = next;
    this.redraw();
  }

  /** Freeze what is on screen. Pair every call with `release()`. */
  hold() {
    this.held = true;
  }

  /** Unfreeze, and put one correct frame up immediately. */
  release() {
    this.held = false;
    this.drawNow();
  }

  onAdd(map: L.Map): this {
    const canvas = L.DomUtil.create("canvas", "citymap-canvas");
    canvas.style.position = "absolute";
    canvas.style.pointerEvents = "none";
    this.canvas = canvas;
    this.visibleCtx = canvas.getContext("2d");

    this.buffer = document.createElement("canvas");
    // `willReadFrequently` is off deliberately: nothing reads this back, and
    // asking for it would push the buffer onto the CPU path.
    this.ctx = this.buffer.getContext("2d");

    map.getPanes().overlayPane?.appendChild(canvas);

    map.on("move zoom viewreset resize zoomanim", this.reposition, this);
    this.reposition();
    return this;
  }

  onRemove(map: L.Map): this {
    map.off("move zoom viewreset resize zoomanim", this.reposition, this);
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.canvas?.remove();
    this.canvas = null;
    this.visibleCtx = null;
    this.buffer = null;
    this.ctx = null;
    return this;
  }

  private reposition = () => {
    const map = this._map;
    if (!map || !this.canvas || !this.buffer) return;
    const size = map.getSize();
    const dpr = window.devicePixelRatio || 1;
    const resized =
      this.buffer.width !== size.x * dpr || this.buffer.height !== size.y * dpr;

    if (resized) {
      // Only the buffer is resized here. The visible canvas is resized inside
      // `blit()`, immediately before it is drawn into - assigning to `width`
      // blanks a canvas, so the clear and the redraw have to be in one task.
      this.buffer.width = size.x * dpr;
      this.buffer.height = size.y * dpr;
      // CSS size is safe to set at any time; it does not clear anything.
      this.canvas.style.width = `${size.x}px`;
      this.canvas.style.height = `${size.y}px`;
    }
    // The canvas covers the viewport, so it has to be pinned back to the
    // top-left of the container every time Leaflet shifts the layer pane.
    L.DomUtil.setPosition(this.canvas, map.containerPointToLayerPoint([0, 0]));

    // A resize just blanked both canvases. Redraw in the SAME task rather than
    // waiting for a frame, so the browser never composites the empty state.
    if (resized) this.drawNow();
    else this.redraw();
  };

  /** Coalesced. Correct for pan and zoom, where a frame of latency is invisible. */
  private redraw() {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.draw();
    });
  }

  /** Immediate. The only correct choice after a resize has cleared the canvas. */
  private drawNow() {
    if (this.frame) {
      cancelAnimationFrame(this.frame);
      this.frame = 0;
    }
    this.draw();
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
    if (!map || !ctx || !this.canvas || !this.buffer) return;

    const dpr = window.devicePixelRatio || 1;
    const size = map.getSize();
    // Everything below draws into the buffer. `blit()` at the end of this method
    // is the only thing that touches the visible canvas.
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
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

    // Mist on the water. Clipped to the river so it cannot creep over the
    // banks, and run top to bottom of the river's own extent so it reads as
    // something lifting off the surface rather than a flat wash over it.
    {
      let top = Infinity;
      let bottom = -Infinity;
      for (const p of city.river.polygon) {
        const sy = t.y(p[1]);
        if (sy < top) top = sy;
        if (sy > bottom) bottom = sy;
      }
      if (bottom > top) {
        ctx.save();
        trace(city.river.polygon);
        ctx.closePath();
        ctx.clip();
        const fog = ctx.createLinearGradient(0, top, 0, bottom);
        fog.addColorStop(0, MAP_COLORS.riverFog);
        fog.addColorStop(0.55, "rgba(150, 180, 196, 0.02)");
        fog.addColorStop(1, "rgba(150, 180, 196, 0)");
        ctx.fillStyle = fog;
        ctx.fillRect(0, top, size.x, bottom - top);
        ctx.restore();
      }
    }

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

      // The avenues are the lit ones. A single wide, nearly transparent pass
      // underneath the carriageway reads as sodium light spilling onto the
      // buildings either side - which is what makes a night map feel inhabited
      // rather than merely dark. One extra pass over the fewest roads in the
      // city, and no blur filter, so it costs almost nothing.
      if (kind === "avenue") {
        ctx.strokeStyle = MAP_COLORS.avenueGlow;
        ctx.lineWidth = roadPx(kind) * 3.4;
        for (const s of city.streets) {
          if (s.kind !== "avenue") continue;
          if (!visible(s.points[0]) && !visible(s.points[s.points.length - 1])) continue;
          trace(s.points);
          ctx.stroke();
        }
      }

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

    /**
     * Close in, every address becomes a chip carrying what kind of place it is;
     * far out it goes back to being a dot.
     *
     * The threshold is not decoration. Twelve hundred glyphs at city scale is a
     * grey mush that hides the streets they sit on, which is the failure the
     * plain dots were already avoiding. A chip needs roughly its own width of
     * clear space to be worth drawing, and that is what this scale buys.
     */
    const CHIP_SCALE = 0.45;
    const chips = scale > CHIP_SCALE;
    const chipR = Math.min(11, 7 + (scale - CHIP_SCALE) * 6);

    for (const loc of city.locations) {
      if (loc.isLandmark) continue;
      const sx = t.x(loc.x);
      const sy = t.y(loc.y);
      if (sx < -pad || sx > size.x + pad || sy < -pad || sy > size.y + pad) continue;
      const seen = this.state.visited.has(loc.id);

      if (!chips) {
        ctx.beginPath();
        ctx.arc(sx, sy, pinRadius, 0, Math.PI * 2);
        ctx.fillStyle = seen ? MAP_COLORS.pinVisited : MAP_COLORS.pin;
        ctx.globalAlpha = seen ? 0.9 : Math.min(0.72, 0.28 + scale * 2.4);
        ctx.fill();
        continue;
      }

      // A filled disc behind the glyph, or the glyph competes with the roads and
      // blocks under it and neither wins.
      ctx.beginPath();
      ctx.arc(sx, sy, chipR, 0, Math.PI * 2);
      ctx.fillStyle = MAP_COLORS.chip;
      ctx.globalAlpha = seen ? 0.82 : 0.94;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.lineWidth = 1;
      ctx.strokeStyle = seen ? MAP_COLORS.chipEdgeVisited : MAP_COLORS.chipEdge;
      ctx.stroke();

      // Somewhere you have been goes quiet. The city has to get smaller as you
      // work it, or a thousand addresses stay a thousand addresses all game.
      ctx.strokeStyle = seen ? MAP_COLORS.pinVisited : MAP_COLORS.chipGlyph;
      ctx.lineWidth = 1.15;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      drawGlyph(ctx, glyphFamily(loc.type), sx, sy, chipR);
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
      // Whichever place you are standing in, and whichever you have selected,
      // both get a marker of their own further down with their name above it.
      // Labelling them here as well printed the name twice, a few pixels apart.
      if (loc.id === this.state.hereId || loc.id === this.state.focusedId) continue;
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

    // --- the drive --------------------------------------------------------
    // Drawn before the markers so the car passes under a label rather than
    // over it, and so the destination pin stays the brightest thing on screen.
    const drive = this.travel;
    if (drive) {
      const ax = t.x(drive.fromX);
      const ay = t.y(drive.fromY);
      const bx = t.x(drive.toX);
      const by = t.y(drive.toY);
      // Eased so the car pulls away and settles rather than tracking at a
      // constant speed, which reads as a cursor rather than a vehicle.
      const e = drive.t < 0.5
        ? 2 * drive.t * drive.t
        : 1 - Math.pow(-2 * drive.t + 2, 2) / 2;
      const hx = ax + (bx - ax) * e;
      const hy = ay + (by - ay) * e;

      // The whole route, faint - you can see where you are going the moment
      // you set off.
      ctx.strokeStyle = MAP_COLORS.routeGhost;
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 6]);
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
      ctx.setLineDash([]);

      // The part already driven, solid.
      ctx.strokeStyle = MAP_COLORS.route;
      ctx.lineWidth = 1.8;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(hx, hy);
      ctx.stroke();

      // The car. A dot with a short warm wake behind it, so direction reads
      // without drawing anything as literal as a vehicle at this scale.
      const wake = ctx.createLinearGradient(ax, ay, hx, hy);
      wake.addColorStop(0, "rgba(201,162,39,0)");
      wake.addColorStop(1, MAP_COLORS.route);
      ctx.strokeStyle = wake;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(ax + (hx - ax) * 0.82, ay + (hy - ay) * 0.82);
      ctx.lineTo(hx, hy);
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(hx, hy, 3.4, 0, Math.PI * 2);
      ctx.fillStyle = MAP_COLORS.here;
      ctx.fill();
    }

    // --- where the team is ------------------------------------------------
    const here = this.state.hereId
      ? city.locations.find((l) => l.id === this.state.hereId)
      : null;
    // Mid-drive the team is not anywhere yet. The destination still gets its
    // pin - that is what you are driving towards - but not the standing marker
    // and its name, or the map would claim you had already arrived.
    if (here && !drive) {
      this.drawMarker(
        ctx,
        t.x(here.x),
        t.y(here.y),
        MAP_COLORS.here,
        here.name,
        true,
        claimed,
      );
    }

    const focused =
      this.state.focusedId && this.state.focusedId !== this.state.hereId
        ? city.locations.find((l) => l.id === this.state.focusedId)
        : null;
    if (focused) {
      this.drawMarker(
        ctx,
        t.x(focused.x),
        t.y(focused.y),
        MAP_COLORS.landmark,
        focused.name,
        false,
        claimed,
      );
    }

    // --- borough names ----------------------------------------------------
    ctx.font = '600 13px Georgia, "Times New Roman", serif';
    ctx.textAlign = "center";
    ctx.shadowColor = MAP_COLORS.ink;
    ctx.shadowBlur = 6;
    ctx.fillStyle = MAP_COLORS.boroughLabel;
    // The one set of labels that had no overlap rejection, and on a phone it
    // showed: at that width Millgate and Bridge District sit close enough to
    // print through each other and read as one nonsense borough. Same box test
    // the street and landmark labels already use.
    //
    // Seeded with `claimed` - the landmark labels - so a borough never prints
    // over one. A landmark name is somewhere you can go; a borough name is
    // context. When they collide the context is what gives way.
    const boroughLabels = [...claimed];
    // Biggest first, so that when two boroughs collide it is the lesser name
    // that is dropped. Shoelace rather than a vertex count: the generator emits
    // more points round a convoluted waterfront than round a large plain block,
    // so counting them would have ranked several boroughs backwards.
    const area = (poly: ReadonlyArray<readonly [number, number]>) => {
      let sum = 0;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        sum += (poly[j][0] + poly[i][0]) * (poly[j][1] - poly[i][1]);
      }
      return Math.abs(sum / 2);
    };
    const byArea = [...city.boroughs].sort(
      (a, b) => area(b.polygon) - area(a.polygon),
    );
    for (const b of byArea) {
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

      const text = b.name.toUpperCase().split("").join(" ");
      const half = ctx.measureText(text).width / 2;
      const box: [number, number, number, number] = [
        sx - half,
        sy - 9,
        sx + half,
        sy + 6,
      ];
      if (
        boroughLabels.some(
          (c) => box[0] < c[2] && box[2] > c[0] && box[1] < c[3] && box[3] > c[1],
        )
      ) {
        continue;
      }
      boroughLabels.push(box);
      ctx.fillText(text, sx, sy);
    }
    ctx.shadowBlur = 0;

    // --- vignette ---------------------------------------------------------
    // Last, so it sits over everything including the labels. One radial fill a
    // draw - there is no per-frame cost here, and it is what stops the city
    // ending in a hard rectangle against the page behind it.
    {
      const cx = size.x / 2;
      const cy = size.y / 2;
      const vg = ctx.createRadialGradient(
        cx,
        cy,
        Math.min(size.x, size.y) * 0.42,
        cx,
        cy,
        Math.max(size.x, size.y) * 0.86,
      );
      vg.addColorStop(0, "rgba(0, 0, 0, 0)");
      vg.addColorStop(1, MAP_COLORS.vignette);
      ctx.fillStyle = vg;
      ctx.fillRect(0, 0, size.x, size.y);
    }

    this.blit();
  }

  /**
   * The buffer becomes the picture, in one operation. Because this is the only
   * write to the visible canvas, it can never be caught half-drawn or empty.
   */
  private blit() {
    const target = this.visibleCtx;
    if (this.held || !target || !this.canvas || !this.buffer) return;

    // Matching the size clears the visible canvas, so it happens here and
    // nowhere else - one statement before the pixels that replace them.
    if (
      this.canvas.width !== this.buffer.width ||
      this.canvas.height !== this.buffer.height
    ) {
      this.canvas.width = this.buffer.width;
      this.canvas.height = this.buffer.height;
    }
    target.setTransform(1, 0, 0, 1, 0, 0);
    target.drawImage(this.buffer, 0, 0);
  }

  /**
   * Where the team is, and whatever address is currently selected.
   *
   * `claimed` is the running list of label boxes already on the plate. This
   * adds its own to it so the borough names drawn afterwards do not print
   * through it - which is exactly what "West Borough" was doing across
   * "Blackthorn Security Company", the one label on the map that names where
   * you are actually standing.
   */
  private drawMarker(
    ctx: CanvasRenderingContext2D,
    sx: number,
    sy: number,
    color: string,
    label: string,
    pulse: boolean,
    claimed?: Array<[number, number, number, number]>,
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
    const ly = sy - 17;
    ctx.fillText(label, sx, ly);

    const half = ctx.measureText(label).width / 2;
    claimed?.push([sx - half - 3, ly - 11, sx + half + 3, ly + 4]);
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
