import { defineConfig } from "vite";

export default defineConfig({
  build: { outDir: "dist", chunkSizeWarningLimit: 1200 },
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
