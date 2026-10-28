// Configurações: seu nome, nichos, regiões, reanálise e exportação.
import { useEffect, useState } from "react";
import { api, baixarArquivo, hojeIso } from "../api.js";
import { paraCsv, paraJson } from "../exportar.js";

const NICHO_NOVO = { id: "", nome: "", termo_busca: "", icone: "✦", agenda: false, pedido_online: false };

export default function Config({ estado, nichos, regioes, aoMudar, aoPedir, avisar }) {
  const [nicho, setNicho] = useState(NICHO_NOVO);
  const [textoRegioes, setTextoRegioes] = useState("");
  const [nome, setNome] = useState(estado.seu_nome || "");
  const [exportando, setExportando] = useState(false);

  useEffect(() => setTextoRegioes(regioes.join("\n")), [regioes]);

  async function salvarNome(e) {
    e.preventDefault();
    try {
      await api.salvarSeuNome(nome);
      avisar("Nome salvo");
      aoMudar();
    } catch (erro) {
      avisar(erro.message, "erro");
    }
  }

  async function exportar(formato, estadoLeads) {
    setExportando(true);
    try {
      const leads = await api.leadsCompletos({ estado: estadoLeads });
      const nomeArquivo = `leads_${estadoLeads || "todos"}_${hojeIso()}`;
      if (formato === "json") baixarArquivo(`${nomeArquivo}.json`, paraJson(leads), "application/json");
      else baixarArquivo(`${nomeArquivo}.csv`, paraCsv(leads), "text/csv;charset=utf-8");
    } catch (erro) {
      avisar(erro.message, "erro");
    } finally {
      setExportando(false);
    }
  }

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
    try {
      await api.excluirNicho(nicho.id);
      setNicho(NICHO_NOVO);
      avisar("Nicho excluído");
      aoMudar();
    } catch (erro) {
      avisar(erro.message, "erro");
    }
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
      await api.reanalisar([], true);
      avisar(estado.pc_ligado ? "Reanálise enviada para o PC… acompanhe em Nova busca"
        : "Reanálise na fila: ela roda quando você ligar o trabalhador no PC");
      aoPedir();
    } catch (erro) {
      avisar(erro.message, "erro");
    }
  }

  return (
    <section className="config">
      <header className="lista-topo"><h1>Configurações</h1></header>

      <div className="config-grade">
        <section className="secao">
          <h2>Seu nome</h2>
          <p className="ajuda">Vai na primeira mensagem de WhatsApp (“Meu nome é …”).</p>
          <form className="form-linha" onSubmit={salvarNome}>
            <input id="seu-nome" value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Seu nome" />
            <button className="btn btn-primario">Salvar</button>
          </form>
        </section>

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
            Os pesos da nota ficam no arquivo <code>dados/potencial.json</code>, no PC. Depois de mudar os pesos
            ou de melhorar o bot, reanalise os leads para atualizar a nota e as oportunidades.
          </p>
          <p className="ajuda">
            {estado.pc_ligado
              ? `PC ligado · IA ${estado.ia ? `ligada (${estado.modelo_ia})` : "desligada: coloque GEMINI_API_KEY no .env do PC"}`
              : "PC desligado: a reanálise fica na fila até você ligar o trabalhador."}
          </p>
          <button className="btn" onClick={reanalisarTodos}>Reanalisar todos os leads do quadro</button>
        </section>

        <section className="secao">
          <h2>Exportar</h2>
          <p className="ajuda">
            Planilha (abre no Excel e no Google Planilhas) com a classe, o que vender, os contatos e todas as redes
            sociais. O PC também guarda um backup completo por dia na pasta <code>saida/backups</code>.
          </p>
          <div className="linha">
            <button className="btn" disabled={exportando} onClick={() => exportar("csv", "ativo")}>Planilha do quadro</button>
            <button className="btn" disabled={exportando} onClick={() => exportar("csv", "")}>Planilha com todos</button>
            <button className="btn" disabled={exportando} onClick={() => exportar("json", "")}>JSON com todos</button>
          </div>
        </section>
      </div>
    </section>
  );
}
