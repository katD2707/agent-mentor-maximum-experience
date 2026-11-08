import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup, configure } from "@testing-library/react";

vi.stubEnv("VITE_API_MOCK", "1");

// The mock API answers on real timers, and files run in parallel jsdom workers. On a busy machine a screen takes
// seconds to settle, so the 1 s findBy/waitFor default fails at random. Waits return as soon as the screen is ready.
configure({ asyncUtilTimeout: 10000 });

// jsdom has no Web Animations or matchMedia; the mascot and motion helpers use both.
if (!Element.prototype.animate) {
  Element.prototype.animate = function () {
    return { finished: Promise.resolve(), cancel() {}, finish() {}, play() {}, onfinish: null } as unknown as Animation;
  };
}
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});
