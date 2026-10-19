import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Pre-bundle every dependency up front so the first page load never stalls
  // while Vite discovers and re-optimises imports.
  optimizeDeps: {
    include: ["react", "react-dom/client", "react/jsx-dev-runtime", "react-router-dom", "recharts", "lucide-react"],
  },
  server: {
    port: 5173,
    // In development every /api request goes to the FastAPI backend.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
