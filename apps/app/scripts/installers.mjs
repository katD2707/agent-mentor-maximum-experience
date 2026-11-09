// Installers for trying the app, copied straight into the repo root (Mentor_<version>_...), so nobody has to dig through
// src-tauri/target/... to find them. They are gitignored: too big for the repo. Signed release builds are a separate
// pipeline (scripts/release.mjs).
//
//   VITE_API_BASE=https://<domain>/api pnpm -C apps/app installers           this OS: build, then copy
//   VITE_API_BASE=https://<domain>/api pnpm -C apps/app installers --linux   Linux .deb + .AppImage via Docker, from any OS
//   pnpm -C apps/app installers --collect-only                              copy what the last build made
//
// Windows: Mentor_<version>_x64-setup.exe. macOS (on a Mac): Mentor_<version>_universal.dmg. Linux: .deb and .AppImage.
import { copyFileSync, existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const app = fileURLToPath(new URL("..", import.meta.url));
const repo = resolve(app, "../..");
const version = JSON.parse(readFileSync(join(app, "src-tauri/tauri.conf.json"), "utf8")).version;
const os = process.platform;
const target = join(app, "src-tauri", "target");
const linuxOut = join(target, "linux-docker"); // Docker writes here first, never into the repo root itself

// pnpm is a .cmd on Windows and needs the shell; docker is an .exe and must not get one (the shell would split the
// repo path, which has spaces, into several arguments)
function run(cmd, args, cwd) {
  const r = spawnSync(cmd, args, { cwd, stdio: "inherit", shell: os === "win32" && cmd === "pnpm" });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

if (!process.argv.includes("--collect-only")) {
  const api = process.env.VITE_API_BASE;
  if (process.argv.includes("--linux")) {
    if (!api) {
      console.error("Set VITE_API_BASE (the server address compiled into the app), e.g. http://127.0.0.1:8000/api");
      process.exit(1);
    }
    run("docker", ["build", "-f", "infra/linux-app.Dockerfile", "--build-arg", `VITE_API_BASE=${api}`,
      "--output", `type=local,dest=${linuxOut}`, "."], repo);
  } else {
    if (!api) console.warn("VITE_API_BASE is not set: the app will call http://localhost:8000/api");
    const bundles = os === "win32" ? "nsis" : os === "darwin" ? "dmg" : "deb,appimage";
    run("pnpm", ["tauri", "build", "--bundles", bundles, ...(os === "darwin" ? ["--target", "universal-apple-darwin"] : [])], app);
  }
}

const dirs = [
  ...["nsis", "dmg", "deb", "appimage"].map((b) => join(target, "release", "bundle", b)),
  join(target, "universal-apple-darwin", "release", "bundle", "dmg"),
  linuxOut,
];
const KINDS = [".exe", ".dmg", ".deb", ".AppImage"];
const copied = [];
for (const dir of dirs.filter((d) => existsSync(d))) {
  for (const f of readdirSync(dir)) {
    // only this version's installers: older builds and update signatures stay where they are
    if (!f.startsWith("Mentor_") || !f.includes(`_${version}_`) || !KINDS.some((k) => f.endsWith(k))) continue;
    copyFileSync(join(dir, f), join(repo, f));
    copied.push(f);
  }
}
if (!copied.length) {
  console.error(`No ${version} installer found under ${target}. Build first (without --collect-only).`);
  process.exit(1);
}
console.log(`Installers in ${repo}:\n${copied.map((f) => "  " + f).join("\n")}`);
