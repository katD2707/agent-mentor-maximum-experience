"use client";

import { Suspense } from "react";
import { PracticeHome } from "@/components/practice/Entry";
import { Loading } from "@/components/ui";

export default function PracticePage() {
  return (
    <Suspense fallback={<Loading full />}>
      <PracticeHome />
    </Suspense>
  );
}
