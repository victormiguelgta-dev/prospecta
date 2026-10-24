import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import Busca from "./componentes/Busca.jsx";
import Config from "./componentes/Config.jsx";
import Detalhe from "./componentes/Detalhe.jsx";
import Lista from "./componentes/Lista.jsx";
import Quadro from "./componentes/Quadro.jsx";

const ABAS = [
  { id: "quadro", nome: "Quadro" },
  { id: "ligar", nome: "Ligar hoje" },
  { id: "congelados", nome: "Congelados" },
  { id: "arquivados", nome: "Arquivados" },
  { id: "busca", nome: "Nova busca" },
  { id: "config", nome: "Configurações" },
];
const FILTROS_VAZIOS = { texto: "", nicho: "", classe: "", servico: "" };

function abaDoEndereco() {
  const hash = window.location.hash.replace("#", "");
  return ABAS.some((a) => a.id === hash) ? hash : "quadro";
}

export default function App() {
  const [estado, setEstado] = useState(null);
  const [aba, setAba] = useState(abaDoEndereco);
  const [filtros, setFiltros] = useState(FILTROS_VAZIOS);
  const [leads, setLeads] = useState([]);
  const [fora, setFora] = useState([]);           // leads da aba atual fora do quadro
  const [nichos, setNichos] = useState([]);
  const [regioes, setRegioes] = useState([]);
  const [aberto, setAberto] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [tarefa, setTarefa] = useState({ rodando: false, tipo: null, log: [], resultado: null });
  const desdeLog = useRef(0);
  const inicioTarefa = useRef(undefined);

  const avisar = useCallback((texto, tipo = "ok") => {
    setAviso({ texto, tipo, id: Date.now() });
  }, []);

  useEffect(() => {
    if (!aviso) return undefined;
    const t = setTimeout(() => setAviso(null), aviso.tipo === "erro" ? 6000 : 3000);
    return () => clearTimeout(t);
  }, [aviso]);

  const carregarEstado = useCallback(() => api.estado().then(setEstado).catch((e) => avisar(e.message, "erro")), [avisar]);

  const carregarLeads = useCallback(async () => {
    try {
      if (aba === "quadro") setLeads(await api.leads(filtros));
      else if (aba === "ligar") setFora(await api.ligarHoje());
      else if (aba === "congelados") setFora(await api.leads({ ...filtros, estado: "congelado" }));
      else if (aba === "arquivados") {
        const [arquivados, descartados] = await Promise.all([
          api.leads({ ...filtros, estado: "arquivado" }), api.leads({ ...filtros, estado: "descartado" })]);
        setFora([...arquivados, ...descartados]);
      }
    } catch (e) {
      avisar(e.message, "erro");
    }
  }, [aba, filtros, avisar]);

  const recarregar = useCallback(() => {
    carregarEstado();
    carregarLeads();
  }, [carregarEstado, carregarLeads]);

  const carregarConfig = useCallback(() => {
    api.nichos().then(setNichos);
    api.regioes().then(setRegioes);
  }, []);

  useEffect(() => {
    carregarEstado();
    carregarConfig();
  }, [carregarEstado, carregarConfig]);

  useEffect(() => {
    const espera = setTimeout(carregarLeads, filtros.texto ? 250 : 0);
    return () => clearTimeout(espera);
  }, [carregarLeads, filtros.texto]);

  useEffect(() => {
    window.location.hash = aba;
  }, [aba]);

  // Acompanha a tarefa longa (busca, reanálise...) enquanto ela roda
  const consultarTarefa = useCallback(async () => {
    try {
      let t = await api.tarefa(desdeLog.current);
      let recomecou = false;
      if (t.inicio !== inicioTarefa.current) {
        // Começou uma tarefa nova: o log do servidor recomeçou do zero
        t = await api.tarefa(0);
        inicioTarefa.current = t.inicio;
        recomecou = true;
      }
      setTarefa((anterior) => ({
        rodando: t.rodando, tipo: t.tipo, resultado: t.resultado,
        log: recomecou ? t.log : [...anterior.log, ...t.log],
      }));
      desdeLog.current = t.total;
      return t.rodando;
    } catch {
      return false;
    }
  }, []);

  useEffect(() => {
    let ativo = true;
    let rodavaAntes = false;
    async function ciclo() {
      if (!ativo) return;
      const rodando = await consultarTarefa();
      if (rodando || rodavaAntes) recarregar();   // atualiza o quadro enquanto os leads chegam
      rodavaAntes = rodando;
      setTimeout(ciclo, rodando ? 1500 : 5000);
    }
    ciclo();
    return () => {
      ativo = false;
    };
  }, [consultarTarefa, recarregar]);

  async function mover(lead, etapa) {
    setLeads((lista) => lista.map((l) => (l.id === lead.id ? { ...l, etapa } : l)));
    try {
      await api.editar(lead.id, { etapa });
      recarregar();
    } catch (e) {
      avisar(e.message, "erro");
      carregarLeads();
    }
  }

  async function reativar(lead) {
    try {
      await api.reativar(lead.id);
      avisar(`${lead.nome} voltou para o quadro`);
      recarregar();
    } catch (e) {
      avisar(e.message, "erro");
    }
  }

  if (!estado) {
    return <div className="carregando-tela">Carregando o Prospecta…</div>;
  }

  const resumo = estado.resumo;
  const contagem = {
    quadro: Object.values(resumo.por_etapa).reduce((a, b) => a + b, 0),
    ligar: resumo.ligar_hoje,
    congelados: resumo.por_estado.congelado,
    arquivados: resumo.por_estado.arquivado + resumo.por_estado.descartado,
  };
  const mostraFiltros = ["quadro", "congelados", "arquivados"].includes(aba);

  return (
    <div className="app">
      <nav className="menu" aria-label="Seções">
        <div className="marca">Prospecta</div>
        {ABAS.map((a) => (
          <button key={a.id} className={`menu-item${aba === a.id ? " ativo" : ""}`} onClick={() => setAba(a.id)}>
            {a.nome}
            {contagem[a.id] > 0 && <span className={`contador${a.id === "ligar" ? " alerta" : ""}`}>{contagem[a.id]}</span>}
            {a.id === "busca" && tarefa.rodando && <span className="pulso" aria-label="rodando" />}
          </button>
        ))}
        <div className="menu-rodape">IA {estado.ia ? "ligada" : "desligada"}</div>
      </nav>

      <main className="area-principal">
        {mostraFiltros && (
          <div className="filtros">
            <input id="filtro-texto" type="search" placeholder="Buscar nome, região ou categoria" value={filtros.texto}
                   onChange={(e) => setFiltros({ ...filtros, texto: e.target.value })} />
            <select id="filtro-nicho" value={filtros.nicho} onChange={(e) => setFiltros({ ...filtros, nicho: e.target.value })}>
              <option value="">Todos os nichos</option>
              {nichos.map((n) => <option key={n.id} value={n.id}>{n.nome}</option>)}
            </select>
            <select id="filtro-servico" value={filtros.servico} onChange={(e) => setFiltros({ ...filtros, servico: e.target.value })}>
              <option value="">Qualquer serviço</option>
              {estado.servicos.map((s) => <option key={s.id} value={s.id}>Pode comprar: {s.nome}</option>)}
            </select>
            <div className="classes" role="group" aria-label="Classe">
              <button className={`chip${!filtros.classe ? " ativo" : ""}`} onClick={() => setFiltros({ ...filtros, classe: "" })}>
                Todas
              </button>
              {estado.classes.map((c) => (
                <button key={c.id} className={`chip chip-${c.id}${filtros.classe === c.id ? " ativo" : ""}`}
                        onClick={() => setFiltros({ ...filtros, classe: filtros.classe === c.id ? "" : c.id })}>
                  {c.nome} {aba === "quadro" && <b>{resumo.por_classe[c.id]}</b>}
                </button>
              ))}
            </div>
          </div>
        )}

        {aba === "quadro" && (
          <Quadro etapas={estado.etapas} leads={leads} redes={estado.redes} aoAbrir={setAberto} aoMover={mover} />
        )}
        {aba === "ligar" && (
          <Lista titulo="Ligar hoje" leads={fora} redes={estado.redes} aoAbrir={setAberto} mostrarData
                 ajuda="Leads do quadro e congelados com próximo passo para hoje ou atrasado."
                 vazio="Nada para hoje. Marque o próximo passo com data na ficha do lead." />
        )}
        {aba === "congelados" && (
          <Lista titulo="Congelados" leads={fora} redes={estado.redes} aoAbrir={setAberto} aoReativar={reativar} mostrarData
                 ajuda="Quem demonstrou interesse e parou de responder. No dia marcado, eles aparecem em Ligar hoje."
                 vazio="Nenhum lead congelado." />
        )}
        {aba === "arquivados" && (
          <Lista titulo="Arquivados" leads={fora} redes={estado.redes} aoAbrir={setAberto} aoReativar={reativar}
                 ajuda="Sem interesse agora (arquivados por você) e descartados pelo bot (fechado, sem telefone ou franquia)."
                 vazio="Nenhum lead arquivado." />
        )}
        {aba === "busca" && (
          <Busca estado={estado} nichos={nichos} regioes={regioes} tarefa={tarefa} avisar={avisar}
                 aoIniciar={() => { avisar("Busca iniciada"); consultarTarefa(); }} />
        )}
        {aba === "config" && (
          <Config estado={estado} nichos={nichos} regioes={regioes} avisar={avisar}
                  aoMudar={() => { carregarConfig(); recarregar(); }} />
        )}
      </main>

      {aberto && (
        <Detalhe id={aberto} estado={estado} avisar={avisar} aoFechar={() => setAberto(null)} aoMudar={recarregar} />
      )}

      {aviso && <div key={aviso.id} className={`aviso aviso-${aviso.tipo}`} role="status">{aviso.texto}</div>}
    </div>
  );
}
