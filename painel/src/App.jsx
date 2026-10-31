import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { configurado } from "./supabase.js";
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
  const [pedidos, setPedidos] = useState([]);
  const [menuAberto, setMenuAberto] = useState(false);   // menu do celular (botão ⋯)

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
    api.nichos().then(setNichos).catch((e) => avisar(e.message, "erro"));
    api.regioes().then(setRegioes).catch((e) => avisar(e.message, "erro"));
  }, [avisar]);

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

  const carregarPedidos = useCallback(async () => {
    try {
      const lista = await api.pedidos();
      setPedidos(lista);
      return lista;
    } catch {
      return null;
    }
  }, []);

  // Acompanha a fila de pedidos do PC. Com pedido aberto, olha a cada 3 segundos;
  // sem, a cada 20 (para não gastar a cota do Supabase à toa).
  // Os leads novos aparecem no quadro a cada 15 segundos durante a busca e no fim dela.
  const abertosAntes = useRef(false);
  const ultimaRecarga = useRef(0);
  const recarregarAgora = useRef(recarregar);
  recarregarAgora.current = recarregar;
  useEffect(() => {
    let ativo = true;
    let espera;
    async function ciclo() {
      if (!ativo) return;
      const lista = await carregarPedidos();
      const abertos = Boolean(lista?.some((p) => p.status === "pendente" || p.status === "rodando"));
      const rodando = Boolean(lista?.some((p) => p.status === "rodando"));
      const acabou = abertosAntes.current && !abertos;
      if (acabou || (rodando && Date.now() - ultimaRecarga.current > 15000)) {
        ultimaRecarga.current = Date.now();
        recarregarAgora.current();
      } else if (!document.hidden && Date.now() - ultimaRecarga.current > 60000) {
        ultimaRecarga.current = Date.now();
        carregarEstado();   // mantém o "PC ligado/desligado" em dia
      }
      abertosAntes.current = abertos;
      espera = setTimeout(ciclo, abertos ? 3000 : 20000);
    }
    ciclo();
    return () => {
      ativo = false;
      clearTimeout(espera);
    };
  }, [carregarPedidos, carregarEstado]);

  const aoPedir = useCallback(() => {
    abertosAntes.current = true;
    carregarPedidos();
    carregarEstado();
  }, [carregarPedidos, carregarEstado]);

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

  if (!configurado) {
    return (
      <div className="carregando-tela">
        Falta configurar o banco: crie o arquivo painel/.env (ou as variáveis no Netlify) com
        VITE_SUPABASE_URL e VITE_SUPABASE_CHAVE.
      </div>
    );
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
      <nav className={`menu${menuAberto ? " aberto" : ""}`} aria-label="Seções">
        <div className="menu-topo">
          <div className="marca">Prospecta</div>
          <span className="menu-atual">{ABAS.find((a) => a.id === aba)?.nome}</span>
          <button className="menu-botao" aria-label={menuAberto ? "Fechar menu" : "Abrir menu"}
                  aria-expanded={menuAberto} aria-controls="menu-itens" onClick={() => setMenuAberto(!menuAberto)}>
            {menuAberto ? "×" : "⋯"}
          </button>
        </div>
        <div className="menu-itens" id="menu-itens">
        {ABAS.map((a) => (
          <button key={a.id} className={`menu-item${aba === a.id ? " ativo" : ""}`}
                  onClick={() => { setAba(a.id); setMenuAberto(false); }}>
            {a.nome}
            {contagem[a.id] > 0 && <span className={`contador${a.id === "ligar" ? " alerta" : ""}`}>{contagem[a.id]}</span>}
            {a.id === "busca" && pedidos.some((p) => p.status === "rodando") && <span className="pulso" aria-label="rodando" />}
          </button>
        ))}
        <div className="menu-rodape">
          <span className={`bolinha ${estado.pc_ligado ? "ligado" : "desligado"}`} aria-hidden="true" />
          PC {estado.pc_ligado ? "ligado" : "desligado"}
        </div>
        </div>
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
          <Busca estado={estado} nichos={nichos} regioes={regioes} pedidos={pedidos} avisar={avisar} aoPedir={aoPedir} />
        )}
        {aba === "config" && (
          <Config estado={estado} nichos={nichos} regioes={regioes} avisar={avisar} aoPedir={aoPedir}
                  aoMudar={() => { carregarConfig(); recarregar(); }} />
        )}
      </main>

      {aberto && (
        <Detalhe id={aberto} estado={estado} avisar={avisar} aoFechar={() => setAberto(null)} aoMudar={recarregar}
                 aoPedir={aoPedir} />
      )}

      {aviso && <div key={aviso.id} className={`aviso aviso-${aviso.tipo}`} role="status">{aviso.texto}</div>}
    </div>
  );
}
