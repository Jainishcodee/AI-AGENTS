/**
 * Generates content/city.json - the city of Marrowgate.
 *
 * Marrowgate is our own place. The Ebb splits it into two banks joined by four
 * crossings, with boroughs that differ sharply by class; the texture is Los
 * Angeles blended with London - wide jittered boulevards and a neon strip on
 * one side of the river, a tangled old core and dockland lanes on the other.
 *
 * The shape of a class-divided river city was suggested by the gaslight-occult
 * genre generally, but every name here is invented. An earlier draft seeded the
 * street vocabulary from a published novel's setting, which is somebody else's
 * copyrighted work and is not ours to ship. `ESTATE` below replaced it.
 *
 * Everything is deterministic: same seed, same city. Run once, commit the JSON.
 *
 *   npx tsx scripts/generate-city.ts
 */

import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import type {
  Bank,
  Block,
  Borough,
  Bridge,
  City,
  CityLocation,
  LocationType,
  Point,
  Street,
  StreetPattern,
} from "../lib/engine/citySchema";

const SEED = 18840317;
const SIZE: Point = [6400, 4400];

// ---------------------------------------------------------------------------
// Deterministic randomness
// ---------------------------------------------------------------------------

function mulberry32(seed: number) {
  let s = seed >>> 0;
  return function () {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(SEED);
const between = (lo: number, hi: number) => lo + rand() * (hi - lo);
const pick = <T>(xs: readonly T[]): T => xs[Math.floor(rand() * xs.length)];
const chance = (p: number) => rand() < p;

/** Weighted pick. Weights need not sum to anything in particular. */
function weighted<T extends string>(table: Record<string, number>): T {
  const total = Object.values(table).reduce((a, b) => a + b, 0);
  let r = rand() * total;
  for (const [k, w] of Object.entries(table)) {
    r -= w;
    if (r <= 0) return k as T;
  }
  return Object.keys(table)[0] as T;
}

// ---------------------------------------------------------------------------
// The Ebb. X-monotonic, so "which bank" is a cheap comparison.
// ---------------------------------------------------------------------------

const RIVER: Point[] = [
  [0, 2750],
  [900, 2620],
  [1800, 2400],
  [2700, 2150],
  [3600, 2000],
  [4500, 1800],
  [5400, 1550],
  [6400, 1400],
];
const RIVER_WIDTH_SOURCE = 230;
const RIVER_WIDTH_MOUTH = 640;

/**
 * The Ebb widens into an estuary as it runs east, which is what gives
 * Saltney open water to be a harbour on - and why the eastern crossing is a
 * ferry rather than a bridge.
 */
function riverWidthAt(x: number): number {
  const t = Math.min(1, Math.max(0, x / SIZE[0]));
  const eased = t * t * (3 - 2 * t);
  return RIVER_WIDTH_SOURCE + eased * (RIVER_WIDTH_MOUTH - RIVER_WIDTH_SOURCE);
}

function riverYAt(x: number): number {
  if (x <= RIVER[0][0]) return RIVER[0][1];
  if (x >= RIVER[RIVER.length - 1][0]) return RIVER[RIVER.length - 1][1];
  for (let i = 0; i < RIVER.length - 1; i++) {
    const [x0, y0] = RIVER[i];
    const [x1, y1] = RIVER[i + 1];
    if (x >= x0 && x <= x1) {
      const t = (x - x0) / (x1 - x0);
      return y0 + t * (y1 - y0);
    }
  }
  return RIVER[RIVER.length - 1][1];
}

/** Half-width plus a margin, so nothing is built on the embankment. */
function riverClearanceAt(x: number): number {
  return riverWidthAt(x) / 2 + 70;
}

function inRiver(x: number, y: number): boolean {
  return Math.abs(y - riverYAt(x)) < riverClearanceAt(x);
}

/** Both banks as one closed ring, sampled finely enough to show the widening. */
function riverPolygon(): Point[] {
  const north: Point[] = [];
  const south: Point[] = [];
  for (let x = 0; x <= SIZE[0]; x += 100) {
    const y = riverYAt(x);
    const half = riverWidthAt(x) / 2;
    north.push([x, Math.round(y + half)]);
    south.push([x, Math.round(y - half)]);
  }
  return [...north, ...south.reverse()];
}

function bankAt(x: number, y: number): Bank {
  return y > riverYAt(x) ? "north" : "south";
}

// ---------------------------------------------------------------------------
// Boroughs. Seeds only - the actual extents fall out of nearest-seed assignment,
// which keeps the borders irregular instead of rectangular.
// ---------------------------------------------------------------------------

interface BoroughSeed {
  id: string;
  name: string;
  bank: Bank;
  seed: Point;
  pattern: StreetPattern;
  /** Rotation of the local street frame, radians. */
  angle: number;
  /** Block size along each axis of the local frame, metres. */
  spacing: Point;
  /** For `organic` boroughs: how far streets wander, and over what distance.
   *  Harrowfield sweeps in long curves round a hill; East Borough just kinks. */
  meander?: { amplitude: number; wavelength: number };
  neighbors: string[];
  character: string;
  blurb: string;
  /** Relative share of the city's locations. */
  weight: number;
  streetNames: string[];
  suffixes: string[];
  typeMix: Partial<Record<GeneratedType, number>>;
}

const LONDON_OLD = "Whitcombe Blackfriar Cheapside Ludgate Shadwell Coldbath Aldgate Bishopsgate Wapping Bermond Clerkenwell Houndsditch Fetter Cripplegate Threadneedle Lombard Cannon Fleet Barbican Poultry Cloth Camomile".split(" ");
const LA_WIDE = "Alvarado Cahuenga Figueroa Normandie Sepulveda Vermont Wilshire Hyperion Beaudry Kenmore Occidental Manzanita Larchmont Cordova Bonnie Rampart Silverlake Effie Sanborn Vendome Marathon".split(" ");
const ESTATE =
  "Marrow Ashgrove Ebbswell Harrowfield Quillon Ravensgate Sablewick Thornfen Greymarsh Corvin Nettlebed Ferrers Bellamy Wexford Ossary Calder Merrow Ryehill Larkspur".split(
    " ",
  );

const BOROUGHS: BoroughSeed[] = [
  {
    id: "b_harrowfield",
    name: "Harrowfield",
    bank: "north",
    seed: [950, 3800],
    pattern: "organic",
    angle: 0.34,
    spacing: [115, 98],
    meander: { amplitude: 52, wavelength: 620 },
    neighbors: ["b_vermilion", "b_sovereign"],
    character: "Old money on the high ground.",
    blurb: "Hedges, gate lodges, and driveways that curve so you cannot see the house from the road. Nobody walks here.",
    weight: 10,
    streetNames: [...LONDON_OLD.slice(0, 10), ...ESTATE.slice(4, 12)],
    suffixes: ["Terrace", "Gardens", "Hill", "Crescent", "Drive", "Rise"],
    typeMix: { apartment: 5, office: 3, church: 3, clinic: 2, theatre: 1, garage: 1, diner: 2, hall: 2 },
  },
  {
    id: "b_vermilion",
    name: "Vermilion",
    bank: "north",
    seed: [3000, 3750],
    pattern: "boulevard",
    angle: 0.06,
    spacing: [170, 78],
    neighbors: ["b_harrowfield", "b_ravensgate", "b_sovereign", "b_westborough"],
    character: "The strip. Neon and appetite.",
    blurb: "Four miles of marquee lights, and behind every one of them a parking lot where the real business happens.",
    weight: 13,
    streetNames: [...LA_WIDE.slice(0, 14), ...ESTATE.slice(0, 4)],
    suffixes: ["Boulevard", "Avenue", "Strip", "Way", "Street"],
    typeMix: { club: 5, bar: 5, theatre: 4, motel: 4, diner: 3, pawnshop: 2, apartment: 3, garage: 1, hall: 1 },
  },
  {
    id: "b_ravensgate",
    name: "Ravensgate",
    bank: "north",
    seed: [5300, 3350],
    pattern: "radial",
    angle: 0,
    spacing: [100, 100],
    neighbors: ["b_vermilion", "b_westborough"],
    character: "University, libraries, and the circus grounds.",
    blurb: "Reading rooms, lecture halls, and a green where a permanent circus has been packing up for eleven years.",
    weight: 11,
    streetNames: [...ESTATE.slice(6, 18), ...LONDON_OLD.slice(10, 18)],
    suffixes: ["Square", "Row", "Walk", "Street", "Circle", "Green"],
    typeMix: { hall: 4, office: 3, church: 2, apartment: 4, diner: 3, theatre: 2, clinic: 2, market: 2 },
  },
  {
    id: "b_sovereign",
    name: "Sovereign Borough",
    bank: "north",
    seed: [2000, 2820],
    pattern: "grid",
    angle: 0.02,
    spacing: [115, 95],
    neighbors: ["b_harrowfield", "b_vermilion", "b_westborough"],
    character: "City Hall, the courts, and the Bell of Order.",
    blurb: "Granite, columns, and pigeons. Every window on this street belongs to someone who can ruin you with a memo.",
    weight: 10,
    streetNames: [...ESTATE.slice(4, 16), ...LONDON_OLD.slice(2, 10)],
    suffixes: ["Street", "Place", "Court", "Avenue", "Parade"],
    typeMix: { office: 6, precinct: 3, hall: 3, church: 2, diner: 2, bar: 2, apartment: 2, clinic: 1 },
  },
  {
    id: "b_westborough",
    name: "West Borough",
    bank: "north",
    seed: [4100, 2500],
    pattern: "grid",
    angle: 0.27,
    spacing: [92, 78],
    neighbors: ["b_sovereign", "b_vermilion", "b_ravensgate"],
    character: "Banks, law firms, and private clubs.",
    blurb: "Narrow and vertical. The men here have never once had to explain where the money came from.",
    weight: 11,
    streetNames: [...LONDON_OLD.slice(8, 22), ...ESTATE.slice(12, 20)],
    suffixes: ["Street", "Court", "Lane", "Yard", "Chambers"],
    typeMix: { office: 6, bar: 3, apartment: 3, hall: 2, clinic: 2, diner: 2, market: 1, church: 1 },
  },
  {
    id: "b_millgate",
    name: "Millgate",
    bank: "south",
    seed: [750, 1250],
    pattern: "grid",
    angle: -0.11,
    spacing: [175, 128],
    neighbors: ["b_bridge"],
    character: "Packing plants and rail sidings.",
    blurb: "The air smells like tallow all year. Shifts change at six and again at two, and nothing else marks the time.",
    weight: 9,
    streetNames: [...LA_WIDE.slice(6, 20), ...LONDON_OLD.slice(14, 20)],
    suffixes: ["Street", "Way", "Siding", "Road", "Yard"],
    typeMix: { warehouse: 6, garage: 4, bar: 3, diner: 2, apartment: 2, clinic: 1, market: 1, hall: 1 },
  },
  {
    id: "b_bridge",
    name: "Bridge District",
    bank: "south",
    seed: [2250, 1600],
    pattern: "organic",
    angle: 0.5,
    spacing: [70, 60],
    neighbors: ["b_millgate", "b_eastborough"],
    character: "Markets, printers, and the ferry landings.",
    blurb: "Where the two halves of the city meet and neither one takes responsibility. Everything is for sale by noon.",
    weight: 11,
    streetNames: [...LONDON_OLD.slice(0, 16), ...ESTATE.slice(0, 6)],
    suffixes: ["Row", "Lane", "Market", "Steps", "Alley", "Wharf"],
    typeMix: { market: 5, pawnshop: 4, bar: 4, diner: 3, apartment: 3, warehouse: 2, church: 2, motel: 2 },
  },
  {
    id: "b_eastborough",
    name: "East Borough",
    bank: "south",
    seed: [3550, 1100],
    pattern: "organic",
    angle: 0.19,
    spacing: [64, 55],
    neighbors: ["b_bridge", "b_coldbath", "b_saltney"],
    character: "Tenements. The part of the map the council keeps losing.",
    blurb: "Six floors, no elevator, forty families to a stair. The rent collector comes with someone large.",
    weight: 12,
    streetNames: [...LONDON_OLD.slice(4, 22), ...LA_WIDE.slice(14, 21)],
    suffixes: ["Lane", "Row", "Rents", "Alley", "Buildings", "Passage"],
    typeMix: { apartment: 6, bar: 5, pawnshop: 3, motel: 3, church: 2, clinic: 2, diner: 3, garage: 2 },
  },
  {
    id: "b_coldbath",
    name: "Coldbath",
    bank: "south",
    seed: [4600, 1050],
    pattern: "grid",
    angle: 0.06,
    spacing: [132, 110],
    neighbors: ["b_eastborough", "b_saltney"],
    character: "The prison, the asylum, and the county morgue.",
    blurb: "Institutional brick as far as the eye goes. Everything here has a number stencilled on it, including the people.",
    weight: 7,
    streetNames: [...ESTATE.slice(8, 20), ...LONDON_OLD.slice(5, 12)],
    suffixes: ["Street", "Road", "Gate", "Walk", "Terrace"],
    typeMix: { precinct: 4, clinic: 4, church: 3, apartment: 3, warehouse: 2, office: 2, diner: 1, hall: 1 },
  },
  {
    id: "b_saltney",
    name: "Saltney",
    bank: "south",
    seed: [5750, 620],
    pattern: "grid",
    angle: -0.24,
    spacing: [160, 112],
    neighbors: ["b_eastborough", "b_coldbath"],
    character: "Cranes, container yards, and the union hall.",
    blurb: "The estuary end. Gulls, creosote, and a hiring line that forms at four in the morning and settles nothing.",
    weight: 9,
    streetNames: [...LONDON_OLD.slice(8, 14), ...LA_WIDE.slice(0, 10), ...ESTATE.slice(16, 20)],
    suffixes: ["Wharf", "Quay", "Row", "Dock", "Reach", "Street"],
    typeMix: { pier: 6, warehouse: 5, bar: 4, motel: 2, garage: 2, diner: 2, hall: 2, apartment: 2 },
  },
];

/** Crossings are anchored to the river centreline so they always touch dry land
 *  on both banks, however the Ebb is redrawn. */
function crossing(
  id: string,
  name: string,
  x: number,
  kind: Bridge["kind"],
): Bridge {
  const y = riverYAt(x);
  const reach = riverClearanceAt(x) + 120;
  return {
    id,
    name,
    kind,
    points: [
      [x, Math.round(y + reach)],
      [x, Math.round(y - reach)],
    ],
  };
}

/**
 * Rail. Freight hugs the south bank through the industrial boroughs out to the
 * docks; the passenger line comes in from the north-west to a terminus behind
 * Sovereign Borough. Track carves a corridor through the blocks it crosses.
 */
const RAILWAYS: Array<{ id: string; name: string; points: Point[] }> = [
  {
    id: "rw_dockline",
    name: "Saltney Dock Line",
    points: [
      [0, 560],
      [820, 640],
      [1750, 830],
      [2600, 900],
      [3400, 700],
      [4250, 560],
      [5050, 520],
      [5700, 430],
    ],
  },
  {
    id: "rw_northern",
    name: "Great Northern Line",
    points: [
      [0, 4180],
      [780, 4020],
      [1500, 3620],
      [1960, 3200],
      [2180, 2900],
    ],
  },
  {
    id: "rw_cherwoodloop",
    name: "Ravensgate Loop",
    points: [
      [3120, 4400],
      [3600, 4090],
      [4300, 3980],
      [5000, 4080],
      [5720, 4260],
      [6400, 4300],
    ],
  },
];

const RAIL_CORRIDOR = 55;

function distanceToPolyline(x: number, y: number, pts: Point[]): number {
  let best = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[i + 1];
    const dx = x1 - x0;
    const dy = y1 - y0;
    const lenSq = dx * dx + dy * dy || 1;
    let t = ((x - x0) * dx + (y - y0) * dy) / lenSq;
    t = Math.max(0, Math.min(1, t));
    const d = Math.hypot(x - (x0 + t * dx), y - (y0 + t * dy));
    if (d < best) best = d;
  }
  return best;
}

function onRailCorridor(x: number, y: number): boolean {
  return RAILWAYS.some(
    (r) => distanceToPolyline(x, y, r.points) < RAIL_CORRIDOR,
  );
}

const BRIDGES: Bridge[] = [
  crossing("br_ludgate", "Ludgate Bridge", 1150, "bridge"),
  crossing("br_backlund", "Marrowgate Bridge", 2300, "bridge"),
  crossing("br_ironcross", "Iron Cross Bridge", 3700, "bridge"),
  crossing("br_saltferry", "Saltney Ferry", 5300, "ferry"),
];

// ---------------------------------------------------------------------------
// Borough membership: nearest same-bank seed. Cheap, and gives ragged borders.
// ---------------------------------------------------------------------------

function boroughAt(x: number, y: number): BoroughSeed | null {
  if (x < 60 || y < 60 || x > SIZE[0] - 60 || y > SIZE[1] - 60) return null;
  if (inRiver(x, y)) return null;
  const bank = bankAt(x, y);
  let best: BoroughSeed | null = null;
  let bestD = Infinity;
  for (const b of BOROUGHS) {
    if (b.bank !== bank) continue;
    const dx = x - b.seed[0];
    const dy = y - b.seed[1];
    const d = dx * dx + dy * dy;
    if (d < bestD) {
      bestD = d;
      best = b;
    }
  }
  return best;
}

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

function rotate([x, y]: Point, angle: number, about: Point): Point {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const dx = x - about[0];
  const dy = y - about[1];
  return [about[0] + dx * c - dy * s, about[1] + dx * s + dy * c];
}

const round = (p: Point): Point => [Math.round(p[0]), Math.round(p[1])];

/**
 * Walks a line, keeping only the stretches that fall inside `borough`. One
 * straight line through a ragged borough can yield several separate streets,
 * which is exactly what happens in a real city cut by a river and a rail line.
 */
function clipToBorough(
  line: Point[],
  borough: BoroughSeed,
  step = 25,
): Point[][] {
  const runs: Point[][] = [];
  let current: Point[] = [];

  for (let i = 0; i < line.length - 1; i++) {
    const [x0, y0] = line[i];
    const [x1, y1] = line[i + 1];
    const len = Math.hypot(x1 - x0, y1 - y0);
    const n = Math.max(1, Math.ceil(len / step));
    for (let k = 0; k <= n; k++) {
      const t = k / n;
      const p: Point = [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t];
      if (boroughAt(p[0], p[1])?.id === borough.id) {
        current.push(p);
      } else if (current.length) {
        runs.push(current);
        current = [];
      }
    }
  }
  if (current.length) runs.push(current);

  return runs.filter((r) => r.length > 3 && polylineLength(r) > 58);
}

function polylineLength(pts: Point[]): number {
  let total = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    total += Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]);
  }
  return total;
}

