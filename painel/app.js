/* Painel do Prospecta Sites — JavaScript puro, sem build.
   Cada função conversa com uma rota da API em app.py. */

const ROTULOS_STATUS = {
  novo: "Novo",
  site_gerado: "Site gerado",
  enviado: "Mensagem enviada",
  respondeu: "Respondeu",
  fechado: "Fechou",
  perdido: "Não quis",
  descartado: "Descartado",
};
const ETAPAS_FUNIL = ["novo", "site_gerado", "enviado", "respondeu", "fechado", "perdido"];

const estado = { geral: null, nichos: [], regioes: [], leads: [], selecionados: new Set(), nichoEditando: null };
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

// ---------------------------------------------------------------- utilidades
async function api(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
    body: opcoes.body ? JSON.stringify(opcoes.body) : undefined,
  });
  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) throw new Error(dados.detail || `Erro ${resposta.status}`);
  return dados;
}

function avisar(texto, erro = false) {
  const el = $("#aviso");
  el.textContent = texto;
  el.className = "aviso mostrar" + (erro ? " erro" : "");
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => (el.className = "aviso"), 3200);
}

function esc(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------------------------------------------------------- abas
$$(".aba").forEach((botao) =>
  botao.addEventListener("click", () => abrirAba(botao.dataset.aba))
);
function abrirAba(nome) {
  $$(".aba").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === nome));
  $$(".painel").forEach((p) => p.classList.toggle("ativo", p.id === `aba-${nome}`));
  if (nome === "leads") carregarLeads();
}

// ---------------------------------------------------------------- estado geral
async function carregarEstado() {
  estado.geral = await api("/api/estado");
  const g = estado.geral;
  $("#cont-leads").textContent = g.resumo.potenciais;

  $("#funil").innerHTML = ETAPAS_FUNIL.map(
    (s) => `<button class="etapa${$("#f-status").value === s ? " ativa" : ""}" data-status="${s}" style="--cor: var(--s-${s})">
      <b>${g.resumo.por_status[s] || 0}</b><span>${ROTULOS_STATUS[s]}</span></button>`
  ).join("");
  $$(".etapa").forEach((b) =>
    b.addEventListener("click", () => {
      $("#f-status").value = $("#f-status").value === b.dataset.status ? "" : b.dataset.status;
      abrirAba("leads");
      carregarEstado();
    })
  );

  const item = (ok, texto) => `<span class="${ok ? "ok" : ""}"><i></i>${texto}</span>`;
  $("#integracoes").innerHTML =
    item(g.ia, g.ia ? "IA ligada" : "IA desligada (textos padrão)") +
    item(g.netlify, g.netlify ? "Netlify conectado" : "Netlify não configurado");

  $("#status-integracoes").innerHTML = `
    <dt>IA (Gemini)</dt><dd>${g.ia ? `<span class="ok">Ligada</span>, modelo ${esc(g.modelo_ia)}` : "Sem GEMINI_API_KEY. Os sites usam os textos padrão do nicho (custo zero)."}</dd>
    <dt>Netlify</dt><dd>${g.netlify ? '<span class="ok">Conectado</span>' : "Falta NETLIFY_TOKEN e NETLIFY_SITE_ID."}</dd>
    <dt>Endereço dos demos</dt><dd>${g.url_demos ? esc(g.url_demos) : "Falta URL_DEMOS. Os links da mensagem apontam para o seu computador (localhost) e o cliente não consegue abrir."}</dd>
    <dt>Seu WhatsApp</dt><dd>${g.seu_whatsapp ? '<span class="ok">Configurado</span> (botão "Quero este site" nos demos)' : "Falta SEU_WHATSAPP: os demos ficam sem o botão para o cliente falar com você."}</dd>`;

  const selStatus = $("#f-status");
  if (selStatus.options.length === 1) {
    g.status.forEach((s) => selStatus.add(new Option(ROTULOS_STATUS[s], s)));
  }
  const tplAtual = $("#sel-template").value;
  $("#sel-template").innerHTML = g.templates.map((t) => `<option>${esc(t)}</option>`).join("");
  if (tplAtual && g.templates.includes(tplAtual)) $("#sel-template").value = tplAtual;
}

// ---------------------------------------------------------------- leads
async function carregarLeads() {
  const params = new URLSearchParams({
    texto: $("#f-texto").value,
    nicho: $("#f-nicho").value,
    situacao: $("#f-situacao").value,
    status: $("#f-status").value,
    dados: $("#f-dados").value,
  });
  estado.leads = await api(`/api/leads?${params}`);
  desenharLeads();
}

