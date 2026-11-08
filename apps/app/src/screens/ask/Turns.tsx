import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AskCard, AskProblem } from "../../api";
import { Icon } from "../../components/Icon";
import type { AiTurn, MeTurn } from "../../lib/askState";
import { Md, SpeakButton } from "../courses/blocks";
import { CourseCards, type AddCourse } from "./Courses";

export function MeBubble({ turn }: { turn: MeTurn }) {
  const { t } = useTranslation();
  return (
    <div className={`msg-me${turn.photo ? " photo" : ""}`}>
      {turn.photo && (
        <span className="photo-wrap">
          <img src={turn.photo} alt={t("ask.photoAlt")} />
          {turn.badPhoto && <span className="bad" aria-hidden="true" />}
        </span>
      )}
      {turn.audio && !turn.text && (
        <span className="voice">
          <Icon name="mic" />
          {t("ask.voice")}
        </span>
      )}
      {turn.text && <span>{turn.text}</span>}
    </div>
  );
}

export interface AiHandlers {
  adder: AddCourse;
  onOpenCourse(c: AskCard): void;
  onChoose(p: AskProblem, partial: boolean): void;
  onLastStep(): void;
  onSimpler(): void;
  onSimilar(): void;
  onRetake(): void;
  onRetry(): void;
}

/** Share of the bar per stage and the time it usually takes (photo solve measured at 12-20 s, mostly the solving call). */
export const SOLVE_STAGES = {
  photo: { reading: { from: 0, to: 40, ms: 5000 }, solving: { from: 40, to: 95, ms: 12000 } },
  typed: { solving: { from: 0, to: 95, ms: 12000 } },
} as const;

/** Eases towards the stage's end: about 90 % of the way after the usual time, never reaching it, so a slow call never looks stuck at 100 %. */
export function solveProgress(seg: { from: number; to: number; ms: number }, elapsedMs: number): number {
  return seg.from + (seg.to - seg.from) * (1 - Math.exp((-2.3 * Math.max(0, elapsedMs)) / seg.ms));
}