/**
 * Douglas-Peucker. Straight grid streets collapse to two points, winding lanes
 * keep their character, and the JSON stays a fraction of the size.
 */
function simplify(pts: Point[], tolerance = 9): Point[] {
  if (pts.length < 3) return pts;
  let maxDist = 0;
  let index = 0;
  const [ax, ay] = pts[0];
  const [bx, by] = pts[pts.length - 1];
  const dx = bx - ax;
  const dy = by - ay;
  const denom = Math.hypot(dx, dy) || 1;

  for (let i = 1; i < pts.length - 1; i++) {
    const d = Math.abs(dy * pts[i][0] - dx * pts[i][1] + bx * ay - by * ax) / denom;
    if (d > maxDist) {
      maxDist = d;
      index = i;
    }
  }
  if (maxDist <= tolerance) return [pts[0], pts[pts.length - 1]];
  return [
    ...simplify(pts.slice(0, index + 1), tolerance).slice(0, -1),
    ...simplify(pts.slice(index), tolerance),
  ];
}

/** Perpendicular wander, so an "organic" borough reads as an old street plan. */
function meander(pts: Point[], amplitude: number, wavelength: number): Point[] {
  if (pts.length < 2) return pts;
  const phase = rand() * Math.PI * 2;
  let travelled = 0;
  return pts.map((p, i) => {
    if (i === 0 || i === pts.length - 1) return p;
    travelled += Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]);
    const prev = pts[i - 1];
    const next = pts[i + 1] ?? p;
    const tx = next[0] - prev[0];
    const ty = next[1] - prev[1];
    const len = Math.hypot(tx, ty) || 1;
    const offset =
      Math.sin(phase + travelled / wavelength) * amplitude +
      Math.sin(phase * 2.3 + travelled / (wavelength * 0.43)) * amplitude * 0.35;
    return [p[0] - (ty / len) * offset, p[1] + (tx / len) * offset] as Point;
  });
}