function desenharLeads() {
  const lista = $("#lista-leads");
  if (!estado.leads.length) {
    lista.innerHTML = `<div class="vazio"><strong>Nenhum lead aqui ainda</strong>
      Rode uma busca no Maps para encontrar negócios sem site.<br><br>
      <button class="btn btn-principal" onclick="abrirAba('busca')">Fazer uma busca</button></div>`;
    atualizarLote();
    return;
  }
  const nomeNicho = Object.fromEntries(estado.nichos.map((n) => [n.id, n.nome]));
  lista.innerHTML = estado.leads
    .map((l) => {
      const tel = l.telefone
        ? `<span class="tel ${l.telefone_tipo}">${esc(l.telefone)}${l.telefone_tipo === "fixo" ? " · fixo" : ""}</span>`
        : `<span class="tel">sem telefone</span>`;
      const opcoes = estado.geral.status
        .map((s) => `<option value="${s}" ${s === l.status ? "selected" : ""}>${ROTULOS_STATUS[s]}</option>`)
        .join("");
      return `<div class="lead" data-id="${esc(l.id)}">
        <input type="checkbox" class="sel" aria-label="Selecionar ${esc(l.nome)}" ${estado.selecionados.has(l.id) ? "checked" : ""}>
        <div>
          <button class="lead-nome">${esc(l.nome)}</button>
          <div class="lead-sub">${esc(l.categoria || nomeNicho[l.nicho] || "")} em ${esc((l.regiao || "").split(",")[0])}${l.nota ? `, ${String(l.nota).replace(".", ",")} ★` : ""}</div>
        </div>
        <div><span class="selo ${l.situacao_site}">${esc(l.situacao_rotulo)}</span>
          <span class="selo-dados ${l.qualidade.nivel}" title="Falta: ${esc(l.qualidade.falta.join(", ") || "nada")}">Dados ${l.qualidade.pontos}/${l.qualidade.maximo}</span><br>${tel}</div>
        <select class="status" style="--cor: var(--s-${l.status})" aria-label="Etapa">${opcoes}</select>
        <div class="lead-acoes">
          ${l.slug
            ? `<a class="btn btn-pequeno" href="${l.demo_local}" target="_blank">Ver site</a>
               <button class="btn btn-pequeno btn-refazer" title="Gera de novo com o template atual do nicho (mesmos textos)">Refazer</button>`
            : `<button class="btn btn-pequeno btn-gerar">Gerar site</button>`}
          ${l.slug && l.link_whatsapp ? `<button class="btn btn-pequeno btn-whats btn-enviar">Enviar no WhatsApp</button>` : ""}
        </div>
      </div>`;
    })
    .join("");
  atualizarLote();
}

// Eventos da lista (um ouvinte só, para todas as linhas)
$("#lista-leads").addEventListener("click", async (e) => {
  const linha = e.target.closest(".lead");
  if (!linha) return;
  const lead = estado.leads.find((l) => l.id === linha.dataset.id);
  if (e.target.classList.contains("lead-nome")) abrirGaveta(lead);
  if (e.target.classList.contains("btn-gerar")) gerarSite(lead, e.target);
  if (e.target.classList.contains("btn-refazer")) gerarSite(lead, e.target);
  if (e.target.classList.contains("btn-enviar")) enviarWhatsapp(lead);
});
$("#lista-leads").addEventListener("change", async (e) => {
  const linha = e.target.closest(".lead");
  if (!linha) return;
  if (e.target.classList.contains("sel")) {
    e.target.checked ? estado.selecionados.add(linha.dataset.id) : estado.selecionados.delete(linha.dataset.id);
    atualizarLote();
  }
  if (e.target.classList.contains("status")) {
    await mudarStatus(linha.dataset.id, e.target.value);
  }
});

async function mudarStatus(id, status) {
  const atualizado = await api(`/api/leads/${encodeURIComponent(id)}`, { method: "PATCH", body: { status } });
  const i = estado.leads.findIndex((l) => l.id === id);
  if (i >= 0) estado.leads[i] = atualizado;
  avisar(`Etapa: ${ROTULOS_STATUS[status]}`);
  carregarEstado();
  return atualizado;
}

async function gerarSite(lead, botao, refazer = false) {
  if (botao) { botao.disabled = true; botao.textContent = "Gerando..."; }
  try {
    const usarIa = $("#lote-ia").checked;
    await api(`/api/leads/${encodeURIComponent(lead.id)}/gerar`, { method: "POST", body: { usar_ia: usarIa, refazer_textos: refazer } });
    avisar(lead.slug ? `Site de ${lead.nome} refeito` : `Site de ${lead.nome} gerado`);
    await carregarLeads();
    carregarEstado();
    const novo = estado.leads.find((l) => l.id === lead.id);
    if ($("#gaveta").open && novo) abrirGaveta(novo);
  } catch (erro) {
    avisar(erro.message, true);
    if (botao) { botao.disabled = false; botao.textContent = botao.classList.contains("btn-refazer") ? "Refazer" : "Gerar site"; }
  }
}

function enviarWhatsapp(lead) {
  if (!estado.geral.url_demos && !confirm("URL_DEMOS não está configurada: o link na mensagem aponta para o seu computador e o cliente não vai conseguir abrir. Enviar mesmo assim?")) return;
  if (lead.telefone_tipo === "fixo" && !confirm("Esse número é fixo e pode não ter WhatsApp. Tentar mesmo assim?")) return;
  window.open(lead.link_whatsapp, "_blank");
  if (["novo", "site_gerado"].includes(lead.status)) mudarStatus(lead.id, "enviado").then(desenharLeads);
}

function atualizarLote() {
  const qtd = estado.selecionados.size;
  $("#barra-lote").hidden = qtd === 0;
  $("#lote-qtd").textContent = `${qtd} selecionado${qtd === 1 ? "" : "s"}`;
}

$("#btn-gerar-lote").addEventListener("click", async () => {
  const ids = [...estado.selecionados];
  try {
    await api("/api/gerar-lote", { method: "POST", body: { ids, usar_ia: $("#lote-ia").checked, incluir_fracos: $("#lote-fracos").checked } });
    estado.selecionados.clear();
    acompanharTarefa("Gerando sites");
  } catch (erro) { avisar(erro.message, true); }
});

let filtroTimer;
$("#f-texto").addEventListener("input", () => { clearTimeout(filtroTimer); filtroTimer = setTimeout(carregarLeads, 250); });
["#f-nicho", "#f-situacao", "#f-status", "#f-dados"].forEach((s) => $(s).addEventListener("change", () => { carregarLeads(); carregarEstado(); }));

