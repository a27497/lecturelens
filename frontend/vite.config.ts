import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backendTarget = env.VITE_BACKEND_PROXY_TARGET || "http://127.0.0.1:8080";

  return {
    plugins: [vue()],
    server: {
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/actuator": {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
