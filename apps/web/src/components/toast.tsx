"use client";

import { createContext, useContext, type ReactNode } from "react";
import { Toaster, toast } from "sonner";

type ToastKind = "info" | "ok" | "error";

const ToastContext = createContext<((text: string, kind?: ToastKind) => void) | null>(null);

/** Plain text toasts; same signature as before Sonner, so callers did not change. */
function push(text: string, kind: ToastKind = "info") {
  if (kind === "error") toast.error(text, { duration: 8000 });
  else if (kind === "ok") toast.success(text);
  else toast(text);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <ToastContext.Provider value={push}>
      {children}
      <Toaster
        position="bottom-right"
        visibleToasts={4}
        gap={10}
        offset={16}
        mobileOffset={12}
        closeButton
        containerAriaLabel="Thông báo"
        toastOptions={{
          duration: 4500,
          unstyled: true,
          closeButtonAriaLabel: "Đóng thông báo",
          classNames: {
            toast: "toast",
            title: "toast-title",
            description: "toast-desc",
            closeButton: "toast-close",
            success: "toast-ok",
            error: "toast-error",
            icon: "toast-icon",
          },
        }}
      />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const v = useContext(ToastContext);
  if (!v) throw new Error("useToast outside ToastProvider");
  return v;
}
