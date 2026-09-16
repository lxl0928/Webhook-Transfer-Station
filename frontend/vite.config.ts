import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "element-plus": ["element-plus"],
          "vue-vendor": ["vue", "vue-router"],
          "http-client": ["axios"],
        },
      },
    },
  },
  server: {
    proxy: Object.fromEntries(
      ["/api", "/webhooks", "/health", "/docs", "/openapi.json"].map((path) => [
        path,
        { target: "http://127.0.0.1:8000", changeOrigin: true },
      ]),
    ),
  },
});
