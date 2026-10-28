// Pacote do cliente: um documento só com tudo o que o sistema sabe sobre o lead.
// Serve para chegar na conversa com argumento e para mandar a uma IA fazer o site,
// o perfil do Maps ou outro serviço. Nada é inventado: o que falta vai em
// "O que falta pegar com o cliente". As cores da logo são calculadas pelo PC na análise.
import { CLASSES, NOMES_ETAPA, NOMES_REDES, SERVICOS, SITUACOES } from "./regras.js";

const NOMES_CLASSE = Object.fromEntries(CLASSES.map((c) => [c.id, c.nome]));
const NOMES_SERVICO = Object.fromEntries(SERVICOS.map((s) => [s.id, s.nome]));
const NOMES_FORCA = { alta: "alta", media: "média", baixa: "baixa" };

export function oQueFalta(lead) {
  const falta = [];
  if (!lead.logo_url) falta.push("Logo");
  if ((lead.fotos || []).length < 3) falta.push("Fotos do negócio (o Maps tem poucas)");
  if (!lead.descricao) falta.push("Descrição do negócio e lista de serviços");
  if (!(lead.horario || []).length) falta.push("Horário de funcionamento");
  if (!lead.email) falta.push("E-mail");
  if (!lead.whatsapp) falta.push("WhatsApp (só há telefone fixo ou nenhum)");
  if (!Object.keys(lead.redes || {}).length) falta.push("Redes sociais (nenhuma encontrada)");
  return falta;
}

// O pacote como objeto (base do Markdown e do JSON)
export function montarPacote(lead) {
  const analise = lead.analise_ia || {};
  const auditoria = lead.sinais?.site || {};
  return {
    gerado_em: new Date().toISOString().slice(0, 16),
    negocio: {
      nome: lead.nome, categoria: lead.categoria, regiao: lead.regiao, endereco: lead.endereco,
      descricao_do_dono: lead.descricao, publico: analise.publico, diferencial: analise.diferencial,
      resumo: analise.resumo,
    },
    classificacao: {
      nota: lead.nota_potencial, classe: NOMES_CLASSE[lead.classe] || "",
      servico_principal: NOMES_SERVICO[lead.servico_principal] || "", etapa: NOMES_ETAPA[lead.etapa] || "",
      conta: lead.nota_detalhe || [],
    },
    contato: { telefone: lead.telefone, whatsapp: lead.whatsapp, email: lead.email, maps: lead.maps_url },
    redes: lead.redes || {},
    instagram: { seguidores: lead.instagram_seguidores, posts: lead.instagram_posts },
    google: {
      nota: lead.nota, avaliacoes: lead.avaliacoes, horario: lead.horario || [],
      saude_maps: lead.saude_maps, problemas_maps: lead.problemas_maps || [],
    },
    site_atual: {
      endereco: lead.site, situacao: SITUACOES[lead.situacao_site] || "", https: auditoria.https,
      versao_celular: auditoria.celular, tempo_para_abrir_ms: auditoria.tempo_ms,
    },
    oportunidades: lead.oportunidades || [],
    dores: analise.dores || [],
    angulo_de_abordagem: analise.angulo,
    identidade_visual: { logo: lead.logo_url, cores: lead.cores || {}, fotos: lead.fotos || [] },
    o_que_falta: oQueFalta(lead),
    historico: (lead.contatos || []).map(({ data, tipo, anotacao }) => ({ data, tipo, anotacao })),
  };
}

function linha(rotulo, valor) {
  return valor === null || valor === undefined || valor === "" ? "" : `- **${rotulo}:** ${valor}\n`;
}

const dataHora = (valor) => String(valor || "").slice(0, 16).replace("T", " ");

