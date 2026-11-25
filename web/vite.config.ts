import { defineConfig } from "vitest/config";

// Relative base: the same build works at the GitHub Pages project path and locally.
export default defineConfig({
  base: "./",
  build: { target: "es2022", sourcemap: true },
  test: { include: ["tests/**/*.test.ts"], environment: "node" },
});
