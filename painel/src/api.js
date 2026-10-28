// Conversa do painel com o banco no Supabase.
// O painel lê e grava os leads direto no banco. O trabalho pesado (buscar no Maps,
// analisar com IA, diagnóstico) vira um "pedido" na fila, que o trabalhador do seu PC executa.
import { supabase } from "./supabase.js";
import {
  CLASSES, ETAPAS, NOMES_ETAPA, NOMES_REDES, SERVICOS, SITUACOES, TIPOS_CONTATO, enriquecer, normalizarWhatsapp,
} from "./regras.js";

// Na lista não vêm as avaliações lidas (são só para classificar e pesam bastante)
const COLUNAS_LISTA = [
  "id", "nicho", "regiao", "nome", "categoria", "endereco", "telefone", "whatsapp", "email", "site",
  "situacao_site", "instagram", "redes", "instagram_seguidores", "instagram_posts", "logo_url", "maps_url",
  "nota", "avaliacoes", "nota_potencial", "classe", "saude_maps", "oportunidades", "servico_principal",
  "analise_ia", "etapa", "estado", "motivo", "proximo_passo", "data_proximo_passo", "etapa_em", "criado_em",
].join(",");
const PAGINA = 1000;   // o Supabase devolve no máximo 1000 linhas por vez

// O PC conta como ligado se avisou nos últimos 90 segundos
const PC_LIGADO_SEGUNDOS = 90;

function conferir({ data, error }) {
  if (error) throw new Error(error.message || "Erro ao falar com o banco");
  return data;
}

// Busca todas as páginas de uma consulta (montar() devolve a consulta nova a cada página)
async function todas(montar) {
  const linhas = [];
  for (let inicio = 0; ; inicio += PAGINA) {
    const pagina = conferir(await montar().range(inicio, inicio + PAGINA - 1));
    linhas.push(...pagina);
    if (pagina.length < PAGINA) return linhas;
  }
}

