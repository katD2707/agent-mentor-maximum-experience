"use client";

import { Suspense } from "react";
import { MockEntry } from "@/components/practice/Entry";
import { Loading } from "@/components/ui";

export default function MockPage() {
  return (
    <Suspense fallback={<Loading full />}>
      <MockEntry />
    </Suspense>
  );
}
