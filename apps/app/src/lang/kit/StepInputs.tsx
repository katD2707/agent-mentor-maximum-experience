import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type { QuizPart } from "../../api";
import { renderMdGaps } from "../../lib/md";
import { shuffled, stemPieces } from "../../lib/quiz";
import "../styles/kit.css";
import { Md } from "./blocks";

/**
 * The three tap-to-answer kinds of the stepped lesson (hs-05), as controlled inputs: the lesson player and the practice
 * screens both use them. Tiles are shown shuffled; tapping moves a tile, tapping it again takes it back.
 */
export type Tone = "right" | "wrong" | null;

const text = (p: QuizPart) => <Md md={p.text} className="inline" />;

const DOLLAR = /(?<!\\)\$/g;

/** True when some blank of the stem sits inside a $...$ formula (it cannot be cut into pieces: the formula would break). */
export function gapInMath(stem: string): boolean {
  let open = false;
  const pieces = stemPieces(stem);
  for (let i = 0; i < pieces.length - 1; i++) {
    if ((pieces[i].match(DOLLAR) ?? []).length % 2) open = !open;
    if (open) return true;
  }
  return false;
}

/** The stem as one Markdown/KaTeX text with each blank an empty box (`data-gap`) that gets the tile through a portal. */
function GapStem({ stem, slot }: { stem: string; slot(i: number): ReactNode }) {
  const html = useMemo(() => renderMdGaps(stem), [stem]);
  const box = useRef<HTMLDivElement>(null);
  const [hosts, setHosts] = useState<HTMLElement[]>([]);
  useLayoutEffect(() => {
    const els = [...(box.current?.querySelectorAll<HTMLElement>("[data-gap]") ?? [])].sort((a, b) => Number(a.dataset.gap) - Number(b.dataset.gap));
    for (const e of els) {
      e.textContent = "";
      e.classList.add("gap-host");
    }
    setHosts(els);
  }, [html]);
  return (
    <>
      <div className="md inline" ref={box} dangerouslySetInnerHTML={{ __html: html }} />
      {hosts.map((h, i) => createPortal(slot(i), h))}
    </>
  );
}

/** FILL_TILES: the stem with its gaps, and the tile bank below. `value` has one entry per gap (null = empty). */
export function TilesInput({ stem, parts, seed, value, onChange, locked, tone }: { stem: string; parts: QuizPart[]; seed: string; value: (string | null)[]; onChange(v: (string | null)[]): void; locked: boolean; tone?: Tone }) {
  const { t } = useTranslation();
  const pieces = useMemo(() => stemPieces(stem), [stem]);
  const gaps = pieces.length - 1;
  const bank = useMemo(() => shuffled(parts, seed), [parts, seed]);
  const byId = new Map(parts.map((p) => [p.id, p]));
  const cells = Array.from({ length: gaps }, (_, i) => value[i] ?? null);
  const used = new Set(cells.filter(Boolean));
  const put = (id: string) => {
    if (locked) return;
    const at = cells.indexOf(null);
    if (at < 0) return;
    onChange(cells.map((c, i) => (i === at ? id : c)));
  };
  const take = (i: number) => !locked && onChange(cells.map((c, k) => (k === i ? null : c)));
  const inMath = useMemo(() => gapInMath(stem), [stem]);
  const slot = (i: number) =>
    cells[i] ? (
      <button type="button" className="tile placed" disabled={locked} aria-label={t("lesson.takeBack", { text: byId.get(cells[i]!)?.text ?? "" })} onClick={() => take(i)}>
        {text(byId.get(cells[i]!)!)}
      </button>
    ) : (
      <span className="gap" role="img" aria-label={t("lesson.gap", { n: i + 1 })} />
    );
  return (
    <>
      <div className={`slots ${tone ?? ""}`}>
        {inMath ? (
          <GapStem stem={stem} slot={(i) => slot(i)} />
        ) : (
          pieces.map((piece, i) => (
            <span key={i} className="slot-piece">
              {piece.trim() && <Md md={piece} className="inline" />}
              {i < gaps && slot(i)}
            </span>
          ))
        )}
      </div>
      <div className="bank" role="group" aria-label={t("lesson.tiles")}>
        {bank.map((p) => (
          <button key={p.id} type="button" className={`tile ${used.has(p.id) ? "used" : ""}`} disabled={locked || used.has(p.id)} onClick={() => put(p.id)}>
            {text(p)}
          </button>
        ))}
      </div>
    </>
  );
}

