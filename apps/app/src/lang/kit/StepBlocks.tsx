import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { InteractiveBlock, RecallBlock } from "../../api";
import { Diagram } from "../../components/Diagram";
import { Icon } from "../../components/Icon";
import { buildDiagram } from "../../lib/diagram/diagram";
import { parseExpr } from "../../lib/diagram/expr";
import type { FunctionPlotSpec } from "../../lib/diagram/types";
import { onMediaError } from "../../lib/mediaRetry";
import { Md, SpeakButton, type BlockCtx } from "./blocks";

/** "1 800" / "0,25": decimal comma, thin grouping, at most 4 significant digits. */
export function fmtVal(n: number, lang: string): string {
  const r = Number(n.toPrecision(4));
  const [int, dec] = String(r).split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, lang === "en" ? "," : " ");
  return dec ? `${grouped}${lang === "en" ? "." : ","}${dec}` : grouped;
}

const decimals = (step: number) => {
  const s = String(step);
  return s.includes(".") ? s.split(".")[1].length : 0;
};

// ------------------------------------------------------------------ "Kéo sơ đồ"

/**
 * A function plot with a point the learner drags along x (pointer or arrow keys). The readout follows; inside the target
 * band the chicken praises and the lesson's "Tiếp tục" turns on (`onReached`).
 */
