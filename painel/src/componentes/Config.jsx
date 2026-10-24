// Configurações: nichos, regiões, reanálise e exportação.
import { useEffect, useState } from "react";
import { api } from "../api.js";

const NICHO_NOVO = { id: "", nome: "", termo_busca: "", icone: "✦", agenda: false, pedido_online: false };

export default function Config({ estado, nichos, regioes, aoMudar, avisar }) {
  const [nicho, setNicho] = useState(NICHO_NOVO);
  const [textoRegioes, setTextoRegioes] = useState("");

  useEffect(() => setTextoRegioes(regioes.join("\n")), [regioes]);

  async function salvarNicho(e) {
    e.preventDefault();
    try {
      const salvo = await api.salvarNicho(nicho);
      setNicho(salvo);
      avisar("Nicho salvo");
      aoMudar();
    } catch (erro) {
      avisar(erro.message, "erro");
    }
  }

  async function excluirNicho() {
    if (!nicho.id || !window.confirm(`Excluir o nicho ${nicho.nome}? Os leads dele continuam no quadro.`)) return;
    await api.excluirNicho(nicho.id);
    setNicho(NICHO_NOVO);
    avisar("Nicho excluído");
    aoMudar();
  }

  async function salvarRegioes() {
    try {
      await api.salvarRegioes(textoRegioes.split("\n"));
      avisar("Regiões salvas");
      aoMudar();
    } catch (erro) {
      avisar(erro.message, "erro");
    }
  }

  async function reanalisarTodos() {
    if (!window.confirm("Analisar de novo todos os leads do quadro? Com IA, isso gasta tokens do Gemini.")) return;
    try {
      const r = await api.reanalisar([], estado.ia);
      avisar(`Reanalisando ${r.total} leads… acompanhe em Nova busca`);
      aoMudar();
    } catch (erro) {
      avisar(erro.message, "erro");
    }
  }

  return (
    <section className="config">
      <header className="lista-topo"><h1>Configurações</h1></header>

      <div className="config-grade">
        <section className="secao">
          <h2>Nichos</h2>
          <div className="chips">
            {nichos.map((n) => (
              <button key={n.id} className={`chip${nicho.id === n.id ? " ativo" : ""}`} onClick={() => setNicho(n)}>
                {n.icone} {n.nome}
              </button>
            ))}
            <button className="chip" onClick={() => setNicho(NICHO_NOVO)}>+ Novo nicho</button>
          </div>
          <form className="form-nicho" onSubmit={salvarNicho}>
            <label>Nome
              <input id="nicho-nome" value={nicho.nome} onChange={(e) => setNicho({ ...nicho, nome: e.target.value })}
                     placeholder="Ex.: Salões de beleza" required />
            </label>
            <label>O que o bot digita no Maps
              <input id="nicho-termo" value={nicho.termo_busca}
                     onChange={(e) => setNicho({ ...nicho, termo_busca: e.target.value })} placeholder="Ex.: Salão de beleza" />
            </label>
            <label>Ícone
              <input id="nicho-icone" value={nicho.icone} maxLength={4} onChange={(e) => setNicho({ ...nicho, icone: e.target.value })} />
            </label>
            <label className="check"><input type="checkbox" checked={nicho.agenda}
              onChange={(e) => setNicho({ ...nicho, agenda: e.target.checked })} />
              O ramo costuma agendar horário (liga a oportunidade “sem agendamento online”)</label>
            <label className="check"><input type="checkbox" checked={nicho.pedido_online}
              onChange={(e) => setNicho({ ...nicho, pedido_online: e.target.checked })} />
              O ramo vende por pedido (liga a oportunidade “sem pedido online nem cardápio digital”)</label>
            <div className="linha">
              <button className="btn btn-primario">Salvar nicho</button>
              {nicho.id && <button type="button" className="btn btn-perigo" onClick={excluirNicho}>Excluir</button>}
            </div>
          </form>
        </section>

        <section className="secao">
          <h2>Regiões</h2>
          <p className="ajuda">Uma por linha, do jeito que você digitaria no Maps (ex.: Taguatinga, DF).</p>
          <textarea id="regioes" rows={12} value={textoRegioes} onChange={(e) => setTextoRegioes(e.target.value)} />
          <button className="btn btn-primario" onClick={salvarRegioes}>Salvar regiões</button>
        </section>

        <section className="secao">
          <h2>Classificação</h2>
          <p className="ajuda">
            Os pesos da nota ficam no arquivo <code>dados/potencial.json</code>. Depois de mudar os pesos
            ou de melhorar o bot, reanalise os leads para atualizar a nota e as oportunidades.
          </p>
          <p className="ajuda">IA: {estado.ia ? `ligada (${estado.modelo_ia})` : "desligada — coloque GEMINI_API_KEY no arquivo .env"}</p>
          <button className="btn" onClick={reanalisarTodos}>Reanalisar todos os leads do quadro</button>
        </section>

        <section className="secao">
          <h2>Exportar</h2>
          <p className="ajuda">Planilha com a classe, o que vender, os contatos e todas as redes sociais.</p>
          <div className="linha">
            <a className="btn" href={api.linkExportar({ formato: "xlsx" })}>Excel do quadro</a>
            <a className="btn" href={api.linkExportar({ formato: "xlsx", estado: "" })}>Excel com todos</a>
            <a className="btn" href={api.linkExportar({ formato: "json" })}>JSON do quadro</a>
          </div>
        </section>
      </div>
    </section>
  );
}
