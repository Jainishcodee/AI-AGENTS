/**
 * The map's whole colour vocabulary, in one place. Backlund at night: cold
 * water, a little sodium light on the main roads, everything else drained.
 *
 * This is the canvas half of the palette in `app/globals.css`, and the two are
 * deliberately the same city. Canvas cannot read CSS custom properties without
 * a `getComputedStyle` per draw, so the values are repeated here rather than
 * referenced - which makes it worth saying explicitly that `ink` is
 * `--color-ink`, `here` is `--color-gold`, and the greys sit on the same cold
 * axis as the text ladder. Changing one without the other will show.
 */
export const MAP_COLORS = {
  ink: "#08090b",
  water: "#0b1720",
  waterEdge: "#132a36",

  // Blocks have to sit clearly above the background or the city reads as a bare
  // road network with holes in it.
  blockBuilt: "#191b20",
  blockBuiltEdge: "#262930",
  blockPark: "#141f19",
  blockParkEdge: "#1f2c25",
  blockYard: "#1c1d1f",
  blockYardEdge: "#292b2e",

  // Roads sit only just above the blocks they divide. They were much brighter,
  // which turned the whole city into a lit web that fought the panel for
  // attention - and a map you have to look past is not doing its job. The
  // hierarchy between the three is what carries navigation, not their absolute
  // brightness, so it survives the drop intact.
  lane: "#24262c",
  street: "#31343b",
  avenue: "#45474d",
  rail: "#34363a",
  bridge: "#5c5d62",

  // The only warm marks on the whole map, and the same rule as the UI: gold is
  // where you are, and where you could go. Everywhere you have already been
  // goes cold and stops competing for attention.
  pin: "#8a7a3f",
  pinVisited: "#4a525a",
  landmark: "#a24a3c",
  here: "#c9a227",

  boroughLabel: "#6f757d",
  landmarkLabel: "#9aa0a8",

  // --- address chips ------------------------------------------------------
  // Close in, every address is a disc carrying its category glyph. The disc has
  // to be darker than the blocks it sits on so the glyph inside it reads, which
  // is the opposite of the dots it replaces - those had to be brighter.
  chip: "#0a0c0f",
  chipEdge: "#4b525d",
  chipEdgeVisited: "#2b2f36",
  chipGlyph: "#c6ccd5",

  // --- atmosphere ---------------------------------------------------------
  // Not features of the city, but of the night it is sitting in. All three are
  // painted once per draw like everything else here - there is no animation
  // loop behind any of it.
  /** Sodium light spilling off the main roads. Very low alpha, laid wide. */
  avenueGlow: "rgba(198, 162, 96, 0.055)",
  /** Mist coming off the Tussock, heaviest at the near bank. */
  riverFog: "rgba(150, 180, 196, 0.07)",
  /**
   * Corners of the plate, so the city does not end in a hard rectangle.
   * Kept light: this is a frame, not a spotlight, and the far boroughs still
   * have to be readable enough to navigate by.
   */
  vignette: "rgba(0, 0, 0, 0.42)",
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
