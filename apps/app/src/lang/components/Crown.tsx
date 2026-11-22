/** The small gold crown of a Cao thủ chicken (growth stage 4, level 10+). With `label` it reads "Cao thủ" beside the crown. */
export function Crown({ stage, label }: { stage: number; label?: string }) {
  if (stage < 4) return null;
  return (
    <span className={"lg-crown" + (label ? "" : " solo")} {...(label ? {} : { role: "img", "aria-label": "Cao thủ" })}>
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M3 8l4.5 4L12 5l4.5 7L21 8l-2 11H5L3 8z" />
      </svg>
      {label && <b>{label}</b>}
    </span>
  );
}