/** Waiting for a solve: label, step 1/2 (photo) and a progress bar. The bar is time-based; the server only says which stage it is in. */
function SolveWait({ stage }: { stage: "reading" | "solving" }) {
  const { t } = useTranslation();
  const photo = useRef(stage === "reading"); // a typed problem skips "reading": one stage, no step count
  const since = useRef(performance.now());
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    since.current = performance.now();
    setNow(since.current);
    const id = window.setInterval(() => setNow(performance.now()), 200);
    return () => window.clearInterval(id);
  }, [stage]);
  const seg = photo.current ? SOLVE_STAGES.photo[stage] : SOLVE_STAGES.typed.solving;
  const pct = Math.round(solveProgress(seg, now - since.current));
  return (
    <div className="solve-wait" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-valuetext={t(`ask.stage.${stage}`)}>
      <p className="sw-label">
        <span>{t(`ask.stage.${stage}`)}</span>
        {photo.current && <span className="sw-step">{stage === "reading" ? "1/2" : "2/2"}</span>}
      </p>
      <div className="sw-track">
        <i style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

const ERR_KEYS = new Set(["model_unavailable", "network", "role_mismatch", "file_too_large"]);

/** One answer of Mực: every state of the solve / learn flows (hs-08). `latest` turns keep their follow-up buttons. */
export function AiBubble({ turn, latest, busy, lang, h }: { turn: AiTurn; latest: boolean; busy: boolean; lang: "vi" | "en"; h: AiHandlers }) {
  const { t } = useTranslation();
  const idle = latest && !busy && !turn.open;
  const empty = !turn.answer && !turn.courses && !turn.message && !turn.choices && !turn.problem && !turn.solution && !turn.similar && !turn.error;
  const sol = turn.solution;
  const lastShown = !!turn.lastStep;
  const retakeTips = turn.message?.tips?.length ? turn.message.tips : (t("ask.retake.tips", { returnObjects: true }) as string[]);

  return (
    <div className="msg-ai">
      <span className="logo-mark" aria-hidden="true">
        M
      </span>
      <div className="body" aria-live="polite" aria-busy={turn.open}>
        {turn.stage === "reading" || turn.stage === "solving" ? (
          <SolveWait stage={turn.stage} />
        ) : turn.stage ? (
          <p className="wait" role="status">
            <span className="dots" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            {t(`ask.stage.${turn.stage}`)}
          </p>
        ) : (
          turn.open && empty && (
            <p className="wait" role="status">
              <span className="dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              {t("ask.thinking")}
            </p>
          )
        )}
        {turn.cancelled && <p className="muted">{t("ask.stopped")}</p>}

        {turn.answer && (
          <div className="ans">
            <p>{turn.answer}</p>
            <SpeakButton text={turn.answer} lang={lang} label={t("ask.readAloud")} />
          </div>
        )}

        {turn.courses && turn.courses.items.length > 0 && (
          <CourseCards items={turn.courses.items} startWith={turn.courses.startWith} suggestedAllAges={turn.courses.suggestedAllAges} adder={h.adder} onOpen={h.onOpenCourse} />
        )}

        {turn.message && (
          <div className="msg-note">
            {turn.message.kind === "retake" && <p className="err-title">{turn.message.where ? t("ask.retake.titleWhere", { where: turn.message.where }) : t("ask.retake.title")}</p>}
            <p>{turn.message.text || t(`ask.msg.${turn.message.kind}`, { defaultValue: "" })}</p>
            {turn.message.kind === "retake" && (
              <ul className="err-tips">
                {retakeTips.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            )}
            {latest && !busy && (turn.message.kind === "retake" || turn.message.kind === "bad_image" || turn.message.kind === "no_problem") && !turn.choices && (
              <div className="acts">
                <button className="btn btn-primary" type="button" onClick={h.onRetake}>
                  <Icon name="camera" />
                  <span>{t("ask.retake.again")}</span>
                </button>
              </div>
            )}
          </div>
        )}

        {turn.choices && turn.choices.problems.length > 0 && (
          <div className="choices" data-guide="ask-choices" data-guide-label={t("ask.choose.solve")}>
            <p className="small muted">{turn.choices.reason === "partial" ? t("ask.choose.partial") : t("ask.choose.multiple", { count: turn.choices.problems.length })}</p>
            <ul className="choice-list">
              {turn.choices.problems.map((p) => (
                <li className="choice" key={p.id}>
                  <b className="ask-chip">{p.label}</b>
                  <Md md={p.text} className="inline" />
                  {idle && (
                    <button className="btn btn-ghost" type="button" onClick={() => h.onChoose(p, turn.choices?.reason === "partial")}>
                      {turn.choices?.reason === "partial" ? t("ask.choose.only", { label: p.label.toLowerCase() }) : t("ask.choose.solve")}
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {turn.choices.reason === "partial" && latest && !busy && (
              <div className="acts">
                <button className="btn btn-primary" type="button" onClick={h.onRetake}>
                  <Icon name="camera" />
                  <span>{t("ask.retake.again")}</span>
                </button>
              </div>
            )}
          </div>
        )}

        {turn.problem && (
          <div className="problem oli" aria-label={t("ask.solve.problem")}>
            <b className="ask-chip">{turn.problem.label}</b>
            <Md md={turn.problem.text} />
          </div>
        )}

        {sol && (
          <div className="solution" data-guide="ask-solution" data-guide-label={t("ask.solve.problem")}>
            <ol className="solve-steps">
              {sol.steps.map((s, i) => (
                <li key={i}>
                  <div>
                    <b>{s.title}</b>
                    <Md md={s.md} className="m" />
                  </div>
                </li>
              ))}
              {lastShown && turn.lastStep && (
                <li>
                  <div>
                    <b>{turn.lastStep.title}</b>
                    <Md md={turn.lastStep.md} className="m" />
                  </div>
                </li>
              )}
              {sol.lastStepWithheld && !lastShown && (
                <li className="locked">
                  <div>
                    <span>{t("ask.solve.lastLocked")}</span>
                    <p>
                      <button className="btn btn-ghost" type="button" onClick={h.onLastStep} disabled={busy}>
                        {t("ask.solve.showLast")}
                      </button>
                    </p>
                    {turn.note && <p className="small muted">{turn.note}</p>}
                  </div>
                </li>
              )}
            </ol>
            {sol.tip && (
              <p className="tip-card">
                <Icon name="bulb" />
                <span>
                  <b>{t("ask.solve.tip")}:</b> {sol.tip}
                </span>
              </p>
            )}
            {idle && (
              <div className="acts">
                <button className="btn btn-ghost" type="button" onClick={h.onSimpler}>
                  <Icon name="refresh" />
                  <span>{t("ask.solve.simpler")}</span>
                </button>
                <button className="btn btn-primary" type="button" onClick={h.onSimilar}>
                  <Icon name="quiz" />
                  <span>{t("ask.solve.similar")}</span>
                </button>
              </div>
            )}
          </div>
        )}

        {turn.similar && (
          <div className="similar">
            <p className="err-title">{t("ask.solve.similarTitle")}</p>
            <ol className="solve-steps">
              {turn.similar.map((s, i) => (
                <li key={i}>
                  <div>
                    <Md md={s.problem_md} className="m" />
                    <details className="reveal">
                      <summary>{t("ask.solve.showAnswer")}</summary>
                      <Md md={s.answer_md} />
                    </details>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}

        {turn.error && (
          <div className="msg-note" role="alert">
            <p>{t(ERR_KEYS.has(turn.error.code) ? `ask.err.${turn.error.code}` : "ask.err.unknown")}</p>
            {latest && !busy && (
              <div className="acts">
                <button className="btn btn-ghost" type="button" onClick={h.onRetry}>
                  <Icon name="refresh" />
                  <span>{t("ask.err.retry")}</span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
