import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // echarts is irreducibly ~590 kB raw (~200 kB gzip) even tree-shaken to the
    // chart types/components this app uses, and it ships zrender inlined so it
    // cannot be split further. It now lives in its own chunk that loads only on
    // chart routes, so we lift the warning threshold just above it while still
    // catching any future chunk that balloons past echarts.
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return;
          if (id.includes("echarts") || id.includes("zrender")) return "echarts";
          if (id.includes("leaflet")) return "leaflet";
          if (
            /react-markdown|remark|micromark|unified|mdast|hast|unist|vfile|bail|trough|devlop|decode-named|character-entities|property-information|space-separated|comma-separated|html-url-attributes|estree|hastscript|web-namespaces|zwitch|stringify-entities/.test(
              id,
            )
          )
            return "markdown";
          if (id.includes("react") || id.includes("scheduler")) return "react";
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
  },
});
