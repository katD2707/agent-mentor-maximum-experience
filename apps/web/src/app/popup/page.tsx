"use client";

import { AuthGate } from "@/components/AuthGate";
import { GlobalUi } from "@/components/GlobalUi";
import { ChatView } from "@/components/chat/ChatView";
import { TourProvider } from "@/components/Tour";

/**
 * Compact, borderless chat for the Tauri pop-up panel. `desktopNudges`: forwards nudges to the shell
 * (`desktop_nudge`) and applies balloon clicks (`mentor://nudge-action`) through the API (CONTRACTS 9).
 */
export default function PopupPage() {
  return (
    <AuthGate>
      <TourProvider surface="popup">
        <div className="popup">
          <ChatView compact desktopNudges />
          <GlobalUi />
        </div>
      </TourProvider>
    </AuthGate>
  );
}
