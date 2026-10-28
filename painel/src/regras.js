// Regras do painel que não dependem do banco: nomes, links de contato e a mensagem de WhatsApp.

export const ETAPAS = [
  { id: "lead_novo", nome: "Lead novo" },
  { id: "em_contato", nome: "Em contato" },
  { id: "interessado", nome: "Cliente interessado" },
  { id: "fechado", nome: "Fechado" },
];
export const NOMES_ETAPA = Object.fromEntries(ETAPAS.map((e) => [e.id, e.nome]));
export const CLASSES = [
  { id: "potencial", nome: "Potencial" },
  { id: "talvez", nome: "Talvez" },
  { id: "pouco", nome: "Pouco potencial" },
];
export const SERVICOS = [
  { id: "maps", nome: "Google Maps" },
  { id: "site", nome: "Site" },
  { id: "desenvolvimento", nome: "Desenvolvimento" },
];
export const TIPOS_CONTATO = ["ligacao", "whatsapp", "visita", "email", "anotacao"];
export const NOMES_REDES = {
  instagram: "Instagram", facebook: "Facebook", tiktok: "TikTok", youtube: "YouTube",
  linkedin: "LinkedIn", linktree: "Linktree", ifood: "iFood", x: "X (Twitter)",
};
export const SITUACOES = {
  sem_site: "Sem site",
  so_rede_social: "Só rede social",
  site_fraco: "Site gratuito/fraco",
  fora_do_ar: "Site fora do ar",
  site_proprio: "Tem site próprio",
};

// ---------- Telefone e WhatsApp (mesmas regras do bot em Python) ----------
export function normalizarWhatsapp(telefone) {
  let numero = String(telefone || "").replace(/\D/g, "").replace(/^0+/, "");
  if (numero.startsWith("55") && (numero.length === 12 || numero.length === 13)) numero = numero.slice(2);
  if (numero.length !== 10 && numero.length !== 11) return "";
  return "55" + numero;
}

export function ehCelular(telefone) {
  const numero = normalizarWhatsapp(telefone);
  return numero.length === 13 && numero[4] === "9";
}

const TEXTOS_SERVICO = {
  maps: "vi o perfil de vocês no Google Maps e tenho algumas ideias para ele aparecer melhor para quem procura na região.",
  site: "vi vocês no Google Maps e reparei que ainda não têm um site próprio. Trabalho justamente com isso aqui na região.",
  desenvolvimento: "vi vocês no Google Maps e trabalho com automações de atendimento e agendamento para negócios da região.",
};

export function mensagemInicial(lead, seuNome) {
  const angulo = (lead.analise_ia?.angulo || "").trim();
  let corpo = angulo || TEXTOS_SERVICO[lead.servico_principal] || "vi vocês no Google Maps e queria conversar rapidinho.";
  if (!angulo) corpo = corpo[0].toUpperCase() + corpo.slice(1);
  return `Olá, ${lead.nome || ""}! Tudo bem? Meu nome é ${seuNome || ""}. ${corpo}\n\nPosso te explicar como funciona?`;
}

export function linkWhatsapp(lead, texto) {
  const contato = lead.whatsapp || normalizarWhatsapp(lead.telefone);
  const numero = lead.whatsapp || (ehCelular(contato) ? contato : "");
  return numero ? `https://wa.me/${numero}?text=${encodeURIComponent(texto)}` : "";
}

export function linkLigar(lead) {
  const numero = lead.whatsapp || normalizarWhatsapp(lead.telefone);
  return numero ? `tel:+${numero}` : "";
}

// Acrescenta ao lead os campos que o painel mostra (links prontos, rótulos)
export function enriquecer(lead, seuNome) {
  const mensagem = mensagemInicial(lead, seuNome);
  return {
    ...lead,
    situacao_rotulo: SITUACOES[lead.situacao_site] || "",
    mensagem,
    link_whatsapp: linkWhatsapp(lead, mensagem),
    link_ligar: linkLigar(lead),
  };
}
