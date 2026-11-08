/** Ripple where the finger or mouse lands on a .btn (off under reduced motion). */
export function installRipple() {
  document.addEventListener("pointerdown", (e) => {
    const target = e.target as Element | null;
    const b = target?.closest?.(".btn") as HTMLElement | null;
    if (!b || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const r = b.getBoundingClientRect();
    const s = Math.max(r.width, r.height) * 2.2;
    const rp = document.createElement("span");
    rp.className = "ripple";
    rp.style.width = rp.style.height = s + "px";
    rp.style.left = e.clientX - r.left - s / 2 + "px";
    rp.style.top = e.clientY - r.top - s / 2 + "px";
    b.appendChild(rp);
    setTimeout(() => rp.remove(), 600);
  });
}
