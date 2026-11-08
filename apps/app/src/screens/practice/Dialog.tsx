import { useEffect } from "react";

/** A small modal (Esc and a tap outside close it). */
export function Dialog({ title, children, onClose }: { title: string; children: React.ReactNode; onClose(): void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="pr-scrim" onClick={onClose}>
      <div className="pr-dialog oli" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}
