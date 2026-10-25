import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import ui from "@nuxt/ui/vite";
export default defineConfig({
  plugins: [
    vue(),
    ui({
      colorMode: false,
      icon: { clientBundle: { scan: true } },
      ui: { colors: { primary: "emerald", neutral: "slate" } },
    }),
  ],
  server: { host: "127.0.0.1", proxy: { "/api": "http://127.0.0.1:8000" } },
  preview: { host: "127.0.0.1" },
});
