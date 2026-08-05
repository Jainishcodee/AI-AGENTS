/**
 * The bits of a playthrough that more than one suite needs.
 *
 * These lived copy-pasted in each script, and the copies drifted: a change to
 * how you travel broke two suites separately, and the second one only surfaced
 * after the first was fixed. One definition, one place to update.
 */

/**
 * Travels to an address the way a player does: bring it on screen, click the
 * pin, open the card it puts up, drive over.
 *
 * The pan is not the test cheating. The map opens on the team's own doorstep
 * rather than on the whole city, so an address across the river is genuinely
 * off screen - a player drags or pinches to it first, and a test clicking blind
 * coordinates would be exercising something nobody can actually do.
 */
export async function travelTo(page, locationId) {
  const pt = await page.evaluate(async (id) => {
    const city = await fetch("/city.json").then((r) => r.json());
    const loc = city.locations.find((l) => l.id === id);
    const map = window.__cityMap;
    if (!loc || !map) return null;
    map.setView([loc.y, loc.x], map.getZoom(), { animate: false });
    const p = map.latLngToContainerPoint({ lat: loc.y, lng: loc.x });
    const rect = map.getContainer().getBoundingClientRect();
    return { x: rect.left + p.x, y: rect.top + p.y };
  }, locationId);
  if (!pt) throw new Error(`could not locate ${locationId} on screen`);

  await page.mouse.click(pt.x, pt.y);

  // Clicking a pin puts up a card with the place's picture and its name. The
  // card opens the full entry, and the drive happens from there.
  const card = page.getByTestId("place-card");
  await card.waitFor({ timeout: 10000 });
  await card.getByRole("button").last().click();
  await page.getByRole("button", { name: /DRIVE OVER/ }).click();
  await page.waitForTimeout(500);
}

/**
 * Files a complete, correct accusation for the tutorial case.
 *
 * Written out rather than picked from a list, because that is now the only way
 * to file one. Kept here so the wording is identical everywhere it is used - if
 * the grader ever stops accepting this, every suite that closes a case says so
 * at once rather than one of them quietly scoring lower.
 */
export const QUIET_ROOM_CASE =
  "Vane had been charging her for consultations she never had. Her own account books show she went back years and totalled the money - that ledger is why she died. The digitalis was in the tea cup before the lamp went out, so the dark and the seance are beside the point, and the dose was several times what any doctor would write. He wrote her a prescription three days beforehand for a bottle she never asked for, so her medicine cabinet would explain the overdose.";

export async function accuse(page, name, argument) {
  await page.getByRole("button", { name: /^ACCUSE/ }).click();
  await page.waitForTimeout(300);
  await page.getByPlaceholder("A name").fill(name);
  await page
    .getByPlaceholder("What happened, why, and what proves it.")
    .fill(argument);
  await page.getByRole("button", { name: "FILE THE ACCUSATION" }).click();
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: "GO AHEAD" }).click();
  await page.waitForTimeout(1000);
}