// ---------------------------------------------------------------------------
// Street + block generation
// ---------------------------------------------------------------------------

interface Generated {
  streets: Street[];
  blocks: Block[];
}

/** Extent of the local rotated frame needed to cover a borough's whole area. */
const FRAME_REACH = 2100;

function generateGridLike(b: BoroughSeed): Generated {
  const streets: Street[] = [];
  const blocks: Block[] = [];
  const [sa, sb] = b.spacing;
  const stepsA = Math.ceil(FRAME_REACH / sa);
  const stepsB = Math.ceil(FRAME_REACH / sb);
  const organic = b.pattern === "organic";
  // Half the carriageway width. Larger insets leave the blocks looking marooned
  // in a sea of road once you zoom in.
  const roadInset = organic ? 8 : 12;
  const wander = b.meander ?? { amplitude: 26, wavelength: 240 };

  // Lines along the local X axis, spaced along Y.
  for (let j = -stepsB; j <= stepsB; j++) {
    const y = b.seed[1] + j * sb;
    let line: Point[] = [];
    for (let t = -FRAME_REACH; t <= FRAME_REACH; t += 60) {
      line.push(rotate([b.seed[0] + t, y], b.angle, b.seed));
    }
    if (organic) line = meander(line, wander.amplitude, wander.wavelength);
    const isAvenue = j % 4 === 0;
    for (const run of clipToBorough(line, b)) {
      streets.push(makeStreet(b, run, isAvenue ? "avenue" : organic ? "lane" : "street"));
    }
  }

  // Lines along the local Y axis, spaced along X.
  for (let i = -stepsA; i <= stepsA; i++) {
    const x = b.seed[0] + i * sa;
    let line: Point[] = [];
    for (let t = -FRAME_REACH; t <= FRAME_REACH; t += 60) {
      line.push(rotate([x, b.seed[1] + t], b.angle, b.seed));
    }
    if (organic) {
      line = meander(line, wander.amplitude * 0.85, wander.wavelength * 0.88);
    }
    const isAvenue = b.pattern === "boulevard" ? i === 0 : i % 4 === 0;
    for (const run of clipToBorough(line, b)) {
      streets.push(makeStreet(b, run, isAvenue ? "avenue" : organic ? "lane" : "street"));
    }
  }

  // Blocks sit on the unjittered grid. In organic boroughs the streets wander
  // around them, which is what an old city actually looks like from above.
  for (let i = -stepsA; i < stepsA; i++) {
    for (let j = -stepsB; j < stepsB; j++) {
      if (chance(0.12)) continue; // lots, yards, bomb sites
      const x0 = b.seed[0] + i * sa + roadInset;
      const x1 = b.seed[0] + (i + 1) * sa - roadInset;
      const y0 = b.seed[1] + j * sb + roadInset;
      const y1 = b.seed[1] + (j + 1) * sb - roadInset;
      const centre: Point = [(x0 + x1) / 2, (y0 + y1) / 2];
      const world = rotate(centre, b.angle, b.seed);
      if (boroughAt(world[0], world[1])?.id !== b.id) continue;
      if (onRailCorridor(world[0], world[1])) continue;

      const corners: Point[] = [
        [x0, y0],
        [x1, y0],
        [x1, y1],
        [x0, y1],
      ];
      const polygon = corners
        .map((c) => rotate(c, b.angle, b.seed))
        .map((c): Point =>
          organic ? [c[0] + between(-12, 12), c[1] + between(-12, 12)] : c,
        )
        .map(round);
      blocks.push({ polygon, boroughId: b.id, kind: "built" });
    }
  }

  return { streets, blocks };
}

