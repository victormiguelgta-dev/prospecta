// Quadro do CRM: 4 colunas (etapas). Arraste o cartão para mudar de etapa.
// No celular, segure o cartão por meio segundo antes de arrastar (assim a tela ainda rola).
import {
  DndContext, DragOverlay, PointerSensor, TouchSensor, useDraggable, useDroppable, useSensor, useSensors,
} from "@dnd-kit/core";
import { useState } from "react";
import { dataBr, hojeIso } from "../api.js";
import { Redes, SeloClasse, SeloServico } from "./Selos.jsx";

export function Cartao({ lead, redes, aoAbrir, arrastando }) {
  const atrasado = lead.data_proximo_passo && lead.data_proximo_passo.slice(0, 10) <= hojeIso();
  return (
    <article className={`cartao${arrastando ? " arrastando" : ""}`} onClick={() => aoAbrir?.(lead.id)}>
      <header>
        <h3>{lead.nome}</h3>
        <SeloClasse classe={lead.classe} nota={lead.nota_potencial} />
      </header>
      <p className="cartao-local">{[lead.categoria, (lead.regiao || "").split(",")[0]].filter(Boolean).join(" · ")}</p>
      {lead.oportunidades?.length > 0 && (
        <div className="cartao-servicos">
          {lead.oportunidades.map((o) => (
            <SeloServico key={o.servico} oportunidade={o} principal={o.servico === lead.servico_principal} />
          ))}
        </div>
      )}
      <footer>
        <Redes redes={lead.redes} nomes={redes} />
        {lead.data_proximo_passo && (
          <span className={`proximo${atrasado ? " atrasado" : ""}`} title={lead.proximo_passo || "Próximo passo"}>
            {dataBr(lead.data_proximo_passo)}
          </span>
        )}
      </footer>
    </article>
  );
}

function CartaoArrastavel({ lead, redes, aoAbrir }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: lead.id });
  return (
    <div ref={setNodeRef} {...listeners} {...attributes} className={isDragging ? "fantasma" : ""}>
      <Cartao lead={lead} redes={redes} aoAbrir={aoAbrir} />
    </div>
  );
}

function Coluna({ etapa, leads, redes, aoAbrir }) {
  const { setNodeRef, isOver } = useDroppable({ id: etapa.id });
  return (
    <section ref={setNodeRef} className={`coluna${isOver ? " sobre" : ""}`} aria-label={etapa.nome}>
      <h2>
        {etapa.nome} <span className="contador">{leads.length}</span>
      </h2>
      <div className="coluna-cartoes">
        {leads.map((lead) => (
          <CartaoArrastavel key={lead.id} lead={lead} redes={redes} aoAbrir={aoAbrir} />
        ))}
        {!leads.length && <p className="vazio">Nenhum lead aqui.</p>}
      </div>
    </section>
  );
}

export default function Quadro({ etapas, leads, redes, aoAbrir, aoMover }) {
  const [arrastado, setArrastado] = useState(null);
  const sensores = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 450, tolerance: 8 } }),
  );

  function soltar({ active, over }) {
    setArrastado(null);
    if (!over) return;
    const lead = leads.find((l) => l.id === active.id);
    if (lead && lead.etapa !== over.id) aoMover(lead, over.id);
  }

  return (
    <DndContext sensors={sensores} onDragStart={({ active }) => setArrastado(leads.find((l) => l.id === active.id))}
                onDragEnd={soltar} onDragCancel={() => setArrastado(null)}>
      <div className="quadro">
        {etapas.map((etapa) => (
          <Coluna key={etapa.id} etapa={etapa} redes={redes} aoAbrir={aoAbrir}
                  leads={leads.filter((l) => (l.etapa || "lead_novo") === etapa.id)} />
        ))}
      </div>
      <DragOverlay>{arrastado ? <Cartao lead={arrastado} redes={redes} arrastando /> : null}</DragOverlay>
    </DndContext>
  );
}
