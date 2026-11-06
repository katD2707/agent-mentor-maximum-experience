"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { IS_MOCK } from "@/lib/api";
import { OPEN_SEARCH_EVENT } from "@/lib/conversationNav";
import { GlobalUi } from "./GlobalUi";
import { Icon, type IconName } from "./Icon";
import { TourProvider } from "./Tour";
import { useMe, useSession } from "./session";
import { ThemeToggle } from "./ThemeToggle";

interface NavItem {
  href: string;
  label: string;
  icon: IconName;
}

function navFor(role: "thpt" | "ncs" | null): NavItem[] {
  const chat: NavItem = { href: "/chat", label: "Trò chuyện", icon: "chat" };
  const goals: NavItem = { href: "/plans", label: "Mục tiêu", icon: "goals" };
  const memory: NavItem = { href: "/memory", label: "Mentor nhớ gì về tôi", icon: "memory" };
  const settings: NavItem = { href: "/settings", label: "Cài đặt", icon: "settings" };
  if (role === "ncs") return [chat, { href: "/research", label: "Nghiên cứu", icon: "research" }, goals, memory, settings];
  return [
    chat,
    { href: "/practice", label: "Luyện tập", icon: "cards" },
    { href: "/progress", label: "Tiến bộ", icon: "chart" },
    goals,
    memory,
    { href: "/reports", label: "Báo cáo phụ huynh", icon: "reports" },
    settings,
  ];
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <TourProvider surface="app">
      <Shell>{children}</Shell>
    </TourProvider>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const me = useMe();
  const { logout } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const items = navFor(me.role);
  const current = items.find((i) => pathname === i.href || pathname.startsWith(i.href + "/"));

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="shell" data-nav-open={open}>
      <a href="#main" className="skip-link">
        Bỏ qua điều hướng
      </a>
      {open && <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <nav className="sidebar" aria-label="Điều hướng chính" id="sidebar">
        <Link href="/chat" className="brand" onClick={() => setOpen(false)}>
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          Mentor
        </Link>
        <ul className="nav">
          {items.map((i) => {
            const active = current?.href === i.href;
            return (
              <li key={i.href}>
                <Link
                  href={i.href}
                  aria-current={active ? "page" : undefined}
                  data-tour={i.href === "/practice" ? "nav-practice" : undefined}
                  onClick={() => setOpen(false)}
                >
                  <Icon name={i.icon} className="nav-icon" />
                  {i.label}
                </Link>
              </li>
            );
          })}
        </ul>
        <div className="sidebar-footer">
          <button
            type="button"
            className="btn btn-ghost btn-sm guide-link"
            onClick={() => {
              setOpen(false);
              window.dispatchEvent(new Event(OPEN_SEARCH_EVENT));
            }}
          >
            <Icon name="research" size={16} /> Tìm kiếm <kbd>Ctrl K</kbd>
          </button>
          <div className="who">
            <div style={{ fontWeight: 600 }}>{me.display_name}</div>
            <div className="faint" style={{ fontSize: "0.8rem" }}>
              {me.role === "thpt" ? "Học sinh THPT" : "Nghiên cứu sinh / Sinh viên"} · {me.email}
            </div>
          </div>
          <div className="row">
            <ThemeToggle compact />
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
            >
              <Icon name="logout" size={16} /> Đăng xuất
            </button>
          </div>
        </div>
      </nav>
      <div className="main">
        {IS_MOCK && (
          <div className="mock-banner">
            Chế độ mock: dữ liệu giả lập trong trình duyệt. <Link href="/settings#mock">Đổi dữ liệu mẫu</Link>
          </div>
        )}
        <div className="topbar">
          <button
            type="button"
            className="btn btn-ghost btn-icon"
            aria-label="Mở menu"
            aria-expanded={open}
            aria-controls="sidebar"
            onClick={() => setOpen(true)}
          >
            <Icon name="menu" />
          </button>
          <span className="topbar-title">{current?.label ?? "Mentor"}</span>
        </div>
        <main id="main" tabIndex={-1} style={{ outline: "none", flex: 1, minHeight: 0 }}>
          {children}
        </main>
      </div>
      <GlobalUi />
    </div>
  );
}