function generateRadial(b: BoroughSeed): Generated {
  const streets: Street[] = [];
  const blocks: Block[] = [];
  const rings = 19;
  const spokes = 24;
  const ringGap = 100;

  for (let r = 1; r <= rings; r++) {
    const radius = r * ringGap;
    const line: Point[] = [];
    const segments = Math.max(24, Math.round(radius / 30));
    for (let k = 0; k <= segments; k++) {
      const a = (k / segments) * Math.PI * 2;
      line.push([
        b.seed[0] + Math.cos(a) * radius,
        b.seed[1] + Math.sin(a) * radius,
      ]);
    }
    for (const run of clipToBorough(line, b)) {
      streets.push(makeStreet(b, run, r % 3 === 0 ? "avenue" : "street"));
    }
  }

  for (let s = 0; s < spokes; s++) {
    const a = (s / spokes) * Math.PI * 2;
    const line: Point[] = [];
    for (let radius = 60; radius <= rings * ringGap + 400; radius += 60) {
      line.push([
        b.seed[0] + Math.cos(a) * radius,
        b.seed[1] + Math.sin(a) * radius,
      ]);
    }
    for (const run of clipToBorough(line, b)) {
      streets.push(makeStreet(b, run, s % 3 === 0 ? "avenue" : "street"));
    }
  }

  for (let r = 0; r < rings; r++) {
    for (let s = 0; s < spokes; s++) {
      if (chance(0.14)) continue;
      const r0 = r * ringGap + 11;
      const r1 = (r + 1) * ringGap - 11;
      const a0 = (s / spokes) * Math.PI * 2 + 0.035;
      const a1 = ((s + 1) / spokes) * Math.PI * 2 - 0.035;
      const corners: Point[] = [
        [b.seed[0] + Math.cos(a0) * r0, b.seed[1] + Math.sin(a0) * r0],
        [b.seed[0] + Math.cos(a1) * r0, b.seed[1] + Math.sin(a1) * r0],
        [b.seed[0] + Math.cos(a1) * r1, b.seed[1] + Math.sin(a1) * r1],
        [b.seed[0] + Math.cos(a0) * r1, b.seed[1] + Math.sin(a0) * r1],
      ];
      const cx = corners.reduce((a, c) => a + c[0], 0) / 4;
      const cy = corners.reduce((a, c) => a + c[1], 0) / 4;
      if (boroughAt(cx, cy)?.id !== b.id) continue;
      if (onRailCorridor(cx, cy)) continue;
      blocks.push({ polygon: corners.map(round), boroughId: b.id, kind: "built" });
    }
  }

  return { streets, blocks };
}

