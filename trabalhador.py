"""
Trabalhador do Prospecta: roda no seu computador e faz o trabalho pesado.

Rode com:   python trabalhador.py

O painel (no Netlify) não busca nada sozinho: quando você pede uma busca, uma
reanálise ou um diagnóstico, ele grava um "pedido" no Supabase. Este programa
fica olhando a fila, faz o pedido (abre o Maps, classifica, chama a IA) e
escreve o progresso de volta, que aparece no painel.

Enquanto ele estiver rodando, o painel mostra "PC ligado". Com o PC desligado,
os pedidos esperam na fila e rodam quando você ligar o trabalhador de novo.
Ele também faz um backup de todos os leads neste computador, uma vez por dia.
"""
import asyncio
import sys
import time
from datetime import datetime

from core import analise, config, db
from core.diagnostico import diagnosticar
from core.ia import ia_disponivel, modelo_em_uso
from core.oportunidades import NOMES_SERVICOS
from core.scraper import recoletar_lead, rodar_busca

ESPERA_ENTRE_OLHADAS = 5        # segundos entre uma olhada e outra na fila
AVISO_LIGADO_A_CADA = 30        # segundos entre os avisos de "PC ligado"
BACKUP_A_CADA = 24 * 60 * 60    # um backup por dia

_ultimo_aviso = float("-inf")


def avisar_que_estou_ligado(forcar=False):
    """Atualiza o "PC ligado" do painel (no máximo a cada AVISO_LIGADO_A_CADA segundos)."""
    global _ultimo_aviso
    if forcar or time.monotonic() - _ultimo_aviso > AVISO_LIGADO_A_CADA:
        try:
            db.avisar_que_estou_ligado(ia_disponivel(), modelo_em_uso())
            _ultimo_aviso = time.monotonic()
        except Exception as erro:
            print(f"  (não consegui avisar o painel que o PC está ligado: {erro})")


class LogDoPedido:
    """Escreve no terminal e manda as linhas para o painel a cada 2 segundos."""

    def __init__(self, pedido_id: int):
        self.pedido_id = pedido_id
        self.pendentes = []
        self.ultimo_envio = time.monotonic()
        self.parar_cache = (0.0, False)

    def __call__(self, *partes):
        linha = f"{datetime.now():%H:%M:%S}  " + " ".join(str(p) for p in partes)
        print(linha, flush=True)
        self.pendentes.append(linha)
        if time.monotonic() - self.ultimo_envio > 2:
            self.enviar()

    def enviar(self):
        if not self.pendentes:
            return
        linhas, self.pendentes = self.pendentes, []
        try:
            db.escrever_no_pedido(self.pedido_id, linhas)
        except Exception as erro:
            print(f"  (não consegui mandar o log para o painel: {erro})")
        self.ultimo_envio = time.monotonic()
        avisar_que_estou_ligado()   # numa busca longa, o painel continua vendo "PC ligado"

    def deve_parar(self) -> bool:
        """Confere no máximo a cada 3 segundos se você clicou em Parar no painel."""
        quando, resposta = self.parar_cache
        if time.monotonic() - quando > 3:
            try:
                resposta = db.pediu_para_parar(self.pedido_id)
            except Exception:
                pass
            self.parar_cache = (time.monotonic(), resposta)
        return resposta


def _analisar_e_contar(lead_id: str, usar_ia: bool, log):
    """Analisa um lead e escreve no log a classe e o que vender."""
    try:
        lead = analise.analisar(lead_id, usar_ia, log=log)
    except Exception as erro:
        log(f"    análise falhou: {str(erro)[:120]}")
        return
    if lead.get("estado") == "descartado":
        log(f"    ⛔ descartado: {lead.get('motivo')}")
    else:
        servicos = ", ".join(NOMES_SERVICOS[o["servico"]] for o in lead.get("oportunidades") or []) or "nada"
        log(f"    ✅ {db.NOMES_CLASSES.get(lead['classe'], '')} ({lead['nota_potencial']}/100) · vender: {servicos}")


