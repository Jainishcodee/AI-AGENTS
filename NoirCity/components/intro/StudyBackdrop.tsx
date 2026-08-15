/**
 * The room the case files are sitting in.
 *
 * Two fixed gradients and nothing else: a lamp pool falling from the upper
 * left, and a vignette closing the corners. Both are painted once by the
 * compositor and never touched again - there is no canvas here and no frame
 * loop, because a still room does not need one and a home screen that costs
 * battery to look at is a bad trade for atmosphere.
 *
 * `pointer-events-none` throughout: this is scenery, and nothing in it should
 * ever intercept a click meant for a case file.
 */
export function StudyBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10">
      {/* The lamp. Warm, off-centre, and falling short of the far corner so the
          room has somewhere dark left in it. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 90% at 18% 0%, rgba(201,162,39,0.10) 0%, rgba(160,128,60,0.045) 26%, rgba(0,0,0,0) 62%)",
        }}
      />
      {/* A second, tighter pool so the light has a source rather than a haze. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(38% 30% at 14% -4%, rgba(232,224,207,0.07) 0%, rgba(0,0,0,0) 70%)",
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(120% 100% at 50% 45%, rgba(0,0,0,0) 35%, rgba(0,0,0,0.55) 100%)",
        }}
      />
    </div>
  );
}