$("#btn-exportar").addEventListener("click", () => {
  const p = new URLSearchParams({ formato: "xlsx", nicho: $("#f-nicho").value, situacao: $("#f-situacao").value });
  window.location = `/api/exportar?${p}`;
});
$("#btn-publicar").addEventListener("click", async () => {
  try {
    await api("/api/publicar", { method: "POST" });
    acompanharTarefa("Publicando no Netlify");
  } catch (erro) { avisar(erro.message, true); }
});

// ---------------------------------------------------------------- gaveta do lead
function abrirGaveta(lead) {
  const linha = (rotulo, valor) => (valor ? `<dt>${rotulo}</dt><dd>${valor}</dd>` : "");
  const link = (url, texto) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(texto || url)}</a>`;
  // Fotos do Maps: a primeira vai para o topo do site; dá para trocar e tirar as ruins
  const fotos = (lead.fotos || []).map((f, i) => `
    <figure class="foto-lead${i === 0 ? " capa" : ""}" data-i="${i}">
      <img src="${esc(f)}" alt="Foto ${i + 1} do Maps" referrerpolicy="no-referrer" loading="lazy">
      <figcaption>${i === 0 ? "<b>No topo</b>" : `<button type="button" class="link foto-topo">Pôr no topo</button>`}
        <button type="button" class="link foto-tirar">Tirar</button></figcaption>
    </figure>`).join("");
  const logo = lead.logo_url ? `<img class="logo-mini" src="${esc(lead.logo_url)}" alt="Logo" referrerpolicy="no-referrer">` : "";

  $("#gaveta-conteudo").innerHTML = `
    <div class="gaveta-topo">
      <div><h2>${esc(lead.nome)}</h2><span class="selo ${lead.situacao_site}">${esc(lead.situacao_rotulo)}</span></div>
      <button class="btn btn-pequeno" id="fechar-gaveta">Fechar</button>
    </div>
    <div>
      <div class="titulo-fotos"><strong>Fotos do Maps</strong>
        <span class="acoes"><button type="button" class="btn btn-pequeno" id="g-recoletar">Buscar de novo no Maps</button>
        <button type="button" class="btn btn-pequeno" id="g-diagnostico" title="Abre a ficha no Maps e gera prints e um relatório do que o bot encontrou">Diagnóstico do bot</button></span></div>
      ${fotos ? `<div class="grade-fotos-lead">${logo}${fotos}</div>
        <p class="dica">A primeira foto vai para o topo do site. Tire fotos ruins (produto, cardápio, foto escura) e clique em Refazer site.</p>`
        : `<p class="dica">Nenhuma foto. Clique em "Buscar de novo no Maps" para pegar a galeria e as avaliações.</p>`}
    </div>
    <dl class="dados">
      ${linha("Categoria", esc(lead.categoria))}
      ${linha("Região", esc(lead.regiao))}
      ${linha("Endereço", esc(lead.endereco))}
      ${linha("Telefone", esc(lead.telefone) + (lead.telefone_tipo === "fixo" ? " (fixo)" : ""))}
      ${linha("WhatsApp", esc(lead.whatsapp))}
      ${linha("Instagram", lead.instagram ? link(lead.instagram) : "")}
      ${linha("Site no Maps", lead.site ? link(lead.site) : "")}
      ${linha("E-mail", esc(lead.email))}
      ${linha("Nota", lead.nota ? `${String(lead.nota).replace(".", ",")} ★ (${lead.avaliacoes || 0} avaliações)` : "")}
      ${linha("Maps", lead.maps_url ? link(lead.maps_url, "Abrir no Google Maps") : "")}
      ${linha("Dados", `<span class="selo-dados ${lead.qualidade.nivel}">${lead.qualidade.pontos}/${lead.qualidade.maximo}</span>` +
        (lead.qualidade.falta.length ? ` <span class="falta">falta: ${esc(lead.qualidade.falta.join(", "))}</span>` : ""))}
      ${linha("Fotos", (lead.fotos || []).length ? `${lead.fotos.length} do Maps` : "")}
      ${linha("Descrição", esc(lead.descricao))}
      ${linha("Avaliações", (lead.depoimentos || []).slice(0, 2).map((d) => `<p class="depo-mini">${"★".repeat(d.estrelas)} ${esc(d.texto.slice(0, 140))}… <b>${esc(d.autor)}</b></p>`).join(""))}
      ${linha("Textos", lead.textos ? (lead.textos._origem === "padrao" ? "padrão do nicho" : `IA (${lead.textos._tokens || "?"} tokens)`) : "")}
    </dl>
    <label style="display:grid;gap:4px;font-weight:600">WhatsApp do lead <span class="dica">corrija se o número do Maps não for o WhatsApp</span>
      <input id="g-whats" value="${esc(lead.whatsapp || "")}" placeholder="61999998888"></label>
    <label style="display:grid;gap:4px;font-weight:600">Observações
      <textarea id="g-obs" rows="3">${esc(lead.observacoes || "")}</textarea></label>
    <div class="acoes"><button class="btn" id="g-salvar">Salvar dados</button></div>

    <h2 style="margin:8px 0 0">Site demo</h2>
    ${lead.slug ? `
      <iframe class="previa-frame" src="${lead.demo_local}" title="Prévia do site"></iframe>
      <div class="acoes">
        <a class="btn" href="${lead.demo_local}" target="_blank">Abrir em tela cheia</a>
        <button class="btn" id="g-regerar">Refazer site (mesmos textos)</button>
        <button class="btn" id="g-novos-textos">Refazer com textos novos (IA)</button>
        <button class="btn btn-perigo" id="g-apagar-site">Apagar demo</button>
      </div>
      ${lead.demo_publico ? `<p class="dica">Link público: ${link(lead.demo_publico)} (depois de publicar no Netlify)</p>` : ""}
      <h2 style="margin:8px 0 0">Mensagem</h2>
      <div class="mensagem">${esc(lead.mensagem)}</div>
      <div class="acoes">
        ${lead.link_whatsapp ? `<button class="btn btn-whats" id="g-enviar">Abrir no WhatsApp</button>` : `<span class="dica">Sem telefone: use o Instagram para contato.</span>`}
        <button class="btn" id="g-copiar">Copiar mensagem</button>
      </div>`
      : `<p class="dica">Ainda não tem site. Gere para ver a prévia aqui.</p>
         <div class="acoes"><button class="btn btn-principal" id="g-gerar">Gerar site</button></div>`}
    <div class="acoes" style="margin-top:20px;border-top:1px solid var(--linha);padding-top:16px">
      <button class="btn btn-perigo" id="g-excluir">Excluir lead</button>
    </div>`;

  const g = $("#gaveta");
  if (!g.open) g.showModal();
  const id = encodeURIComponent(lead.id);
  $("#fechar-gaveta").onclick = () => g.close();
  $("#g-salvar").onclick = async () => {
    await api(`/api/leads/${id}`, { method: "PATCH", body: { whatsapp: $("#g-whats").value, observacoes: $("#g-obs").value } });
    avisar("Dados salvos");
    await carregarLeads();
    abrirGaveta(estado.leads.find((l) => l.id === lead.id) || lead);
  };
  $("#g-gerar") && ($("#g-gerar").onclick = (e) => gerarSite(lead, e.target));
  $("#g-regerar") && ($("#g-regerar").onclick = (e) => gerarSite(lead, e.target));
  $("#g-novos-textos") && ($("#g-novos-textos").onclick = (e) => gerarSite(lead, e.target, true));
  $("#g-enviar") && ($("#g-enviar").onclick = () => enviarWhatsapp(lead));
  $("#g-copiar") && ($("#g-copiar").onclick = async () => { await navigator.clipboard.writeText(lead.mensagem); avisar("Mensagem copiada"); });
  $("#g-apagar-site") && ($("#g-apagar-site").onclick = async () => {
    if (!confirm("Apagar o site demo deste lead?")) return;
    await api(`/api/leads/${id}/site`, { method: "DELETE" });
    avisar("Demo apagado");
    await carregarLeads();
    abrirGaveta(estado.leads.find((l) => l.id === lead.id) || lead);
  });
  const salvarFotos = async (lista, msg) => {
    await api(`/api/leads/${id}`, { method: "PATCH", body: { fotos: lista } });
    await carregarLeads();
    abrirGaveta(estado.leads.find((l) => l.id === lead.id) || lead);
    avisar(msg + (lead.slug ? ". Clique em Refazer site para aplicar" : ""));
  };
  $$(".foto-lead").forEach((fig) => {
    const i = Number(fig.dataset.i);
    fig.querySelector(".foto-topo")?.addEventListener("click", () => {
      const lista = [...lead.fotos]; const [f] = lista.splice(i, 1); lista.unshift(f);
      salvarFotos(lista, "Foto colocada no topo");
    });
    fig.querySelector(".foto-tirar").addEventListener("click", () => {
      salvarFotos(lead.fotos.filter((_, n) => n !== i), "Foto removida");
    });
  });
  $("#g-recoletar").onclick = async () => {
    try {
      await api(`/api/leads/${id}/recoletar`, { method: "POST" });
      aoTerminarTarefa = async () => { await carregarLeads(); abrirGaveta(estado.leads.find((l) => l.id === lead.id) || lead); };
      acompanharTarefa("Buscando de novo no Maps");
    } catch (erro) { avisar(erro.message, true); }
  };
  $("#g-diagnostico").onclick = async () => {
    try {
      await api(`/api/leads/${id}/diagnostico`, { method: "POST" });
      acompanharTarefa("Diagnóstico do bot");
    } catch (erro) { avisar(erro.message, true); }
  };
  $("#g-excluir").onclick = async () => {
    if (!confirm(`Excluir ${lead.nome} do banco? Ele pode voltar numa próxima busca.`)) return;
    await api(`/api/leads/${id}`, { method: "DELETE" });
    g.close();
    avisar("Lead excluído");
    carregarLeads();
    carregarEstado();
  };
}
$("#gaveta").addEventListener("click", (e) => { if (e.target.id === "gaveta") e.target.close(); });

// ---------------------------------------------------------------- busca
async function carregarNichos() {
  estado.nichos = await api("/api/nichos");
  const atual = $("#f-nicho").value;
  $("#f-nicho").innerHTML = `<option value="">Todos os nichos</option>` +
    estado.nichos.map((n) => `<option value="${esc(n.id)}">${esc(n.nome)}</option>`).join("");
  $("#f-nicho").value = atual;

  const escolhido = $("input[name=busca-nicho]:checked")?.value;
  $("#busca-nichos").innerHTML = estado.nichos
    .map((n, i) => `<label class="nicho-opcao"><input type="radio" name="busca-nicho" value="${esc(n.id)}" ${(escolhido ? n.id === escolhido : i === 0) ? "checked" : ""}>
      <span>${esc(n.icone || "")} ${esc(n.nome)}</span></label>`)
    .join("") + ` <button type="button" class="link" onclick="abrirAba('nichos');novoNicho()">+ criar nicho</button>`;

  $("#lista-nichos").innerHTML = estado.nichos
    .map((n) => `<li><button data-id="${esc(n.id)}" class="${estado.nichoEditando === n.id ? "ativo" : ""}"><i>${esc(n.icone || "•")}</i>${esc(n.nome)}</button></li>`)
    .join("");
  $$("#lista-nichos button").forEach((b) => b.addEventListener("click", () => editarNicho(b.dataset.id)));
}

async function carregarRegioes() {
  estado.regioes = await api("/api/regioes");
  $("#busca-regioes").innerHTML = estado.regioes
    .map((r) => `<label><input type="checkbox" value="${esc(r)}"> ${esc(r)}</label>`)
    .join("");
  $("#txt-regioes").value = estado.regioes.join("\n");
  contarRegioes();
}
function contarRegioes() {
  const n = $$("#busca-regioes input:checked").length;
  $("#regioes-qtd").textContent = n ? `(${n} selecionada${n > 1 ? "s" : ""})` : "";
}
$("#busca-regioes").addEventListener("change", contarRegioes);
$$("[data-marcar]").forEach((b) =>
  b.addEventListener("click", () => {
    const alvo = b.dataset.marcar;
    $$("#busca-regioes input").forEach((c) => {
      c.checked = alvo === "todas" ? true : alvo === "nenhuma" ? false : c.value.trim().endsWith(alvo) || c.checked;
    });
    contarRegioes();
  })
);

$("#form-busca").addEventListener("submit", async (e) => {
  e.preventDefault();
  const corpo = {
    nicho: $("input[name=busca-nicho]:checked")?.value,
    regioes: $$("#busca-regioes input:checked").map((c) => c.value),
    limite: Number($("#busca-limite").value),
    headless: $("#busca-headless").checked,
    buscar_instagram: $("#busca-instagram").checked,
    coletar_extras: $("#busca-extras").checked,
  };
  if (!corpo.nicho) return avisar("Escolha um nicho", true);
  if (!corpo.regioes.length) return avisar("Escolha pelo menos uma região", true);
  try {
    await api("/api/busca", { method: "POST", body: corpo });
    acompanharTarefa("Buscando no Maps");
  } catch (erro) { avisar(erro.message, true); }
});

// ---------------------------------------------------------------- nichos
function linhasParaServicos(texto) {
  return texto.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
    const [titulo, ...resto] = l.split("|");
    return { titulo: titulo.trim(), descricao: resto.join("|").trim() };
  });
}

async function editarNicho(id) {
  const n = await api(`/api/nichos/${encodeURIComponent(id)}`);
  estado.nichoEditando = id;
  preencherFormNicho(n);
  $$("#lista-nichos button").forEach((b) => b.classList.toggle("ativo", b.dataset.id === id));
  carregarArquivosNicho(id);
}
function preencherFormNicho(n) {
  const f = $("#form-nicho");
  f.nicho_id.value = n.id || "";
  f.nome.value = n.nome || "";
  f.termo_busca.value = n.termo_busca || "";
  f.template.value = n.template || "padrao";
  f.cor_padrao.value = n.cor_padrao || "#2563eb";
  f.icone.value = n.icone || "";
  f.roteiro.value = n.roteiro || "";
  const tp = n.textos_padrao || {};
  f.tp_slogan.value = tp.slogan || "";
  f.tp_cta.value = tp.cta || "";
  f.tp_subtitulo.value = tp.subtitulo || "";
  f.tp_sobre.value = tp.sobre || "";
  f.servicos.value = (n.servicos_padrao || []).map((s) => `${s.titulo} | ${s.descricao}`).join("\n");
  f.diferenciais.value = (n.diferenciais_padrao || []).join("\n");
  f.mensagem_whatsapp.value = n.mensagem_whatsapp || "";
  $("#btn-excluir-nicho").hidden = !n.id;
}
function novoNicho() {
  estado.nichoEditando = null;
  $$("#lista-nichos button").forEach((b) => b.classList.remove("ativo"));
  // começa com a mensagem e o template de um nicho existente, para não partir do zero
  const base = estado.nichos[0] || {};
  preencherFormNicho({ template: "padrao", cor_padrao: "#2563eb", mensagem_whatsapp: base.mensagem_whatsapp || "" });
  carregarArquivosNicho(null);
  $("#form-nicho").nome.focus();
}
$("#btn-novo-nicho").addEventListener("click", novoNicho);

$("#form-nicho").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const corpo = {
    id: f.nicho_id.value, nome: f.nome.value, termo_busca: f.termo_busca.value, template: f.template.value,
    cor_padrao: f.cor_padrao.value, icone: f.icone.value, roteiro: f.roteiro.value,
    textos_padrao: { slogan: f.tp_slogan.value, cta: f.tp_cta.value, subtitulo: f.tp_subtitulo.value, sobre: f.tp_sobre.value },
    servicos_padrao: linhasParaServicos(f.servicos.value),
    diferenciais_padrao: f.diferenciais.value.split("\n").map((l) => l.trim()).filter(Boolean),
    mensagem_whatsapp: f.mensagem_whatsapp.value,
  };
  try {
    const salvo = await api("/api/nichos", { method: "POST", body: corpo });
    estado.nichoEditando = salvo.id;
    f.nicho_id.value = salvo.id;
    $("#btn-excluir-nicho").hidden = false;
    avisar(`Nicho "${salvo.nome}" salvo`);
    carregarNichos();
    carregarArquivosNicho(salvo.id);
  } catch (erro) { avisar(erro.message, true); }
});
$("#btn-excluir-nicho").addEventListener("click", async () => {
  const f = $("#form-nicho");
  if (!f.nicho_id.value || !confirm(`Excluir o nicho "${f.nome.value}"? Os leads dele continuam no banco.`)) return;
  await api(`/api/nichos/${encodeURIComponent(f.nicho_id.value)}`, { method: "DELETE" });
  avisar("Nicho excluído");
  await carregarNichos();
  if (estado.nichos[0]) editarNicho(estado.nichos[0].id); else novoNicho();
});

// ---------------------------------------------------------------- imagens e consulta do nicho
async function carregarArquivosNicho(id) {
  $("#arquivos-bloqueado").hidden = Boolean(id);
  $("#arquivos-conteudo").hidden = !id;
  if (!id) return;
  desenharArquivos(id, await api(`/api/nichos/${encodeURIComponent(id)}/arquivos`));
  desenharModelo(id, await api(`/api/nichos/${encodeURIComponent(id)}/modelo`));
}

// ---------------------------------------------------------------- modelo de site do nicho
function desenharModelo(id, m) {
  estado.modeloAtual = m;
  const rota = `/api/nichos/${encodeURIComponent(id)}/modelo`;
  $("#modelo-variaveis").textContent = m.variaveis;
  $("#modelo-tema").value = m.tema;
  const caixa = $("#modelo-status");
  if (!m.tem_original && !m.convertido) {
    caixa.className = "modelo-status";
    caixa.innerHTML = `<strong>Sem modelo</strong><span class="dica">Os sites deste nicho usam o template "${esc($("#form-nicho").template.value)}".</span>`;
  } else if (!m.convertido) {
    caixa.className = "modelo-status pendente";
    caixa.innerHTML = `<strong>Modelo enviado, falta converter</strong>
      <span class="dica">${esc(m.nome_enviado || "")}: ${m.caracteres.toLocaleString("pt-BR")} caracteres${m.arquivos_extras ? `, ${m.arquivos_extras} arquivos de CSS/imagem` : ""}.
      A conversão com IA gasta cerca de ${m.tokens_estimados.toLocaleString("pt-BR")} tokens, uma vez só.</span>`;
  } else {
    caixa.className = "modelo-status pronto";
    caixa.innerHTML = `<strong>Modelo pronto${m.em_uso ? " e em uso neste nicho" : " (não está em uso)"}</strong>
      <span class="dica">${esc(m.nome_enviado || "")}${m.enviado_em ? `, enviado em ${new Date(m.enviado_em).toLocaleString("pt-BR")}` : ""}.
        ${m.origem === "ia" ? `Convertido pela IA${m.tokens_conversao ? ` (${m.tokens_conversao.toLocaleString("pt-BR")} tokens)` : ""}.` : ""}
        Sites gerados antes do envio continuam com o visual antigo: use "Refazer sites do nicho".</span>`;
  }
  const botoes = [];
  if (m.tem_original && !m.ja_e_template) {
    botoes.push(m.ia_disponivel
      ? `<button type="button" class="btn ${m.convertido ? "" : "btn-principal"}" data-acao="converter">${m.convertido ? "Converter de novo com IA" : "Converter com IA"}</button>`
      : `<span class="dica">Sem chave do Gemini: converta à mão (baixe o original, troque o conteúdo pelas variáveis e envie o template editado).</span>`);
  }
  if (m.tem_original) botoes.push(`<a class="btn" href="${rota}/baixar?qual=original">Baixar original</a>`);
  if (m.convertido) {
    botoes.push(`<button type="button" class="btn btn-principal" data-acao="previa">Ver prévia com dados de exemplo</button>`);
    botoes.push(`<a class="btn" href="${rota}/baixar?qual=template">Baixar template</a>`);
    botoes.push(`<button type="button" class="btn" data-acao="${m.em_uso ? "desativar" : "ativar"}">${m.em_uso ? "Parar de usar" : "Usar neste nicho"}</button>`);
    if (m.em_uso) botoes.push(`<button type="button" class="btn" data-acao="refazer">Refazer sites do nicho</button>`);
  }
  if (m.tem_original || m.convertido) {
    botoes.push(`<label class="btn botao-arquivo-sec">Enviar template editado<input type="file" id="modelo-template" accept=".j2,.html,.htm" hidden></label>`);
    botoes.push(`<button type="button" class="btn btn-perigo" data-acao="remover">Remover modelo</button>`);
  }
  $("#modelo-acoes").innerHTML = botoes.join("");
  $("#modelo-template")?.addEventListener("change", async (e) => {
    if (!e.target.files.length) return;
    await enviarModelo("template", e.target.files[0]);
    e.target.value = "";
  });
}

