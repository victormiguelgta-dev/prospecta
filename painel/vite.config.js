import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// npm run dev: painel com recarga automática (lê o painel/.env com o endereço do Supabase).
// npm run build: gera a pasta painel/dist, que o Netlify publica.
export default defineConfig({
  plugins: [react()],
  server: { host: true },
  build: { outDir: "dist", emptyOutDir: true },
});
