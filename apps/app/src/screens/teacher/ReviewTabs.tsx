import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AssetRef, Block, Chapter, CoursePack, Lesson, QuizItem, TeacherTest, UnsureStep } from "../../api";
import { Icon } from "../../components/Icon";
import { questionsByLevel, rightText, STEP_ICON, stepKind, stepLabel } from "../../lib/teacher/steps";
import { StaticBlock, type BlockCtx } from "../courses/blocks";
import { QuizItemView } from "../courses/QuizItemView";
import { InteractiveView, Muc, RecallView } from "../courses/StepBlocks";
import "../../styles/lesson.css";
import { StepEditor } from "./StepEditor";

type Patch = Record<string, unknown>;
const noop = () => undefined;
const GAP_RE = /\{\{gap\}\}/g;

/** The step as students see it, read only (same components as the student player). */
function Preview({ b, ctx }: { b: Block; ctx: BlockCtx }) {
  if (b.kind === "quiz")
    return (
      <>
        {b.items.map((item) => (
          <QuizItemView key={item.id} item={item} ctx={ctx} kid={false} onResult={noop} onDone={noop} />
        ))}
      </>
    );
  // drag diagram and recall: the student's own components, so the teacher can try them exactly as students will
  if (b.kind === "interactive")
    return (
      <div className="lesson rv-lesson">
        <InteractiveView key={b.id + b.expr + b.target_y} b={b} muc={<Muc />} onReached={noop} />
      </div>
    );
  if (b.kind === "recall")
    return (
      <div className="lesson rv-lesson">
        <RecallView key={b.id + b.items.map((i) => i.prompt + i.answer).join("|")} b={b} ctx={ctx} muc={<Muc />} onMark={noop} onFoot={noop} />
      </div>
    );
  return <StaticBlock b={b} ctx={ctx} />;
}

function OneLine({ label, placeholder, onSend }: { label: string; placeholder: string; onSend(text: string): Promise<void> }) {
  const { t } = useTranslation();
  const [v, setV] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="cbox"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!v.trim() || busy) return;
        setBusy(true);
        try {
          await onSend(v.trim());
          setV("");
        } finally {
          setBusy(false);
        }
      }}
    >
      <Icon name="comment" />
      <input type="text" value={v} aria-label={label} placeholder={placeholder} onChange={(e) => setV(e.target.value)} />
      <button className="icon-btn" type="submit" aria-label={t("gv.send")} disabled={!v.trim() || busy}>
        <Icon name="send" />
      </button>
    </form>
  );
}