async function enviarModelo(tipo, arquivo) {
  const id = $("#form-nicho").nicho_id.value;
  const form = new FormData();
  form.append("arquivo", arquivo);
  form.append("tema", $("#modelo-tema").value);
  const rota = `/api/nichos/${encodeURIComponent(id)}/modelo${tipo === "template" ? "/template" : ""}`;
  const resposta = await fetch(rota, { method: "POST", body: form });
  const dados = await resposta.json();
  if (!resposta.ok) return avisar(dados.detail || "Erro no envio", true);
  desenharModelo(id, dados);
  avisar(dados.convertido ? "Template salvo e em uso neste nicho" : "Modelo enviado. Agora converta.");
  await carregarEstado();
  if (dados.em_uso) $("#form-nicho").template.value = dados.template;
}

$("#modelo-arquivo").addEventListener("change", async (e) => {
  if (e.target.files.length) await enviarModelo("original", e.target.files[0]);
  e.target.value = "";
});
$("#modelo-tema").addEventListener("change", async (e) => {
  const id = $("#form-nicho").nicho_id.value;
  if (!id || !estado.modeloAtual?.existe) return;   // sem modelo ainda: o tema vai junto no envio
  desenharModelo(id, await api(`/api/nichos/${encodeURIComponent(id)}/modelo`, { method: "PATCH", body: { tema: e.target.value } }));
  avisar("Fundo do modelo atualizado");
});
$("#modelo-acoes").addEventListener("click", async (e) => {
  const acao = e.target.dataset.acao;
  if (!acao) return;
  const id = $("#form-nicho").nicho_id.value;
  const rota = `/api/nichos/${encodeURIComponent(id)}/modelo`;
  try {
    if (acao === "converter") {
      await api(`${rota}/converter`, { method: "POST" });
      aoTerminarTarefa = async () => { await carregarEstado(); editarNicho(id); };
      acompanharTarefa("Convertendo o modelo");
    }
    if (acao === "refazer") {
      if (!confirm("Refazer todos os sites já gerados deste nicho com o modelo atual? Os textos são mantidos (não gasta IA).")) return;
      const r = await api(`/api/nichos/${encodeURIComponent(id)}/refazer-sites`, { method: "POST" });
      acompanharTarefa(`Refazendo ${r.total} sites`);
    }
    if (acao === "previa") {
      const janela = window.open("about:blank", "_blank");
      const { url } = await api(`${rota}/previa`, { method: "POST" });
      janela.location = url;
    }
    if (acao === "ativar" || acao === "desativar") {
      const m = await api(rota, { method: "PATCH", body: { em_uso: acao === "ativar" } });
      desenharModelo(id, m);
      await carregarEstado();
      const n = await api(`/api/nichos/${encodeURIComponent(id)}`);
      $("#form-nicho").template.value = n.template;
      avisar(acao === "ativar" ? "Modelo em uso neste nicho" : "Nicho voltou para o template padrão");
    }
    if (acao === "remover") {
      if (!confirm("Remover o modelo deste nicho? Os sites voltam a usar o template padrão.")) return;
      desenharModelo(id, await api(rota, { method: "DELETE" }));
      await carregarEstado();
      const n = await api(`/api/nichos/${encodeURIComponent(id)}`);
      $("#form-nicho").template.value = n.template;
      avisar("Modelo removido");
    }
  } catch (erro) { avisar(erro.message, true); }
});

