import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Forward API calls to the Flask backend (backend/server.py)
    proxy: {
      "/api": "http://localhost:5001",
    },
  },
});
