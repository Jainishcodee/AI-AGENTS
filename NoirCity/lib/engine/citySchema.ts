import { z } from "zod";

/**
 * Backlund - a fictional city in a fictional coordinate space.
 *
 * Structure is lifted from the Lord of the Mysteries map: a river cutting the
 * city into two banks, joined by a handful of bridges, with class-divided
 * boroughs on either side. Texture is a blend of Los Angeles (wide boulevards,
 * sprawl, a harbour, a neon strip) and London (a winding old core, tenement
 * lanes, a civic quarter).
 *
 * Coordinates are plain metres from the south-west corner, NOT lat/lng. There
 * is no real place to fetch tiles for, so the map is drawn from this data with
 * Leaflet's CRS.Simple. That costs us a renderer and buys us total control of
 * the look, no attribution, and no tile rate limits.
 */

export const LOCATION_TYPES = [
  "bar",
  "diner",
  "warehouse",
  "apartment",
  "office",
  "precinct",
  "club",
  "motel",
  "pier",
  "church",
  "garage",
  "clinic",
  "theatre",
  "pawnshop",
  "market",
  "hall",
  "station",
  "prison",
  "university",
  "monument",
] as const;

export type LocationType = (typeof LOCATION_TYPES)[number];

/** Which side of the Tussock a borough sits on. Crossing costs extra time. */
export const BANKS = ["north", "south"] as const;
export type Bank = (typeof BANKS)[number];

/** Drives street generation and the type mix of what gets built there. */
export const STREET_PATTERNS = [
  "grid",
  "organic",
  "radial",
  "boulevard",
] as const;
export type StreetPattern = (typeof STREET_PATTERNS)[number];

export const pointSchema = z.tuple([z.number(), z.number()]);
export type Point = [number, number];

export const boroughSchema = z.object({
  id: z.string(),
  name: z.string(),
  bank: z.enum(BANKS),
  /** Closed polygon in city metres. */
  polygon: z.array(pointSchema),
  /** Boroughs reachable without a detour. Same-bank only. */
  neighbors: z.array(z.string()),
  pattern: z.enum(STREET_PATTERNS),
  blurb: z.string(),
  /** Rough social register, used for flavour and the type mix. */
  character: z.string(),
});

export const streetSchema = z.object({
  id: z.string(),
  name: z.string(),
  boroughId: z.string(),
  kind: z.enum(["avenue", "street", "lane"]),
  points: z.array(pointSchema),
});

export const bridgeSchema = z.object({
  id: z.string(),
  name: z.string(),
  /** Crossing points, north bank to south bank. */
  points: z.array(pointSchema),
  /** A ferry is slower and atmospheric; a bridge is the fast way over. */
  kind: z.enum(["bridge", "ferry"]),
});

/** Parks and yards break up the block mass and give the map somewhere to breathe. */
export const BLOCK_KINDS = ["built", "park", "yard"] as const;
export type BlockKind = (typeof BLOCK_KINDS)[number];

/** Building masses, drawn under the street lines. Pure decoration. */
export const blockSchema = z.object({
  polygon: z.array(pointSchema),
  boroughId: z.string(),
  kind: z.enum(BLOCK_KINDS).default("built"),
});

export const railwaySchema = z.object({
  id: z.string(),
  name: z.string(),
  points: z.array(pointSchema),
});

export const cityLocationSchema = z.object({
  id: z.string(),
  name: z.string(),
  type: z.enum(LOCATION_TYPES),
  boroughId: z.string(),
  /** Street it fronts onto, for the address line. */
  streetId: z.string(),
  address: z.string(),
  x: z.number(),
  y: z.number(),
  /** Shown when a location has no case content. Flavour, never a hint. */
  blurb: z.string(),
  /** Hand-authored anchors - City Hall, the prison, the union hall. Cases hang
   *  off these, and the map labels them at any zoom. */
  isLandmark: z.boolean().default(false),
});

export const citySchema = z.object({
  id: z.string(),
  name: z.string(),
  /** [width, height] in city metres. Origin is south-west. */
  size: pointSchema,
  river: z.object({
    name: z.string(),
    /** Centreline, north-west to south-east. */
    points: z.array(pointSchema),
    /** Both banks as one closed ring. The Tussock widens into an estuary as it
     *  runs east, so a single width would not describe it. */
    polygon: z.array(pointSchema),
    widthAtSource: z.number(),
    widthAtMouth: z.number(),
  }),
  bridges: z.array(bridgeSchema),
  railways: z.array(railwaySchema),
  boroughs: z.array(boroughSchema),
  streets: z.array(streetSchema),
  blocks: z.array(blockSchema),
  locations: z.array(cityLocationSchema),
});

export type Borough = z.infer<typeof boroughSchema>;
export type Street = z.infer<typeof streetSchema>;
export type Bridge = z.infer<typeof bridgeSchema>;
export type Railway = z.infer<typeof railwaySchema>;
export type Block = z.infer<typeof blockSchema>;
export type CityLocation = z.infer<typeof cityLocationSchema>;
export type City = z.infer<typeof citySchema>;

/** Indexed view of a city, built once and reused by the reducer. */
export interface CityIndex {
  city: City;
  locations: Map<string, CityLocation>;
  boroughs: Map<string, Borough>;
  streets: Map<string, Street>;
}

export function indexCity(city: City): CityIndex {
  return {
    city,
    locations: new Map(city.locations.map((l) => [l.id, l])),
    boroughs: new Map(city.boroughs.map((b) => [b.id, b])),
    streets: new Map(city.streets.map((s) => [s.id, s])),
  };
}

export const TRAVEL_COST = {
  sameBorough: 1,
  adjacentBorough: 2,
  acrossBank: 3,
  /** Added on top when the trip has to cross the Tussock. Bridges are the
   *  chokepoint the whole map is built around - this is where the tension is. */
  riverCrossing: 1,
} as const;

/** Travel cost in time units between two locations. */
export function travelCost(
  index: CityIndex,
  fromId: string | null,
  toId: string,
): number {
  if (!fromId || fromId === toId) return 0;
  const from = index.locations.get(fromId);
  const to = index.locations.get(toId);
  if (!from || !to) return TRAVEL_COST.acrossBank + TRAVEL_COST.riverCrossing;

  const fromB = index.boroughs.get(from.boroughId);
  const toB = index.boroughs.get(to.boroughId);
  if (!fromB || !toB) return TRAVEL_COST.acrossBank;

  if (fromB.id === toB.id) return TRAVEL_COST.sameBorough;

  const crossesRiver = fromB.bank !== toB.bank;
  const base = fromB.neighbors.includes(toB.id)
    ? TRAVEL_COST.adjacentBorough
    : TRAVEL_COST.acrossBank;

  return base + (crossesRiver ? TRAVEL_COST.riverCrossing : 0);
}

export function parseCity(raw: unknown): City {
  return citySchema.parse(raw);
}
