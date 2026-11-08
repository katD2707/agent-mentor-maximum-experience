import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { QuizItem } from "../../api";
import { Icon } from "../../components/Icon";
import { speak } from "../../lib/speak";
import { plainText } from "../../lib/text";
import { onMediaError } from "../../lib/mediaRetry";
import { canSubmit, checkAnswer, type Answer, type Verdict } from "../../lib/quiz";
import { Md, SpeakButton, type BlockCtx } from "./blocks";

export interface QuizItemProps {
  item: QuizItem;
  ctx: BlockCtx;
  /** grades 1-5: wrong answers get a hint and another try instead of the red-pen reveal */
  kid: boolean;
  /** number shown before the stem ("Câu 2"), omit for a single question */
  n?: number;
  /** every submit, right or wrong */
  onResult(r: { item_id: string; correct: boolean; seconds: number }): void;
  /** the item is finished (answered in normal mode, answered right in kid mode) */
  onDone(correct: boolean): void;
}

const STAR = "M12 2.5l2.9 6 6.6.8-4.9 4.5 1.3 6.5L12 17l-5.9 3.3 1.3-6.5L2.5 9.3l6.6-.8z";

export function QuizItemView({ item, ctx, kid, n, onResult, onDone }: QuizItemProps) {
  const { t, i18n } = useTranslation();
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [verdict, setVerdict] = useState<Verdict | null>(null); // locked result
  const [slip, setSlip] = useState(0); // kid mode: wrong attempts so far (re-triggers the wiggle)
  const [hint, setHint] = useState(false);
  const t0 = useRef(Date.now());
  const done = verdict !== null;

  const submit = (a: Answer) => {
    if (done) return;
    const v = checkAnswer(item, a);
    onResult({ item_id: item.id, correct: v.correct, seconds: Math.round((Date.now() - t0.current) / 100) / 10 });
    if (kid && !v.correct) {
      setSlip((s) => s + 1);
      setHint(true);
      speak(item.hint ?? t("courses.player.countAgain"), ctx.lang || i18n.language);
      if (item.type !== "TAP_COUNT") setAnswer(a);
      return;
    }
    setAnswer(a);
    setVerdict(v);
    onDone(v.correct);
  };

  const stemImg = ctx.url(item.stem_image);
  const stem = (
    <div className="q-stem">
      {n !== undefined && <span className="qn">{t("courses.player.questionN", { n })}</span>}
      <Md md={item.stem} className="inline" />
      <SpeakButton text={item.stem} audioUrl={ctx.url(item.stem_audio)} lang={ctx.lang} />
    </div>
  );

  const chosen = answer?.kind === "choice" ? answer.id : null;

  return (
    <section className={`q q-${item.type.toLowerCase().replace(/_/g, "-")}`} data-item={item.id} aria-label={t("courses.player.quizTitle")}>
      {stem}
      {stemImg && <img className="q-img" src={stemImg} alt="" onError={onMediaError} />}

      {(item.type === "SINGLE_CHOICE" || item.type === "PICTURE_CHOICE") && (
        <div className={item.type === "PICTURE_CHOICE" ? "pics" : "opts"} role="group">
          {item.options.map((o) => {
            const isRight = done && verdict.correctOptionId === o.id;
            const isWrong = done && chosen === o.id && !isRight;
            const wiggle = kid && !done && chosen === o.id && slip > 0;
            const img = ctx.url(o.image);
            const label = o.text ? plainText(o.text) : o.id;
            return (
              <button
                key={`${o.id}-${wiggle ? slip : 0}`}
                type="button"
                className={`opt ${item.type === "PICTURE_CHOICE" ? "pic" : ""} ${isRight ? "right" : ""} ${isWrong ? "wrong" : ""} ${wiggle ? "wrong wiggle" : ""}`}
                disabled={done}
                aria-label={item.type === "PICTURE_CHOICE" ? label : undefined}
                onClick={() => submit({ kind: "choice", id: o.id })}
              >
                {item.type === "PICTURE_CHOICE" ? (
                  img ? <img src={img} alt="" onError={onMediaError} /> : <span className="k">{o.id}</span>
                ) : (
                  <>
                    <span className="k">{o.id}</span>
                    <span className="opt-text">
                      {img && <img src={img} alt="" onError={onMediaError} />}
                      {o.text && <Md md={o.text} className="inline" />}
                    </span>
                    {isRight && <Icon name="check" />}
                    {isWrong && <Icon name="x" />}
                  </>
                )}
              </button>
            );
          })}
        </div>
      )}

      {item.type === "TRUE_FALSE_GROUP" && (
        <>
          <ul className="tf">
            {item.statements.map((s) => {
              const given = answer?.kind === "tf" ? answer.values[s.id] : undefined;
              const bad = done && verdict.wrong?.includes(s.id);
              return (
                <li key={s.id} className={`${done ? (bad ? "wrong" : "right") : ""}`}>
                  <span className="tf-text">
                    <b className="k">{s.id}</b>
                    <Md md={s.text} className="inline" />
                  </span>
                  <span className="tf-btns" role="group" aria-label={s.text}>
                    {[true, false].map((val) => (
                      <button
                        key={String(val)}
                        type="button"
                        className="chip"
                        aria-pressed={given === val}
                        disabled={done}
                        onClick={() => setAnswer({ kind: "tf", values: { ...(answer?.kind === "tf" ? answer.values : {}), [s.id]: val } })}
                      >
                        {t(val ? "courses.player.true" : "courses.player.false")}
                      </button>
                    ))}
                  </span>
                </li>
              );
            })}
          </ul>
          {!done && <CheckButton disabled={!canSubmit(item, answer)} onClick={() => answer && submit(answer)} />}
        </>
      )}

      {item.type === "SHORT_ANSWER" && (
        <form
          className="short"
          onSubmit={(e) => {
            e.preventDefault();
            if (answer && canSubmit(item, answer)) submit(answer);
          }}
        >
          <input
            className={`short-in ${done ? (verdict.correct ? "right" : "wrong") : ""}`}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            disabled={done}
            value={answer?.kind === "text" ? answer.value : ""}
            onChange={(e) => setAnswer({ kind: "text", value: e.target.value })}
            placeholder={t("courses.player.answerPlaceholder")}
            aria-label={t("courses.player.answer")}
          />
          {!done && <CheckButton submit disabled={!canSubmit(item, answer)} />}
        </form>
      )}

      {item.type === "TAP_COUNT" && item.tap && <TapCount item={item} ctx={ctx} done={done} slip={slip} onCheck={(count) => submit({ kind: "count", value: count })} />}

      {!kid && !done && item.hint && (
        <div className="hint-line">
          {hint ? (
            <p className="hint" role="status">
              <b>{t("courses.player.hint")}:</b> {item.hint}
            </p>
          ) : (
            <button type="button" className="btn-link" onClick={() => setHint(true)}>
              {t("courses.player.showHint")}
            </button>
          )}
        </div>
      )}

      {kid && hint && !done && (
        <p className="hint pill-hint" role="status">
          <Icon name="volume" />
          <span>{item.hint ?? t("courses.player.countAgain")}</span>
        </p>
      )}

      {done && <Feedback item={item} verdict={verdict} chosen={chosen} kid={kid} />}
    </section>
  );
}