function desenharArquivos(id, dados) {
  const usos = dados.usos;
  if (!$("#img-uso").options.length) {
    $("#img-uso").innerHTML = Object.entries(usos).map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("");
  }
  // nomes curtos para caber no cartão da imagem
  const CURTO = { fundo: "Topo (sem foto real)", detalhe: "Entre as seções", textura: "Fundo da chamada", pessoas: "Pessoas (slides)" };
  const opcoesUso = (atual) => Object.keys(usos)
    .map((v) => `<option value="${v}" ${v === atual ? "selected" : ""}>${esc(CURTO[v] || v)}</option>`).join("");

  $("#lista-imagens").innerHTML = dados.imagens.length
    ? dados.imagens.map((i) => `<li data-arquivo="${esc(i.arquivo)}">
        <img src="/arquivos-nicho/${encodeURIComponent(id)}/${encodeURIComponent(i.arquivo)}" alt="${esc(i.descricao)}" loading="lazy">
        <div class="campos">
          <select class="img-uso" aria-label="Função">${opcoesUso(i.uso)}</select>
          <input class="img-desc" value="${esc(i.descricao)}" placeholder="Descrição (vira o texto alternativo)">
          <button type="button" class="btn btn-pequeno btn-perigo img-remover">Remover</button>
        </div></li>`).join("")
    : `<li class="vazio-mini">Nenhuma imagem ainda. Sem imagens, o site usa só as fotos do próprio negócio.</li>`;

  const contagem = Object.keys(usos).map((u) => `${dados.imagens.filter((i) => i.uso === u).length} de ${u}`).join(", ");
  $("#lista-imagens").dataset.resumo = contagem;

  $("#lista-consulta").innerHTML = dados.consulta.length
    ? dados.consulta.map((c) => `<li data-arquivo="${esc(c.arquivo)}">
        <span>${esc(c.arquivo)}</span><small class="dica">${c.caracteres.toLocaleString("pt-BR")} caracteres</small>
        <button type="button" class="btn btn-pequeno consulta-ver">Ver</button>
        <button type="button" class="btn btn-pequeno btn-perigo consulta-remover">Remover</button></li>`).join("")
    : `<li class="vazio-mini">Nenhum arquivo. A IA usa só o roteiro do nicho.</li>`;

  const tokens = Math.round(dados.consulta_enviada / 4);
  $("#consulta-uso").textContent = dados.consulta.length
    ? `A IA recebe ${dados.consulta_enviada.toLocaleString("pt-BR")} caracteres, cerca de ${tokens} tokens a mais por site (limite: ${dados.limite_consulta.toLocaleString("pt-BR")})` +
      (dados.consulta_caracteres > dados.limite_consulta ? ". O que passar do limite é cortado: deixe os arquivos mais importantes primeiro." : ".")
    : "";
  if (dados.erros?.length) avisar(dados.erros.join(" "), true);
}

