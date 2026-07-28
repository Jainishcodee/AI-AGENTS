/**
 * The map's whole colour vocabulary, in one place. Backlund at night: cold
 * water, warm sodium light on the main roads, everything else drained.
 */
export const MAP_COLORS = {
  ink: "#08090b",
  water: "#0d1a22",
  waterEdge: "#16303c",

  // Blocks have to sit clearly above the background or the city reads as a bare
  // road network with holes in it.
  blockBuilt: "#1d1e23",
  blockBuiltEdge: "#2b2c33",
  blockPark: "#16241a",
  blockParkEdge: "#233327",
  blockYard: "#211f19",
  blockYardEdge: "#302b23",

  lane: "#34343c",
  street: "#454851",
  avenue: "#5f5c53",
  rail: "#4a463f",
  bridge: "#8d8168",

  pin: "#c9a227",
  pinVisited: "#5f6b70",
  landmark: "#d94f3d",
  here: "#f2e5c4",

  boroughLabel: "#8f887a",
  landmarkLabel: "#cdc5b2",
} as const;

/**
 * Carriageway widths in METRES, not pixels - a road has to grow with the city
 * as you zoom in, the same as the blocks either side of it. `minPx` keeps the
 * hierarchy readable when the whole city is on screen.
 */
export const ROAD_WIDTH = {
  avenue: { metres: 26, minPx: 1.7 },
  street: { metres: 14, minPx: 1.1 },
  lane: { metres: 9, minPx: 0.7 },
} as const;
