/** Read text aloud with the platform voice (picture-first mode for grades 1-5). No-op if unsupported. */
export function speak(text: string, lang: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang === "en" ? "en-US" : "vi-VN";
  window.speechSynthesis.speak(u);
}
