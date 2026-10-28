// Conexão com o banco no Supabase. Os valores vêm do arquivo painel/.env
// (VITE_SUPABASE_URL e VITE_SUPABASE_CHAVE). A chave aqui é a "publishable":
// ela é pública e pode ir para o navegador. Nunca use a chave "secret" no painel.
import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const chave = import.meta.env.VITE_SUPABASE_CHAVE;

export const configurado = Boolean(url && chave);
export const supabase = configurado ? createClient(url, chave, { auth: { persistSession: false } }) : null;
