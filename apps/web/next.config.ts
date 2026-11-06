import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The app is fully client-rendered against the gateway; no server-side data fetching.
  images: { unoptimized: true },
  // Do not write AGENTS.md/CLAUDE.md here: AGENTS.md means the mentor identity file in this repo.
  agentRules: false,
  // The floating dev badge covers the sidebar footer (logout button).
  devIndicators: false,
};

export default nextConfig;
