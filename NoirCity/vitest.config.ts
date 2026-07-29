import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": root,
      // See test/stubs/server-only.ts for why this is aliased rather than
      // removed from the modules under test.
      "server-only": `${root}test/stubs/server-only.ts`,
    },
  },
  test: {
    include: ["lib/**/*.test.ts", "scripts/**/*.test.ts"],
    environment: "node",
  },
});
