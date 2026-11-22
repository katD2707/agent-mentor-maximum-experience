import type { ReactElement } from "react";

/**
 * The three bosses of the Arena (original art from mockups/lg-05): one per subject family, each with four faces (calm, hit,
 * grin, knocked out) switched by the stage's `data-fx`. Static, trusted markup of this file, so it is set as inner HTML.
 */
const face = (cx: number, cy: number, s: number): string => {
    const T = `translate(${cx} ${cy}) scale(${s})`;
    const eyes = `<ellipse cx="-24" cy="-4" rx="15" ry="18" fill="#fff" stroke="#1d1530" stroke-width="3"/><ellipse cx="24" cy="-4" rx="15" ry="18" fill="#fff" stroke="#1d1530" stroke-width="3"/>`;
    return `
    <g class="ar-face-n" transform="${T}">${eyes}<circle cx="-20" cy="0" r="7" fill="#1d1530"/><circle cx="20" cy="0" r="7" fill="#1d1530"/>
      <path d="M-42 -30 L-10 -18 M42 -30 L10 -18" stroke="#1d1530" stroke-width="6" stroke-linecap="round"/>
      <path d="M-20 30 L-10 20 L0 30 L10 20 L20 30" fill="none" stroke="#1d1530" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></g>
    <g class="ar-face-hit" transform="${T}"><path d="M-40 -16 L-14 -4 L-40 8 M40 -16 L14 -4 L40 8" fill="none" stroke="#1d1530" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
      <ellipse cx="0" cy="28" rx="13" ry="10" fill="#1d1530"/><ellipse cx="0" cy="32" rx="7" ry="4" fill="#ff7d7d"/>
      <path d="M52 -26 q8 12 0 18 q-8 -6 0 -18z" fill="#7fd0ff" stroke="#1d1530" stroke-width="2"/></g>
    <g class="ar-face-win" transform="${T}">${eyes}<circle cx="-26" cy="4" r="7" fill="#1d1530"/><circle cx="22" cy="4" r="7" fill="#1d1530"/>
      <path d="M-44 -22 L-10 -8 M44 -22 L10 -8" stroke="#1d1530" stroke-width="6" stroke-linecap="round"/>
      <path d="M-28 18 Q0 54 28 18Z" fill="#1d1530" stroke="#1d1530" stroke-width="3" stroke-linejoin="round"/><path d="M-18 21h36" stroke="#fff" stroke-width="6"/></g>
    <g class="ar-face-ko" transform="${T}"><path d="M-38 -16 l22 22 M-16 -16 l-22 22 M16 -16 l22 22 M38 -16 l-22 22" stroke="#1d1530" stroke-width="6" stroke-linecap="round"/>
      <path d="M-14 28 H14" stroke="#1d1530" stroke-width="5" stroke-linecap="round"/><path d="M0 28 v12 a6 6 0 0 0 12 0 v-12z" fill="#ff7d7d" stroke="#1d1530" stroke-width="3"/>
      <path d="M-20 -50 l4 9 9 1 -7 6 2 9 -8 -5 -8 5 2 -9 -7 -6 9 -1z" fill="#ffcf3d" transform="translate(6 -14) scale(.7)"/></g>`;
};
const BOSSES: Record<string, (c: string) => string> = {
    toan: (c) => `<svg viewBox="0 0 200 200" aria-hidden="true">
      <path d="M72 38 L60 8 M128 38 L142 8" stroke="#2f2160" stroke-width="6" stroke-linecap="round"/><circle cx="60" cy="8" r="9" fill="#ffcf3d" stroke="#2f2160" stroke-width="4"/><circle cx="142" cy="8" r="9" fill="#ffcf3d" stroke="#2f2160" stroke-width="4"/>
      <path d="M32 112 q-26 -4 -26 -34 M168 112 q26 -4 26 -34" fill="none" stroke="#2f2160" stroke-width="9" stroke-linecap="round"/><circle cx="6" cy="76" r="11" fill="#7b5cc9" stroke="#2f2160" stroke-width="5"/><circle cx="194" cy="76" r="11" fill="#7b5cc9" stroke="#2f2160" stroke-width="5"/>
      <ellipse cx="72" cy="186" rx="26" ry="10" fill="#2f2160"/><ellipse cx="130" cy="186" rx="26" ry="10" fill="#2f2160"/>
      <path d="M26 112 C16 56 64 26 102 28 C148 26 186 62 176 116 C170 160 142 182 100 182 C58 182 32 164 26 112Z" fill="#7b5cc9" stroke="#2f2160" stroke-width="6" stroke-linejoin="round"/>
      <g fill="#d8ccff" font-family="Lexend, sans-serif" font-weight="800" font-size="24"><text x="42" y="62" transform="rotate(-18 42 62)">7</text><text x="140" y="56" transform="rotate(16 140 56)">π</text><text x="38" y="150" transform="rotate(14 38 150)">÷</text><text x="146" y="152" transform="rotate(-12 146 152)">9</text><text x="94" y="172">−3</text></g>
      <path d="M44 128 q20 -22 36 -4 t38 -6 t34 10" fill="none" stroke="#d8ccff" stroke-width="3" stroke-dasharray="2 7" stroke-linecap="round"/>
      ${c}</svg>`,
    van: (c) => `<svg viewBox="0 0 200 200" aria-hidden="true">
      <path d="M150 34 C176 8 188 4 194 2 C190 22 176 44 154 56Z" fill="#8fe0ff" stroke="#1d3b6b" stroke-width="4" stroke-linejoin="round"/><path d="M154 52 L136 70" stroke="#1d3b6b" stroke-width="5" stroke-linecap="round"/>
      <path d="M30 120 C14 62 58 26 104 28 C152 28 188 66 174 122 C168 150 150 160 136 160 L136 178 q-6 18 -14 0 L120 160 C100 166 84 164 74 160 L68 188 q-8 14 -14 -2 L52 158 C40 150 34 138 30 120Z" fill="#2b2f6b" stroke="#141848" stroke-width="6" stroke-linejoin="round"/>
      <ellipse cx="62" cy="62" rx="22" ry="12" fill="#5a62c8" opacity=".6" transform="rotate(-24 62 62)"/>
      <circle cx="18" cy="150" r="9" fill="#2b2f6b"/><circle cx="188" cy="150" r="6" fill="#2b2f6b"/><circle cx="12" cy="30" r="5" fill="#2b2f6b"/>
      <g fill="#aeb6ff" font-family="Lexend, sans-serif" font-weight="700" font-size="16"><text x="44" y="150">“?</text><text x="136" y="148">…!</text></g>
      ${c}</svg>`,
    anh: (c) => `<svg viewBox="0 0 200 200" aria-hidden="true">
      <path d="M40 160 L22 196 L78 168Z" fill="#f08a3c" stroke="#8a3c0a" stroke-width="6" stroke-linejoin="round"/>
      <rect x="14" y="22" width="172" height="146" rx="46" fill="#f08a3c" stroke="#8a3c0a" stroke-width="6"/>
      <path d="M44 40 L36 12 M156 40 L166 12" stroke="#8a3c0a" stroke-width="6" stroke-linecap="round"/><circle cx="36" cy="12" r="8" fill="#fff" stroke="#8a3c0a" stroke-width="4"/><circle cx="166" cy="12" r="8" fill="#fff" stroke="#8a3c0a" stroke-width="4"/>
      <g fill="#fff3dc" font-family="Lexend, sans-serif" font-weight="800" font-size="20"><text x="30" y="60" transform="rotate(-10 30 60)">goed</text><text x="128" y="154">are?</text><text x="30" y="150">he go</text></g>
      <path d="M126 50 q10 -8 20 0 t20 0" fill="none" stroke="#b3261e" stroke-width="4" stroke-linecap="round"/>
      ${c}</svg>`,
};

/** gateway art ids `boss-toan|boss-van|boss-anh`; anything else wears the maths boss */
const KIND: Record<string, "toan" | "van" | "anh"> = { "boss-toan": "toan", "boss-van": "van", "boss-anh": "anh" };
const FACE: Record<"toan" | "van" | "anh", [number, number, number]> = { toan: [100, 104, 1], van: [102, 92, 1], anh: [100, 94, 1] };
export const bossKind = (art: string): "toan" | "van" | "anh" => KIND[art] ?? "toan";
export const bossSvg = (art: string): string => {
  const k = bossKind(art);
  return BOSSES[k](face(...FACE[k]));
};

export function BossArt({ art, className = "ar-btile", id }: { art: string; className?: string; id?: string }): ReactElement {
  return <span className={className} id={id} aria-hidden="true" dangerouslySetInnerHTML={{ __html: bossSvg(art) }} />;
}