// Texto da busca sem os caracteres que têm significado no filtro do Supabase
function limparTexto(texto) {
  return String(texto || "").replace(/[,()*%"\\]/g, " ").replace(/\s+/g, " ").trim();
}

let seuNome = "";
const comLinks = (lead) => enriquecer(lead, seuNome);

function diasDesde(valor) {
  if (!valor) return null;
  const dias = Math.floor((Date.now() - new Date(valor).getTime()) / 86400000);
  return Number.isNaN(dias) ? null : Math.max(0, dias);
}

async function anotar(leadId, anotacao, tipo = "anotacao") {
  conferir(await supabase.from("contatos").insert({ lead_id: leadId, tipo, anotacao }));
}

async function atualizarLead(id, campos) {
  conferir(await supabase.from("leads").update(campos).eq("id", id));
}

async function leadAtual(id) {
  const lead = conferir(await supabase.from("leads").select("*").eq("id", id).maybeSingle());
  if (!lead) throw new Error("Lead não encontrado");
  return lead;
}

async function criarPedido(tipo, parametros) {
  return conferir(await supabase.from("pedidos").insert({ tipo, parametros }).select().single());
}

export const api = {
  // Números do menu, nome para a mensagem e se o PC está ligado
  async estado() {
    const [contagem, ajustes, trabalhadores, pedidosAbertos] = await Promise.all([
      todas(() => supabase.from("leads").select("estado,etapa,classe,data_proximo_passo")),
      supabase.from("ajustes").select("chave,valor").then(conferir),
      supabase.from("trabalhador").select("*").order("visto_em", { ascending: false }).limit(1).then(conferir),
      supabase.from("pedidos").select("id", { count: "exact", head: true })
        .in("status", ["pendente", "rodando"]).then((r) => { conferir(r); return r.count || 0; }),
    ]);
    const ajuste = Object.fromEntries(ajustes.map((a) => [a.chave, a.valor]));
    seuNome = ajuste.seu_nome || "";

    const hoje = hojeIso();
    const resumo = {
      por_etapa: Object.fromEntries(ETAPAS.map((e) => [e.id, 0])),
      por_classe: Object.fromEntries(CLASSES.map((c) => [c.id, 0])),
      por_estado: { ativo: 0, congelado: 0, arquivado: 0, descartado: 0 },
      ligar_hoje: 0,
    };
    for (const l of contagem) {
      resumo.por_estado[l.estado] = (resumo.por_estado[l.estado] || 0) + 1;
      if (l.estado === "ativo") {
        resumo.por_etapa[l.etapa] = (resumo.por_etapa[l.etapa] || 0) + 1;
        if (l.classe) resumo.por_classe[l.classe] = (resumo.por_classe[l.classe] || 0) + 1;
      }
      if (["ativo", "congelado"].includes(l.estado) && l.data_proximo_passo && l.data_proximo_passo <= hoje) {
        resumo.ligar_hoje += 1;
      }
    }

    const pc = trabalhadores[0];
    const pcLigado = Boolean(pc && (Date.now() - new Date(pc.visto_em).getTime()) / 1000 < PC_LIGADO_SEGUNDOS);
    return {
      resumo,
      seu_nome: seuNome,
      pc_ligado: pcLigado,
      pc_visto_em: pc?.visto_em || null,
      ia: Boolean(pc?.ia),
      modelo_ia: pc?.modelo_ia || "",
      pedidos_abertos: pedidosAbertos,
      etapas: ETAPAS,
      classes: CLASSES,
      servicos: SERVICOS,
      tipos_contato: TIPOS_CONTATO,
      redes: NOMES_REDES,
      situacoes: SITUACOES,
    };
  },

  async leads({ texto = "", nicho = "", classe = "", servico = "", estado = "ativo" } = {}) {
    const linhas = await todas(() => {
      let consulta = supabase.from("leads").select(COLUNAS_LISTA);
      if (estado) consulta = consulta.eq("estado", estado);
      if (nicho) consulta = consulta.eq("nicho", nicho);
      if (classe) consulta = consulta.eq("classe", classe);
      // oportunidades é uma lista JSON: "contém um item com este serviço"
      if (servico) consulta = consulta.filter("oportunidades", "cs", JSON.stringify([{ servico }]));
      const t = limparTexto(texto);
      if (t) consulta = consulta.or(["nome", "regiao", "categoria", "endereco"].map((c) => `${c}.ilike."*${t}*"`).join(","));
      return consulta
        .order("nota_potencial", { ascending: false, nullsFirst: false })
        .order("criado_em", { ascending: false })
        .order("id");
    });
    return linhas.map((l) => ({ ...comLinks(l), dias_na_etapa: diasDesde(l.etapa_em) }));
  },

  async ligarHoje() {
    const linhas = await todas(() => supabase.from("leads").select(COLUNAS_LISTA)
      .in("estado", ["ativo", "congelado"])
      .lte("data_proximo_passo", hojeIso())
      .order("data_proximo_passo")
      .order("id"));
    return linhas.map(comLinks);
  },

  async lead(id) {
    const [lead, contatos] = await Promise.all([
      leadAtual(id),
      supabase.from("contatos").select("*").eq("lead_id", id).order("data", { ascending: false }).then(conferir),
    ]);
    return { ...comLinks(lead), dias_na_etapa: diasDesde(lead.etapa_em), contatos };
  },

  async editar(id, campos) {
    const lead = await leadAtual(id);
    const dados = { ...campos };
    if ("etapa" in dados) {
      if (!NOMES_ETAPA[dados.etapa]) throw new Error("Etapa inválida");
      if (dados.etapa !== lead.etapa) await anotar(id, `Movido para ${NOMES_ETAPA[dados.etapa]}`);
      if (lead.estado === "descartado") dados.estado = "ativo";   // você decidiu trabalhar com ele mesmo assim
    }
    if ("whatsapp" in dados) dados.whatsapp = normalizarWhatsapp(dados.whatsapp);
    if ("data_proximo_passo" in dados && !dados.data_proximo_passo) dados.data_proximo_passo = null;
    await atualizarLead(id, dados);
    return api.lead(id);
  },

  async congelar(id, dataLigar, motivo = "Parou de responder") {
    await atualizarLead(id, {
      estado: "congelado", motivo,
      proximo_passo: dataLigar ? "Ligar de novo (congelado)" : "",
      data_proximo_passo: dataLigar || null,
    });
    await anotar(id, `Congelado: ${motivo}`);
    return api.lead(id);
  },

  async arquivar(id, motivo = "Sem interesse agora") {
    await atualizarLead(id, { estado: "arquivado", motivo, data_proximo_passo: null });
    await anotar(id, `Arquivado: ${motivo}`);
    return api.lead(id);
  },

  async reativar(id) {
    const lead = await leadAtual(id);
    await atualizarLead(id, { estado: "ativo", motivo: "" });
    await anotar(id, `Voltou para o quadro (estava ${lead.estado})`);
    return api.lead(id);
  },

  async excluir(id) {
    conferir(await supabase.from("leads").delete().eq("id", id));
  },

  async novoContato(id, tipo, anotacao) {
    await anotar(id, (anotacao || "").trim(), tipo);
    await atualizarLead(id, { atualizado_em: new Date().toISOString() });
    return api.lead(id);
  },

  async apagarContato(contatoId) {
    conferir(await supabase.from("contatos").delete().eq("id", contatoId));
  },

  // ---------- Pedidos para o PC (fila) ----------
  analisar: (id, usarIa = true) => criarPedido("analisar", { ids: [id], usar_ia: usarIa }),
  recoletar: (id) => criarPedido("recoletar", { id }),
  diagnostico: (id) => criarPedido("diagnostico", { id }),
  reanalisar: (ids = [], usarIa = true) => criarPedido("analisar", { ids, usar_ia: usarIa }),
  buscar: (opcoes) => criarPedido("busca", opcoes),

  async pedidos(limite = 15) {
    return conferir(await supabase.from("pedidos").select("*").order("id", { ascending: false }).limit(limite));
  },

  async pedido(id) {
    return conferir(await supabase.from("pedidos").select("*").eq("id", id).maybeSingle());
  },

  async pararPedido(pedido) {
    // Pendente: nem começou, é só cancelar. Rodando: o PC para depois do item atual.
    if (pedido.status === "pendente") {
      conferir(await supabase.from("pedidos").update({ status: "cancelado", concluido_em: new Date().toISOString() })
        .eq("id", pedido.id).eq("status", "pendente"));
    }
    conferir(await supabase.from("pedidos").update({ parar: true }).eq("id", pedido.id));
  },

  // ---------- Nichos, regiões e ajustes ----------
  nichos: async () => conferir(await supabase.from("nichos").select("*").order("nome")),

  async salvarNicho(nicho) {
    const nome = (nicho.nome || "").trim();
    if (!nome) throw new Error("O nicho precisa de um nome.");
    const id = nicho.id || slugify(nome);
    if (!nicho.id) {
      const existe = conferir(await supabase.from("nichos").select("id").eq("id", id).maybeSingle());
      if (existe) throw new Error(`Já existe um nicho "${nome}". Abra ele na lista ou use outro nome.`);
    }
    const dados = {
      id, nome,
      termo_busca: (nicho.termo_busca || "").trim() || nome,
      icone: nicho.icone || "✦",
      agenda: Boolean(nicho.agenda),
      pedido_online: Boolean(nicho.pedido_online),
    };
    return conferir(await supabase.from("nichos").upsert(dados).select().single());
  },

  async excluirNicho(id) {
    conferir(await supabase.from("nichos").delete().eq("id", id));
  },

  regioes: async () => conferir(await supabase.from("regioes").select("nome").order("ordem")).map((r) => r.nome),

  async salvarRegioes(lista) {
    const limpas = [...new Set(lista.map((r) => r.trim()).filter(Boolean))];
    const linhas = limpas.map((nome, ordem) => ({ nome, ordem }));
    if (linhas.length) conferir(await supabase.from("regioes").upsert(linhas));
    // Apaga as que saíram da lista
    const atuais = conferir(await supabase.from("regioes").select("nome")).map((r) => r.nome);
    const sairam = atuais.filter((r) => !limpas.includes(r));
    if (sairam.length) conferir(await supabase.from("regioes").delete().in("nome", sairam));
    return limpas;
  },

  async salvarSeuNome(nome) {
    conferir(await supabase.from("ajustes").upsert({ chave: "seu_nome", valor: nome.trim() }));
    seuNome = nome.trim();
  },

  // Todos os leads de um estado, com tudo (para exportar)
  async leadsCompletos({ nicho = "", estado = "ativo", classe = "" } = {}) {
    return todas(() => {
      let consulta = supabase.from("leads").select("*");
      if (estado) consulta = consulta.eq("estado", estado);
      if (nicho) consulta = consulta.eq("nicho", nicho);
      if (classe) consulta = consulta.eq("classe", classe);
      return consulta.order("nota_potencial", { ascending: false, nullsFirst: false }).order("id");
    });
  },
};

// "Pizzaria do Zé" -> "pizzaria-do-ze" (igual ao Python)
export function slugify(texto) {
  const limpo = String(texto || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return limpo.slice(0, 60).replace(/-+$/, "") || "negocio";
}

// Datas no formato brasileiro. Data com hora vem do banco em UTC: mostra no horário do aparelho.
export function dataBr(valor) {
  if (!valor) return "";
  if (valor.length > 10) {
    const d = new Date(valor);
    if (!Number.isNaN(d.getTime())) return d.toLocaleDateString("pt-BR");
  }
  const [ano, mes, dia] = valor.slice(0, 10).split("-");
  return dia ? `${dia}/${mes}/${ano}` : valor;
}

export function horaBr(valor) {
  const d = new Date(valor || "");
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export function hojeIso() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function somarDias(dias) {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

// Baixa um texto como arquivo no navegador
export function baixarArquivo(nome, conteudo, tipo) {
  const url = URL.createObjectURL(new Blob([conteudo], { type: tipo }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
