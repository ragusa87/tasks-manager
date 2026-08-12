#!/usr/bin/env node
/**
 * Capture the screenshots referenced by README.md.
 *
 * It logs in through the app's login form, then visits each documented page and
 * writes a PNG into docs/img/. Re-run it whenever the UI changes.
 *
 * It captures whatever data the instance already has — it does NOT seed or reset the
 * database. Use `just capture-docs`, which resets and seeds demo data first
 * (`just fixturize --clear`) and then runs this script.
 *
 * Usage:
 *   node scripts/capture_docs_screenshots.mjs [BASE_URL]
 *
 * Configuration (env vars, with sensible fallbacks):
 *   BASE_URL     base URL of a running instance   (default https://tasks.docker.test)
 *   DOCS_USER    login username                   (default user1, the fixturize demo user)
 *   DOCS_PASS    login password                   (default "password")
 *
 * Requires Playwright (auto-provisioned via npx, or a system Chromium). Runs on the host.
 */

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { mkdirSync, existsSync } from "node:fs";
import { execSync } from "node:child_process";

// Resolve Playwright: a normal install, an explicit PLAYWRIGHT_MODULE override, or —
// when it isn't installed at all — provision it on the fly through the `npx` cache.
const require = createRequire(import.meta.url);
function resolvePlaywright() {
  // 1. project / global install
  try {
    return require("playwright");
  } catch {}
  // 2. explicit override (e.g. a path into the npx cache)
  if (process.env.PLAYWRIGHT_MODULE) return require(process.env.PLAYWRIGHT_MODULE);
  // 3. let npx fetch playwright into its cache, then resolve it from there. npx prepends
  //    its cache's .bin to PATH, so we derive the sibling node_modules dir from that.
  try {
    const nodeModules = execSync(
      `npx --yes --package=playwright node -p "process.env.PATH.split(':').find(p => p.endsWith('/.bin') && p.includes('_npx')).slice(0, -5)"`,
      { encoding: "utf8" },
    ).trim();
    return require(join(nodeModules, "playwright"));
  } catch {
    console.error("Playwright not found and could not be provisioned via npx.");
    console.error("Install it (`npm i -D playwright`) or set PLAYWRIGHT_MODULE to an install.");
    process.exit(1);
  }
}
const { chromium } = resolvePlaywright();

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..");
const outDir = join(repoRoot, "docs", "img");

const BASE_URL = (process.argv[2] || process.env.BASE_URL || "https://tasks.docker.test").replace(/\/$/, "");
// Mirror the fixturize demo user (task_processor/management/commands/fixturize.py).
const USER = process.env.DOCS_USER || "user1";
const PASS = process.env.DOCS_PASS || "password";

// Pages to capture. `fullPage` defaults to false (viewport only) — the dashboard
// lists dozens of demo items, a full-page shot would be mostly repeated rows.
// `viewport` overrides the default desktop size (the offload page is a
// mobile-first capture form, shoot it phone-sized). Everything is captured in
// dark theme except the shots that set `theme: "light"`.
const shots = [
  { name: "dashboard", path: "/" },
  { name: "dashboard_light", path: "/", theme: "light" },
  { name: "offload", path: "/item/offload/", viewport: { width: 420, height: 800 } },
  { name: "nirvana_import", path: "/settings/nirvana-import/" },
];

const DEFAULT_VIEWPORT = { width: 1440, height: 900 };

// Fake mic (a generated tone) so the voice-recording shots work headless
// without a real audio device or a permission prompt.
const LAUNCH_ARGS = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"];

async function launchBrowser() {
  try {
    return await chromium.launch({ args: LAUNCH_ARGS });
  } catch (e) {
    // Fall back to a system Chromium if Playwright's bundled browser is absent.
    for (const p of ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]) {
      if (existsSync(p)) return await chromium.launch({ executablePath: p, args: LAUNCH_ARGS });
    }
    throw e;
  }
}

// The fixture item that carries the sample documents (see the fixturize
// management command) — the modal screenshots open this one.
const DOC_ITEM_TITLE = "Prepare quarterly review meeting";

async function login(page) {
  await page.goto(`${BASE_URL}/login/`, { waitUntil: "domcontentloaded" });
  await page.fill('input[name="username"]', USER);
  await page.fill('input[name="password"]', PASS);
  await Promise.all([
    page.waitForLoadState("networkidle"),
    page.click('button[type="submit"]'),
  ]);
}

// The theme override is a plain cookie read server-side (core/views.py).
async function setTheme(context, value) {
  await context.addCookies([{ name: "theme", value, url: BASE_URL }]);
}

