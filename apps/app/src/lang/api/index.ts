import { isMock } from "../../api";
import { httpLg } from "./http";
import { mockLg } from "./mock";
import type { LgApi } from "./types";

/** The Làng gà endpoints: the gateway, or the in-browser mock with VITE_API_MOCK=1. */
export const lg: LgApi = isMock ? mockLg : httpLg;
export * from "./types";
export { streamChat, type ChatEvent, type ChatRequest } from "./chat";
export { mockGiveXp, mockSeedWeek } from "./mock";
