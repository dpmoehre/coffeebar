import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

import { flattenCssLayers } from "./src/cssLayers.js";

function flattenLayersPlugin() {
  return {
    name: "flatten-css-layers",
    apply: "build",
    generateBundle(_opts, bundle) {
      for (const item of Object.values(bundle)) {
        if (item.type !== "asset" || !item.fileName.endsWith(".css")) continue;
        const text = typeof item.source === "string" ? item.source : new TextDecoder().decode(item.source);
        const next = flattenCssLayers(text);
        item.source = typeof item.source === "string" ? next : new TextEncoder().encode(next);
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), flattenLayersPlugin()],
  server: {
    // 开发时前端 5173，API 打到本机 FastAPI
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist" },
});
