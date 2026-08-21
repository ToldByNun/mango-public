import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    resolve: {
      extensions: [".ts", ".js"],
    },
    watch: {
      ignored: ["**/.mango/**", "**/.devdeck/**", "**/math_utils.py", "**/test_math_utils.py"],
    },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
  },
  renderer: {
    resolve: {
      alias: {
        "@": resolve("src/renderer/src"),
        "@shared": resolve("src/shared"),
      },
      extensions: [".tsx", ".ts", ".jsx", ".js"],
    },
    plugins: [react()],
  },
});
