import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { DesktopBridge } from "@/components/DesktopBridge";
import { SessionProvider } from "@/components/session";
import { ToastProvider } from "@/components/toast";
import { THEME_SCRIPT } from "@/components/ThemeToggle";
import { TEXT_SCALE_SCRIPT } from "@/lib/uiPrefs";
import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Mentor", template: "%s · Mentor" },
  description: "Mentor học tập cá nhân với trí nhớ dài hạn",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f7f5" },
    { media: "(prefers-color-scheme: dark)", color: "#121614" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <script dangerouslySetInnerHTML={{ __html: TEXT_SCALE_SCRIPT }} />
      </head>
      <body>
        <SessionProvider>
          <ToastProvider>{children}</ToastProvider>
          <DesktopBridge />
        </SessionProvider>
      </body>
    </html>
  );
}
