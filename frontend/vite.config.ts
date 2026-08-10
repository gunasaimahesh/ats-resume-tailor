import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // In dev mode, forward API calls to the FastAPI server.
      "/api": "http://localhost:8000",
    },
  },
});
