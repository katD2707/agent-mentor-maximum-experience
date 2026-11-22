import { useEffect, useRef, type ReactNode } from "react";

/** A wooden confirm dialog: Esc and a tap outside close it, Tab stays inside, focus starts on the first button. */
export function ArDialog({ title, children, onClose }: { title: string; children: ReactNode; onClose(): void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    box.current?.querySelector<HTMLElement>("button")?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") return onClose();
      if (e.key !== "Tab" || !box.current) return;
      const f = [...box.current.querySelectorAll<HTMLElement>("button:not([disabled])")];
      if (!f.length) return;
      const i = f.indexOf(document.activeElement as HTMLElement);
      e.preventDefault();
      f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
    };
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("keydown", key);
      opener?.focus?.();
    };
  }, [onClose]);
  return (
    <>
      <div className="ar-scrim" onClick={onClose} />
      <div className="ar-dlg" ref={box} role="alertdialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        {children}
      </div>
    </>
  );
}
