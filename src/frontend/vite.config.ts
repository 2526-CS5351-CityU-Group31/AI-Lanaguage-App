import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],

  server: {
    port: 5173,

    proxy: {
      "/api": {
        target:
          process.env.VITE_API_PROXY_TARGET ??
          "http://localhost:8000",

        changeOrigin: true,

        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },

  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/tests/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
