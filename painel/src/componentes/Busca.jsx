// Nova busca no Maps e a fila de pedidos para o PC (busca, reanálise, diagnóstico).
import { useEffect, useRef, useState } from "react";
import { api, dataBr, horaBr } from "../api.js";

const NOMES_PEDIDO = { busca: "Busca", analisar: "Análise", recoletar: "Buscar de novo", diagnostico: "Diagnóstico" };
const NOMES_STATUS = {
  pendente: "Na fila", rodando: "Rodando", concluido: "Pronto", erro: "Deu erro", cancelado: "Cancelado",
};
const aberto = (p) => p.status === "pendente" || p.status === "rodando";

function descrever(p) {
  const par = p.parametros || {};
  if (p.tipo === "busca") return `${par.nicho || ""} · ${(par.regioes || []).length} região(ões)`;
  if (p.tipo === "analisar") return par.ids?.length ? `${par.ids.length} lead(s)` : "todos do quadro";
  return "";
}

export default function Busca({ estado, nichos, regioes, pedidos, aoPedir, avisar }) {
  const [form, setForm] = useState({
    nicho: "", regioes: [], limite: 10, headless: true, buscar_instagram: true, coletar_extras: true, usar_ia: true,
  });
  const [escolhido, setEscolhido] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const fimDoLog = useRef(null);

  useEffect(() => {
    if (!form.nicho && nichos.length) setForm((f) => ({ ...f, nicho: nichos[0].id }));
  }, [nichos, form.nicho]);

  // Sem escolha, mostra o pedido rodando (ou o mais recente)
  const pedido = pedidos.find((p) => p.id === escolhido) || pedidos.find((p) => p.status === "rodando") || pedidos[0];
  const log = pedido?.log || [];

  useEffect(() => {
    fimDoLog.current?.scrollIntoView({ block: "nearest" });
  }, [log.length]);

  function alternarRegiao(regiao) {
    setForm((f) => ({
      ...f,
      regioes: f.regioes.includes(regiao) ? f.regioes.filter((r) => r !== regiao) : [...f.regioes, regiao],
    }));
  }

  async function iniciar(e) {
    e.preventDefault();
    setEnviando(true);
    try {
      const novo = await api.buscar({ ...form, limite: Number(form.limite) });
      setEscolhido(novo.id);
      avisar(estado.pc_ligado ? "Busca enviada para o PC" : "Busca na fila: ela começa quando o PC ligar o trabalhador");
      aoPedir();
    } catch (erro) {
      avisar(erro.message, "erro");
    } finally {
      setEnviando(false);
    }
  }

  async function parar(p) {
    try {
      await api.pararPedido(p);
      avisar(p.status === "pendente" ? "Pedido cancelado" : "Parando depois do item atual…");
      aoPedir();
    } catch (erro) {
      avisar(erro.message, "erro");
    }
  }

  return (
    <section className="busca">
      <header className="lista-topo">
        <h1>Nova busca</h1>
        <p className="ajuda">
          O bot procura o nicho em cada região, coleta os dados de cada negócio e já classifica:
          Potencial (70 ou mais), Talvez (40 a 69) e Pouco potencial (abaixo de 40). Comece com poucas regiões e
          10 locais por região: buscas grandes aumentam o risco de bloqueio do Google.
        </p>
      </header>

      <div className={`status-pc ${estado.pc_ligado ? "ligado" : "desligado"}`} role="status">
        <span className="bolinha" aria-hidden="true" />
        {estado.pc_ligado ? (
          <span>PC ligado · IA {estado.ia ? `ligada (${estado.modelo_ia})` : "desligada"}</span>
        ) : (
          <span>
            PC desligado{estado.pc_visto_em && ` (visto por último em ${dataBr(estado.pc_visto_em)} ${horaBr(estado.pc_visto_em)})`}.
            Você pode pedir a busca mesmo assim: ela fica na fila e roda quando você ligar o trabalhador no PC.
          </span>
        )}
      </div>

      <form className="form-busca" onSubmit={iniciar}>
        <label>Nicho
          <select id="busca-nicho" value={form.nicho} onChange={(e) => setForm({ ...form, nicho: e.target.value })}>
            {nichos.map((n) => <option key={n.id} value={n.id}>{n.icone} {n.nome}</option>)}
          </select>
        </label>
        <label>Locais novos por região
          <input id="busca-limite" type="number" min={1} max={60} value={form.limite}
                 onChange={(e) => setForm({ ...form, limite: e.target.value })} />
        </label>

        <fieldset>
          <legend>Regiões ({form.regioes.length} escolhidas)</legend>
          <div className="regioes">
            {regioes.map((r) => (
              <label key={r} className={`chip${form.regioes.includes(r) ? " ativo" : ""}`}>
                <input type="checkbox" checked={form.regioes.includes(r)} onChange={() => alternarRegiao(r)} />
                {r}
              </label>
            ))}
            {!regioes.length && <p className="vazio">Cadastre regiões em Configurações.</p>}
          </div>
        </fieldset>

        <fieldset className="opcoes">
          <legend>Opções</legend>
          <label className="check"><input type="checkbox" checked={form.coletar_extras}
            onChange={(e) => setForm({ ...form, coletar_extras: e.target.checked })} />
            Ler avaliações e fotos (classificação melhor, busca mais lenta)</label>
          <label className="check"><input type="checkbox" checked={form.buscar_instagram}
            onChange={(e) => setForm({ ...form, buscar_instagram: e.target.checked })} />
            Abrir o Instagram para contar posts e seguidores</label>
          <label className="check"><input type="checkbox" checked={form.usar_ia}
            onChange={(e) => setForm({ ...form, usar_ia: e.target.checked })} />
            Usar a IA (o que vender, dores e redes pela web; precisa da chave do Gemini no .env do PC)</label>
          <label className="check"><input type="checkbox" checked={!form.headless}
            onChange={(e) => setForm({ ...form, headless: !e.target.checked })} />
            Mostrar o navegador no PC enquanto o bot trabalha</label>
        </fieldset>

        <div className="linha">
          <button className="btn btn-primario" disabled={enviando || !form.regioes.length || !form.nicho}>
            {estado.pc_ligado ? "Começar busca" : "Pôr busca na fila"}
          </button>
        </div>
      </form>

      <section className="log" aria-live="polite">
        <h2>Pedidos para o PC</h2>
        {pedidos.length > 0 ? (
          <ul className="pedidos">
            {pedidos.map((p) => (
              <li key={p.id}>
                <button className={`pedido${pedido?.id === p.id ? " ativo" : ""}`} onClick={() => setEscolhido(p.id)}>
                  <span className={`status status-${p.status}`}>{NOMES_STATUS[p.status]}</span>
                  <strong>{NOMES_PEDIDO[p.tipo]}</strong>
                  <span>{descrever(p)}</span>
                  <time>{dataBr(p.criado_em)} {horaBr(p.criado_em)}</time>
                </button>
              </li>
            ))}
          </ul>
        ) : <p className="vazio">Nenhum pedido ainda.</p>}

        {pedido && (
          <>
            <div className="linha">
              <h3>{NOMES_PEDIDO[pedido.tipo]} · {NOMES_STATUS[pedido.status]}{pedido.parar && aberto(pedido) ? " (parando…)" : ""}</h3>
              {aberto(pedido) && !pedido.parar && (
                <button type="button" className="btn btn-perigo" onClick={() => parar(pedido)}>
                  {pedido.status === "pendente" ? "Cancelar" : "Parar"}
                </button>
              )}
            </div>
            <pre>
              {log.join("\n") || (pedido.status === "pendente" ? "Esperando o PC pegar este pedido…" : "Sem mensagens.")}
              <span ref={fimDoLog} />
            </pre>
            {pedido.resultado?.arquivo_no_pc && (
              <p className="ajuda">Arquivo salvo no PC: <code>{pedido.resultado.arquivo_no_pc}</code></p>
            )}
          </>
        )}
      </section>
    </section>
  );
}
