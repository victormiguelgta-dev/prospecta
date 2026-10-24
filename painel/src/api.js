// Conversa com o servidor Python (FastAPI). Todas as rotas começam com /api.

async function chamar(metodo, caminho, corpo) {
  const opcoes = { method: metodo, headers: {} };
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  const resposta = await fetch(`/api${caminho}`, opcoes);
  if (!resposta.ok) {
    let mensagem = `Erro ${resposta.status}`;
    try {
      const dados = await resposta.json();
      if (dados.detail) mensagem = typeof dados.detail === "string" ? dados.detail : JSON.stringify(dados.detail);
    } catch {
      /* resposta sem JSON */
    }
    throw new Error(mensagem);
  }
  return resposta.json();
}

function consulta(filtros) {
  const partes = Object.entries(filtros || {}).filter(([, v]) => v !== "" && v != null);
  return partes.length ? "?" + new URLSearchParams(partes).toString() : "";
}

export const api = {
  estado: () => chamar("GET", "/estado"),
  leads: (filtros) => chamar("GET", `/leads${consulta(filtros)}`),
  ligarHoje: () => chamar("GET", "/ligar-hoje"),
  lead: (id) => chamar("GET", `/leads/${encodeURIComponent(id)}`),
  editar: (id, campos) => chamar("PATCH", `/leads/${encodeURIComponent(id)}`, campos),
  congelar: (id, dataLigar, motivo) =>
    chamar("POST", `/leads/${encodeURIComponent(id)}/congelar`, { data_ligar: dataLigar, motivo }),
  arquivar: (id, motivo) => chamar("POST", `/leads/${encodeURIComponent(id)}/arquivar`, { motivo }),
  reativar: (id) => chamar("POST", `/leads/${encodeURIComponent(id)}/reativar`),
  excluir: (id) => chamar("DELETE", `/leads/${encodeURIComponent(id)}`),
  novoContato: (id, tipo, anotacao) =>
    chamar("POST", `/leads/${encodeURIComponent(id)}/contatos`, { tipo, anotacao }),
  apagarContato: (contatoId) => chamar("DELETE", `/contatos/${contatoId}`),
  analisar: (id, usarIa = true) => chamar("POST", `/leads/${encodeURIComponent(id)}/analisar?usar_ia=${usarIa}`),
  recoletar: (id) => chamar("POST", `/leads/${encodeURIComponent(id)}/recoletar`),
  diagnostico: (id) => chamar("POST", `/leads/${encodeURIComponent(id)}/diagnostico`),
  pacote: (id) => chamar("GET", `/leads/${encodeURIComponent(id)}/pacote`),
  linkPacote: (id, formato) => `/api/leads/${encodeURIComponent(id)}/pacote?formato=${formato}&baixar=true`,
  reanalisar: (ids = [], usarIa = true) => chamar("POST", "/reanalisar", { ids, usar_ia: usarIa }),
  nichos: () => chamar("GET", "/nichos"),
  salvarNicho: (nicho) => chamar("POST", "/nichos", nicho),
  excluirNicho: (id) => chamar("DELETE", `/nichos/${encodeURIComponent(id)}`),
  regioes: () => chamar("GET", "/regioes"),
  salvarRegioes: (lista) => chamar("PUT", "/regioes", lista),
  buscar: (opcoes) => chamar("POST", "/busca", opcoes),
  tarefa: (desde) => chamar("GET", `/tarefa?desde=${desde}`),
  pararTarefa: () => chamar("POST", "/tarefa/parar"),
  linkExportar: (filtros) => `/api/exportar${consulta(filtros)}`,
};

// Datas no formato brasileiro
export function dataBr(valor) {
  if (!valor) return "";
  const [ano, mes, dia] = valor.slice(0, 10).split("-");
  return dia ? `${dia}/${mes}/${ano}` : valor;
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
