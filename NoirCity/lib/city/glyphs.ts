import { LOCATION_TYPES, type LocationType } from "@/lib/engine/citySchema";

/**
 * What each kind of address looks like on the map.
 *
 * Nineteen location types is far too many distinct pictures to tell apart at
 * eleven pixels, so they collapse into nine families. The point of the glyph is
 * not to say precisely what a building is - the label and the panel do that -
 * but to let you sweep the map and see that this street is bars and that one is
 * warehouses. Nine shapes is about the limit of what reads at a glance anyway.
 *
 * Drawn as paths rather than an icon font or sprite sheet: they are on a canvas
 * with everything else, they have to take their colour from the state of the
 * place they mark, and this way they cost no request and no layout.
 */

export const GLYPH_FAMILIES = [
  "home",
  "drink",
  "work",
  "civic",
  "faith",
  "care",
  "trade",
  "culture",
  "water",
] as const;

export type GlyphFamily = (typeof GLYPH_FAMILIES)[number];

const FAMILY_OF: Record<LocationType, GlyphFamily> = {
  apartment: "home",
  motel: "home",

  bar: "drink",
  club: "drink",
  diner: "drink",

  office: "work",
  warehouse: "work",
  garage: "work",

  precinct: "civic",
  hall: "civic",
  prison: "civic",
  station: "civic",

  church: "faith",
  monument: "faith",

  clinic: "care",

  market: "trade",
  pawnshop: "trade",

  theatre: "culture",
  university: "culture",

  pier: "water",
};

export function glyphFamily(type: LocationType): GlyphFamily {
  return FAMILY_OF[type];
}

/** Human names for the legend. */
export const FAMILY_LABEL: Record<GlyphFamily, string> = {
  home: "Homes and rooms",
  drink: "Bars and diners",
  work: "Offices and yards",
  civic: "Civic and law",
  faith: "Churches",
  care: "Doctors",
  trade: "Shops and pawn",
  culture: "Theatres and schools",
  water: "The waterfront",
};

/**
 * Draws one glyph centred on (cx, cy), sized to fit inside a circle of radius
 * `r`. Stroke colour and width are the caller's - these only describe shape, so
 * the same glyph can be drawn dim for somewhere you have been and bright for
 * somewhere you have not.
 */
