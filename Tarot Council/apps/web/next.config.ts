import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // The browser never talks to the Python service directly. Everything goes
  // through app/api/council/[...path], which keeps this a single origin: no CORS
  // preflight on the streaming POST, no API URL in client bundles, and one place
  // to add auth in Phase 2.
  env: {},
};

export default config;
