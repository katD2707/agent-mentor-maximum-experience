import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Block, QuizItem } from "../../api";
import { Icon } from "../../components/Icon";

type Patch = Record<string, unknown>;

function Field({ label, value, onChange, area, locked, type }: { label: string; value: string; onChange(v: string): void; area?: boolean; locked: boolean; type?: "number" }) {
  return (
    <label className="f">
      <span className="fl">{label}</span>
      {area ? <textarea rows={3} value={value} readOnly={locked} onChange={(e) => onChange(e.target.value)} /> : <input type={type ?? "text"} value={value} readOnly={locked} onChange={(e) => onChange(e.target.value)} />}
    </label>
  );
}

/** The editable fields of one quiz question: stem, options with the right one, explanation, "if they pick X" notes, tiles/parts. */
function QuizFields({ item, locked, onPatch }: { item: QuizItem; locked: boolean; onPatch(p: Record<string, unknown>): void }) {
  const { t } = useTranslation();
  const key = item.answer_key as Record<string, unknown>;
  const choice = typeof key.correct_option_id === "string";
  return (
    <div className="qfields">
      <Field label={t("gv.fQuestion")} area locked={locked} value={item.stem} onChange={(v) => onPatch({ stem: v })} />
      {choice &&
        item.options.map((o, i) => (
          <div key={o.id}>
            <div className="orow">
              <input type="radio" name={`right-${item.id}`} checked={key.correct_option_id === o.id} disabled={locked} aria-label={t("gv.fRight", { n: i + 1 })} onChange={() => onPatch({ answer_key: { ...key, correct_option_id: o.id } })} />
              <b>{String.fromCharCode(65 + i)}</b>
              <input type="text" value={o.text ?? ""} readOnly={locked} aria-label={t("gv.fOption", { n: i + 1 })} onChange={(e) => onPatch({ options: item.options.map((x) => (x.id === o.id ? { ...x, text: e.target.value } : x)) })} />
            </div>
            {key.correct_option_id !== o.id && (
              <label className="onote">
                <span>{t("gv.fIfPick", { n: String.fromCharCode(65 + i) })}</span>
                <input type="text" value={item.option_feedback[o.id] ?? ""} readOnly={locked} aria-label={t("gv.fIfPick", { n: String.fromCharCode(65 + i) })} onChange={(e) => onPatch({ option_feedback: { ...item.option_feedback, [o.id]: e.target.value } })} />
              </label>
            )}
          </div>
        ))}
      {Array.isArray(key.accepted) && <Field label={t("gv.fRight", { n: "" })} locked={locked} value={(key.accepted as string[]).join(", ")} onChange={(v) => onPatch({ answer_key: { ...key, accepted: v.split(",").map((s) => s.trim()).filter(Boolean) } })} />}
      {(item.parts ?? []).map((p, i) => (
        <Field key={p.id} label={t(item.type === "FILL_TILES" ? "gv.fTiles" : "gv.fParts", { n: i + 1 })} locked={locked} value={p.text} onChange={(v) => onPatch({ parts: (item.parts ?? []).map((x) => (x.id === p.id ? { ...x, text: v } : x)) })} />
      ))}
      <Field label={t("gv.fExplain")} area locked={locked} value={item.explanation} onChange={(v) => onPatch({ explanation: v })} />
    </div>
  );
}

/** Fields of one step by kind. Save sends only this block's fields (PATCH .../blocks/{id}); a quiz sends `items: [{id, ...}]`. */
export function StepEditor({ block, english, locked, saving, onSave }: { block: Block; english: boolean; locked: boolean; saving: boolean; onSave(patch: Patch): void }) {
  const { t } = useTranslation();
  const [d, setD] = useState<Block>(block);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    setD(block);
    setDirty(false);
  }, [block]);
  const set = (p: Record<string, unknown>) => {
    setD((x) => ({ ...x, ...p }) as Block);
    setDirty(true);
  };

  let body: React.ReactNode = null;
  let patch: Patch = {};
  switch (d.kind) {
    case "text":
      body = (
        <>
          <Field label={t("gv.fMuc")} area locked={locked} value={d.md} onChange={(v) => set({ md: v })} />
          {(english || d.gloss) && <Field label={t("gv.fGloss")} area locked={locked} value={d.gloss ?? ""} onChange={(v) => set({ gloss: v })} />}
        </>
      );
      patch = { md: d.md, ...(english || d.gloss ? { gloss: d.gloss ?? "" } : {}) };
      break;
    case "callout":
      body = (
        <>
          <Field label={t("gv.fTitle")} locked={locked} value={d.title ?? ""} onChange={(v) => set({ title: v })} />
          <Field label={t("gv.fMuc")} area locked={locked} value={d.md} onChange={(v) => set({ md: v })} />
        </>
      );
      patch = { title: d.title ?? "", md: d.md };
      break;
    case "quiz": {
      const q = d;
      body = q.items.map((it) => <QuizFields key={it.id} item={it} locked={locked} onPatch={(p) => set({ items: q.items.map((x) => (x.id === it.id ? { ...x, ...p } : x)) })} />);
      patch = { items: q.items.map((it) => ({ id: it.id, stem: it.stem, options: it.options, parts: it.parts, answer_key: it.answer_key, explanation: it.explanation, option_feedback: it.option_feedback })) };
      break;
    }
    case "interactive":
      body = (
        <>
          <Field label={t("gv.fPrompt")} area locked={locked} value={d.prompt} onChange={(v) => set({ prompt: v })} />
          <Field label={t("gv.fTarget")} type="number" locked={locked} value={String(d.target_y)} onChange={(v) => set({ target_y: Number(v) })} />
          <Field label={t("gv.fPraise")} locked={locked} value={d.praise} onChange={(v) => set({ praise: v })} />
        </>
      );
      patch = { prompt: d.prompt, target_y: d.target_y, praise: d.praise };
      break;
    case "recall": {
      const r = d;
      body = r.items.map((it, i) => (
        <div key={i} className="prow">
          <Field label={t("gv.fRecallQ", { n: i + 1 })} locked={locked} value={it.prompt} onChange={(v) => set({ items: r.items.map((x, j) => (j === i ? { ...x, prompt: v } : x)) })} />
          <Field label={t("gv.fRecallA", { n: i + 1 })} locked={locked} value={it.answer} onChange={(v) => set({ items: r.items.map((x, j) => (j === i ? { ...x, answer: v } : x)) })} />
        </div>
      ));
      patch = { items: r.items.map((x) => ({ prompt: x.prompt, answer: x.answer })) };
      break;
    }
    default:
      return null;
  }
  return (
    <div className="stepfields">
      {body}
      {locked ? (
        <p className="muted small">{t("gv.lockedHint")}</p>
      ) : (
        <button type="button" className="btn btn-primary say-b" disabled={!dirty || saving} onClick={() => onSave(patch)}>
          <Icon name="check" />
          <span>{t("gv.save")}</span>
        </button>
      )}
    </div>
  );
}
