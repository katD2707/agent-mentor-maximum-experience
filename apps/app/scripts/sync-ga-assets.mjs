// Copies the Làng gà art from mockups/assets/ga into public/ga (same relative layout), so a re-run refreshes it when the
// village painting is regenerated. layout.js becomes layout.json. Usage: node scripts/sync-ga-assets.mjs
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "../../../mockups/assets/ga");
const DEST = join(here, "../public/ga");
if (!existsSync(SRC)) {
  console.error("source not found: " + SRC);
  process.exit(1);
}

const copy = (rel, destRel = rel) => {
  const to = join(DEST, destRel);
  mkdirSync(dirname(to), { recursive: true });
  cpSync(join(SRC, rel), to);
};
const list = (dir) => (existsSync(join(SRC, dir)) ? readdirSync(join(SRC, dir)) : []);

let n = 0;
const take = (rel, destRel) => {
  if (!existsSync(join(SRC, rel))) return;
  copy(rel, destRel);
  n++;
};

// the village: painted tiles, cut-outs, layout and walking sprites
rmSync(join(DEST, "lang"), { recursive: true, force: true });
for (const f of list("lang")) if (/^bg_\d+_\d+\.webp$/.test(f)) take(`lang/${f}`);
for (const f of list("lang/occ")) if (f.endsWith(".webp")) take(`lang/occ/${f}`);
for (const f of list("lang/actors")) if (f.endsWith(".webp") || f === "actors.json") take(`lang/actors/${f}`);
const layoutJs = readFileSync(join(SRC, "lang/layout.js"), "utf8");
const json = layoutJs.replace(/^[^=]*=\s*/, "").replace(/;\s*$/, "");
JSON.parse(json); // fail loudly if the format changes
mkdirSync(join(DEST, "lang"), { recursive: true });
writeFileSync(join(DEST, "lang/layout.json"), json);
n++;

// chickens: <art>.png (grown), <art>-1.png (chick), <art>-2.png (young); <name>-nhay.webp (jump) and <name>-dung.webp (stand, animated)
// for any of those names. The app reads src/lang/gaFiles.json (written below) to know which of them exist, so a chicken without
// its own chick or young drawing falls back to the grown one.
const arts = new Set();
for (const f of list("")) {
  const m = /^([a-z]+)(?:-([12]))?\.png$/.exec(f);
  if (m && !/^(hs|icon|lang)/.test(m[1])) arts.add(m[1]);
}
const manifest = { still: [], dung: [], nhay: [] };
for (const f of list("")) {
  const png = /^(([a-z]+)(?:-[12])?)\.png$/.exec(f);
  if (png && arts.has(png[2])) {
    take(f);
    manifest.still.push(png[1]);
  }
  const web = /^(([a-z]+)(?:-[12])?)-(nhay|dung)\.webp$/.exec(f);
  if (web && arts.has(web[2])) {
    take(f);
    manifest[web[3]].push(web[1]);
  }
}
for (const k of Object.keys(manifest)) manifest[k].sort();
writeFileSync(join(here, "../src/lang/gaFiles.json"), JSON.stringify(manifest) + String.fromCharCode(10));
// the student, the market icon, the login backdrop
for (const f of ["hs-nam.png", "hs-nu.png", "hs-nam.webp", "hs-nu.webp", "cho-icon.webp", "lang.webp", "icon-ga.png"]) take(f);

console.log(`copied ${n} files to ${DEST}`);
