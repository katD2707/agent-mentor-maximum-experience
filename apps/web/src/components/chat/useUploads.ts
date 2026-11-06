"use client";

import { useCallback, useState } from "react";
import { getApi } from "@/lib/api";
import { randomId } from "@/lib/format";
import type { ChatAttachment } from "@/lib/types";
import { errorText } from "../ui";

export interface PendingUpload {
  id: string;
  name: string;
  status: "uploading" | "done" | "error";
  result?: ChatAttachment;
  error?: string;
}

const MAX_BYTES = 25 * 1024 * 1024;

export function useUploads() {
  const [items, setItems] = useState<PendingUpload[]>([]);

  const update = (id: string, patch: Partial<PendingUpload>) =>
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...patch } : x)));

  const addFiles = useCallback((files: File[]) => {
    for (const file of files) {
      const id = randomId("up_");
      const name = file.name || `anh-dan-${Date.now()}.png`;
      if (file.size > MAX_BYTES) {
        setItems((xs) => [...xs, { id, name, status: "error", error: "Tệp quá lớn (tối đa 25 MB)." }]);
        continue;
      }
      setItems((xs) => [...xs, { id, name, status: "uploading" }]);
      getApi()
        .upload(file, name)
        .then(
          (r) => update(id, { status: "done", result: r }),
          (e: unknown) => update(id, { status: "error", error: errorText(e) }),
        );
    }
  }, []);

  /** Attach a file that is already in the workspace (e.g. uploaded from the phone). */
  const addExisting = useCallback((att: ChatAttachment) => {
    setItems((xs) =>
      xs.some((x) => x.result?.path === att.path)
        ? xs
        : [...xs, { id: randomId("up_"), name: att.path.split("/").pop() ?? att.path, status: "done", result: att }],
    );
  }, []);

  const remove = useCallback((id: string) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const clear = useCallback(() => setItems([]), []);

  const ready = items.filter((x) => x.status === "done" && x.result).map((x) => x.result!) as ChatAttachment[];
  const uploading = items.some((x) => x.status === "uploading");

  return { items, addFiles, addExisting, remove, clear, ready, uploading };
}

export { guessMime } from "@/lib/chat/reducer";

/** Grab one frame of a screen/window/tab the user picks. */
export async function captureScreen(): Promise<File> {
  const md = navigator.mediaDevices;
  if (!md?.getDisplayMedia) throw new Error("Trình duyệt này không hỗ trợ chụp màn hình. Bạn có thể dán ảnh (Ctrl+V).");
  const stream = await md.getDisplayMedia({ video: true, audio: false });
  try {
    const video = document.createElement("video");
    video.srcObject = stream;
    video.muted = true;
    await video.play();
    await new Promise((r) => setTimeout(r, 150));
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/png"));
    if (!blob) throw new Error("Không chụp được màn hình.");
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    return new File([blob], `chup-man-hinh-${stamp}.png`, { type: "image/png" });
  } finally {
    stream.getTracks().forEach((t) => t.stop());
  }
}
