// Pequenos selos reaproveitados no quadro, nas listas e no detalhe do lead.

export const NOMES_CLASSE = { potencial: "Potencial", talvez: "Talvez", pouco: "Pouco potencial" };
export const NOMES_SERVICO = { maps: "Maps", site: "Site", desenvolvimento: "Desenvolvimento" };
export const NOMES_FORCA = { alta: "alta", media: "média", baixa: "baixa" };
export const SIGLAS_REDE = {
  instagram: "IG", facebook: "FB", tiktok: "TT", youtube: "YT",
  linkedin: "in", linktree: "LT", ifood: "iF", x: "X",
};

export function SeloClasse({ classe, nota }) {
  if (!classe) return <span className="selo selo-neutro">Sem análise</span>;
  return (
    <span className={`selo selo-${classe}`} title="Nota de potencial (0 a 100)">
      {NOMES_CLASSE[classe]} {nota != null && <b>{nota}</b>}
    </span>
  );
}

export function SeloServico({ oportunidade, principal }) {
  const { servico, forca } = oportunidade;
  return (
    <span
      className={`servico servico-${servico} forca-${forca}${principal ? " principal" : ""}`}
      title={`Força ${NOMES_FORCA[forca]}${principal ? " · serviço principal" : ""}`}
    >
      {NOMES_SERVICO[servico]}
    </span>
  );
}

export function Redes({ redes, nomes }) {
  const lista = Object.entries(redes || {});
  if (!lista.length) return null;
  return (
    <span className="redes">
      {lista.map(([rede, url]) => (
        <a key={rede} href={url} target="_blank" rel="noreferrer" title={nomes?.[rede] || rede}
           onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
          {SIGLAS_REDE[rede] || rede}
        </a>
      ))}
    </span>
  );
}
