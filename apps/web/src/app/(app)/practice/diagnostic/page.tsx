"use client";

import { Suspense } from "react";
import { DiagnosticEntry } from "@/components/practice/Entry";
import { Loading } from "@/components/ui";

export default function DiagnosticPage() {
  return (
    <Suspense fallback={<Loading full />}>
      <DiagnosticEntry />
    </Suspense>
  );
}
