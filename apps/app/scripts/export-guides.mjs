// Writes the chicken guide texts (src/lang/guide/data.ts) to the gateway, where the /guide app-help chat reads them as context.
// Run: pnpm run guides:export (also runs before `build`). The gateway test fails when the JSON is stale.
// Keys: "app" (overview), then "<screen>.<slug of title>" per part, or the data-guide name for parts marked `[data-guide="x"]`.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = readFileSync(new URL("../src/lang/guide/data.ts", import.meta.url), "utf8");
const body = src.split("export const GUIDE_DEFS")[1].split("\nexport const HELLO")[0];
const S = String.raw`"((?:[^"\\]|\\.)*)"`;
const re = new RegExp(`G\\(\\s*${[S, S, S, S, S].join(",\\s*")}(?:,\\s*${S})?\\s*\\)`, "g");
const slug = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const out = {
  app: {
    vi: "Mentor là một làng gà: mỗi môn là một chú gà (Gà Toán, Gà Văn...). Bấm gà để vào chuồng xem khóa và bài học; ở làng có đấu trường đề thi, phòng tự học, tiến độ và thư viện. Việc khác, nhắn ở khung trò chuyện.",
    en: "Mentor is a chicken village: each subject is a chicken (Math chicken, Literature chicken...). Tap a chicken to enter its coop for courses and lessons; the village also has the exam arena, study room, progress and library. For anything else, use the chat box.",
  },
};
const un = (s) => JSON.parse(`"${s}"`);
for (const m of body.matchAll(re)) {
  const [, sel, vt, vd, et, ed, page] = m;
  const dg = sel.match(/data-guide=\\"([\w-]+)\\"/);
  const key = dg ? dg[1] : `${page ? un(page) : "app"}.${slug(un(et))}`;
  out[key] = { vi: `${un(vt)}: ${un(vd)}`, en: `${un(et)}: ${un(ed)}` };
}
if (Object.keys(out).length < 30) throw new Error("no guides found in lang/guide/data.ts");
const dest = new URL("../../../services/gateway/src/mentor_gateway/ask/guide_map.json", import.meta.url);
writeFileSync(dest, JSON.stringify(out, null, 1) + "\n", "utf8");
console.log(`exported ${Object.keys(out).length} guides to ${fileURLToPath(dest)}`);
