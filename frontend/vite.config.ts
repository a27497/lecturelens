import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backendTarget = env.VITE_BACKEND_PROXY_TARGET || "http://127.0.0.1:8080";
  const round3Target = env.ROUND3_PROXY_TARGET;
  const proxy = {
    ...(round3Target ? { "/api/round3": { target: round3Target } } : {}),
    "/api": {
      target: backendTarget,
      changeOrigin: true,
    },
    "/actuator": {
      target: backendTarget,
      changeOrigin: true,
    },
  };

  return {
    plugins: [vue()],
    server: {
      proxy,
    },
    preview: { proxy },
  };
});
