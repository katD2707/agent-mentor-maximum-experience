// Writes the guide map of src/lib/guides.ts to the gateway (Mực's guide chat uses it as context).
// Run: pnpm run guides:export (also runs before `build`). The gateway test fails when the JSON is stale.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = readFileSync(new URL("../src/lib/guides.ts", import.meta.url), "utf8");
const body = src.split("export const GUIDES")[1].split("\nconst strip")[0];
const re = /"?([\w-]+)"?: \{\s*vi: "((?:[^"\\]|\\.)*)",\s*en: "((?:[^"\\]|\\.)*)",?\s*\}/g;
const out = {};
for (const m of body.matchAll(re)) out[m[1]] = { vi: JSON.parse(`"${m[2]}"`), en: JSON.parse(`"${m[3]}"`) };
if (!Object.keys(out).length) throw new Error("no guides found in guides.ts");
const dest = new URL("../../../services/gateway/src/mentor_gateway/ask/guide_map.json", import.meta.url);
writeFileSync(dest, JSON.stringify(out, null, 1) + "\n", "utf8");
console.log(`exported ${Object.keys(out).length} guides to ${fileURLToPath(dest)}`);