async function enviarArquivos(rota, arquivos, extras = {}) {
  const id = $("#form-nicho").nicho_id.value;
  const form = new FormData();
  [...arquivos].forEach((a) => form.append("arquivos", a));
  Object.entries(extras).forEach(([k, v]) => form.append(k, v));
  const resposta = await fetch(`/api/nichos/${encodeURIComponent(id)}/${rota}`, { method: "POST", body: form });
  const dados = await resposta.json();
  if (!resposta.ok) return avisar(dados.detail || "Erro no envio", true);
  desenharArquivos(id, dados);
  if (!dados.erros?.length) avisar(`${arquivos.length} arquivo(s) enviado(s)`);
}

$("#img-arquivos").addEventListener("change", async (e) => {
  if (e.target.files.length) await enviarArquivos("imagens", e.target.files, { uso: $("#img-uso").value });
  e.target.value = "";
});
$("#consulta-arquivos").addEventListener("change", async (e) => {
  if (e.target.files.length) await enviarArquivos("consulta", e.target.files);
  e.target.value = "";
});

$("#lista-imagens").addEventListener("change", async (e) => {
  const li = e.target.closest("li[data-arquivo]");
  if (!li) return;
  const id = encodeURIComponent($("#form-nicho").nicho_id.value);
  const corpo = e.target.classList.contains("img-uso") ? { uso: e.target.value } : { descricao: e.target.value };
  await api(`/api/nichos/${id}/imagens/${encodeURIComponent(li.dataset.arquivo)}`, { method: "PATCH", body: corpo });
  avisar("Imagem atualizada");
});
$("#lista-imagens").addEventListener("click", async (e) => {
  if (!e.target.classList.contains("img-remover")) return;
  const li = e.target.closest("li[data-arquivo]");
  const id = $("#form-nicho").nicho_id.value;
  const dados = await api(`/api/nichos/${encodeURIComponent(id)}/imagens/${encodeURIComponent(li.dataset.arquivo)}`, { method: "DELETE" });
  desenharArquivos(id, dados);
  avisar("Imagem removida");
});
$("#lista-consulta").addEventListener("click", async (e) => {
  const li = e.target.closest("li[data-arquivo]");
  if (!li) return;
  const id = $("#form-nicho").nicho_id.value;
  const rota = `/api/nichos/${encodeURIComponent(id)}/consulta/${encodeURIComponent(li.dataset.arquivo)}`;
  if (e.target.classList.contains("consulta-remover")) {
    desenharArquivos(id, await api(rota, { method: "DELETE" }));
    avisar("Arquivo removido");
  }
  if (e.target.classList.contains("consulta-ver")) {
    const aberto = li.nextElementSibling?.classList.contains("previa-consulta");
    $$(".previa-consulta").forEach((el) => el.remove());
    if (aberto) return;
    const { texto } = await api(rota);
    li.insertAdjacentHTML("afterend", `<li class="previa-consulta" style="border:0;padding:0;display:block"><pre>${esc(texto.slice(0, 4000))}${texto.length > 4000 ? "\n…" : ""}</pre></li>`);
  }
});