let streetSeq = 0;
const usedStreetNames = new Set<string>();

function makeStreet(
  b: BoroughSeed,
  points: Point[],
  kind: Street["kind"],
): Street {
  let name = "";
  for (let attempt = 0; attempt < 25; attempt++) {
    name = `${pick(b.streetNames)} ${pick(b.suffixes)}`;
    if (!usedStreetNames.has(name)) break;
  }
  // A city reuses names across boroughs; only bail if we cannot find anything.
  usedStreetNames.add(name);
  return {
    id: `st_${String(streetSeq++).padStart(4, "0")}`,
    name,
    boroughId: b.id,
    kind,
    points: simplify(points).map(round),
  };
}

// ---------------------------------------------------------------------------
// Business names
// ---------------------------------------------------------------------------

const SURNAMES = "Kowalski Voss Dorsey Amato Reyes Baptiste Lindqvist Okafor Brennan Sokolov Marchetti Ferraro Whelan Delgado Novak Ashworth Calloway Petrakis Hollis Zagorski Mancuso Tavares Brackett Sandoval Rennick Yarrow Falk Bertrand Halloran Tsai Moreau Castellano Winthrop Salazar Grimaldi Preston Vachon Marlowe Quist Ibarra Nazari Deakin".split(" ");
const ADJ = "Blue Golden Silver Red Midnight Broken Lucky Crimson Velvet Iron Copper Amber Lonely Crooked Electric Neon Paper Glass Hollow Ruby Emerald Dusty Quiet Sunken Faded Bitter Grand Royal".split(" ");
const NOUN = "Note Anchor Palm Lantern Room Star Crown Key Mirror Dollar Rose Moon Kettle Spur Wire Orchid Coin Bell Fox Marlin Dial Ladder Vault Wing Tide Harp Sparrow Lion".split(" ");

/**
 * Types the generator invents filler for. Stations, the prison, the university
 * and the monuments exist exactly once each and are hand-authored below, so
 * they deliberately have no name bank.
 */
type GeneratedType = Exclude<
  LocationType,
  "station" | "prison" | "university" | "monument"
>;

