/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const mascot = fileURLToPath(new URL("../../packages/mentor-mascot", import.meta.url));

const version = (JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string }).version;

/** Gives every build its own service worker bytes, so browsers notice the new build and the old shell cache is dropped. */
const stampWorker = (): Plugin => ({
  name: "stamp-sw",
  apply: "build",
  writeBundle(opts) {
    const file = join(opts.dir ?? "dist", "sw.js");
    writeFileSync(file, readFileSync(file, "utf8").replace("__BUILD_ID__", `${version}-${Date.now().toString(36)}`));
  },
});

export default defineConfig({
  plugins: [react(), stampWorker()],
  define: { __APP_VERSION__: JSON.stringify(version) },
  clearScreen: false,
  resolve: { alias: { "@mentor/mentor-mascot": mascot } },
  server: { port: 5173, strictPort: true, fs: { allow: [".", mascot] } },
  build: { target: "es2022" },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    css: false,
    testTimeout: 30000,
  },
});
