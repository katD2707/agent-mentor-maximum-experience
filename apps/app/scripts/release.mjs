// App release (desktop bundles + web build + channel manifest). Separate from publishing courses: a course never
// needs this (see RELEASING.md).
//
//   node scripts/release.mjs --bump patch|minor|major | --version x.y.z   (omit both to rebuild the current version)
//        --channel stable|beta --base-url https://updates.example.org/app [--out release-out]
//        [--pubkey-file path] [--dev-feed] [--no-bump-files]
//
// Needs TAURI_SIGNING_PRIVATE_KEY (the key file path or its content) and TAURI_SIGNING_PRIVATE_KEY_PASSWORD in the environment (never on the
// command line). Run it on each OS to add that platform to the same latest.json.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync, copyFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { addPlatform, CHANNELS, checkUrl, feedUrl, nextVersion, platformBundle, validateManifest } from "./release-lib.mjs";

const app = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const tauriDir = join(app, "src-tauri");
const { values: a } = parseArgs({
  options: { bump: { type: "string" }, version: { type: "string" }, channel: { type: "string", default: "stable" }, "base-url": { type: "string" }, out: { type: "string", default: "release-out" }, "pubkey-file": { type: "string" }, "dev-feed": { type: "boolean", default: false }, notes: { type: "string", default: "" } },
});
const die = (m) => {
  console.error(`release: ${m}`);
  process.exit(1);
};

if (!CHANNELS.includes(a.channel)) die(`channel must be one of ${CHANNELS.join(", ")}`);
if (!a["base-url"]) die("--base-url is required (the https folder that will hold <channel>/latest.json)");
if (!process.env.TAURI_SIGNING_PRIVATE_KEY || !process.env.TAURI_SIGNING_PRIVATE_KEY_PASSWORD) die("set TAURI_SIGNING_PRIVATE_KEY and TAURI_SIGNING_PRIVATE_KEY_PASSWORD");
try {
  checkUrl(a["base-url"], { allowDevHttp: a["dev-feed"] });
} catch (e) {
  die(e.message);
}

const pkgFile = join(app, "package.json");
const confFile = join(tauriDir, "tauri.conf.json");
const cargoFile = join(tauriDir, "Cargo.toml");
const current = JSON.parse(readFileSync(pkgFile, "utf8")).version;
const version = a.bump || a.version ? nextVersion(current, a.bump ?? a.version) : current;

// 1. the version lives in three files; keep them equal
if (version !== current) {
  const pkg = readFileSync(pkgFile, "utf8").replace(/("version":\s*")[^"]+/, `$1${version}`);
  writeFileSync(pkgFile, pkg);
  const conf = readFileSync(confFile, "utf8").replace(/("version":\s*")[^"]+/, `$1${version}`);
  writeFileSync(confFile, conf);
  const cargo = readFileSync(cargoFile, "utf8").replace(/^version = ".*"$/m, `version = "${version}"`);
  writeFileSync(cargoFile, cargo);
  console.log(`release: version ${current} -> ${version}`);
}

// 2. build: signed desktop bundle (this also builds the web bundle into dist/)
const bundle = platformBundle(process.platform, process.arch, version);
const updater = { endpoints: [feedUrl(a["base-url"], a.channel, "latest.json")], ...(a["dev-feed"] ? { dangerousInsecureTransportProtocol: true } : {}) };
if (a["pubkey-file"]) updater.pubkey = readFileSync(a["pubkey-file"], "utf8").trim();
const scratch = mkdtempSync(join(tmpdir(), "mentor-release-"));
const override = join(scratch, "tauri.release.conf.json");
writeFileSync(override, JSON.stringify({ bundle: { createUpdaterArtifacts: true, targets: bundle.targets }, plugins: { updater } }));
const args = ["tauri", "build", "--config", override, ...(a["dev-feed"] ? ["--features", "insecure-dev-feed"] : [])];
const built = spawnSync("pnpm", args, { cwd: app, stdio: "inherit", shell: true });
rmSync(scratch, { recursive: true, force: true });
if (built.status !== 0) die("tauri build failed");

// 3. collect, hash and describe
const out = resolve(app, a.out);
const dir = join(tauriDir, "target", "release", "bundle", bundle.dir);
const file = readdirSync(dir).find((f) => bundle.pattern.test(f));
if (!file || !existsSync(join(dir, `${file}.sig`))) die(`no signed bundle found in ${dir}`);
const dest = join(out, a.channel, version);
mkdirSync(dest, { recursive: true });
copyFileSync(join(dir, file), join(dest, file));
const sha256 = createHash("sha256").update(readFileSync(join(dir, file))).digest("hex");
const manifestFile = join(out, a.channel, "latest.json");
const existing = existsSync(manifestFile) ? JSON.parse(readFileSync(manifestFile, "utf8")) : null;
const manifest = validateManifest(
  addPlatform(existing, { version, notes: a.notes, platform: bundle.key, url: feedUrl(a["base-url"], a.channel, version, encodeURIComponent(file)), signature: readFileSync(join(dir, `${file}.sig`), "utf8").trim(), sha256, pubDate: new Date().toISOString() }),
  { allowDevHttp: a["dev-feed"] },
);
writeFileSync(manifestFile, JSON.stringify(manifest, null, 2) + "\n");

// 4. the web build, ready for any static host (the service worker inside tells browsers about the new build)
cpSync(join(app, "dist"), join(out, "web"), { recursive: true });
console.log(`release: ${a.channel} ${version} (${bundle.key}) -> ${out}\n  sha256 ${sha256}`);
