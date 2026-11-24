// Copies the Làng gà art from mockups/assets/ga into public/ga (same relative layout), so a re-run refreshes it when the
// village painting is regenerated. layout.js becomes layout.json. Usage: node scripts/sync-ga-assets.mjs
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, "../../../mockups/assets/ga");
const DEST = join(here, "../public/ga");
if (!existsSync(SRC)) {
  console.error("source not found: " + SRC);
  process.exit(1);
}
// the chickens are regenerated from scratch: drop every old chicken picture first (the student, icons and the village are re-copied below)
rmSync(DEST, { recursive: true, force: true });

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
// only the student's sheets (nam, nu): the chickens are costume pictures now
for (const f of list("lang/actors")) if (/^(nam|nu)-.*\.webp$/.test(f)) take(`lang/actors/${f}`);
const act = JSON.parse(readFileSync(join(SRC, "lang/actors/actors.json"), "utf8"));
for (const k of Object.keys(act.actors ?? {})) if (!/^(nam|nu)$/.test(k)) delete act.actors[k];
mkdirSync(join(DEST, "lang/actors"), { recursive: true });
writeFileSync(join(DEST, "lang/actors/actors.json"), JSON.stringify(act));
n++;
const layoutJs = readFileSync(join(SRC, "lang/layout.js"), "utf8");
const json = layoutJs.replace(/^[^=]*=\s*/, "").replace(/;\s*$/, "");
JSON.parse(json); // fail loudly if the format changes
mkdirSync(join(DEST, "lang"), { recursive: true });
writeFileSync(join(DEST, "lang/layout.json"), json);
n++;

// chickens: the costume pictures, assets/ga/trang-phuc/<id>-1.png (chick), <id>-2.png (young), <id>.png (grown, stage 3), <id>-4.png
// (master, with the halo) and <id>-gian.png (angry, drawn grown). They are converted to WebP (quality 90, alpha kept) as <id>.webp,
// <id>-1.webp ... The animated ones (<name>-dung.webp stand, <name>-nhay.webp jump, today only Gà Toán) are copied as they are.
// src/lang/gaFiles.json lists what exists, so the app never points at a missing file and falls back to a still with a CSS bob.
// The older per-subject drawings (assets/ga/<id>.png ...) and the old walking sheets of toan / van / anh are not copied any more.
const COS = join(SRC, "trang-phuc");
const STILL = /^([a-z]+)(-1|-2|-4|-gian)?\.png$/;
const ANIM = /^(([a-z]+)(?:-1|-2|-4|-gian)?)-(nhay|dung)\.webp$/;
const manifest = { still: [], dung: [], nhay: [] };
const jobs = [];
for (const f of existsSync(COS) ? readdirSync(COS) : []) {
  const m = STILL.exec(f);
  if (m && m[1] !== "ss") {
    jobs.push([join(COS, f), join(DEST, f.replace(/\.png$/, ".webp"))]);
    manifest.still.push(f.replace(/\.png$/, ""));
    continue;
  }
  const a = ANIM.exec(f);
  if (a && a[2] !== "ss") {
    mkdirSync(DEST, { recursive: true });
    cpSync(join(COS, f), join(DEST, f));
    manifest[a[3]].push(a[1]);
    n++;
  }
}
if (jobs.length) {
  mkdirSync(DEST, { recursive: true });
  const py = ["import sys", "from PIL import Image", "for i in range(1, len(sys.argv), 2):", "    Image.open(sys.argv[i]).save(sys.argv[i + 1], 'WEBP', quality=90, method=4)"].join(String.fromCharCode(10));
  for (let i = 0; i < jobs.length; i += 40) {
    const r = spawnSync("python", ["-c", py, ...jobs.slice(i, i + 40).flat()], { stdio: "inherit" });
    if (r.status !== 0) {
      console.error("PNG to WebP failed (needs python with Pillow)");
      process.exit(1);
    }
  }
  n += jobs.length;
}
for (const k of Object.keys(manifest)) manifest[k].sort();
writeFileSync(join(here, "../src/lang/gaFiles.json"), JSON.stringify(manifest) + String.fromCharCode(10));
// the student, the market icon, the login backdrop
for (const f of ["hs-nam.png", "hs-nu.png", "hs-nam.webp", "hs-nu.webp", "cho-icon.webp", "lang.webp", "icon-ga.png"]) take(f);

console.log(`copied ${n} files to ${DEST}`);