export function drawGlyph(
  ctx: CanvasRenderingContext2D,
  family: GlyphFamily,
  cx: number,
  cy: number,
  r: number,
): void {
  // Everything below is expressed in units of `s`, so a glyph scales with the
  // chip rather than being pinned to one size.
  const s = r * 0.62;

  ctx.beginPath();
  switch (family) {
    // A roof over a box.
    case "home":
      ctx.moveTo(cx - s, cy);
      ctx.lineTo(cx, cy - s);
      ctx.lineTo(cx + s, cy);
      ctx.moveTo(cx - s * 0.68, cy);
      ctx.lineTo(cx - s * 0.68, cy + s * 0.8);
      ctx.lineTo(cx + s * 0.68, cy + s * 0.8);
      ctx.lineTo(cx + s * 0.68, cy);
      break;

    // A glass, stem down.
    case "drink":
      ctx.moveTo(cx - s * 0.8, cy - s * 0.75);
      ctx.lineTo(cx + s * 0.8, cy - s * 0.75);
      ctx.lineTo(cx, cy + s * 0.15);
      ctx.closePath();
      ctx.moveTo(cx, cy + s * 0.15);
      ctx.lineTo(cx, cy + s * 0.85);
      ctx.moveTo(cx - s * 0.5, cy + s * 0.85);
      ctx.lineTo(cx + s * 0.5, cy + s * 0.85);
      break;

    // A block with windows.
    case "work":
      ctx.rect(cx - s * 0.78, cy - s * 0.85, s * 1.56, s * 1.7);
      ctx.moveTo(cx - s * 0.3, cy - s * 0.4);
      ctx.lineTo(cx - s * 0.3, cy - s * 0.4);
      ctx.moveTo(cx + s * 0.28, cy - s * 0.4);
      ctx.lineTo(cx + s * 0.28, cy - s * 0.4);
      ctx.moveTo(cx - s * 0.3, cy + s * 0.25);
      ctx.lineTo(cx - s * 0.3, cy + s * 0.25);
      ctx.moveTo(cx + s * 0.28, cy + s * 0.25);
      ctx.lineTo(cx + s * 0.28, cy + s * 0.25);
      break;

    // A pediment on columns.
    case "civic":
      ctx.moveTo(cx - s, cy - s * 0.35);
      ctx.lineTo(cx, cy - s * 0.95);
      ctx.lineTo(cx + s, cy - s * 0.35);
      ctx.moveTo(cx - s * 0.6, cy - s * 0.15);
      ctx.lineTo(cx - s * 0.6, cy + s * 0.7);
      ctx.moveTo(cx, cy - s * 0.15);
      ctx.lineTo(cx, cy + s * 0.7);
      ctx.moveTo(cx + s * 0.6, cy - s * 0.15);
      ctx.lineTo(cx + s * 0.6, cy + s * 0.7);
      ctx.moveTo(cx - s * 0.9, cy + s * 0.9);
      ctx.lineTo(cx + s * 0.9, cy + s * 0.9);
      break;

    // A cross with a longer foot.
    case "faith":
      ctx.moveTo(cx, cy - s);
      ctx.lineTo(cx, cy + s);
      ctx.moveTo(cx - s * 0.6, cy - s * 0.35);
      ctx.lineTo(cx + s * 0.6, cy - s * 0.35);
      break;

    // An even cross - the doctor's, not the church's.
    case "care":
      ctx.moveTo(cx, cy - s * 0.85);
      ctx.lineTo(cx, cy + s * 0.85);
      ctx.moveTo(cx - s * 0.85, cy);
      ctx.lineTo(cx + s * 0.85, cy);
      break;

    // An awning over a counter.
    case "trade":
      ctx.moveTo(cx - s * 0.9, cy - s * 0.25);
      ctx.lineTo(cx + s * 0.9, cy - s * 0.25);
      ctx.moveTo(cx - s * 0.65, cy - s * 0.25);
      ctx.lineTo(cx - s * 0.45, cy - s * 0.8);
      ctx.moveTo(cx + s * 0.65, cy - s * 0.25);
      ctx.lineTo(cx + s * 0.45, cy - s * 0.8);
      ctx.moveTo(cx - s * 0.7, cy - s * 0.05);
      ctx.lineTo(cx - s * 0.7, cy + s * 0.85);
      ctx.lineTo(cx + s * 0.7, cy + s * 0.85);
      ctx.lineTo(cx + s * 0.7, cy - s * 0.05);
      break;

    // A proscenium arch.
    case "culture":
      ctx.moveTo(cx - s * 0.85, cy + s * 0.85);
      ctx.lineTo(cx - s * 0.85, cy - s * 0.1);
      ctx.arc(cx, cy - s * 0.1, s * 0.85, Math.PI, 0);
      ctx.lineTo(cx + s * 0.85, cy + s * 0.85);
      ctx.moveTo(cx - s * 0.85, cy + s * 0.85);
      ctx.lineTo(cx + s * 0.85, cy + s * 0.85);
      break;

    // Two waves.
    case "water":
      for (const dy of [-s * 0.3, s * 0.45]) {
        ctx.moveTo(cx - s * 0.9, cy + dy);
        ctx.quadraticCurveTo(cx - s * 0.45, cy + dy - s * 0.45, cx, cy + dy);
        ctx.quadraticCurveTo(cx + s * 0.45, cy + dy + s * 0.45, cx + s * 0.9, cy + dy);
      }
      break;
  }
  ctx.stroke();
}

/** Every family, in a stable order, for the legend. */
export const LEGEND: Array<{ family: GlyphFamily; label: string; types: string }> =
  GLYPH_FAMILIES.map((family) => ({
    family,
    label: FAMILY_LABEL[family],
    types: LOCATION_TYPES.filter((t) => FAMILY_OF[t] === family).join(", "),
  }));
