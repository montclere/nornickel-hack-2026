import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Фронт общается с бэкендом по HTTP (CORS на бэке открыт). Адрес API —
// import.meta.env.VITE_API_URL (по умолчанию http://localhost:8000).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true },
});
