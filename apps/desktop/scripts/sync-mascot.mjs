// Copies the shared mascot element (packages/mentor-mascot/mascot.js, owned by the mascot track)
// next to bubble.html, because the bubble's frontend is plain files (`frontendDist: ../src`).
// Runs as Tauri's beforeDevCommand and beforeBuildCommand, so `pnpm tauri dev`, `pnpm tauri build`
// and build-release.ps1 all ship the current version; `pnpm sync-mascot` runs it by hand.
// Writes only when the content changed. If the package is missing, the committed copy stays (and
// without any copy the bubble falls back to the "M" glyph), so this never fails a build.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "..", "..", "packages", "mentor-mascot", "mascot.js");
const target = join(here, "..", "src", "mascot.js");

if (!existsSync(source)) {
  console.warn(`sync-mascot: ${source} not found; keeping ${existsSync(target) ? "the existing copy" : "the M glyph"}`);
  process.exit(0);
}
const banner = "// Copied from packages/mentor-mascot/mascot.js by scripts/sync-mascot.mjs. Do not edit here.\n";
const next = banner + readFileSync(source, "utf8");
const current = existsSync(target) ? readFileSync(target, "utf8") : "";
if (current === next) {
  console.log("sync-mascot: src/mascot.js is up to date");
} else {
  writeFileSync(target, next);
  console.log("sync-mascot: copied packages/mentor-mascot/mascot.js -> src/mascot.js");
}