def fazer_busca(parametros: dict, log) -> dict:
    nicho = db.carregar_nicho(parametros.get("nicho"))
    if not nicho:
        raise ValueError("Nicho não encontrado")
    regioes = parametros.get("regioes") or []
    if not regioes:
        raise ValueError("Nenhuma região escolhida")
    opcoes = {
        "limite": max(1, min(int(parametros.get("limite") or 10), 60)),
        "headless": parametros.get("headless", True),
        "buscar_instagram": parametros.get("buscar_instagram", True),
        "coletar_extras": parametros.get("coletar_extras", True),
    }
    usar_ia = parametros.get("usar_ia", True)

    async def ao_salvar(lead_id):
        await asyncio.to_thread(_analisar_e_contar, lead_id, usar_ia, log)

    total = asyncio.run(rodar_busca(nicho, regioes, opcoes, log, log.deve_parar, ao_salvar))
    return {"leads_novos": total}


def reanalisar(parametros: dict, log) -> dict:
    ids = parametros.get("ids") or []
    leads = db.listar(ids=ids) if ids else db.listar(estado="ativo")
    for i, lead in enumerate(leads, 1):
        if log.deve_parar():
            log("⏹ Interrompido.")
            break
        log(f"[{i}/{len(leads)}] {lead['nome']}")
        _analisar_e_contar(lead["id"], parametros.get("usar_ia", True), log)
    log(f"🏁 {len(leads)} leads analisados.")
    return {"analisados": len(leads)}


def recoletar(parametros: dict, log) -> dict:
    lead = db.buscar(parametros.get("id"))
    if not lead:
        raise ValueError("Lead não encontrado")
    nicho = db.carregar_nicho(lead["nicho"]) or {"id": lead["nicho"], "nome": lead["nicho"]}
    log(f"🔄 Buscando de novo no Maps: {lead['nome']}")
    asyncio.run(recoletar_lead(lead, nicho, log))
    _analisar_e_contar(lead["id"], True, log)
    return {"id": lead["id"]}


def diagnostico(parametros: dict, log) -> dict:
    lead = db.buscar(parametros.get("id"))
    if not lead:
        raise ValueError("Lead não encontrado")
    nome = asyncio.run(diagnosticar(lead, log))
    caminho = config.PASTA_SAIDA / "diagnostico" / nome
    log(f"Arquivo salvo neste computador: {caminho}")
    return {"arquivo_no_pc": str(caminho)}


TAREFAS = {"busca": fazer_busca, "analisar": reanalisar, "recoletar": recoletar, "diagnostico": diagnostico}


def executar(pedido: dict):
    log = LogDoPedido(pedido["id"])
    log(f"▶ Pedido {pedido['id']} ({pedido['tipo']}) começou neste computador.")
    try:
        resultado = TAREFAS[pedido["tipo"]](pedido.get("parametros") or {}, log)
        status = "cancelado" if log.deve_parar() else "concluido"
    except KeyboardInterrupt:
        log("⏹ O trabalhador foi fechado no meio do pedido.")
        log.enviar()
        db.concluir_pedido(pedido["id"], "cancelado", {"erro": "trabalhador fechado"})
        raise
    except Exception as erro:
        log(f"❌ Erro: {str(erro).splitlines()[0][:200] if str(erro) else erro.__class__.__name__}")
        resultado, status = {"erro": str(erro)[:500]}, "erro"
    log.enviar()
    db.concluir_pedido(pedido["id"], status, resultado)


def principal():
    print("\n  Prospecta: trabalhador ligado. Deixe esta janela aberta.")
    print(f"  IA: {'ligada (' + modelo_em_uso() + ')' if ia_disponivel() else 'desligada (sem GEMINI_API_KEY)'}")
    print("  Para parar: Ctrl + C\n")
    ultimo_backup = 0.0
    while True:
        try:
            avisar_que_estou_ligado()
            if time.monotonic() - ultimo_backup > BACKUP_A_CADA or not ultimo_backup:
                print(f"  💾 Backup salvo em {db.fazer_backup()}")
                ultimo_backup = time.monotonic()
            pedido = db.pegar_proximo_pedido()
            if pedido:
                executar(pedido)
                avisar_que_estou_ligado(forcar=True)
                continue
        except KeyboardInterrupt:
            raise
        except Exception as erro:
            print(f"  ⚠ {str(erro)[:200]} (tentando de novo em instantes)")
        time.sleep(ESPERA_ENTRE_OLHADAS)


if __name__ == "__main__":
    try:
        principal()
    except KeyboardInterrupt:
        print("\n  Trabalhador desligado. Os pedidos novos esperam na fila até você ligar de novo.")
        sys.exit(0)
