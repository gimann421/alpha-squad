// End-to-end draft rehearsal, driven in a real Chromium against the real API and the real
// current-season projections. This is the manual-draft counterpart to the unit suites: it
// exercises the things only a browser can show -- persistence through a reload, pick-number
// correction re-ordering a live board, and the recommendation moving when the board moves.
//
// Run it with both servers up:
//     make serve        # FastAPI on :8000
//     make serve-web    # Vite on :5173
//     cd web && node draft-rehearsal.mjs
//
// Committed because it has now caught four real bugs that code review did not (D78): the Draft
// view sitting on last season while current-season projections existed, a picker that froze
// after every pick, a drafted player rendering as a raw `asq_<hash>`, and a ranked pool serving
// two model versions at once. Requires `playwright` (a devDependency) and CHROMIUM_PATH below
// to point at an installed browser.

// Human-in-the-loop draft rehearsal, driven in a real Chromium against the real API and the
// real 2026 projections. Follows the 17-step gate verbatim.
import { chromium } from "playwright";

const BASE = "http://localhost:5173";
const results = [];
function check(step, ok, detail) {
  results.push({ step, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${step}${detail ? ` — ${detail}` : ""}`);
}

const CHROMIUM_PATH = process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const browser = await chromium.launch({ executablePath: CHROMIUM_PATH });
const page = await browser.newPage();
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message));

// ---------------------------------------------------------------- 1. clean manual draft
await page.goto(BASE);
await page.evaluate(() => localStorage.clear());
await page.reload();
await page.waitForTimeout(1500);
// Select the manual (non-Sleeper) league: the pick-number and my-picks tracking under test
// exists only for a league with no live Sleeper draft feed to read from.
await page.locator(".league-selector-bar select").first().selectOption("target_league");
await page.waitForTimeout(2500);
await page.getByRole("button", { name: "Draft", exact: true }).click();
await page.waitForTimeout(3000);

const heading = await page.locator("h2").first().textContent();
check("1. clean manual draft opens", heading?.includes("Draft") ?? false, `heading=${heading}`);

// season should default to the CURRENT season from /seasons/latest, not a hardcoded 2025
const seasonVal = await page.locator('label:has-text("Season") input').inputValue();
check("17a. app defaults to the current projection season", seasonVal === "2026", `season=${seasonVal}`);

// set the draft slot so snake pick numbers are derived
await page.locator('label:has-text("My draft slot") input').fill("3");
await page.waitForTimeout(400);
const snakeText = await page.locator("p.muted", { hasText: "Snake order from slot" }).first().textContent();
check(
  "extra. snake pick numbers prepared in advance",
  snakeText?.includes("#3") && snakeText?.includes("#18") && snakeText?.includes("#23"),
  snakeText?.slice(0, 120),
);

// --------------------------------------------------------- 2. enter several picks manually
async function markDrafted(name) {
  const field = page.locator('.picker-field:has-text("Mark drafted") input');
  await field.fill(name);
  await page.waitForTimeout(900);
  await page.locator(".player-picker-results li").first().click();
  await page.waitForTimeout(400);
}
async function markMine(name) {
  const field = page.locator('.picker-field:has-text("Mark my pick") input');
  await field.fill(name);
  await page.waitForTimeout(900);
  await page.locator(".player-picker-results li").first().click();
  await page.waitForTimeout(400);
}

for (const name of ["Ja'Marr Chase", "Bijan Robinson", "Trey McBride", "Puka Nacua"]) {
  await markDrafted(name);
}
const draftedRows = page.locator("ul.action-list").filter({ has: page.locator("input.pick-number") }).locator("li");
check("2. four picks entered manually", (await draftedRows.count()) === 4, `rows=${await draftedRows.count()}`);

// ------------------------------------------------------------- 3. verify pick numbers
async function pickNumbers() {
  const inputs = page.locator("input.pick-number");
  const n = await inputs.count();
  const out = [];
  for (let i = 0; i < n; i++) out.push(await inputs.nth(i).inputValue());
  return out;
}
async function draftedNames() {
  const n = await draftedRows.count();
  const out = [];
  for (let i = 0; i < n; i++) out.push((await draftedRows.nth(i).textContent())?.trim());
  return out;
}
check("3. overall pick numbers are 1..N contiguous", JSON.stringify(await pickNumbers()) === '["1","2","3","4"]', (await pickNumbers()).join(","));
const beforeCorrection = await draftedNames();

// ------------------------------------------------ 4. correct an incorrectly logged number
// Puka Nacua was logged 4th; say he was really the 2nd pick.
const puka = draftedRows.filter({ hasText: "Puka Nacua" });
await puka.locator("input.pick-number").fill("2");
await page.waitForTimeout(600);
const afterNames = await draftedNames();
check(
  "4. correcting a pick number moves the player and renumbers the rest",
  afterNames[1]?.includes("Puka Nacua") && JSON.stringify(await pickNumbers()) === '["1","2","3","4"]',
  afterNames.map((s) => s?.split("\n")[0]).join(" | "),
);
check(
  "4b. no pick was lost or duplicated by the correction",
  afterNames.length === beforeCorrection.length,
  `${beforeCorrection.length} -> ${afterNames.length}`,
);

// ------------------------------------------------------------ 6. make my own pick
await markMine("De'Von Achane");
await page.waitForTimeout(600);
const myRows = page.locator("ul.action-list").filter({ has: page.locator(".pick-number-badge") }).locator("li");
check("6. my own pick recorded", (await myRows.count()) === 1, `rows=${await myRows.count()}`);

// --------------------------------------------- 8. roster positions stay synchronized
const derived = await page.locator("p.muted", { hasText: "Roster positions used for need/fit" }).textContent();
check("8. 'Roster positions' auto-updates from the marked pick", derived?.includes("RB") ?? false, derived?.trim());

// my pick must also appear on the league-wide board with a pick number
const myPickNumber = await myRows.first().locator(".pick-number-badge").textContent();
check("3b. my picks carry their overall pick number", /^#\d+$/.test((myPickNumber ?? "").trim()), myPickNumber?.trim());

// ------------------------------------------------------------- 10. Alpha recommendation
await page.getByRole("button", { name: "Who should I take?" }).click();
await page.waitForTimeout(6000);
const rec1 = await page.locator(".card", { hasText: "Recommended pick" }).first().textContent();
const recName1 = rec1?.match(/Recommended pick:\s*([^\n]+?)\s*mark drafted/)?.[1]?.trim();
check("10. Alpha produced a recommendation", Boolean(recName1), recName1);

// 7. roster-aware/MSV state is really in play: the server echoes the roster it priced against
const priced = await page.locator("p.muted", { hasText: "Priced against roster" }).textContent();
check("7. engine priced against the roster derived from my picks", priced?.includes("RB") ?? false, priced?.trim());

// ------------------------------- 9 + 11. more picks change the board, recommendation moves
if (recName1) {
  await markDrafted(recName1);
}
await page.waitForTimeout(500);
await page.getByRole("button", { name: "Who should I take?" }).click();
await page.waitForTimeout(6000);
const rec2 = await page.locator(".card", { hasText: "Recommended pick" }).first().textContent();
const recName2 = rec2?.match(/Recommended pick:\s*([^\n]+?)\s*mark drafted/)?.[1]?.trim();
check(
  "11. recommendation changes when its own pick leaves the board",
  Boolean(recName2) && recName2 !== recName1,
  `${recName1} -> ${recName2}`,
);

// ------------------------------------------------------------------ 12. undo a pick
const countBeforeUndo = await draftedRows.count();
await draftedRows.filter({ hasText: "Trey McBride" }).locator("button", { hasText: "undo" }).click();
await page.waitForTimeout(600);
check(
  "12. undo removes the pick and renumbers",
  (await draftedRows.count()) === countBeforeUndo - 1 &&
    !(await draftedNames()).some((n) => n?.includes("Trey McBride")),
  `${countBeforeUndo} -> ${await draftedRows.count()}`,
);
const stateBeforeReload = {
  names: await draftedNames(),
  numbers: await pickNumbers(),
  slot: await page.locator('label:has-text("My draft slot") input').inputValue(),
  mine: await myRows.count(),
  derivedPositions: (await page.locator("p.muted", { hasText: "Roster positions used" }).textContent())?.trim(),
};

// -------------------------------------------------- 13-16. reload and confirm persistence
await page.reload();
await page.waitForTimeout(2000);
await page.getByRole("button", { name: "Draft", exact: true }).click();
await page.waitForTimeout(2500);

const after = {
  names: await draftedNames(),
  numbers: await pickNumbers(),
  slot: await page.locator('label:has-text("My draft slot") input').inputValue(),
  mine: await myRows.count(),
  derivedPositions: (await page.locator("p.muted", { hasText: "Roster positions used" }).textContent())?.trim(),
};

check(
  "13/14. draft state persists through a reload",
  JSON.stringify(after.names) === JSON.stringify(stateBeforeReload.names),
  `${stateBeforeReload.names.length} rows -> ${after.names.length}`,
);
check(
  "5/15. corrected pick numbers persist through a reload",
  JSON.stringify(after.numbers) === JSON.stringify(stateBeforeReload.numbers) &&
    after.names[1]?.includes("Puka Nacua"),
  after.numbers.join(","),
);
check(
  "16. roster state persists (my picks + derived positions)",
  after.mine === stateBeforeReload.mine && after.derivedPositions === stateBeforeReload.derivedPositions,
  after.derivedPositions,
);
check("15b. draft slot persists", after.slot === stateBeforeReload.slot, `slot=${after.slot}`);

// --------------------- 17. recommendation still uses the right board + current projections
await page.getByRole("button", { name: "Who should I take?" }).click();
await page.waitForTimeout(6000);
const rec3 = await page.locator(".card", { hasText: "Recommended pick" }).first().textContent();
const recName3 = rec3?.match(/Recommended pick:\s*([^\n]+?)\s*mark drafted/)?.[1]?.trim();
const stillDrafted = (await draftedNames()).some((n) => n?.includes(recName3 ?? "@@@"));
check(
  "17. post-reload recommendation excludes everyone already drafted",
  Boolean(recName3) && !stillDrafted,
  recName3,
);
const seasonAfter = await page.locator('label:has-text("Season") input').inputValue();
check("17b. still scoring the current season", seasonAfter === "2026", `season=${seasonAfter}`);

await page.screenshot({ path: process.env.SCREENSHOT_PATH ?? "draft-rehearsal.png", fullPage: true });
await browser.close();

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
if (failed.length) {
  console.log("FAILED:", failed.map((f) => f.step).join("; "));
  process.exit(1);
}
