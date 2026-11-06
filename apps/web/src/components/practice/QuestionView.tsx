"use client";

import { useId } from "react";
import { decodeTF, normalizeShortAnswerInput, parseShortAnswer, setStatement, shortAnswerHint, STATEMENT_COUNT, LEVEL_NAMES } from "@/lib/practice/logic";
import type { ClientItem, PracticeAsset } from "@/lib/practice/types";
import { Icon } from "../Icon";
import { RichText, StemView } from "./RichText";

export interface Outcome {
  /** The item's key (letter, `TFTF`, or the number) once the answer is shown. */
  correctAnswer?: string;
  correct?: boolean | null;
  /** Per statement: did the learner get it right. */
  statementResults?: (boolean | null)[];
  /** Why the chosen distractor is tempting (only the chosen option's, or all in review). */
  optionFeedback?: Record<string, string> | null;
}

export const LETTERS = ["A", "B", "C", "D"];

/** Level as dots plus its name, so it never relies on colour. */
export function LevelPips({ level }: { level: number }) {
  const name = LEVEL_NAMES[Math.min(4, Math.max(1, level)) - 1];
  return (
    <span className="pips" title={name} aria-label={`Mức ${name}`}>
      {[1, 2, 3, 4].map((i) => (
        <span key={i} className="pip" data-on={i <= level} aria-hidden="true" />
      ))}
      <span className="pips-name">{name}</span>
    </span>
  );
}

export function ItemMeta({ item, part, flagged }: { item: ClientItem; part?: { label: string; index: number; count: number } | null; flagged?: boolean }) {
  return (
    <div className="item-meta">
      {part && (
        <span className="badge badge-ok">
          {part.label} · câu {part.index}/{part.count}
        </span>
      )}
      <span className="badge">{item.topic_title}</span>
      <LevelPips level={item.level} />
      <span className="badge badge-warn" title="Câu hỏi do dự án biên soạn và được AI kiểm định, chưa qua thẩm định chính thức">
        Thử nghiệm · AI đã kiểm định
      </span>
      {flagged && (
        <span className="badge badge-warn">
          <Icon name="check" size={12} /> Đã đánh dấu xem lại
        </span>
      )}
    </div>
  );
}

function optionState(id: string, selected: string | null, o?: Outcome | null): "idle" | "selected" | "correct" | "wrong" | "dim" {
  if (o?.correctAnswer) {
    if (id === o.correctAnswer) return "correct";
    if (id === selected) return "wrong";
    return "dim";
  }
  return id === selected ? "selected" : "idle";
}