export function InteractiveView({ b, muc, onReached }: { b: InteractiveBlock; muc: ReactNode; onReached(): void }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language === "en" ? "en" : "vi";
  const fn = useMemo(() => {
    try {
      return parseExpr(b.expr);
    } catch {
      return null;
    }
  }, [b.expr]);
  const y = (x: number) => (fn ? fn(x) : NaN);
  const spec = useMemo<FunctionPlotSpec>(() => {
    const ys = [b.target_y - b.tolerance, b.target_y + b.tolerance];
    for (let k = 0; k <= 40; k++) {
      const v = y(b.x_min + ((b.x_max - b.x_min) * k) / 40);
      if (Number.isFinite(v)) ys.push(v);
    }
    const lo = Math.min(0, ...ys);
    const hi = Math.max(...ys);
    const pad = (hi - lo || 1) * 0.1;
    return { kind: "function_plot", x_min: b.x_min, x_max: b.x_max, y_min: lo - (lo < 0 ? pad : 0), y_max: hi + pad, functions: [{ expr: b.expr }], show_grid: true };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [b]);
  const model = useMemo(() => buildDiagram(spec), [spec]);
  // the same frame `buildDiagram` uses for a plot (lib/diagram/diagram.ts, `plot`), so the handle sits on the curve
  const pad = 28;
  const left = pad;
  const right = model.width - pad * 0.6;
  const top = pad * 0.6;
  const bottom = model.height - pad;
  const sx = (x: number) => left + ((x - b.x_min) / (b.x_max - b.x_min)) * (right - left);
  const sy = (v: number) => bottom - ((v - spec.y_min) / (spec.y_max - spec.y_min)) * (bottom - top);

  const [x, setX] = useState(b.x_start);
  const [moved, setMoved] = useState(false);
  const [won, setWon] = useState(false);
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef(false);
  const d = decimals(b.x_step);
  const snap = (v: number) => {
    const k = Math.round((v - b.x_min) / b.x_step);
    return Math.min(b.x_max, Math.max(b.x_min, Number((b.x_min + k * b.x_step).toFixed(d + 2))));
  };
  const yv = y(x);
  const inTarget = Number.isFinite(yv) && Math.abs(yv - b.target_y) <= b.tolerance + 1e-9;
  useEffect(() => {
    if (inTarget && !won) {
      setWon(true);
      onReached();
    }
  }, [inTarget, won, onReached]);

  const move = (v: number) => {
    setMoved(true);
    setX(snap(v));
  };
  const fromPointer = (e: React.PointerEvent) => {
    const r = svg.current?.getBoundingClientRect();
    if (!r || !r.width) return;
    const px = ((e.clientX - r.left) / r.width) * model.width;
    move(b.x_min + ((px - left) / (right - left)) * (b.x_max - b.x_min));
  };
  const onKey = (e: React.KeyboardEvent) => {
    const s = b.x_step;
    const map: Record<string, number> = { ArrowRight: x + s, ArrowUp: x + s, ArrowLeft: x - s, ArrowDown: x - s, PageUp: x + 5 * s, PageDown: x - 5 * s, Home: b.x_min, End: b.x_max };
    if (!(e.key in map)) return;
    e.preventDefault();
    move(map[e.key]);
  };

  const unit = (a: { unit: string }) => (a.unit ? ` ${a.unit}` : "");
  const valueText = `${b.x.label} ${fmtVal(x, lang)}${unit(b.x)}, ${b.y.label} ${fmtVal(yv, lang)}${unit(b.y)}`;
  const say = inTarget ? b.praise : !moved ? t("lesson.drag.start") : yv > b.target_y ? t("lesson.drag.lower") : t("lesson.drag.higher");
  const px = sx(x);
  const py = Number.isFinite(yv) ? Math.max(top, Math.min(bottom, sy(yv))) : bottom;
  const bandTop = sy(b.target_y + b.tolerance);
  const bandH = Math.max(4, sy(b.target_y - b.tolerance) - bandTop);

  return (
    <>
      <p className="ask">{b.prompt}</p>
      <div className="figure drag">
        <div className="drag-plot">
          <Diagram spec={spec} alt={b.prompt} idBase={`drag-${b.id}`.replace(/[^\w-]/g, "_")} />
          <svg
            ref={svg}
            className="drag-hit"
            viewBox={`0 0 ${model.width} ${model.height}`}
            preserveAspectRatio="xMidYMid meet"
            onPointerDown={(e) => {
              drag.current = true;
              e.currentTarget.setPointerCapture?.(e.pointerId);
              fromPointer(e);
            }}
            onPointerMove={(e) => drag.current && fromPointer(e)}
            onPointerUp={() => (drag.current = false)}
            onPointerCancel={() => (drag.current = false)}
          >
            <rect x={left} y={bandTop} width={right - left} height={bandH} className="drag-band" />
            <line x1={px} y1={py} x2={px} y2={bottom} className="drag-drop" />
            <g
              className={`drag-handle ${inTarget ? "on" : ""}`}
              role="slider"
              tabIndex={0}
              aria-label={b.x.label}
              aria-orientation="horizontal"
              aria-valuemin={b.x_min}
              aria-valuemax={b.x_max}
              aria-valuenow={x}
              aria-valuetext={valueText}
              onKeyDown={onKey}
            >
              {!moved && <circle className="pulse" cx={px} cy={py} r={16} />}
              <circle className="ring" cx={px} cy={py} r={17} />
              <circle className="dot" cx={px} cy={py} r={11} />
            </g>
          </svg>
        </div>
        <p className="readout" aria-hidden="true">
          {b.x.symbol} = <b>{fmtVal(x, lang)}</b>
          {unit(b.x)} · {b.y.symbol} = <b>{fmtVal(yv, lang)}</b>
          {unit(b.y)}
          <small>{t("lesson.drag.first", { y: `${b.y.symbol} = ${fmtVal(y(b.x_start), lang)}${unit(b.y)}` })}</small>
        </p>
      </div>
      <div className="ls-say drag-say">
        {muc}
        <div className="ls-bub" role="status" aria-live="polite">
          {inTarget ? <Md md={say} className="inline" /> : say}
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ "Nhớ lại"

type SpeechRec = { lang: string; interimResults: boolean; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null; start(): void; stop(): void };
const speechCtor = (): (new () => SpeechRec) | null => {
  const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};

/** What the bottom button does while a recall block is on screen. */
export type RecallFoot = { kind: "show"; run(): void } | { kind: "marking" } | { kind: "done" };

/**
 * Recall with no options: say or type what you remember, see the idea, mark "Nhớ" / "Chưa nhớ". `onMark(false)` is reported
 * for every idea the learner did not remember (the lesson counts them under "Ôn lại").
 */
export function RecallView({ b, ctx, muc, onMark, onFoot }: { b: RecallBlock; ctx: BlockCtx; muc: ReactNode; onMark(remembered: boolean): void; onFoot(f: RecallFoot): void }) {
  const { t } = useTranslation();
  const [idx, setIdx] = useState(0);
  const [shown, setShown] = useState(false);
  const [done, setDone] = useState(false);
  const [text, setText] = useState("");
  const [heard, setHeard] = useState("");
  const [listening, setListening] = useState(false);
  const rec = useRef<SpeechRec | null>(null);
  const Speech = typeof window !== "undefined" ? speechCtor() : null;
  const it = b.items[idx];

  useEffect(() => {
    onFoot(done ? { kind: "done" } : shown ? { kind: "marking" } : { kind: "show", run: () => setShown(true) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done, shown, idx]);
  useEffect(() => () => rec.current?.stop(), []);

  const mic = () => {
    if (!Speech) return;
    if (listening) return rec.current?.stop();
    const r = new Speech();
    r.lang = ctx.lang === "en" ? "en-US" : "vi-VN";
    r.interimResults = false;
    r.onresult = (e) => {
      const s = e.results[0]?.[0]?.transcript ?? "";
      setHeard(s);
      setText(s);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    rec.current = r;
    setListening(true);
    r.start();
  };
  const mark = (ok: boolean) => {
    onMark(ok);
    rec.current?.stop();
    setText("");
    setHeard("");
    setShown(false);
    if (idx >= b.items.length - 1) setDone(true);
    else setIdx(idx + 1);
  };
  const img = ctx.url(it.image);
  if (done) return <p className="ask">{t("lesson.recall.done")}</p>;
  return (
    <>
      <div className="ls-say">
        {muc}
        <div className="ls-bub">
          <span className="rc-n">
            {idx + 1}/{b.items.length}
          </span>
          <br />
          <Md md={it.prompt} className="inline" />
          <SpeakButton text={it.prompt} lang={ctx.lang} />
        </div>
      </div>
      {img && (
        <figure className="blk-image">
          <img src={img} alt="" onError={onMediaError} />
        </figure>
      )}
      {!shown && (
        <div className="rc-body">
          <div className={`rc-in ${Speech ? "has-mic" : ""}`}>
            <input type="text" autoComplete="off" value={text} onChange={(e) => setText(e.target.value)} aria-label={t("lesson.recall.yours")} placeholder={t("lesson.recall.type")} />
            {Speech && (
              <button className="mic" type="button" aria-pressed={listening} aria-label={t("lesson.recall.say")} onClick={mic}>
                <Icon name="mic" />
              </button>
            )}
          </div>
          <p className="rc-heard" role="status" aria-live="polite">
            {heard && t("lesson.recall.heard", { text: heard })}
          </p>
        </div>
      )}
      {shown && (
        <>
          <div className="rc-ans">
            <small>{t("lesson.recall.idea")}</small>
            <Md md={it.answer} className="inline" />
          </div>
          <div className="rc-mark">
            <button className="tile no" type="button" onClick={() => mark(false)}>
              {t("lesson.recall.no")}
            </button>
            <button className="tile yes" type="button" onClick={() => mark(true)}>
              {t("lesson.recall.yes")}
            </button>
          </div>
        </>
      )}
    </>
  );
}