const NAME_PATTERNS: Record<GeneratedType, Array<() => string>> = {
  bar: [() => `The ${pick(ADJ)} ${pick(NOUN)}`, () => `${pick(SURNAMES)}'s Tavern`, () => `The ${pick(NOUN)} & Anchor`, () => `${pick(SURNAMES)}'s Public House`],
  diner: [() => `${pick(SURNAMES)}'s Coffee Shop`, () => `The ${pick(ADJ)} ${pick(NOUN)} Diner`, () => `${pick(SURNAMES)} & Sons Cafe`, () => `The All-Night ${pick(NOUN)}`],
  warehouse: [() => `${pick(SURNAMES)} Freight & Storage`, () => `Bond Warehouse ${2 + Math.floor(rand() * 40)}`, () => `${pick(SURNAMES)} Cold Storage`, () => `${pick(ADJ)} ${pick(NOUN)} Haulage`],
  apartment: [() => `The ${pick(ADJ)} ${pick(NOUN)} Apartments`, () => `${pick(SURNAMES)} Buildings`, () => `${pick(SURNAMES)} Court`, () => `${pick(NOUN)} Mansions`],
  office: [() => `${pick(SURNAMES)} & ${pick(SURNAMES)}, Attorneys`, () => `${pick(SURNAMES)} Realty`, () => `The ${pick(SURNAMES)} Building`, () => `${pick(SURNAMES)} Assurance Co.`],
  precinct: [() => `Precinct ${1 + Math.floor(rand() * 22)}`, () => `${pick(SURNAMES)} Street Station House`, () => `Divisional Headquarters`],
  club: [() => `Club ${pick(NOUN)}`, () => `The ${pick(ADJ)} ${pick(NOUN)} Lounge`, () => `${pick(SURNAMES)}'s`, () => `The ${pick(NOUN)} Club`],
  motel: [() => `The ${pick(ADJ)} ${pick(NOUN)} Motel`, () => `${pick(SURNAMES)} Motor Inn`, () => `Hotel ${pick(SURNAMES)}`, () => `The ${pick(NOUN)} Rooms`],
  pier: [() => `Berth ${10 + Math.floor(rand() * 80)}`, () => `${pick(SURNAMES)} Boatworks`, () => `${pick(ADJ)} ${pick(NOUN)} Wharf`, () => `Dry Dock ${1 + Math.floor(rand() * 9)}`],
  church: [() => `St. ${pick(SURNAMES)}'s`, () => `${pick(SURNAMES)} Mission`, () => `Chapel of the ${pick(ADJ)} ${pick(NOUN)}`, () => `The ${pick(NOUN)} Meeting House`],
  garage: [() => `${pick(SURNAMES)} Auto Body`, () => `${pick(SURNAMES)} Service Station`, () => `${pick(ADJ)} ${pick(NOUN)} Motors`, () => `${pick(SURNAMES)} Wrecking Yard`],
  clinic: [() => `${pick(SURNAMES)} Medical Clinic`, () => `The ${pick(NOUN)} Free Clinic`, () => `Dr. ${pick(SURNAMES)}, Physician`, () => `${pick(SURNAMES)} Infirmary`],
  theatre: [() => `The ${pick(ADJ)} ${pick(NOUN)}`, () => `The ${pick(SURNAMES)} Theatre`, () => `${pick(SURNAMES)} Playhouse`, () => `The ${pick(NOUN)} Picture House`],
  pawnshop: [() => `${pick(SURNAMES)} Loan & Pawn`, () => `${pick(NOUN)} Trading Post`, () => `${pick(ADJ)} ${pick(NOUN)} Exchange`, () => `${pick(SURNAMES)} Curios`],
  market: [() => `${pick(SURNAMES)}'s Grocery`, () => `The ${pick(NOUN)} Market`, () => `${pick(ADJ)} ${pick(NOUN)} Provisions`, () => `${pick(SURNAMES)} Fish Market`],
  hall: [() => `The ${pick(SURNAMES)} Institute`, () => `${pick(NOUN)} Union Hall`, () => `The ${pick(ADJ)} ${pick(NOUN)} Library`, () => `${pick(SURNAMES)} Assembly Rooms`],
};

const BLURBS: Record<GeneratedType, string[]> = {
  bar: ["Sticky floors, a jukebox with three working songs, and a bartender who has heard it all.", "Dim, low-ceilinged, full of men who came in at noon and have not moved.", "Nobody looks up when the door opens. That is the whole appeal."],
  diner: ["Formica counters and coffee that has been on the burner since morning.", "Steam on the windows, a radio going, nobody in a hurry.", "Open all night, which is the only reason anyone comes."],
  warehouse: ["Corrugated walls, a padlock, and the smell of diesel.", "Pallets stacked to the roof and dust hanging in the light.", "Nothing moves here after six except rats."],
  apartment: ["Half the mailboxes are broken. The stairwell smells of boiled cabbage.", "Six floors, no elevator, walls you could put a fist through.", "Somebody's television is on too loud on the third floor."],
  office: ["Frosted glass, a name in gold leaf, a secretary who does not want to help.", "Filing cabinets and a view of an airshaft.", "Dark windows. Closed for the day, or closed for good."],
  precinct: ["Fluorescent light, a desk sergeant, and a bench full of people waiting.", "Coffee, carbon paper, and a hostility you can taste.", "Nobody here is going to do you a favour twice."],
  club: ["A velvet rope and a doorman with opinions.", "Cigarette smoke thick enough to lean on.", "A band nobody is listening to, a crowd nobody wants to remember."],
  motel: ["Twelve units around a cracked lot. The vacancy sign flickers.", "A clerk behind wire glass who does not ask for names.", "Thin curtains and thinner walls."],
  pier: ["Gulls, creosote, and water slapping the pilings.", "Nets, rust, and a dog that watches you the whole way down.", "Fog comes in off the estuary and takes the far end of the dock."],
  church: ["Cool, dim, and empty on a weekday.", "Votive candles and a poor box with a new lock.", "Somebody is always kneeling in the back row."],
  garage: ["A hoist, an oil pit, and a radio playing ball scores.", "Three cars in various stages of coming apart.", "The owner wipes his hands and does not stop working."],
  clinic: ["Vinyl chairs and a two-hour wait.", "Antiseptic and magazines from four years ago.", "A nurse who has seen worse than whatever you brought in."],
  theatre: ["Faded velvet, a marquee missing letters, half the seats empty.", "A matinee running to nobody at all.", "Popcorn grease and a projector you can hear from the lobby."],
  pawnshop: ["Wedding rings under glass and a shotgun behind the counter.", "Guitars on the wall, none of them sold in years.", "The man behind the counter remembers every face."],
  market: ["Crates on the pavement and a man shouting prices nobody disputes.", "Sawdust, ice, and the smell of yesterday's fish.", "Everything is cheaper here and none of it has papers."],
  hall: ["Notice boards four layers deep and a caretaker who wants to lock up.", "Long tables, bad acoustics, a portrait of somebody nobody can name.", "The meeting ended an hour ago. The arguing did not."],
};

// ---------------------------------------------------------------------------
// Open ground and hand-authored anchors
// ---------------------------------------------------------------------------

/** Parks, cemeteries and rail yards. Named, so cases can send you to one. */
const GREENS: Array<{
  name: string;
  centre: Point;
  radius: number;
  kind: "park" | "yard";
}> = [
  { name: "The Circus Ground", centre: [5300, 3350], radius: 215, kind: "park" },
  { name: "Whitcombe Gardens", centre: [700, 3350], radius: 230, kind: "park" },
  { name: "Bell Square", centre: [2150, 2700], radius: 150, kind: "park" },
  { name: "Vermilion Green", centre: [2400, 4100], radius: 175, kind: "park" },
  { name: "Cripplegate Cemetery", centre: [3050, 700], radius: 190, kind: "park" },
  { name: "Coldbath Fields", centre: [4600, 1100], radius: 200, kind: "park" },
  { name: "Chambers Court", centre: [4350, 2450], radius: 120, kind: "park" },
  { name: "Millgate Marshalling Yard", centre: [1150, 780], radius: 265, kind: "yard" },
  { name: "Saltney Container Yard", centre: [5400, 780], radius: 245, kind: "yard" },
];