function Options({ item, answer, onAnswer, readOnly, outcome, shakeKey }: Props & { shakeKey: number }) {
  const groupId = useId();
  return (
    <div className="opts" role="radiogroup" aria-labelledby={`${groupId}-q`}>
      <span id={`${groupId}-q`} className="sr-only">
        Chọn một đáp án
      </span>
      {(item.options ?? []).map((o, i) => {
        const st = optionState(o.id, answer, outcome);
        const fb = st === "wrong" ? outcome?.optionFeedback?.[o.id] : undefined;
        return (
          <div key={o.id} className="opt-wrap">
            <button
              type="button"
              role="radio"
              aria-checked={o.id === answer}
              data-pkey="option"
              className="opt"
              data-state={st}
              data-shake={st === "wrong" ? shakeKey : undefined}
              disabled={readOnly}
              onClick={() => onAnswer(o.id)}
            >
              <span className="opt-badge" aria-hidden="true">
                {st === "correct" ? "✓" : st === "wrong" ? "✗" : LETTERS[i]}
              </span>
              <span className="opt-text">
                <RichText text={o.text} assets={item.assets} inline />
              </span>
              {st === "correct" && <span className="sr-only"> (đáp án đúng)</span>}
              {st === "wrong" && <span className="sr-only"> (bạn đã chọn, chưa đúng)</span>}
              {!readOnly && <kbd className="keycap" aria-hidden="true">{i + 1}</kbd>}
            </button>
            {fb && (
              <p className="opt-fb">
                <RichText text={fb} inline />
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function TrueFalse({ item, answer, onAnswer, readOnly, outcome }: Props) {
  const choices = decodeTF(answer);
  const truths = outcome?.correctAnswer ? decodeTF(outcome.correctAnswer) : null;
  return (
    <div className="tf" role="group" aria-label="Đúng hoặc Sai cho từng ý">
      {(item.statements ?? []).slice(0, STATEMENT_COUNT).map((s, i) => {
        const choice = choices[i];
        const right = outcome?.statementResults?.[i] ?? null;
        const mine = choice === true ? "Đúng" : choice === false ? "Sai" : "bỏ trống";
        return (
          <div key={s.id} className="tf-row" data-result={right === null ? undefined : right ? "right" : "wrong"}>
            <span className="opt-badge" aria-hidden="true">
              {s.id}
            </span>
            <div className="tf-text">
              <RichText text={s.text} assets={item.assets} inline />
              {truths && (
                <p className="tf-res" data-right={right === true}>
                  {right === true ? `✓ Bạn chọn ${mine}, chính xác` : `✗ Bạn chọn ${mine} · đáp án: ${truths[i] ? "Đúng" : "Sai"}`}
                </p>
              )}
            </div>
            <div className="tf-btns" role="radiogroup" aria-label={`Ý ${s.id}`}>
              {([true, false] as const).map((v) => (
                <button
                  key={String(v)}
                  type="button"
                  role="radio"
                  aria-checked={choice === v}
                  data-pkey="option"
                  className="tf-btn"
                  data-on={choice === v}
                  disabled={readOnly}
                  onClick={() => onAnswer(setStatement(answer, i, choice === v ? null : v))}
                >
                  {choice === v ? "● " : ""}
                  {v ? "Đúng" : "Sai"}
                </button>
              ))}
            </div>
            {!readOnly && <kbd className="keycap" aria-hidden="true">{i + 1}</kbd>}
          </div>
        );
      })}
    </div>
  );
}

function ShortAnswer({ item, answer, onAnswer, readOnly, outcome }: Props) {
  const id = useId();
  const sa = item.short_answer;
  const max = sa?.max_chars ?? null;
  const text = answer ?? "";
  const bad = text !== "" && parseShortAnswer(text, sa?.unit) === null;
  const done = outcome?.correctAnswer !== undefined;
  return (
    <div className="sa">
      <label htmlFor={id} className="field-label">
        Đáp án của bạn
      </label>
      <div className="sa-row">
        <input
          id={id}
          className="input sa-input"
          data-state={done ? (outcome?.correct ? "correct" : "wrong") : undefined}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          placeholder="Nhập số"
          value={text}
          readOnly={readOnly}
          aria-describedby={`${id}-hint`}
          aria-invalid={bad || undefined}
          onChange={(e) => onAnswer(normalizeShortAnswerInput(e.target.value, max) || null)}
        />
        {max && (
          <span className="faint sa-count" aria-hidden="true">
            {text.length}/{max} kí tự
          </span>
        )}
      </div>
      <p id={`${id}-hint`} className="hint">
        {shortAnswerHint(sa)}
      </p>
      {bad && !readOnly && (
        <p className="sa-err" role="alert">
          Chưa đúng dạng số (ví dụ 12 hoặc -0,5).
        </p>
      )}
    </div>
  );
}

interface Props {
  item: ClientItem;
  answer: string | null;
  onAnswer: (next: string | null) => void;
  readOnly: boolean;
  outcome?: Outcome | null;
}

/** Stem card plus the answer area of one item (all three formats). Presentational: the caller owns state. */
export function QuestionView(
  props: Props & {
    part?: { label: string; index: number; count: number } | null;
    flagged?: boolean;
    shakeKey?: number;
    extraAssets?: PracticeAsset[];
  },
) {
  const { item, part, flagged, shakeKey = 0, extraAssets } = props;
  return (
    <div className="q">
      <section className="card q-stem" aria-label="Đề bài">
        <ItemMeta item={item} part={part} flagged={flagged} />
        <StemView item={item} extraAssets={extraAssets} />
      </section>
      <section className="q-answers" aria-label="Trả lời">
        {item.type === "SINGLE_CHOICE" && <Options {...props} shakeKey={shakeKey} />}
        {item.type === "TRUE_FALSE_GROUP" && <TrueFalse {...props} />}
        {item.type === "SHORT_ANSWER" && <ShortAnswer {...props} />}
      </section>
    </div>
  );
}
