// Nova busca no Maps e acompanhamento das tarefas longas (busca, reanálise, diagnóstico).
import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

export default function Busca({ estado, nichos, regioes, tarefa, aoIniciar, avisar }) {
  const [form, setForm] = useState({
    nicho: "", regioes: [], limite: 10, headless: true, buscar_instagram: true, coletar_extras: true, usar_ia: true,
  });
  const fimDoLog = useRef(null);

  useEffect(() => {
    if (!form.nicho && nichos.length) setForm((f) => ({ ...f, nicho: nichos[0].id }));
  }, [nichos, form.nicho]);

  useEffect(() => {
    fimDoLog.current?.scrollIntoView({ block: "nearest" });
  }, [tarefa.log.length]);

  function alternarRegiao(regiao) {
    setForm((f) => ({
      ...f,
      regioes: f.regioes.includes(regiao) ? f.regioes.filter((r) => r !== regiao) : [...f.regioes, regiao],
    }));
  }

  async function iniciar(e) {
    e.preventDefault();
    try {
      await api.buscar({ ...form, limite: Number(form.limite) });
      aoIniciar();
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
          <label className="check"><input type="checkbox" checked={form.usar_ia} disabled={!estado.ia}
            onChange={(e) => setForm({ ...form, usar_ia: e.target.checked })} />
            Usar a IA (o que vender, dores e redes pela web){!estado.ia && " — sem chave do Gemini no .env"}</label>
          <label className="check"><input type="checkbox" checked={!form.headless}
            onChange={(e) => setForm({ ...form, headless: !e.target.checked })} />
            Mostrar o navegador enquanto o bot trabalha</label>
        </fieldset>

        <div className="linha">
          <button className="btn btn-primario" disabled={tarefa.rodando || !form.regioes.length || !form.nicho}>
            Começar busca
          </button>
          {tarefa.rodando && <button type="button" className="btn btn-perigo" onClick={() => api.pararTarefa()}>Parar</button>}
        </div>
      </form>

      <section className="log" aria-live="polite">
        <h2>{tarefa.rodando ? `Rodando: ${tarefa.tipo}…` : tarefa.tipo ? `Última tarefa: ${tarefa.tipo}` : "Nenhuma tarefa ainda"}</h2>
        <pre>
          {tarefa.log.join("\n") || "O progresso aparece aqui."}
          <span ref={fimDoLog} />
        </pre>
        {tarefa.resultado?.download && (
          <a className="btn" href={tarefa.resultado.download}>Baixar {tarefa.resultado.nome}</a>
        )}
      </section>
    </section>
  );
}