/**
 * The map's fixed points. Everything else in Marrowgate is generated filler; these
 * are the places a case can actually be about, so they are written by hand.
 */
const LANDMARKS: Array<{
  name: string;
  type: LocationType;
  at: Point;
  blurb: string;
}> = [
  { name: "Marrowgate City Hall", type: "hall", at: [2000, 2900], blurb: "Granite steps, brass doors, and a lobby built to make you feel small. It works." },
  { name: "The Bell of Order", type: "monument", at: [2150, 2620], blurb: "Cast in a year nobody agrees on. It rings the hour and, twice in living memory, something else." },
  { name: "The Assize Courts", type: "hall", at: [1700, 3050], blurb: "Where the city decides what happened. Accuracy is not the first consideration." },
  { name: "Divisional Police Headquarters", type: "precinct", at: [2450, 2980], blurb: "Six floors of filing and one honest lieutenant, and nobody will tell you which floor." },
  { name: "Sodela Palace", type: "monument", at: [1560, 2760], blurb: "Closed to the public since the fire. The railings alone cost more than this borough earns in a year." },
  { name: "The Marrowgate Exchange", type: "office", at: [4160, 2560], blurb: "A trading floor that empties at three and a basement that does not." },
  { name: "Blackthorn Security Company", type: "office", at: [4020, 2420], blurb: "Private enquiries, discreet. Two rooms above a tobacconist on Iron Cross Street." },
  { name: "Marrowgate University", type: "university", at: [5300, 3640], blurb: "Quadrangles, bicycles, and a chemistry department that does not log who signs the key out." },
  { name: "The Ravensgate Public Library", type: "hall", at: [5060, 3300], blurb: "Four floors of stacks. The restricted room needs a letter from somebody who matters." },
  { name: "St. Selena's Cathedral", type: "church", at: [880, 3770], blurb: "Cold stone and a choir that rehearses at seven. The verger notices everyone who comes in." },
  { name: "The Orpheum", type: "theatre", at: [2860, 3720], blurb: "Two thousand seats, gilt flaking off the boxes, and a stage door that is never locked." },
  { name: "The Golden Marlin", type: "club", at: [3180, 3810], blurb: "The strip's oldest room. The house takes a cut of everything, including conversations." },
  { name: "Marrowgate Bridge Market", type: "market", at: [2320, 1790], blurb: "Two hundred stalls under the arches. Anything can be bought here and nothing can be traced." },
  { name: "The Ferry Steps", type: "pier", at: [2450, 1900], blurb: "Worn hollow by two centuries of boots. The tide leaves things on the bottom stair." },
  { name: "The Rookery", type: "apartment", at: [3480, 1060], blurb: "Nine buildings sharing four staircases and no clear ownership. The police come in threes." },
  { name: "Coldbath Fields Prison", type: "prison", at: [4720, 1240], blurb: "Forty-foot wall, one gate, and a governor who answers questions in writing only." },
  { name: "St. Maar Asylum", type: "clinic", at: [4430, 940], blurb: "Red brick and small windows. Committal here requires two signatures and no relatives." },
  { name: "The County Morgue", type: "clinic", at: [4830, 1150], blurb: "Tile, drains, and a duty clerk who will trade a look at the book for a bottle." },
  { name: "Millgate Terminus", type: "station", at: [1290, 1420], blurb: "Soot, steam, and the departure board clacking over. Anyone leaving the city leaves from here." },
  { name: "Sovereign Road Station", type: "station", at: [2280, 3230], blurb: "The northern line's last stop. Commuters by day, nobody you want to meet by night." },
  { name: "The Dockers' Union Hall", type: "hall", at: [5680, 700], blurb: "The hiring list is posted at four. Whoever controls this room controls the waterfront." },
  { name: "No. 4 Dry Dock", type: "pier", at: [5900, 520], blurb: "Drained, echoing, and forty feet deep. Things go in that do not come back up." },
];

function circlePolygon(centre: Point, radius: number, segments = 14): Point[] {
  const pts: Point[] = [];
  for (let i = 0; i < segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    pts.push([
      Math.round(centre[0] + Math.cos(a) * radius),
      Math.round(centre[1] + Math.sin(a) * radius),
    ]);
  }
  return pts;
}

function centroid(pts: Point[]): Point {
  const n = pts.length || 1;
  return [
    pts.reduce((a, p) => a + p[0], 0) / n,
    pts.reduce((a, p) => a + p[1], 0) / n,
  ];
}

function nearestStreet(x: number, y: number, streets: Street[]): Street | null {
  let best: Street | null = null;
  let bestD = Infinity;
  for (const s of streets) {
    const d = distanceToPolyline(x, y, s.points);
    if (d < bestD) {
      bestD = d;
      best = s;
    }
  }
  return best;
}

// ---------------------------------------------------------------------------