async function capture(page, { name, path, fullPage = false, viewport = null, theme = "dark" }) {
  const url = `${BASE_URL}${path}`;
  await setTheme(page.context(), theme);
  await page.setViewportSize(viewport || DEFAULT_VIEWPORT);
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForTimeout(800); // let charts / htmx settle
  await shoot(page, name, url, fullPage);
  if (viewport) await page.setViewportSize(DEFAULT_VIEWPORT);
  if (theme !== "dark") await setTheme(page.context(), "dark");
}

async function shoot(page, name, label, fullPage = false) {
  // Hide the Django Debug Toolbar handle, present on dev instances.
  await page.addStyleTag({ content: "#djDebugRoot { display: none !important; }" });
  const file = join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage });
  console.log(`✓ ${name.padEnd(16)} ${label}`);
}

async function main() {
  mkdirSync(outDir, { recursive: true });
  const browser = await launchBrowser();
  const context = await browser.newContext({
    viewport: DEFAULT_VIEWPORT,
    ignoreHTTPSErrors: true, // local stack uses a self-signed *.docker.test cert
  });
  await context.grantPermissions(["microphone"], { origin: BASE_URL });
  const page = await context.newPage();

  await setTheme(context, "dark");
  await login(page);

  for (const shot of shots) {
    await capture(page, shot);
  }

  // The item detail is a modal: open the fixture item that carries the sample
  // documents (falling back to the first row) and capture it.
  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle" });
  let opener = page
    .locator("[data-item]", { hasText: DOC_ITEM_TITLE })
    .locator("[data-detail-url]")
    .first();
  if (!(await opener.count())) {
    console.warn(`! "${DOC_ITEM_TITLE}" not on the dashboard — using the first item.`);
    opener = page.locator("[data-detail-url]").first();
  }
  if (await opener.count()) {
    // The button is an empty element whose ::after covers the row, so Playwright
    // deems it invisible — dispatch the click instead of a trusted click.
    await opener.dispatchEvent("click");
    await page.waitForSelector("#modal", { state: "visible" });
    await page.waitForTimeout(500);
    await shoot(page, "item_detail", `${BASE_URL}/ (item modal)`);

    // Documents section of the same modal: the fixture documents, then the
    // voice recorder mid-recording (never stopped, so nothing is uploaded).
    await page.locator("#modal .accordion-header", { hasText: "Documents" }).click();
    const recordBtn = page.locator("#modal .audio-record-btn");
    await recordBtn.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300); // accordion expand animation
    await shoot(page, "item_documents", `${BASE_URL}/ (item modal, documents)`);
    await recordBtn.click();
    await page.waitForTimeout(2000); // let the level meter and timer run
    await shoot(page, "item_recording", `${BASE_URL}/ (item modal, recording)`);
  } else {
    console.warn("! item_detail skipped — no item found on the dashboard.");
  }

  // Batch actions: enter batch mode on the dashboard, tick the whole page to
  // reveal the selection bar, then open one action's preview modal.
  await page.setViewportSize(DEFAULT_VIEWPORT);
  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle" });
  const batchToggle = page.locator("#batch-toggle");
  if (await batchToggle.count()) {
    await batchToggle.click();
    await page.locator("#batch-select-page").check();
    await page.waitForTimeout(300); // let the bar enable its action buttons
    await shoot(page, "batch_bar", `${BASE_URL}/ (batch mode, page selected)`);

    const actionBtn = page.locator(".batch-action-btn:not([disabled])").first();
    if (await actionBtn.count()) {
      await actionBtn.click();
      await page.waitForSelector("#modal", { state: "visible" });
      await page.waitForTimeout(500);
      await shoot(page, "batch_action", `${BASE_URL}/ (batch action preview)`);
      await page.keyboard.press("Escape").catch(() => {});
    } else {
      console.warn("! batch_action skipped — no enabled batch action button.");
    }
  } else {
    console.warn("! batch shots skipped — batch toggle not on the dashboard.");
  }

  // Offload page, voice tab, mid-recording (phone-sized like the offload shot).
  await page.setViewportSize({ width: 420, height: 800 });
  await page.goto(`${BASE_URL}/item/offload/`, { waitUntil: "networkidle" });
  await page.click("#tab-voice");
  await page.click("#recBtn");
  await page.waitForTimeout(2000); // let the scope and clock run
  await shoot(page, "offload_voice", `${BASE_URL}/item/offload/ (voice tab, recording)`);
  await page.setViewportSize(DEFAULT_VIEWPORT);

  await browser.close();
  console.log(`\nDone. PNGs written to ${outDir}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
