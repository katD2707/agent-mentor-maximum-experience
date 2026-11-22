import type { CSSProperties } from "react";
import type { Block } from "../../../api";
import { GlossChip, StaticBlock, type BlockCtx } from "../../kit/blocks";
import { InteractiveView, RecallView } from "../../kit/StepBlocks";
import { QuizItemView } from "../../kit/QuizItemView";
import { chickenSrc, jumpSrc, mockAge, reducedMotion, spriteVars, type Pose } from "../../chickenArt";
import "../../styles/fonts";
import "../../styles/lesson-lg.css";

/** The chicken's picture as the lesson draws it: stands next to its words; jumps when the answer is right. */
export function Sprite({ art, stage, pose = "stand", small }: { art: string; stage: number; pose?: Pose; small?: boolean }) {
  const still = reducedMotion();
  const src = pose === "jump" && !still ? (jumpSrc(art, stage) ?? chickenSrc(art, stage, "stand", true)) : chickenSrc(art, stage, "stand", still);
  return (
    <span className="lp-gsp" aria-hidden="true" style={{ ...spriteVars(art, stage), ...(small ? { "--w": "64px" } : {}) } as CSSProperties}>
      <img className={pose === "jump" ? "lp-hop" : undefined} src={src} alt="" onError={(e) => (e.currentTarget.src = chickenSrc(art, stage, "stand", true))} />
    </span>
  );
}

const noop = () => undefined;

/**
 * One step of a lesson drawn exactly as the lg-04 player draws it (the chicken says the text, quiz items with their own answer
 * area, the drag diagram, "Nhớ lại" cards, media), read only. The teacher's review uses it so teachers see what students see.
 */
export function StepPreview({ block, ctx, art = "toan", stage = 3, band = "g10_12" }: { block: Block; ctx: BlockCtx; art?: string; stage?: number; band?: string }) {
  const sprite = (small = false) => <Sprite art={art} stage={stage} small={small} />;
  let body;
  if (block.kind === "quiz") {
    body = (
      <>
        {block.items.map((item) => (
          <div className="lp-twinbox" key={item.id}>
            <QuizItemView item={item} ctx={ctx} kid={band === "g1_5"} stepped onStage={noop} onResult={noop} onDone={noop} />
          </div>
        ))}
      </>
    );
  } else if (block.kind === "text") {
    const bubble = (
      <div className="lp-say">
        {sprite()}
        <div className="lp-bub">
          <StaticBlock b={block} ctx={ctx} />
        </div>
      </div>
    );
    body = block.gloss && ctx.glossPct !== undefined ? (
      <div className="ls-gl">
        <GlossChip pct={ctx.glossPct} />
        {bubble}
      </div>
    ) : (
      <div className="ls-one">{bubble}</div>
    );
  } else if (block.kind === "interactive") {
    body = (
      <div className="ls-int">
        <InteractiveView key={block.id + block.expr + block.target_y} b={block} muc={sprite(true)} onReached={noop} />
      </div>
    );
  } else if (block.kind === "recall") {
    body = (
      <div className="ls-rc">
        <RecallView key={block.id + block.items.map((i) => i.prompt + i.answer).join("|")} b={block} ctx={ctx} muc={sprite(true)} onMark={noop} onFoot={noop} />
      </div>
    );
  } else {
    body = (
      <div className="ls-media">
        <StaticBlock b={block} ctx={ctx} />
      </div>
    );
  }
  return (
    <div className="lp rv-lp" data-age={mockAge(band)} data-lang={ctx.lang}>
      <div className="lp-lesson rv-lesson">
        <div className="lp-stage">
          <div className="lp-in lesson">{body}</div>
        </div>
      </div>
    </div>
  );
}
