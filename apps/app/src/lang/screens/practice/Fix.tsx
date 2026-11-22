import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { practice, type PFix, type PItem, type PReport, type PReviewItem } from "../../../api";
import { useAuth } from "../../../state/auth";
import { canCheck, isStepType, stepText, tfDecode } from "../../../lib/practice";
import { plainText } from "../../../lib/text";
import { Md } from "../../kit/blocks";
import { ItemView } from "./ItemView";

type Phase = { s: "try" } | { s: "right" } | { s: "again"; fix: PFix };

/** The right answer (or the learner's) of an item as a line, by type. */
function lineOf(item: PItem, raw: string | null | undefined, yes: string, no: string): string {
  const v = raw ?? "";
  if (!v) return "";
  if (isStepType(item.type)) return stepText(item, v);
  if (item.type === "TRUE_FALSE_GROUP") {
    const given = tfDecode(item, v);
    return (item.statements ?? []).map((s) => `${s.id}: ${given[s.id] ? yes : no}`).join(", ");
  }
  if (item.type === "SINGLE_CHOICE" || item.type === "PICTURE_CHOICE") {
    const o = item.options?.find((x) => x.id === v);
    return o ? `${o.id}${o.text ? `: ${plainText(o.text)}` : ""}` : v;
  }
  return v;
}

/**
 * hs-06 "Sửa câu sai": the items answered wrong, one by one. Each gets one more try before the solution
 * (POST .../fix); wrong again shows the right answer and the reason. `onDone` reports how many were fixed.
 */
export function FixFlow({ id, report, onDone }: { id: string; report: PReport; onDone(fixed: number, total: number): void }) {
  const { t, i18n } = useTranslation();
  const { token, user } = useAuth();
  const tk = token ?? "";
  const kid = user?.age_band === "g1_5";
  const lang = i18n.language === "en" ? "en" : "vi";
  const wrong = report.wrong ?? [];
  const [items, setItems] = useState<PReviewItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [at, setAt] = useState(0);
  const [value, setValue] = useState("");
  const [phase, setPhase] = useState<Phase>({ s: "try" });
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    practice.review(tk, id).then(
      (r) => {
        if (!alive) return;
        const all = Array.isArray(r) ? r : r.items;
        setItems(wrong.flatMap((w) => all.find((x) => x.id === w.item_id) ?? []));
      },
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tk, id]);

  const none = !!items && items.length === 0;
  useEffect(() => {
    if (none) onDone(0, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [none]);

  if (failed) return <p className="muted" role="alert">{t("practice.loadFailed")}</p>;
  if (!items) return <p className="muted" role="status">{t("practice.fixLoading")}</p>;
  if (!items.length) return null;
  const item = items[at];
  const first = wrong.find((w) => w.item_id === item.id)?.chosen ?? item.answer ?? "";
  const choice = item.type === "SINGLE_CHOICE" || item.type === "PICTURE_CHOICE";
  const last = at === items.length - 1;
  const yes = t("courses.player.true");
  const no = t("courses.player.false");

  const send = async (v: string) => {
    if (busy || phase.s !== "try") return;
    setBusy(true);
    setNote(null);
    try {
      const r = await practice.fix(tk, id, { item_id: item.id, answer: v });
      setDone((d) => ({ ...d, [item.id]: r.correct }));
      setPhase(r.correct ? { s: "right" } : { s: "again", fix: r });
    } catch {
      setNote(t("practice.fixFailed"));
    } finally {
      setBusy(false);
    }
  };
  const change = (v: string) => {
    if (phase.s !== "try") return;
    setValue(v);
    if (choice) void send(v); // one tap on a choice is the answer
  };
  const next = () => {
    if (last) return onDone(Object.values(done).filter(Boolean).length, items.length);
    setAt(at + 1);
    setValue("");
    setPhase({ s: "try" });
    setNote(null);
  };

  const result = phase.s === "right" ? { correct: true, correct_answer: value } : phase.s === "again" ? { correct: false, correct_answer: phase.fix.right } : null;
  return (
    <div className="pr-fix">
      <div className="pr-fix-h">
        <span className="tag">{t("practice.fixCount", { n: at + 1, total: items.length })}</span>
        <div className="qmap" role="group" aria-label={t("practice.fixCount", { n: at + 1, total: items.length })}>
          {items.map((it, i) => (
            <span key={it.id} className={`qn ${done[it.id] ? "fixed done" : "wrong"}`} aria-current={i === at ? "true" : undefined}>
              {it.position + 1}
            </span>
          ))}
        </div>
      </div>
      <ItemView item={item} token={tk} lang={lang} kid={kid} value={value} onChange={change} locked={phase.s !== "try"} result={result} was={choice ? first : undefined} />
      {!choice && first && phase.s === "try" && (
        <p className="muted pr-was">
          {t("practice.chose")}: {lineOf(item, first, yes, no)}
        </p>
      )}
      {phase.s === "try" && <p className="muted">{t("practice.fixHint")}</p>}
      {phase.s === "right" && (
        <div className="feedback pr-fb right" role="status">
          <b>{t("practice.fixRight")}</b> <span>{t("practice.fixRightLine")}</span>
        </div>
      )}
      {phase.s === "again" && (
        <div className="feedback pr-fb wrong" role="status">
          {!choice && phase.fix.right && (
            <span>
              {t("practice.rightIs")}: <b className="ok">{lineOf(item, phase.fix.right, yes, no)}</b>
            </span>
          )}
          {phase.fix.note && <p className="why">{phase.fix.note}</p>}
          {phase.fix.explanation && <Md md={phase.fix.explanation} />}
        </div>
      )}
      {note && (
        <p className="note muted" role="alert">
          {note}
        </p>
      )}
      <p className="pr-row">
        {phase.s === "try" && !choice && (
          <button className="btn btn-primary" type="button" disabled={busy || !canCheck(item, value)} onClick={() => void send(value)}>
            {t("practice.check")}
          </button>
        )}
        {phase.s !== "try" && (
          <button className="btn btn-primary" type="button" onClick={next} autoFocus>
            {last ? t("practice.fixEnd") : t("practice.fixNext")}
          </button>
        )}
      </p>
    </div>
  );
}