// ---------------------------------------------------------------- regiões
$("#form-regioes").addEventListener("submit", async (e) => {
  e.preventDefault();
  const lista = $("#txt-regioes").value.split("\n").map((l) => l.trim()).filter(Boolean);
  await api("/api/regioes", { method: "PUT", body: lista });
  avisar(`${lista.length} regiões salvas`);
  carregarRegioes();
});

// ---------------------------------------------------------------- console de tarefas
let posicaoLog = 0;
let consultando = null;
let aoTerminarTarefa = null;   // função chamada quando a tarefa atual termina
function acompanharTarefa(titulo) {
  const c = $("#console");
  c.hidden = false;
  c.classList.add("rodando");
  $("#console-titulo").textContent = titulo;
  $("#console-log").textContent = "";
  $("#console-extra").hidden = true;
  posicaoLog = 0;
  $("#btn-parar").hidden = false;
  clearInterval(consultando);
  consultando = setInterval(async () => {
    const t = await api(`/api/tarefa?desde=${posicaoLog}`);
    if (t.log.length) {
      const pre = $("#console-log");
      pre.textContent += t.log.join("\n") + "\n";
      pre.scrollTop = pre.scrollHeight;
      posicaoLog = t.total;
    }
    if (!t.rodando) {
      clearInterval(consultando);
      c.classList.remove("rodando");
      $("#btn-parar").hidden = true;
      $("#console-titulo").textContent = titulo + " (concluído)";
      carregarLeads();
      carregarEstado();
      if (aoTerminarTarefa) { aoTerminarTarefa(); aoTerminarTarefa = null; }
      if (t.resultado?.download) {
        $("#console-extra").innerHTML = `<a href="${t.resultado.download}">Baixar ${esc(t.resultado.nome)}</a>`;
        $("#console-extra").hidden = false;
      }
    }
  }, 1000);
}
$("#btn-parar").addEventListener("click", () => api("/api/tarefa/parar", { method: "POST" }));
$("#btn-fechar-console").addEventListener("click", () => ($("#console").hidden = true));

// ---------------------------------------------------------------- início
(async function iniciar() {
  try {
    await carregarEstado();
    await Promise.all([carregarNichos(), carregarRegioes()]);
    await carregarLeads();
    if (estado.nichos[0]) editarNicho(estado.nichos[0].id);
    // Se uma tarefa já estava rodando (ex.: recarregou a página), mostra o progresso
    const t = await api("/api/tarefa");
    if (t.rodando) acompanharTarefa("Tarefa em andamento");
  } catch (erro) {
    avisar("Não consegui falar com o servidor. O app.py está rodando?", true);
  }
})();
