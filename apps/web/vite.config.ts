import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const apiTarget = env.CHANGESAFE_API_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": apiTarget,
        "/healthz": apiTarget,
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./tests/setup.ts"],
    },
  };
});
