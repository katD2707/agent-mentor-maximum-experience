import { artFile } from "../../subjects";
import { cropVars } from "../../chickenArt";
import "../../styles/lang.css";
/** Small glyphs the Làng gà screens share and the shared Icon set does not have. */
export const FlameIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 2c1 4 5 6 5 11a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-4-1-6 1-10z" />
  </svg>
);
export const CheckIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </svg>
);

/** A chicken's costume at its growth stage (the angry one when it is angry); a stage with no drawing shows the grown one. */
export function ChickenImg({ art, stage, className, angry }: { art: string; stage: number; className?: string; angry?: boolean }) {
  const base = import.meta.env.BASE_URL;
  const file = artFile(art, stage, angry);
  return (
    <img
      className={`ga-crop${className ? ` ${className}` : ""}`}
      style={cropVars(art, stage, { angry })}
      src={`${base}ga/${file}`}
      alt=""
      onError={(e) => {
        const img = e.currentTarget;
        const fb = `${base}ga/${art}.webp`;
        if (!img.src.endsWith(fb)) img.src = fb;
      }}
    />
  );
}