/** ORDER_STEPS: tap the steps in order; they pile up in the line above. */
export function OrderInput({ parts, seed, value, onChange, locked, tone }: { parts: QuizPart[]; seed: string; value: string[]; onChange(v: string[]): void; locked: boolean; tone?: Tone }) {
  const { t } = useTranslation();
  const bank = useMemo(() => shuffled(parts, seed), [parts, seed]);
  const byId = new Map(parts.map((p) => [p.id, p]));
  return (
    <>
      <ol className={`slots order ${tone ?? ""}`} data-empty={t("lesson.tapInOrder")} aria-label={t("lesson.yourOrder")}>
        {value.map((id, i) => (
          <li key={id}>
            <button type="button" className="tile ui placed" disabled={locked} aria-label={t("lesson.takeBack", { text: byId.get(id)?.text ?? "" })} onClick={() => !locked && onChange(value.filter((_, k) => k !== i))}>
              <b className="k">{i + 1}</b> {text(byId.get(id)!)}
            </button>
          </li>
        ))}
      </ol>
      <div className="bank" role="group" aria-label={t("lesson.tiles")}>
        {bank.map((p) => (
          <button key={p.id} type="button" className={`tile ui ${value.includes(p.id) ? "used" : ""}`} disabled={locked || value.includes(p.id)} onClick={() => !locked && onChange([...value, p.id])}>
            {text(p)}
          </button>
        ))}
      </div>
    </>
  );
}

/**
 * MATCH_PAIRS: tap one on the left, then its match on the right. With `check` (the lesson knows the key) a right pair locks
 * green at once and a wrong tap shakes and counts as a slip; without it (practice, the server grades) a pair is just joined
 * and tapping it again undoes it.
 */
export function PairsInput({ parts, seed, map, onPair, onUnpair, onSlip, check, locked }: { parts: QuizPart[]; seed: string; map: Record<string, string>; onPair(l: string, r: string): void; onUnpair?(l: string): void; onSlip?(): void; check?: (l: string, r: string) => boolean; locked: boolean }) {
  const { t } = useTranslation();
  const left = parts.filter((p) => p.side === "left");
  const right = useMemo(() => shuffled(parts.filter((p) => p.side === "right"), seed), [parts, seed]);
  const [sel, setSel] = useState<string | null>(null);
  const [shake, setShake] = useState<string[]>([]);
  const rightTaken = new Map(Object.entries(map).map(([l, r]) => [r, l]));
  const tapLeft = (id: string) => {
    if (locked) return;
    if (id in map) return check ? undefined : onUnpair?.(id);
    setSel(sel === id ? null : id);
  };
  const tapRight = (id: string) => {
    if (locked) return;
    const owner = rightTaken.get(id);
    if (owner) return check ? undefined : onUnpair?.(owner);
    if (!sel) return;
    if (check && !check(sel, id)) {
      setShake([sel, id]);
      onSlip?.();
      return;
    }
    onPair(sel, id);
    setSel(null);
    setShake([]);
  };
  const lock = (done: boolean) => (done && check ? "done" : done ? "joined" : "");
  return (
    <div className="pairs" role="group" aria-label={t("lesson.pairs")}>
      <div className="pairs-col">
        {left.map((p) => (
          <button key={p.id} type="button" className={`tile ui ${lock(p.id in map)} ${shake.includes(p.id) ? "shake" : ""}`} aria-pressed={sel === p.id} onClick={() => tapLeft(p.id)}>
            {text(p)}
          </button>
        ))}
      </div>
      <div className="pairs-col">
        {right.map((p) => (
          <button key={p.id} type="button" className={`tile ui ${lock(rightTaken.has(p.id))} ${shake.includes(p.id) ? "shake" : ""}`} onClick={() => tapRight(p.id)}>
            {text(p)}
          </button>
        ))}
      </div>
    </div>
  );
}
