// Pure helpers for scripts/release.mjs (no file or process access, so they can be unit-tested).

export const CHANNELS = ["stable", "beta"];
const SEMVER = /^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/;
const SECRET_QUERY_KEYS = ["token", "access_token", "key", "apikey", "api_key", "secret", "password", "auth"];

export const isSemver = (v) => SEMVER.test(v);

/** "0.1.0" + patch/minor/major, or an explicit version. */
export function nextVersion(current, spec) {
  if (isSemver(spec)) return spec;
  const [maj, min, pat] = current.split("-")[0].split(".").map(Number);
  if (spec === "major") return `${maj + 1}.0.0`;
  if (spec === "minor") return `${maj}.${min + 1}.0`;
  if (spec === "patch") return `${maj}.${min}.${pat + 1}`;
  throw new Error(`version must be x.y.z, patch, minor or major (got "${spec}")`);
}

/** The feed: https, no credentials. Plain http to loopback only with allowDevHttp (local update test). */
export function checkUrl(raw, { allowDevHttp = false } = {}) {
  const u = new URL(raw);
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(u.hostname);
  if (u.protocol !== "https:" && !(allowDevHttp && u.protocol === "http:" && loopback)) throw new Error(`url must be https: ${u.origin}`);
  if (u.username || u.password) throw new Error("url must not carry credentials");
  for (const k of u.searchParams.keys()) if (SECRET_QUERY_KEYS.includes(k.toLowerCase())) throw new Error("url must not carry credentials");
  return u;
}

export const feedUrl = (base, channel, ...rest) => [base.replace(/\/+$/, ""), channel, ...rest].join("/");

/** Adds one platform's bundle to the channel manifest (a same-version manifest keeps the other platforms). */
export function addPlatform(existing, { version, notes, platform, url, signature, sha256, pubDate }) {
  const keep = existing && existing.version === version ? existing.platforms : {};
  return { version, notes, pub_date: pubDate, platforms: { ...keep, [platform]: { signature, url, sha256 } } };
}

/** Throws unless the manifest is one the app would accept: semver, https urls without credentials, signature and sha256 pin. */
export function validateManifest(m, opts = {}) {
  if (!m || !isSemver(m.version)) throw new Error("manifest version is not semver");
  const entries = Object.entries(m.platforms ?? {});
  if (!entries.length) throw new Error("manifest has no platforms");
  for (const [name, e] of entries) {
    checkUrl(e.url, opts);
    if (!e.signature) throw new Error(`${name}: no signature`);
    if (!/^[0-9a-f]{64}$/.test(e.sha256 ?? "")) throw new Error(`${name}: sha256 must be 64 lowercase hex characters`);
  }
  return m;
}

/** Which bundle each OS ships, as the updater's platform key and a file pattern in the bundle folder. */
export function platformBundle(os, arch, version) {
  if (os === "win32") return { key: `windows-${arch === "arm64" ? "aarch64" : "x86_64"}`, targets: ["nsis"], dir: "nsis", pattern: new RegExp(`^Mentor_${version}_(x64|arm64)-setup\.exe$`) };
  if (os === "darwin") return { key: `darwin-${arch === "arm64" ? "aarch64" : "x86_64"}`, targets: ["app", "dmg"], dir: "macos", pattern: /^Mentor\.app\.tar\.gz$/ };
  if (os === "linux") return { key: `linux-${arch === "arm64" ? "aarch64" : "x86_64"}`, targets: ["appimage"], dir: "appimage", pattern: new RegExp(`^Mentor_${version}_.*\.AppImage$`) };
  throw new Error(`unsupported platform ${os}`);
}
