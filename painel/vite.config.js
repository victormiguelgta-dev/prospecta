import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em desenvolvimento (npm run dev), as chamadas para /api vão para o servidor Python na porta 8000.
// No build (npm run build), o painel vai para painel/dist e o próprio Python serve os arquivos.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
