// Ficha completa de um lead: contato, próximo passo, histórico, o que vender, redes, mensagem e pacote.
import { useEffect, useState } from "react";
import { api, baixarArquivo, dataBr, horaBr, somarDias } from "../api.js";
import { montarPacote, nomeDoArquivo, paraMarkdown } from "../pacote.js";
import { NOMES_FORCA, NOMES_SERVICO, SeloClasse } from "./Selos.jsx";

const NOMES_TIPO = { ligacao: "Ligação", whatsapp: "WhatsApp", visita: "Visita", email: "E-mail", anotacao: "Anotação" };
const NOMES_ESTADO = { ativo: "No quadro", congelado: "Congelado", arquivado: "Arquivado", descartado: "Descartado pelo bot" };
const MOTIVOS_ARQUIVO = ["Sem interesse agora", "Sem dinheiro agora", "Já tem alguém", "Não é o dono / contato errado", "Outro"];

function Secao({ titulo, children, extra }) {
  return (
    <section className="secao">
      <div className="secao-titulo">
        <h3>{titulo}</h3>
        {extra}
      </div>
      {children}
    </section>
  );
}

function Campo({ rotulo, children }) {
  if (children == null || children === "" || children === false) return null;
  return (
    <div className="campo">
      <dt>{rotulo}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export default function Detalhe({ id, estado, aoFechar, aoMudar, aoPedir, avisar }) {
  const [lead, setLead] = useState(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [mensagem, setMensagem] = useState("");
  const [passo, setPasso] = useState({ texto: "", data: "" });
  const [contato, setContato] = useState({ tipo: "whatsapp", anotacao: "" });
  const [painelSair, setPainelSair] = useState(null); // "congelar" | "arquivar"
  const [congelar, setCongelar] = useState({ data: somarDias(30), motivo: "Parou de responder" });
  const [arquivar, setArquivar] = useState({ motivo: MOTIVOS_ARQUIVO[0], outro: "" });
  const [pacote, setPacote] = useState("");

  function receber(dados) {
    setLead(dados);
    setMensagem(dados.mensagem || "");
    setPasso({ texto: dados.proximo_passo || "", data: (dados.data_proximo_passo || "").slice(0, 10) });
  }

  useEffect(() => {
    setLead(null);
    setPacote("");
    setPainelSair(null);
    api.lead(id).then(receber).catch((e) => setErro(e.message));
  }, [id]);

  useEffect(() => {
    const fechar = (e) => e.key === "Escape" && aoFechar();
    window.addEventListener("keydown", fechar);
    return () => window.removeEventListener("keydown", fechar);
  }, [aoFechar]);

  async function acao(funcao, aviso) {
    setOcupado(true);
    try {
      const dados = await funcao();
      if (dados && dados.nome) receber(dados);
      if (aviso) avisar(aviso);
      aoMudar();
      return dados;
    } catch (e) {
      avisar(e.message, "erro");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Gaveta aoFechar={aoFechar}><p className="erro">{erro}</p></Gaveta>;
  if (!lead) return <Gaveta aoFechar={aoFechar}><p className="carregando">Carregando…</p></Gaveta>;

  const ia = lead.analise_ia || {};
  const linkWhats = lead.link_whatsapp ? lead.link_whatsapp.split("?")[0] + "?text=" + encodeURIComponent(mensagem) : "";
  const fora = lead.estado !== "ativo";

  // Trabalho pesado vira pedido na fila: quem faz é o trabalhador do PC
  async function pedir(funcao, aviso) {
    setOcupado(true);
    try {
      await funcao();
      avisar(estado.pc_ligado ? `${aviso} Acompanhe em Nova busca.`
        : `${aviso} O PC está desligado: o pedido espera na fila até você ligar o trabalhador.`);
      aoPedir();
    } catch (e) {
      avisar(e.message, "erro");
    } finally {
      setOcupado(false);
    }
  }

  const verPacote = () => setPacote(paraMarkdown(montarPacote(lead)));
  const baixarPacote = (formato) => {
    const dados = montarPacote(lead);
    if (formato === "json") {
      baixarArquivo(`${nomeDoArquivo(lead)}.json`, JSON.stringify(dados, null, 2), "application/json");
    } else {
      baixarArquivo(`${nomeDoArquivo(lead)}.md`, paraMarkdown(dados), "text/markdown;charset=utf-8");
    }
  };

  async function copiar(texto, aviso) {
    try {
      await navigator.clipboard.writeText(texto);
      avisar(aviso);
    } catch {
      avisar("Não consegui copiar. Selecione o texto e copie à mão.", "erro");
    }
  }

  return (
    <Gaveta aoFechar={aoFechar}>
      <header className="detalhe-topo">
        <div>
          <h2>{lead.nome}</h2>
          <p className="cartao-local">{[lead.categoria, lead.regiao].filter(Boolean).join(" · ")}</p>
          <div className="linha">
            <SeloClasse classe={lead.classe} nota={lead.nota_potencial} />
            {fora && <span className={`selo selo-estado-${lead.estado}`}>{NOMES_ESTADO[lead.estado]}</span>}
            {lead.motivo && <span className="motivo">{lead.motivo}</span>}
          </div>
        </div>
        <button className="btn-icone" onClick={aoFechar} aria-label="Fechar">×</button>
      </header>

      <div className="acoes-contato">
        {lead.link_ligar && <a className="btn" href={lead.link_ligar}>Ligar</a>}
        {linkWhats && <a className="btn btn-whats" href={linkWhats} target="_blank" rel="noreferrer">WhatsApp</a>}
        <label className="etapa-select">
          Etapa
          <select value={lead.etapa || "lead_novo"} disabled={ocupado}
                  onChange={(e) => acao(() => api.editar(lead.id, { etapa: e.target.value }), "Etapa alterada")}>
            {estado.etapas.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
          </select>
        </label>
      </div>

      <div className="acoes-sair">
        {fora ? (
          <button className="btn" disabled={ocupado} onClick={() => acao(() => api.reativar(lead.id), "Voltou para o quadro")}>
            Voltar para o quadro
          </button>
        ) : (
          <>
            <button className={`btn${painelSair === "congelar" ? " ativo" : ""}`}
                    onClick={() => setPainelSair(painelSair === "congelar" ? null : "congelar")}>Congelar</button>
            <button className={`btn${painelSair === "arquivar" ? " ativo" : ""}`}
                    onClick={() => setPainelSair(painelSair === "arquivar" ? null : "arquivar")}>Arquivar</button>
          </>
        )}
      </div>

      {painelSair === "congelar" && (
        <form className="caixa-acao" onSubmit={(e) => {
          e.preventDefault();
          acao(() => api.congelar(lead.id, congelar.data, congelar.motivo), "Lead congelado").then(() => setPainelSair(null));
        }}>
          <p>Para quem demonstrou interesse e parou de responder. Ele sai do quadro e aparece em “Ligar hoje” no dia escolhido.</p>
          <label>Ligar de novo em
            <input id="congelar-data" type="date" value={congelar.data} onChange={(e) => setCongelar({ ...congelar, data: e.target.value })} />
          </label>
          <label>Motivo
            <input id="congelar-motivo" value={congelar.motivo} onChange={(e) => setCongelar({ ...congelar, motivo: e.target.value })} />
          </label>
          <button className="btn btn-primario" disabled={ocupado}>Congelar</button>
        </form>
      )}
      {painelSair === "arquivar" && (
        <form className="caixa-acao" onSubmit={(e) => {
          e.preventDefault();
          const motivo = arquivar.motivo === "Outro" ? arquivar.outro || "Outro" : arquivar.motivo;
          acao(() => api.arquivar(lead.id, motivo), "Lead arquivado").then(() => setPainelSair(null));
        }}>
          <p>Para quem não tem interesse agora. Fica guardado em “Arquivados” e dá para voltar depois.</p>
          <label>Motivo
            <select id="arquivar-motivo" value={arquivar.motivo} onChange={(e) => setArquivar({ ...arquivar, motivo: e.target.value })}>
              {MOTIVOS_ARQUIVO.map((m) => <option key={m}>{m}</option>)}
            </select>
          </label>
          {arquivar.motivo === "Outro" && (
            <input id="arquivar-outro" placeholder="Qual?" value={arquivar.outro}
                   onChange={(e) => setArquivar({ ...arquivar, outro: e.target.value })} />
          )}
          <button className="btn btn-primario" disabled={ocupado}>Arquivar</button>
        </form>
      )}

      <Secao titulo="Próximo passo">
        <form className="form-linha" onSubmit={(e) => {
          e.preventDefault();
          acao(() => api.editar(lead.id, { proximo_passo: passo.texto, data_proximo_passo: passo.data }), "Próximo passo salvo");
        }}>
          <input id="passo-texto" placeholder="Ex.: Ligar às 10h" value={passo.texto}
                 onChange={(e) => setPasso({ ...passo, texto: e.target.value })} />
          <input id="passo-data" type="date" value={passo.data} onChange={(e) => setPasso({ ...passo, data: e.target.value })} />
          <button className="btn" disabled={ocupado}>Salvar</button>
        </form>
      </Secao>

      <Secao titulo="O que vender">
        {lead.oportunidades?.length ? (
          <ul className="oportunidades">
            {lead.oportunidades.map((o) => (
              <li key={o.servico} className={`forca-${o.forca}`}>
                <strong>
                  {NOMES_SERVICO[o.servico]}
                  {o.servico === lead.servico_principal && <span className="principal-tag">principal</span>}
                </strong>
                <span className="forca">força {NOMES_FORCA[o.forca]}</span>
                <p>{o.motivo}</p>
                <ul>{o.evidencias.map((e) => <li key={e}>{e}</li>)}</ul>
              </li>
            ))}
          </ul>
        ) : <p className="vazio">Nenhuma oportunidade encontrada.</p>}
      </Secao>

      {(ia.resumo || ia.dores?.length > 0) && (
        <Secao titulo="Análise da IA">
          {ia.resumo && <p>{ia.resumo}</p>}
          {ia.dores?.length > 0 && (
            <ul className="dores">
              {ia.dores.map((d) => <li key={d.dor}><strong>{d.dor}</strong> <span>{d.prova}</span></li>)}
            </ul>
          )}
          <dl className="campos">
            <Campo rotulo="Público">{ia.publico}</Campo>
            <Campo rotulo="Diferencial">{ia.diferencial}</Campo>
          </dl>
        </Secao>
      )}

      <Secao titulo="Mensagem de WhatsApp">
        <textarea id="mensagem" rows={5} value={mensagem} onChange={(e) => setMensagem(e.target.value)} />
        <div className="linha">
          {linkWhats ? <a className="btn btn-whats" href={linkWhats} target="_blank" rel="noreferrer">Abrir no WhatsApp</a>
            : <span className="vazio">Sem celular ou WhatsApp para mandar mensagem.</span>}
          <button className="btn" onClick={() => copiar(mensagem, "Mensagem copiada")}>Copiar</button>
          <button className="btn" disabled={ocupado} onClick={() =>
            acao(() => api.novoContato(lead.id, "whatsapp", "Mensagem enviada"), "Anotado no histórico")}>Marcar como enviada</button>
        </div>
      </Secao>

      <Secao titulo="Histórico">
        <form className="form-linha" onSubmit={(e) => {
          e.preventDefault();
          if (!contato.anotacao.trim()) return;
          acao(() => api.novoContato(lead.id, contato.tipo, contato.anotacao), "Anotado").then(() =>
            setContato({ ...contato, anotacao: "" }));
        }}>
          <select id="contato-tipo" value={contato.tipo} onChange={(e) => setContato({ ...contato, tipo: e.target.value })}>
            {estado.tipos_contato.map((t) => <option key={t} value={t}>{NOMES_TIPO[t]}</option>)}
          </select>
          <input id="contato-anotacao" placeholder="O que aconteceu?" value={contato.anotacao}
                 onChange={(e) => setContato({ ...contato, anotacao: e.target.value })} />
          <button className="btn" disabled={ocupado}>Anotar</button>
        </form>
        <ol className="historico">
          {lead.contatos.map((c) => (
            <li key={c.id}>
              <time>{dataBr(c.data)} {horaBr(c.data)}</time>
              <span className="tipo">{NOMES_TIPO[c.tipo] || c.tipo}</span>
              <span>{c.anotacao}</span>
            </li>
          ))}
          {!lead.contatos.length && <li className="vazio">Nenhum contato ainda.</li>}
        </ol>
      </Secao>

      <Secao titulo="Contato e redes sociais">
        <dl className="campos">
          <Campo rotulo="Telefone">{lead.telefone}</Campo>
          <Campo rotulo="WhatsApp">{lead.whatsapp}</Campo>
          <Campo rotulo="E-mail">{lead.email}</Campo>
          <Campo rotulo="Endereço">{lead.endereco}</Campo>
          <Campo rotulo="Google Maps">{lead.maps_url && <a href={lead.maps_url} target="_blank" rel="noreferrer">Abrir no Maps</a>}</Campo>
          {Object.entries(lead.redes || {}).map(([rede, url]) => (
            <Campo key={rede} rotulo={estado.redes[rede] || rede}>
              <a href={url} target="_blank" rel="noreferrer">{url.replace(/^https?:\/\/(www\.)?/, "")}</a>
              {rede === "instagram" && lead.instagram_posts != null &&
                <span className="nota-campo"> · {lead.instagram_posts} posts, {lead.instagram_seguidores ?? "?"} seguidores</span>}
            </Campo>
          ))}
          {!Object.keys(lead.redes || {}).length && <Campo rotulo="Redes sociais">Nenhuma encontrada</Campo>}
          <Campo rotulo="Redes achadas em">{lead.redes_origem}</Campo>
        </dl>
      </Secao>

      <Secao titulo={`Classificação · Saúde do Maps ${lead.saude_maps ?? "?"}/100`}>
        <ul className="conta">
          {(lead.nota_detalhe || []).map((d) => <li key={d.sinal}><span>{d.sinal}</span><b>+{d.pontos}</b></li>)}
          <li className="total"><span>Nota de potencial</span><b>{lead.nota_potencial ?? "?"}</b></li>
        </ul>
        {lead.problemas_maps?.length > 0 && (
          <>
            <h4>Problemas do perfil no Maps</h4>
            <ul className="lista-simples">{lead.problemas_maps.map((p) => <li key={p}>{p}</li>)}</ul>
          </>
        )}
      </Secao>

      <Secao titulo="Dados do Google e do site">
        <dl className="campos">
          <Campo rotulo="Google">{lead.nota != null && `nota ${String(lead.nota).replace(".", ",")} · ${lead.avaliacoes ?? 0} avaliações`}</Campo>
          <Campo rotulo="Site">{lead.site && <a href={lead.site} target="_blank" rel="noreferrer">{lead.site}</a>}</Campo>
          <Campo rotulo="Situação do site">{lead.situacao_rotulo}</Campo>
          <Campo rotulo="Descrição do dono">{lead.descricao}</Campo>
          <Campo rotulo="Horário">{lead.horario?.length > 0 && lead.horario.join(" · ")}</Campo>
        </dl>
        {lead.fotos?.length > 0 && (
          <div className="fotos">
            {lead.fotos.slice(0, 10).map((f) => (
              <a key={f} href={f} target="_blank" rel="noreferrer"><img src={f.replace(/=w\d+-h\d+.*$/, "=w300-h200-k-no")} alt="" loading="lazy" /></a>
            ))}
          </div>
        )}
      </Secao>

      <Secao titulo="Pacote do cliente" extra={
        <div className="linha">
          <button className="btn" onClick={verPacote}>Ver</button>
          <button className="btn" onClick={() => baixarPacote("md")}>Baixar .md</button>
          <button className="btn" onClick={() => baixarPacote("json")}>Baixar .json</button>
        </div>
      }>
        <p className="ajuda">Tudo sobre o cliente num documento: para a conversa ou para mandar à IA fazer o site.</p>
        {pacote && (
          <>
            <button className="btn" onClick={() => copiar(pacote, "Pacote copiado")}>Copiar pacote</button>
            <pre className="pacote">{pacote}</pre>
          </>
        )}
      </Secao>

      <Secao titulo="Ferramentas">
        <div className="linha">
          <button className="btn" disabled={ocupado} onClick={() => pedir(() => api.analisar(lead.id), "Pedido de análise enviado.")}>
            Analisar de novo
          </button>
          <button className="btn" disabled={ocupado} onClick={() => pedir(() => api.recoletar(lead.id), "Pedido para buscar de novo no Maps enviado.")}>
            Buscar de novo no Maps
          </button>
          <button className="btn" disabled={ocupado} onClick={() => pedir(() => api.diagnostico(lead.id), "Pedido de diagnóstico enviado.")}>
            Diagnóstico do bot
          </button>
          <button className="btn btn-perigo" disabled={ocupado} onClick={async () => {
            if (!window.confirm(`Excluir ${lead.nome} para sempre? (Arquivar guarda o lead.)`)) return;
            await acao(() => api.excluir(lead.id), "Lead excluído");
            aoFechar();
          }}>Excluir</button>
        </div>
        {lead.analisado_em && <p className="ajuda">Analisado em {dataBr(lead.analisado_em)} {horaBr(lead.analisado_em)}</p>}
        <p className="ajuda">Analisar, buscar de novo e o diagnóstico rodam no seu PC (o trabalhador precisa estar ligado).
          O arquivo do diagnóstico fica salvo no PC.</p>
      </Secao>
    </Gaveta>
  );
}

function Gaveta({ children, aoFechar }) {
  return (
    <div className="gaveta-fundo" onClick={aoFechar}>
      <aside className="gaveta" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        {children}
      </aside>
    </div>
  );
}
