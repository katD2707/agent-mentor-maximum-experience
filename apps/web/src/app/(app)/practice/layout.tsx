import type { Metadata } from "next";
import type { ReactNode } from "react";
import { RoleGate } from "@/components/AuthGate";
import "./practice.css";

export const metadata: Metadata = { title: "Luyện tập" };

/** Practice, mock exams and the diagnostic are for THPT learners (the gateway refuses NCS too). */
export default function PracticeLayout({ children }: { children: ReactNode }) {
  return (
    <RoleGate role="thpt" fallback="/chat">
      {children}
    </RoleGate>
  );
}
