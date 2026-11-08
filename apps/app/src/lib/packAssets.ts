import type { AssetRef, CoursePack } from "../api/course";

/** Every asset a pack references, deduplicated by path (mirror of CoursePack.assets() in mentor_schemas). */
export function packAssets(pack: CoursePack): AssetRef[] {
  const out = new Map<string, AssetRef>();
  const add = (...rs: (AssetRef | null | undefined)[]) => rs.forEach((r) => r && !out.has(r.path) && out.set(r.path, r));
  for (const ch of pack.chapters)
    for (const ls of ch.lessons)
      for (const b of ls.blocks) {
        if (b.kind === "text" || b.kind === "callout") add(b.audio);
        else if (b.kind === "image") add(b.image, b.audio);
        else if (b.kind === "video") add(b.video, b.poster, b.captions);
        else if (b.kind === "audio") add(b.audio);
        else if (b.kind === "quiz")
          for (const q of b.items) {
            add(q.stem_audio, q.stem_image, q.tap?.image);
            for (const o of q.options) add(o.image, o.audio);
          }
      }
  return [...out.values()];
}