function CheckButton({ onClick, disabled, submit }: { onClick?: () => void; disabled?: boolean; submit?: boolean }) {
  const { t } = useTranslation();
  return (
    <button className="btn btn-primary check" type={submit ? "submit" : "button"} disabled={disabled} onClick={onClick}>
      {t("courses.player.check")}
    </button>
  );
}

function TapCount({ item, ctx, done, slip, onCheck }: { item: QuizItem; ctx: BlockCtx; done: boolean; slip: number; onCheck(count: number): void }) {
  const { t } = useTranslation();
  const [on, setOn] = useState<Set<number>>(new Set());
  const img = ctx.url(item.tap!.image);
  const toggle = (i: number) =>
    setOn((s) => {
      const next = new Set(s);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  return (
    <div className="tap">
      <div className="bignum" aria-live="polite">
        {on.size}
      </div>
      <div className={`frame ${slip > 0 && !done ? "wiggle" : ""}`} key={slip}>
        {Array.from({ length: item.tap!.total }, (_, i) => (
          <button key={i} type="button" className={`apple ${on.has(i) ? "on" : ""}`} aria-pressed={on.has(i)} aria-label={t("courses.player.tapCount", { n: i + 1 })} disabled={done} onClick={() => toggle(i)}>
            {img ? <img src={img} alt="" onError={onMediaError} /> : <span className="k">{i + 1}</span>}
          </button>
        ))}
      </div>
      {!done && (
        <button className="btn btn-primary btn-big check" type="button" disabled={on.size === 0} onClick={() => onCheck(on.size)}>
          {t("courses.player.done")}
        </button>
      )}
    </div>
  );
}

function Feedback({ item, verdict, chosen, kid }: { item: QuizItem; verdict: Verdict; chosen: string | null; kid: boolean }) {
  const { t } = useTranslation();
  if (kid) {
    return (
      <div className="kid-win" role="status">
        <div className="win-stars" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <svg key={i} viewBox="0 0 24 24" className="s">
              <path d={STAR} fill="#FFC21A" stroke="#9A5200" strokeWidth="1" />
            </svg>
          ))}
        </div>
        <span className="sr">{t("courses.player.right")}</span>
      </div>
    );
  }
  const own = chosen ? item.option_feedback[chosen] : undefined;
  const key = item.answer_key as { accepted?: unknown[] };
  const reveal = !verdict.correct && item.type === "SHORT_ANSWER" && key.accepted?.length ? `${t("courses.player.answer")}: ${String(key.accepted[0])}. ` : "";
  return (
    <p className={`fb ${verdict.correct ? "ok" : "no"}`} role="status">
      <b>{verdict.correct ? t("courses.player.right") : t("courses.player.wrong")}</b> {reveal}
      {!verdict.correct && own ? `${own} ` : ""}
      {item.explanation}
    </p>
  );
}
