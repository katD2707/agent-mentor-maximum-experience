import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Mentor (cửa sổ nhỏ)" };

export default function PopupLayout({ children }: { children: ReactNode }) {
  return children;
}
