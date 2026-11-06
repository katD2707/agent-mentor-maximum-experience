import type { ReactNode } from "react";

/**
 * Re-mounts on every navigation inside the app shell, so each page rises in briefly (220 ms, fade only under
 * reduced motion). Navigation is occasional, so it earns a short transition; nothing inside a page waits on it.
 */
export default function AppTemplate({ children }: { children: ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
