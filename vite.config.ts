import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => {
  const token = loadEnv(mode, process.cwd(), "").SERVICE_TOKEN;
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          headers: {
            "x-service-token": token || "",
            "x-app-origin": "http://127.0.0.1:5173",
          },
        },
      },
    },
  };
});