// ---------------------------------------------------------------- tab: lesson
export function LessonTab({ lesson, ctx, unsure, commented, locked, english, saving, onSave, onSeen, onComment }: { lesson: Lesson; ctx: BlockCtx; unsure: ReadonlyMap<string, UnsureStep>; commented: ReadonlySet<string>; locked: boolean; english: boolean; saving: boolean; onSave(blockId: string, patch: Patch): void; onSeen(blockId: string): void; onComment(blockId: string, text: string): Promise<void> }) {
  const { t } = useTranslation();
  const [at, setAt] = useState(0);
  useEffect(() => setAt(0), [lesson.id]);
  const i = Math.min(at, lesson.blocks.length - 1);
  const b = lesson.blocks[i];
  if (!b) return <p className="none">{t("gv.noSteps")}</p>;
  const un = unsure.get(b.id);
  return (
    <section className="rv" aria-label={t("gv.tabLesson")}>
      <ul className="rv-list" aria-label={t("gv.stepsAria")}>
        {lesson.blocks.map((x, n) => (
          <li key={x.id}>
            <button type="button" className="si" aria-current={n === i} onClick={() => setAt(n)}>
              <span className="sn">{n + 1}</span>
              <Icon name={STEP_ICON[stepKind(x)]} />
              <span className="lb">{stepLabel(x) || t(`gv.kind.${stepKind(x)}`)}</span>
              {unsure.has(x.id) ? <span className="dot maybe" role="img" aria-label={t("gv.unsureDot")} /> : commented.has(x.id) ? <span className="dot said" role="img" aria-label={t("gv.commentDot")} /> : <span />}
            </button>
          </li>
        ))}
      </ul>
      <div className="phone" role="group" aria-label={t("gv.phoneAria")}>
        <div className="pbar">
          <i style={{ width: `${((i + 1) / lesson.blocks.length) * 100}%` }} />
        </div>
        <div className="pv" {...({ inert: true } as object)} data-block={b.id}>
          <Preview b={b} ctx={ctx} />
        </div>
      </div>
      <div className="fields">
        <h2>
          <Icon name={STEP_ICON[stepKind(b)]} />
          {t("gv.stepN", { n: i + 1 })} · {t(`gv.kind.${stepKind(b)}`)}
        </h2>
        {un && (
          <p className="unsure" role="note">
            <Icon name="flag" />
            <span>{ctx.lang === "en" ? un.reason_en : un.reason_vi}</span>
            <button type="button" className="btn" onClick={() => onSeen(b.id)}>
              {t("gv.seenBtn")}
            </button>
          </p>
        )}
        <StepEditor key={b.id} block={b} english={english} locked={locked} saving={saving} onSave={(p) => onSave(b.id, p)} />
        <OneLine label={t("gv.cmtLabel")} placeholder={t("gv.cmtPlaceholder")} onSend={(text) => onComment(b.id, text)} />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- tab: practice
export function PracticeTab({ pack, locked, saving, onSave }: { pack: CoursePack; locked: boolean; saving: boolean; onSave(blockId: string, patch: Patch): void }) {
  const { t } = useTranslation();
  const levels = questionsByLevel(pack);
  const [open, setOpen] = useState<number | null>(null);
  const [cur, setCur] = useState<{ block_id: string; item: QuizItem } | null>(null);
  const block = cur ? pack.chapters.flatMap((c) => c.lessons).flatMap((l) => l.blocks).find((x) => x.id === cur.block_id) : undefined;
  const q = block && block.kind === "quiz" ? block.items.find((x) => x.id === cur!.item.id) : undefined;
  return (
    <section className="pl" aria-label={t("gv.tabPractice")}>
      <div>
        {levels.map((lv) => (
          <div key={lv.level} className={`lvl${open === lv.level ? " open" : ""}`}>
            <button type="button" aria-expanded={open === lv.level} onClick={() => setOpen(open === lv.level ? null : lv.level)}>
              <Icon name="chev" />
              <span>{t(`gv.levelName.${lv.level}`)}</span>
              <span className="ct">{t("gv.qCount", { n: lv.items.length })}</span>
            </button>
            {open === lv.level && (
              <ul className="qs">
                {lv.items.length === 0 && <li className="none">{t("gv.noQuestions")}</li>}
                {lv.items.map((x, n) => (
                  <li key={x.item.id}>
                    <button type="button" className="qrow" aria-current={cur?.item.id === x.item.id} onClick={() => setCur(x)}>
                      <span className="qn">{n + 1}</span>
                      <span className="qs1">{x.item.stem.replace(GAP_RE, "…")}</span>
                      <span className="qa">{rightText(x.item)}</span>
                      <span />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
      <div className="fields">{block && block.kind === "quiz" && q && <StepEditor key={q.id} block={{ ...block, items: [q] }} english={false} locked={locked} saving={saving} onSave={(p) => onSave(block.id, p)} />}</div>
    </section>
  );
}

// ---------------------------------------------------------------- tab: tests
export function TestsTab({ tests, locked, onSave }: { tests: TeacherTest[]; locked: boolean; onSave(profileId: string, body: { items: number; minutes: number }): void }) {
  const { t } = useTranslation();
  if (!tests.length) return <p className="none">{t("gv.noTests")}</p>;
  return (
    <section className="trows" aria-label={t("gv.tabTests")}>
      {tests.map((x) => (
        <TestRow key={x.profile_id} test={x} locked={locked} onSave={(b) => onSave(x.profile_id, b)} />
      ))}
    </section>
  );
}
function TestRow({ test, locked, onSave }: { test: TeacherTest; locked: boolean; onSave(b: { items: number; minutes: number }): void }) {
  const { t } = useTranslation();
  const [items, setItems] = useState(String(test.items));
  const [minutes, setMinutes] = useState(String(test.minutes));
  useEffect(() => {
    setItems(String(test.items));
    setMinutes(String(test.minutes));
  }, [test.items, test.minutes]);
  const commit = () => {
    const n = Math.round(Number(items));
    const m = Math.round(Number(minutes));
    if (!(n >= 1 && m >= 1)) {
      setItems(String(test.items));
      setMinutes(String(test.minutes));
    } else if (n !== test.items || m !== test.minutes) onSave({ items: n, minutes: m });
  };
  return (
    <div className="trow">
      <b>{test.title}</b>
      <label>
        {t("gv.testItems")}
        <input type="number" min={1} value={items} readOnly={locked} onChange={(e) => setItems(e.target.value)} onBlur={commit} />
      </label>
      <label>
        {t("gv.testMinutes")}
        <input type="number" min={1} value={minutes} readOnly={locked} onChange={(e) => setMinutes(e.target.value)} onBlur={commit} />
      </label>
    </div>
  );
}

// ---------------------------------------------------------------- tab: listen
export function RecapTab({ chapters, locked, english, glossStart, urlOf, onSave, onGloss }: { chapters: Chapter[]; locked: boolean; english: boolean; glossStart: number; urlOf(r: AssetRef | null | undefined): string; onSave(chapterId: string, script: string[]): void; onGloss(n: number): void }) {
  const { t } = useTranslation();
  return (
    <section className="chs" aria-label={t("gv.tabListen")}>
      {english && (
        <label className="f mixr">
          <span className="fl">{t("gv.fGlossStart", { n: glossStart })}</span>
          <input type="range" min={0} max={100} step={10} value={glossStart} disabled={locked} aria-label={t("gv.fGlossStart", { n: glossStart })} onChange={(e) => onGloss(Number(e.target.value))} />
        </label>
      )}
      {chapters.map((c) => (
        <RecapChapter key={c.id} ch={c} locked={locked} urlOf={urlOf} onSave={(s) => onSave(c.id, s)} />
      ))}
    </section>
  );
}
function RecapChapter({ ch, locked, urlOf, onSave }: { ch: Chapter; locked: boolean; urlOf(r: AssetRef | null | undefined): string; onSave(s: string[]): void }) {
  const { t } = useTranslation();
  const [text, setText] = useState((ch.recap?.script ?? []).join("\n\n"));
  const [playing, setPlaying] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  useEffect(() => setText((ch.recap?.script ?? []).join("\n\n")), [ch.recap]);
  useEffect(() => () => audio.current?.pause(), []);
  const src = urlOf(ch.recap?.audio);
  const script = text.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean);
  const dirty = script.join("\n") !== (ch.recap?.script ?? []).join("\n");
  const play = () => {
    if (playing) {
      audio.current?.pause();
      setPlaying(false);
      return;
    }
    if (!src) return;
    audio.current = new Audio(src);
    audio.current.onended = () => setPlaying(false);
    void audio.current.play().catch(() => setPlaying(false));
    setPlaying(true);
  };
  return (
    <div className="ch">
      <div className="ch-h">
        <h2>{ch.title}</h2>
        {ch.recap && <span className="dur">{t("gv.recapMin", { m: Math.max(1, Math.round(ch.recap.duration_s / 60)) })}</span>}
        <span className="grow" />
        {ch.recap && (
          <button type="button" className="btn" onClick={play} disabled={!src} title={src ? undefined : t("gv.noAudio")}>
            <Icon name={playing ? "stop" : "volume"} />
            <span>{playing ? t("gv.listenStop") : t("gv.listenTry")}</span>
          </button>
        )}
      </div>
      {!ch.recap ? (
        <p className="none">{t("gv.recapNone")}</p>
      ) : (
        <>
          <textarea rows={Math.min(12, Math.max(4, script.length * 3))} value={text} readOnly={locked} aria-label={ch.title} onChange={(e) => setText(e.target.value)} />
          {!locked && (
            <button type="button" className="btn btn-primary say-b" disabled={!dirty || !script.length} onClick={() => onSave(script)}>
              <Icon name="check" />
              <span>{t("gv.save")}</span>
            </button>
          )}
        </>
      )}
    </div>
  );
}