export function paraMarkdown(p) {
  const { negocio: n, classificacao: c, contato: ct, google: g, site_atual: s } = p;
  const md = [`# ${n.nome}\n\n`];
  md.push(`${n.categoria || ""} · ${n.regiao || ""} · pacote gerado em ${dataHora(p.gerado_em)}\n\n`);

  md.push("## Classificação\n\n");
  md.push(linha("Classe", c.nota !== null && c.nota !== undefined ? `${c.classe} (${c.nota}/100)` : ""));
  md.push(linha("Serviço principal", c.servico_principal));
  md.push(linha("Etapa", c.etapa));
  if (n.resumo) md.push(`\n${n.resumo}\n`);
  md.push("\n");

  md.push("## Contato\n\n");
  md.push(linha("Telefone", ct.telefone));
  if (ct.whatsapp) md.push(linha("WhatsApp", `https://wa.me/${ct.whatsapp}`));
  md.push(linha("E-mail", ct.email));
  md.push(linha("Endereço", n.endereco));
  md.push(linha("Google Maps", ct.maps));
  md.push("\n");

  md.push("## Redes sociais\n\n");
  const redes = Object.entries(p.redes);
  if (redes.length) {
    for (const [rede, url] of redes) {
      let extra = "";
      if (rede === "instagram" && p.instagram.posts !== null && p.instagram.posts !== undefined) {
        extra = ` (${p.instagram.seguidores ?? "?"} seguidores, ${p.instagram.posts} posts)`;
      }
      md.push(`- **${NOMES_REDES[rede] || rede}:** ${url}${extra}\n`);
    }
  } else {
    md.push("Nenhuma rede social encontrada.\n");
  }
  md.push("\n");

  md.push("## O que vender\n\n");
  if (p.oportunidades.length) {
    for (const o of p.oportunidades) {
      md.push(`### ${NOMES_SERVICO[o.servico] || o.servico} (força ${NOMES_FORCA[o.forca] || o.forca})\n\n`);
      md.push(`${o.motivo}\n\n`);
      for (const e of o.evidencias || []) md.push(`- ${e}\n`);
      md.push("\n");
    }
  } else {
    md.push("Nenhuma oportunidade encontrada pelas regras.\n\n");
  }

  if (p.dores.length) {
    md.push("## Dores do negócio\n\n");
    for (const d of p.dores) md.push(`- **${d.dor}** — prova: ${d.prova}\n`);
    md.push("\n");
  }
  if (p.angulo_de_abordagem) md.push(`## Primeira frase da conversa\n\n> ${p.angulo_de_abordagem}\n\n`);

  md.push("## Informações para o site\n\n");
  md.push(linha("Descrição escrita pelo dono", n.descricao_do_dono));
  md.push(linha("Público", n.publico));
  md.push(linha("Diferencial", n.diferencial));
  if (g.nota) md.push(linha("Google", `nota ${String(g.nota).replace(".", ",")} com ${g.avaliacoes || 0} avaliações`));
  if (g.horario.length) {
    md.push("- **Horário:**\n");
    for (const h of g.horario) md.push(`  - ${h}\n`);
  }
  const v = p.identidade_visual;
  md.push(linha("Logo", v.logo));
  if (v.cores?.principal) {
    const k = v.cores;
    md.push(linha("Cores da logo",
      `principal ${k.principal}, destaque ${k.destaque}, fundo ${k.fundo}, superfície ${k.superficie}, texto ${k.texto}`));
  }
  if (v.fotos.length) {
    md.push(`- **Fotos do negócio no Maps (${v.fotos.length}):**\n`);
    for (const f of v.fotos) md.push(`  - ${f}\n`);
  }
  md.push("\n");

  md.push("## Site atual\n\n");
  if (s.endereco) md.push(linha("Endereço", s.endereco));
  md.push(linha("Situação", s.situacao));
  if (s.https !== null && s.https !== undefined) md.push(linha("HTTPS", s.https ? "sim" : "não"));
  if (s.versao_celular !== null && s.versao_celular !== undefined) {
    md.push(linha("Versão para celular", s.versao_celular ? "sim" : "não"));
  }
  if (s.tempo_para_abrir_ms) md.push(linha("Tempo para abrir", `${(s.tempo_para_abrir_ms / 1000).toFixed(1).replace(".", ",")} s`));
  md.push("\n");

  md.push(`## Saúde do Google Maps: ${g.saude_maps ?? "?"}/100\n\n`);
  if (g.problemas_maps.length) for (const problema of g.problemas_maps) md.push(`- ${problema}\n`);
  else md.push("Sem problemas encontrados.\n");
  md.push("\n");

  if (p.o_que_falta.length) {
    md.push("## O que falta pegar com o cliente\n\n");
    for (const item of p.o_que_falta) md.push(`- [ ] ${item}\n`);
    md.push("\n");
  }

  if (p.historico.length) {
    md.push("## Histórico de contatos\n\n");
    for (const h of p.historico) md.push(`- ${dataHora(h.data)} · ${h.tipo} · ${h.anotacao || ""}\n`);
    md.push("\n");
  }
  return md.join("").trimEnd() + "\n";
}

export function nomeDoArquivo(lead) {
  const base = String(lead.nome || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 50);
  return `pacote-${base || "lead"}`;
}
