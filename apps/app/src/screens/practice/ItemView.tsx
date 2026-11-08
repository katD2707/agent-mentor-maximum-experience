import { useState } from "react";
import { useTranslation } from "react-i18next";
import { practiceMediaUrl, type PItem, type PResult } from "../../api";
import { Icon } from "../../components/Icon";
import { Diagram } from "../../components/Diagram";
import { plainText } from "../../lib/text";
import { onMediaError } from "../../lib/mediaRetry";
import { tfDecode, tfEncode } from "../../lib/practice";
import { Md, SpeakButton } from "../courses/blocks";

export interface ItemViewProps {
  item: PItem;
  token: string;
  lang: "vi" | "en";
  /** current answer in the wire encoding (option id, "TFT", text, "7") */
  value: string;
  onChange(v: string): void;
  /** answer is final: practice after the check, a finished mock in review */
  locked: boolean;
  /** server verdict (practice feedback, review); drives green and red */
  result?: PResult | null;
  /** little ones: no red marks, a speaker on every text */
  kid?: boolean;
  /** number shown before the stem */
  n?: number;
}

/**
 * One practice item. Same markup and classes as the lesson quiz (`QuizItemView`) so both look alike; the verdict comes
 * from the server (the key never reaches the app), not from `lib/quiz.ts`.
 */
export function ItemView({ item, token, lang, value, onChange, locked, result, kid, n }: ItemViewProps) {
  const { t } = useTranslation();
  const url = (m: Parameters<typeof practiceMediaUrl>[1]) => practiceMediaUrl(token, m);
  const right = result?.correct_answer ?? "";
  const stemImg = url(item.stem_image);

  return (
    <section className={`q q-${item.type.toLowerCase().replace(/_/g, "-")}`} data-item={item.id} aria-label={t("practice.question")}>
      <div className="q-stem">
        {n !== undefined && <span className="qn">{t("courses.player.questionN", { n })}</span>}
        <Md md={item.stem} className="inline" />
        {(kid || item.stem_audio) && <SpeakButton text={item.stem} audioUrl={url(item.stem_audio)} lang={lang} />}
      </div>
      {stemImg && <img className="q-img" src={stemImg} alt="" onError={onMediaError} />}
      {item.assets?.map((a) => (
        <figure key={a.id} className="pq-asset">
          {a.type === "diagram" && a.diagram && <Diagram spec={a.diagram} alt={a.alt_text ?? ""} idBase={`${item.id}-${a.id}`.replace(/[^\w-]/g, "_")} />}
          {a.type === "table" && a.table && (
            <table className="pq-table">
              <thead>
                <tr>
                  {a.table.headers.map((h, i) => (
                    <th key={i}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {a.table.rows.map((r, i) => (
                  <tr key={i}>
                    {r.map((c, j) => (
                      <td key={j}>{c}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {a.caption && <figcaption className="muted small">{a.caption}</figcaption>}
        </figure>
      ))}

      {(item.type === "SINGLE_CHOICE" || item.type === "PICTURE_CHOICE") && (
        <div className={item.type === "PICTURE_CHOICE" ? "pics" : "opts"} role="group" aria-label={t("practice.options")}>
          {(item.options ?? []).map((o) => {
            const isRight = locked && !!right && right === o.id;
            const isWrong = locked && !!right && value === o.id && !isRight && !kid;
            const mark = locked && value === o.id && !isRight;
            const img = url(o.image);
            const pic = item.type === "PICTURE_CHOICE";
            const label = o.text ? plainText(o.text) : o.id;
            return (
              <button
                key={o.id}
                type="button"
                className={`opt ${pic ? "pic" : ""} ${isRight ? "right" : ""} ${isWrong ? "wrong" : ""} ${value === o.id && !locked ? "picked" : ""}`}
                aria-pressed={value === o.id}
                aria-label={pic ? label : undefined}
                disabled={locked}
                onClick={() => onChange(o.id)}
              >
                {pic ? (
                  img ? <img src={img} alt="" onError={onMediaError} /> : <span className="k">{o.text ? plainText(o.text) : o.id}</span>
                ) : (
                  <>
                    <span className="k">{o.id}</span>
                    <span className="opt-text">
                      {img && <img src={img} alt="" onError={onMediaError} />}
                      {o.text && <Md md={o.text} className="inline" />}
                    </span>
                    {isRight && <Icon name="check" />}
                    {isWrong && mark && <Icon name="x" />}
                  </>
                )}
              </button>
            );
          })}
        </div>
      )}

      {item.type === "TRUE_FALSE_GROUP" && <TrueFalse item={item} value={value} onChange={onChange} locked={locked} result={result} kid={kid} />}

      {item.type === "SHORT_ANSWER" && (
        <div className="short">
          <input
            className={`short-in ${locked && result ? (result.correct ? "right" : kid ? "" : "wrong") : ""}`}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            maxLength={item.short_answer?.max_chars ?? 40}
            disabled={locked}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={t("courses.player.answerPlaceholder")}
            aria-label={t("courses.player.answer")}
          />
          {item.short_answer?.unit && <span className="muted">{item.short_answer.unit}</span>}
        </div>
      )}

      {item.type === "TAP_COUNT" && item.tap && <Tap item={item} token={token} value={value} onChange={onChange} locked={locked} />}
    </section>
  );
}

function TrueFalse({ item, value, onChange, locked, result, kid }: Pick<ItemViewProps, "item" | "value" | "onChange" | "locked" | "result" | "kid">) {
  const { t } = useTranslation();
  const given = tfDecode(item, value);
  const byId = new Map((result?.statement_results ?? []).map((r) => [r.id, r]));
  return (
    <ul className="tf">
      {(item.statements ?? []).map((s) => {
        const r = byId.get(s.id);
        const cls = locked && r ? (r.correct ? "right" : kid ? "" : "wrong") : "";
        return (
          <li key={s.id} className={cls}>
            <span className="tf-text">
              <b className="k">{s.id}</b>
              <Md md={s.text} className="inline" />
            </span>
            <span className="tf-btns" role="group" aria-label={plainText(s.text)}>
              {[true, false].map((val) => (
                <button
                  key={String(val)}
                  type="button"
                  className="chip"
                  aria-pressed={given[s.id] === val}
                  disabled={locked}
                  onClick={() => onChange(tfEncode(item, { ...given, [s.id]: val }))}
                >
                  {t(val ? "courses.player.true" : "courses.player.false")}
                </button>
              ))}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Tap what you count: the number lit is the answer, so it is saved as a draft on every tap. */
function Tap({ item, token, value, onChange, locked }: Pick<ItemViewProps, "item" | "token" | "value" | "onChange" | "locked">) {
  const { t } = useTranslation();
  const total = item.tap!.total;
  const [on, setOn] = useState<Set<number>>(() => new Set(Array.from({ length: Math.min(total, Number(value) || 0) }, (_, i) => i)));
  const img = practiceMediaUrl(token, item.tap!.image);
  const toggle = (i: number) => {
    const next = new Set(on);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    setOn(next);
    onChange(next.size ? String(next.size) : "");
  };
  return (
    <div className="tap">
      <div className="bignum" aria-live="polite">
        {on.size}
      </div>
      <div className="frame">
        {Array.from({ length: total }, (_, i) => (
          <button key={i} type="button" className={`apple ${on.has(i) ? "on" : ""}`} aria-pressed={on.has(i)} aria-label={t("courses.player.tapCount", { n: i + 1 })} disabled={locked} onClick={() => toggle(i)}>
            {img ? <img src={img} alt="" onError={onMediaError} /> : <span className="k">{i + 1}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
