// Lista de leads fora do quadro (ligar hoje, congelados, arquivados, descartados pelo bot).
import { dataBr, hojeIso } from "../api.js";
import { Redes, SeloClasse, SeloServico } from "./Selos.jsx";

const NOMES_ETAPA = { lead_novo: "Lead novo", em_contato: "Em contato", interessado: "Cliente interessado", fechado: "Fechado" };
const NOMES_ESTADO = { ativo: "No quadro", congelado: "Congelado", arquivado: "Arquivado", descartado: "Descartado" };

export default function Lista({ titulo, ajuda, leads, redes, aoAbrir, aoReativar, mostrarData, vazio }) {
  return (
    <section className="lista">
      <header className="lista-topo">
        <h1>{titulo}</h1>
        {ajuda && <p className="ajuda">{ajuda}</p>}
      </header>
      {!leads.length && <p className="vazio grande">{vazio}</p>}
      <ul>
        {leads.map((lead) => {
          const atrasado = lead.data_proximo_passo && lead.data_proximo_passo.slice(0, 10) < hojeIso();
          return (
            <li key={lead.id} className="linha-lead" onClick={() => aoAbrir(lead.id)}>
              <div className="linha-lead-nome">
                <strong>{lead.nome}</strong>
                <span className="cartao-local">
                  {[NOMES_ESTADO[lead.estado] !== "No quadro" ? NOMES_ESTADO[lead.estado] : NOMES_ETAPA[lead.etapa],
                    (lead.regiao || "").split(",")[0]].filter(Boolean).join(" · ")}
                </span>
                {lead.motivo && <span className="motivo">{lead.motivo}</span>}
              </div>
              <div className="linha-lead-info">
                <SeloClasse classe={lead.classe} nota={lead.nota_potencial} />
                {lead.oportunidades?.map((o) => (
                  <SeloServico key={o.servico} oportunidade={o} principal={o.servico === lead.servico_principal} />
                ))}
                <Redes redes={lead.redes} nomes={redes} />
              </div>
              <div className="linha-lead-acoes" onClick={(e) => e.stopPropagation()}>
                {mostrarData && lead.data_proximo_passo && (
                  <span className={`proximo${atrasado ? " atrasado" : ""}`} title={lead.proximo_passo}>
                    {dataBr(lead.data_proximo_passo)} {lead.proximo_passo && `· ${lead.proximo_passo}`}
                  </span>
                )}
                {lead.link_ligar && <a className="btn" href={lead.link_ligar}>Ligar</a>}
                {lead.link_whatsapp && <a className="btn btn-whats" href={lead.link_whatsapp} target="_blank" rel="noreferrer">WhatsApp</a>}
                {aoReativar && lead.estado !== "ativo" && (
                  <button className="btn" onClick={() => aoReativar(lead)}>Voltar para o quadro</button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
