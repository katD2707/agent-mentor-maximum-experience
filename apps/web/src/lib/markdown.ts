/** Light parsers for the workspace's markdown conventions (plan 6.1, CONTRACTS section 4). */

export function splitFrontmatter(text: string): { meta: Record<string, string>; body: string } {
  if (!text.startsWith("---")) return { meta: {}, body: text };
  const end = text.indexOf("\n---", 3);
  if (end === -1) return { meta: {}, body: text };
  const fm = text.slice(3, end).trim();
  const body = text.slice(end + 4).replace(/^\r?\n/, "");
  const meta: Record<string, string> = {};
  for (const line of fm.split(/\r?\n/)) {
    const m = line.match(/^([A-Za-z0-9_]+):\s*(.*)$/);
    if (m) meta[m[1]] = m[2].replace(/^['"]|['"]$/g, "");
  }
  return { meta, body };
}

export interface ChecklistItem {
  /** 0-based line index in the source text. */
  line: number;
  done: boolean;
  text: string;
  /** Leading YYYY-MM-DD if present. */
  date: string | null;
  section: string | null;
  /** Which checkbox on the line (0 = first); inline milestone lines hold several. */
  slot: number;
}

/**
 * All `- [ ]` / `- [x]` items, optionally only under headings matching `section`. Also reads the goal-planning
 * skill's inline form `- Mốc: [ ] 31/10 việc A · [x] 03/11 việc B` as one item per checkbox.
 */
export function parseChecklist(text: string, section?: RegExp): ChecklistItem[] {
  const items: ChecklistItem[] = [];
  let heading: string | null = null;
  text.split(/\r?\n/).forEach((l, i) => {
    const h = l.match(/^#{1,6}\s+(.*)$/);
    if (h) {
      heading = h[1].trim();
      return;
    }
    if (!/^\s*[-*]\s+/.test(l) || !/\[[ xX]\]/.test(l)) return;
    if (section && !(heading && section.test(heading))) return;
    const m = l.match(/^\s*[-*]\s+\[([ xX])\]\s+(.*)$/);
    if (m) {
      let body = m[2].trim();
      const d = body.match(/^(\d{4}-\d{2}-\d{2})\s*[—–-]?\s*/);
      if (d) body = body.slice(d[0].length);
      items.push({ line: i, done: m[1] !== " ", text: body, date: d ? d[1] : null, section: heading, slot: 0 });
      return;
    }
    let slot = 0;
    for (const c of l.matchAll(/\[([ xX])\]\s*([^·\[]*)/g)) {
      const body = c[2].trim();
      if (body) items.push({ line: i, done: c[1] !== " ", text: body, date: null, section: heading, slot });
      slot++;
    }
  });
  return items;
}

/** Toggle the `slot`-th checkbox on a given line. */
export function toggleChecklistLine(text: string, line: number, done: boolean, slot = 0): string {
  const lines = text.split("\n");
  let n = 0;
  lines[line] = lines[line].replace(/\[([ xX])\]/g, (box) => (n++ === slot ? (done ? "[x]" : "[ ]") : box));
  return lines.join("\n");
}

export interface MemoryItem {
  line: number;
  text: string;
  section: string | null;
  inferred: boolean;
}

/** Bullet items of a me/ file, each one forgettable on its own ("quên mục này"). */
export function parseMemoryItems(text: string): MemoryItem[] {
  const items: MemoryItem[] = [];
  let heading: string | null = null;
  text.split(/\r?\n/).forEach((l, i) => {
    const h = l.match(/^#{1,6}\s+(.*)$/);
    if (h) {
      heading = h[1].trim();
      return;
    }
    const m = l.match(/^\s*[-*]\s+(.*)$/);
    if (m) items.push({ line: i, text: m[1].trim(), section: heading, inferred: /^\[suy luận\]/i.test(m[1].trim()) });
  });
  return items;
}

export function removeLine(text: string, line: number): string {
  const lines = text.split("\n");
  lines.splice(line, 1);
  return lines.join("\n");
}

/** Replace the text of a bullet line, keeping its indent and marker. */
export function replaceBulletText(text: string, line: number, newText: string): string {
  const lines = text.split("\n");
  lines[line] = lines[line].replace(/^(\s*[-*]\s+).*$/, (_, lead: string) => lead + newText.replace(/\s*\n\s*/g, " ").trim());
  return lines.join("\n");
}