function main() {
  const streets: Street[] = [];
  const blocks: Block[] = [];

  console.log("Laying out Marrowgate\n");
  for (const b of BOROUGHS) {
    const gen = b.pattern === "radial" ? generateRadial(b) : generateGridLike(b);
    streets.push(...gen.streets);
    blocks.push(...gen.blocks);
    console.log(
      `  ${b.name.padEnd(16)} ${String(gen.streets.length).padStart(4)} streets  ${String(gen.blocks.length).padStart(4)} blocks  (${b.pattern})`,
    );
  }

  // Greens displace whatever was built there.
  console.log("");
  const greenBlocks: Block[] = [];
  for (const g of GREENS) {
    const borough = boroughAt(g.centre[0], g.centre[1]);
    if (!borough) {
      console.log(`  ! ${g.name} falls in the Ebb - skipped`);
      continue;
    }
    for (let i = blocks.length - 1; i >= 0; i--) {
      const c = centroid(blocks[i].polygon);
      if (Math.hypot(c[0] - g.centre[0], c[1] - g.centre[1]) < g.radius) {
        blocks.splice(i, 1);
      }
    }
    greenBlocks.push({
      polygon: circlePolygon(g.centre, g.radius),
      boroughId: borough.id,
      kind: g.kind,
    });
    console.log(`  ${g.name.padEnd(28)} ${g.kind} in ${borough.name}`);
  }
  blocks.push(...greenBlocks);

  // Locations sit on a street frontage, so every address is real.
  const TOTAL = 1200;
  const totalWeight = BOROUGHS.reduce((a, b) => a + b.weight, 0);
  const locations: CityLocation[] = [];
  const usedNames = new Set<string>();
  let locSeq = 0;

  console.log("");
  for (const b of BOROUGHS) {
    const target = Math.round((b.weight / totalWeight) * TOTAL);
    const boroughStreets = streets.filter((s) => s.boroughId === b.id);
    if (!boroughStreets.length) {
      console.log(`  ${b.name.padEnd(16)} SKIPPED - no streets generated`);
      continue;
    }

    let placed = 0;
    let guard = 0;
    while (placed < target && guard++ < target * 40) {
      const street = pick(boroughStreets);
      const segment = Math.floor(rand() * (street.points.length - 1));
      const [x0, y0] = street.points[segment];
      const [x1, y1] = street.points[segment + 1];
      const t = rand();
      const px = x0 + (x1 - x0) * t;
      const py = y0 + (y1 - y0) * t;

      // Step off the carriageway onto one side or the other.
      const dx = x1 - x0;
      const dy = y1 - y0;
      const len = Math.hypot(dx, dy) || 1;
      const side = chance(0.5) ? 1 : -1;
      const offset = between(24, 46) * side;
      const x = px - (dy / len) * offset;
      const y = py + (dx / len) * offset;

      if (boroughAt(x, y)?.id !== b.id) continue;

      const type = weighted<GeneratedType>(b.typeMix as Record<string, number>);
      let name = "";
      for (let attempt = 0; attempt < 20; attempt++) {
        name = pick(NAME_PATTERNS[type])();
        if (!usedNames.has(name)) break;
      }
      if (usedNames.has(name)) continue;
      usedNames.add(name);

      const number = 1 + Math.floor(rand() * 240);
      locations.push({
        id: `loc_${String(locSeq++).padStart(4, "0")}`,
        name,
        type,
        boroughId: b.id,
        streetId: street.id,
        address: `${number} ${street.name}`,
        x: Math.round(x),
        y: Math.round(y),
        blurb: pick(BLURBS[type]),
        isLandmark: false,
      });
      placed++;
    }
    console.log(`  ${b.name.padEnd(16)} ${String(placed).padStart(4)} locations`);
  }

  // Landmarks go in last so they never lose a name collision to filler.
  console.log("");
  let landmarksPlaced = 0;
  for (const lm of LANDMARKS) {
    const borough = boroughAt(lm.at[0], lm.at[1]);
    if (!borough) {
      console.log(`  ! ${lm.name} falls in the Ebb - skipped`);
      continue;
    }
    const boroughStreets = streets.filter((s) => s.boroughId === borough.id);
    const street = nearestStreet(lm.at[0], lm.at[1], boroughStreets);
    if (!street) {
      console.log(`  ! ${lm.name} has no street to front onto - skipped`);
      continue;
    }
    locations.push({
      id: `loc_lm_${lm.name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")}`,
      name: lm.name,
      type: lm.type,
      boroughId: borough.id,
      streetId: street.id,
      address: `${1 + Math.floor(rand() * 90)} ${street.name}`,
      x: lm.at[0],
      y: lm.at[1],
      blurb: lm.blurb,
      isLandmark: true,
    });
    landmarksPlaced++;
  }
  console.log(`  ${landmarksPlaced} of ${LANDMARKS.length} landmarks placed`);

  // Borough polygons are the convex hull of their blocks - enough for labels,
  // hover highlighting and a soft fill, without tracing a true boundary.
  const boroughs: Borough[] = BOROUGHS.map((b) => ({
    id: b.id,
    name: b.name,
    bank: b.bank,
    polygon: convexHull(
      blocks.filter((bl) => bl.boroughId === b.id).flatMap((bl) => bl.polygon),
    ),
    neighbors: b.neighbors,
    pattern: b.pattern,
    blurb: b.blurb,
    character: b.character,
  }));

  const city: City = {
    id: "marrowgate",
    name: "Marrowgate",
    size: SIZE,
    river: {
      name: "The Ebb",
      points: RIVER,
      polygon: riverPolygon(),
      widthAtSource: RIVER_WIDTH_SOURCE,
      widthAtMouth: RIVER_WIDTH_MOUTH,
    },
    bridges: BRIDGES,
    railways: RAILWAYS,
    boroughs,
    streets,
    blocks,
    locations,
  };

  // Lives in public/ so the browser fetches it as a static asset rather than
  // having half a megabyte of JSON inlined into the JS bundle. The server reads
  // the same file off disk, so there is only ever one copy.
  const dir = join(process.cwd(), "public");
  mkdirSync(dir, { recursive: true });
  const json = JSON.stringify(city);
  writeFileSync(join(dir, "city.json"), json);

  // The server only ever needs to answer "where is this and what does it cost
  // to get there" - it never draws anything. Shipping the streets and blocks
  // into a Cloudflare Worker bundle would be half a megabyte of dead weight, so
  // navigation data gets its own much smaller file.
  const nav = {
    id: city.id,
    name: city.name,
    size: city.size,
    river: { ...city.river, points: city.river.points, polygon: [] },
    bridges: city.bridges,
    railways: [],
    boroughs: city.boroughs.map((b) => ({ ...b, polygon: [] })),
    streets: [],
    blocks: [],
    locations: city.locations,
  };
  const navJson = JSON.stringify(nav);
  const contentDir = join(process.cwd(), "content");
  mkdirSync(contentDir, { recursive: true });
  writeFileSync(join(contentDir, "city-nav.json"), navJson);

  console.log(
    `\n  ${streets.length} streets, ${blocks.length} blocks, ${locations.length} locations`,
  );
  console.log(`  public/city.json       ${(json.length / 1024).toFixed(0)} KB  (browser: full geometry)`);
  console.log(`  content/city-nav.json  ${(navJson.length / 1024).toFixed(0)} KB  (server: navigation only)`);
}

/** Andrew's monotone chain. */
function convexHull(points: Point[]): Point[] {
  if (points.length < 3) return points;
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: Point, a: Point, b: Point) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);

  const lower: Point[] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
      lower.pop();
    }
    lower.push(p);
  }
  const upper: Point[] = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
      upper.pop();
    }
    upper.push(p);
  }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

main();
