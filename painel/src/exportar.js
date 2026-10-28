// Exporta os leads para planilha (CSV, abre no Excel e no Google Planilhas) ou JSON.
import { CLASSES, ETAPAS, NOMES_REDES, SERVICOS, SITUACOES } from "./regras.js";

const NOMES_CLASSE = Object.fromEntries(CLASSES.map((c) => [c.id, c.nome]));
const NOMES_ETAPA = Object.fromEntries(ETAPAS.map((e) => [e.id, e.nome]));
const NOMES_SERVICO = Object.fromEntries(SERVICOS.map((s) => [s.id, s.nome]));

function paraLinha(l) {
  const redes = l.redes || {};
  const linha = {
    "Nome": l.nome,
    "Classe": NOMES_CLASSE[l.classe] || "",
    "Nota de potencial": l.nota_potencial ?? "",
    "O que vender": (l.oportunidades || []).map((o) => NOMES_SERVICO[o.servico] || o.servico).join(", "),
    "Serviço principal": NOMES_SERVICO[l.servico_principal] || "",
    "Etapa": NOMES_ETAPA[l.etapa] || "",
    "Estado": l.estado || "",
    "Categoria": l.categoria || "",
    "Telefone": l.telefone || "",
    "WhatsApp": l.whatsapp || "",
    "E-mail": l.email || "",
    "Situação do site": SITUACOES[l.situacao_site] || "",
    "Site": l.site || "",
    "Saúde do Maps": l.saude_maps ?? "",
    "Nota Google": l.nota ?? "",
    "Avaliações": l.avaliacoes ?? "",
  };
  for (const [rede, nome] of Object.entries(NOMES_REDES)) linha[nome] = redes[rede] || "";
  Object.assign(linha, {
    "Posts no Instagram": l.instagram_posts ?? "",
    "Seguidores no Instagram": l.instagram_seguidores ?? "",
    "Endereço": l.endereco || "",
    "Região": l.regiao || "",
    "Próximo passo": l.proximo_passo || "",
    "Data do próximo passo": l.data_proximo_passo || "",
    "Maps": l.maps_url || "",
  });
  return linha;
}

function celula(valor) {
  let texto = String(valor ?? "");
  // Texto que começa com = + - @ viraria fórmula no Excel (dados vêm da internet)
  if (typeof valor === "string" && /^[=+\-@]/.test(texto)) texto = "'" + texto;
  return /[";\n\r]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

// Separador ";" e BOM no começo: é o que o Excel em português abre certo, com acentos
export function paraCsv(leads) {
  const linhas = leads.map(paraLinha);
  if (!linhas.length) return "\uFEFF";
  const colunas = Object.keys(linhas[0]);
  const corpo = [colunas, ...linhas.map((l) => colunas.map((c) => l[c]))].map((l) => l.map(celula).join(";"));
  return "\uFEFF" + corpo.join("\r\n") + "\r\n";
}

export function paraJson(leads) {
  return JSON.stringify(leads, null, 2);
}
