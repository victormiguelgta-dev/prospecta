"""
Servidor do Prospecta (CRM de prospecção). Rode com:   python app.py
e abra http://localhost:8000 no navegador.

Ele junta tudo: serve o painel em React (pasta painel/dist, gerada pelo
"npm run build") e expõe a API que o painel usa para conversar com o bot.
"""
import asyncio
import re
import sys
import threading
from datetime import date, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import analise, config, db, exportar, nichos, pacote
from core.diagnostico import PASTA_DIAGNOSTICO, diagnosticar
from core.ia import ia_disponivel, modelo_em_uso
from core.limpeza import NOMES_REDES, SITUACOES, normalizar_whatsapp
from core.mensagem import link_ligar, link_whatsapp, mensagem_inicial
from core.oportunidades import NOMES_SERVICOS
from core.scraper import recoletar_lead, rodar_busca

app = FastAPI(title="Prospecta")
db.iniciar()


@app.middleware("http")
async def sem_cache(request, chamar):
    """O navegador não guarda cópia da API: o painel sempre vê os dados mais novos."""
    resposta = await chamar(request)
    if request.url.path.startswith("/api"):
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


# ---------------------------------------------------------------------------
# Tarefas longas (busca, recoleta, reanálise) rodam numa thread separada.
# O painel consulta o progresso a cada segundo.
# Só uma tarefa por vez, para não abrir vários navegadores juntos.
# ---------------------------------------------------------------------------
class Tarefa:
    def __init__(self):
        self.tipo = None
        self.rodando = False
        self.parar = False
        self.log = []
        self.inicio = None
        self.resultado = None   # ex.: link de download no fim do diagnóstico

    def escrever(self, *partes):
        linha = " ".join(str(p) for p in partes)
        self.log.append(f"{datetime.now():%H:%M:%S}  {linha}")
        print(linha)

    def iniciar(self, tipo, funcao):
        if self.rodando:
            raise HTTPException(409, f"Já existe uma tarefa rodando ({self.tipo}). Espere ou clique em Parar.")
        self.tipo, self.rodando, self.parar, self.log, self.inicio = tipo, True, False, [], datetime.now()
        self.resultado = None

        def executar():
            try:
                funcao()
            except Exception as erro:
                self.escrever(f"❌ Erro: {erro}")
            finally:
                self.rodando = False

        threading.Thread(target=executar, daemon=True).start()


tarefa = Tarefa()


def _rodar_async(corrotina):
    """Roda código async numa thread própria (Playwright no Windows precisa do Proactor)."""
    loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
    try:
        return loop.run_until_complete(corrotina)
    finally:
        loop.close()


def _enriquecer(lead: dict) -> dict:
    """Campos calculados que o painel usa (links prontos, rótulos)."""
    lead["situacao_rotulo"] = SITUACOES.get(lead.get("situacao_site"), "")
    lead["mensagem"] = mensagem_inicial(lead)
    lead["link_whatsapp"] = link_whatsapp(lead)
    lead["link_ligar"] = link_ligar(lead)
    if lead.get("etapa_em"):
        try:
            lead["dias_na_etapa"] = (date.today() - datetime.fromisoformat(lead["etapa_em"]).date()).days
        except ValueError:
            lead["dias_na_etapa"] = None
    # O painel não precisa das avaliações inteiras na lista (são só para classificar)
    lead.pop("avaliacoes_lidas", None)
    lead.pop("depoimentos", None)
    return lead


def _lead_ou_404(lead_id: str) -> dict:
    lead = db.buscar(lead_id)
    if not lead:
        raise HTTPException(404, "Lead não encontrado")
    return lead


# ------------------------------- Estado geral ------------------------------
@app.get("/api/estado")
def estado():
    return {
        "ia": ia_disponivel(),
        "modelo_ia": modelo_em_uso(),
        "seu_nome": config.SEU_NOME,
        "resumo": db.resumo(),
        "etapas": [{"id": e, "nome": db.NOMES_ETAPAS[e]} for e in db.ETAPAS],
        "classes": [{"id": c, "nome": db.NOMES_CLASSES[c]} for c in db.CLASSES],
        "servicos": [{"id": s, "nome": n} for s, n in NOMES_SERVICOS.items()],
        "tipos_contato": db.TIPOS_CONTATO,
        "situacoes": SITUACOES,
        "redes": NOMES_REDES,
        "tarefa_rodando": tarefa.rodando,
    }


# ---------------------------------- Nichos ---------------------------------
class NichoEntrada(BaseModel):
    id: str = ""
    nome: str
    termo_busca: str = ""
    icone: str = "✦"
    agenda: bool = False
    pedido_online: bool = False


@app.get("/api/nichos")
def listar_nichos():
    return nichos.listar_nichos()


@app.post("/api/nichos")
def salvar_nicho(nicho: NichoEntrada):
    dados = nicho.model_dump()
    # Nicho novo (sem id) com o nome de um que já existe: avisa em vez de sobrescrever
    if not dados["id"] and nichos.carregar_nicho(dados["nome"]):
        raise HTTPException(409, f'Já existe um nicho "{dados["nome"]}". Abra ele na lista ou use outro nome.')
    try:
        return nichos.salvar_nicho(dados)
    except ValueError as erro:
        raise HTTPException(400, str(erro))


@app.delete("/api/nichos/{nicho_id}")
def excluir_nicho(nicho_id: str):
    nichos.excluir_nicho(nicho_id)
    return {"ok": True}


# --------------------------------- Regiões ---------------------------------
@app.get("/api/regioes")
def listar_regioes():
    return nichos.listar_regioes()


@app.put("/api/regioes")
def salvar_regioes(regioes: list[str]):
    return nichos.salvar_regioes(regioes)


# ---------------------------------- Busca ----------------------------------
class BuscaEntrada(BaseModel):
    nicho: str
    regioes: list[str]
    limite: int = 10
    headless: bool = True
    buscar_instagram: bool = True
    coletar_extras: bool = True
    usar_ia: bool = True


def _analisar_e_contar(lead_id: str, usar_ia: bool):
    """Analisa o lead que o bot acabou de salvar e escreve a classe no log."""
    try:
        lead = analise.analisar(lead_id, usar_ia, log=tarefa.escrever)
    except Exception as erro:
        tarefa.escrever(f"    análise falhou: {str(erro)[:120]}")
        return
    if lead.get("estado") == "descartado":
        tarefa.escrever(f"    ⛔ descartado: {lead.get('motivo')}")
    else:
        servicos = ", ".join(NOMES_SERVICOS[o["servico"]] for o in lead.get("oportunidades") or []) or "nada"
        tarefa.escrever(f"    ✅ {db.NOMES_CLASSES.get(lead['classe'], '')} ({lead['nota_potencial']}/100) · vender: {servicos}")


@app.post("/api/busca")
def iniciar_busca(busca: BuscaEntrada):
    nicho = nichos.carregar_nicho(busca.nicho)
    if not nicho:
        raise HTTPException(404, "Nicho não encontrado")
    if not busca.regioes:
        raise HTTPException(400, "Escolha pelo menos uma região")
    opcoes = {"limite": max(1, min(busca.limite, 60)), "headless": busca.headless,
              "buscar_instagram": busca.buscar_instagram, "coletar_extras": busca.coletar_extras}

    async def ao_salvar(lead_id):
        await asyncio.to_thread(_analisar_e_contar, lead_id, busca.usar_ia)

    tarefa.iniciar("busca", lambda: _rodar_async(
        rodar_busca(nicho, busca.regioes, opcoes, tarefa.escrever, lambda: tarefa.parar, ao_salvar)))
    return {"ok": True}


@app.get("/api/tarefa")
def ver_tarefa(desde: int = 0):
    return {"tipo": tarefa.tipo, "rodando": tarefa.rodando, "total": len(tarefa.log), "log": tarefa.log[desde:],
            "resultado": tarefa.resultado, "inicio": tarefa.inicio.isoformat() if tarefa.inicio else None}


@app.post("/api/tarefa/parar")
def parar_tarefa():
    tarefa.parar = True
    tarefa.escrever("⏸ Parando depois do item atual...")
    return {"ok": True}


# ---------------------------------- Leads ----------------------------------
@app.get("/api/leads")
def listar_leads(nicho: str = "", etapa: str = "", estado: str = "ativo", classe: str = "", servico: str = "",
                 texto: str = ""):
    return [_enriquecer(l) for l in db.listar(nicho or None, etapa or None, estado or None, classe or None,
                                               servico or None, texto or None)]


@app.get("/api/ligar-hoje")
def leads_para_ligar_hoje():
    return [_enriquecer(l) for l in db.ligar_hoje()]


@app.get("/api/leads/{lead_id}")
def ver_lead(lead_id: str):
    lead = _enriquecer(_lead_ou_404(lead_id))
    lead["contatos"] = db.listar_contatos(lead_id)
    return lead


class LeadEdicao(BaseModel):
    etapa: str | None = None
    proximo_passo: str | None = None
    data_proximo_passo: str | None = None
    observacoes: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    nome: str | None = None


@app.patch("/api/leads/{lead_id}")
def editar_lead(lead_id: str, edicao: LeadEdicao):
    lead = _lead_ou_404(lead_id)
    campos = {k: v for k, v in edicao.model_dump().items() if v is not None}
    if "etapa" in campos:
        if campos["etapa"] not in db.ETAPAS:
            raise HTTPException(400, "Etapa inválida")
        if campos["etapa"] != lead.get("etapa"):
            db.adicionar_contato(lead_id, "anotacao",
                                 f"Movido para {db.NOMES_ETAPAS[campos['etapa']]}")
        if lead.get("estado") == "descartado":
            campos["estado"] = "ativo"   # você decidiu trabalhar com ele mesmo assim
    if "whatsapp" in campos:
        campos["whatsapp"] = normalizar_whatsapp(campos["whatsapp"])
    db.atualizar(lead_id, campos)
    return ver_lead(lead_id)


class CongelarEntrada(BaseModel):
    data_ligar: str = ""     # AAAA-MM-DD: o dia em que você quer ligar de novo
    motivo: str = "Parou de responder"


@app.post("/api/leads/{lead_id}/congelar")
def congelar(lead_id: str, entrada: CongelarEntrada):
    _lead_ou_404(lead_id)
    if entrada.data_ligar and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entrada.data_ligar):
        raise HTTPException(400, "Data inválida (use AAAA-MM-DD)")
    db.atualizar(lead_id, {"estado": "congelado", "motivo": entrada.motivo,
                           "proximo_passo": "Ligar de novo (congelado)" if entrada.data_ligar else "",
                           "data_proximo_passo": entrada.data_ligar})
    db.adicionar_contato(lead_id, "anotacao", f"Congelado: {entrada.motivo}")
    return ver_lead(lead_id)


class ArquivarEntrada(BaseModel):
    motivo: str = "Sem interesse agora"


@app.post("/api/leads/{lead_id}/arquivar")
def arquivar(lead_id: str, entrada: ArquivarEntrada):
    _lead_ou_404(lead_id)
    db.atualizar(lead_id, {"estado": "arquivado", "motivo": entrada.motivo, "data_proximo_passo": ""})
    db.adicionar_contato(lead_id, "anotacao", f"Arquivado: {entrada.motivo}")
    return ver_lead(lead_id)


@app.post("/api/leads/{lead_id}/reativar")
def reativar(lead_id: str):
    lead = _lead_ou_404(lead_id)
    db.atualizar(lead_id, {"estado": "ativo", "motivo": ""})
    db.adicionar_contato(lead_id, "anotacao", f"Voltou para o quadro (estava {lead.get('estado')})")
    return ver_lead(lead_id)


@app.delete("/api/leads/{lead_id}")
def excluir_lead(lead_id: str):
    db.excluir(lead_id)
    return {"ok": True}


class ContatoEntrada(BaseModel):
    tipo: str = "anotacao"
    anotacao: str = ""


@app.post("/api/leads/{lead_id}/contatos")
def novo_contato(lead_id: str, contato: ContatoEntrada):
    _lead_ou_404(lead_id)
    if contato.tipo not in db.TIPOS_CONTATO:
        raise HTTPException(400, "Tipo de contato inválido")
    db.adicionar_contato(lead_id, contato.tipo, contato.anotacao.strip())
    return ver_lead(lead_id)


@app.delete("/api/contatos/{contato_id}")
def apagar_contato(contato_id: int):
    db.excluir_contato(contato_id)
    return {"ok": True}


# ------------------------------- Análise -----------------------------------
@app.post("/api/leads/{lead_id}/analisar")
def analisar_um(lead_id: str, usar_ia: bool = True):
    _lead_ou_404(lead_id)
    try:
        analise.analisar(lead_id, usar_ia)
    except Exception as erro:
        raise HTTPException(500, f"Não consegui analisar: {erro}")
    return ver_lead(lead_id)


class ReanaliseEntrada(BaseModel):
    ids: list[str] = []      # vazio = todos os leads ativos
    usar_ia: bool = True


@app.post("/api/reanalisar")
def reanalisar(entrada: ReanaliseEntrada):
    ids = entrada.ids or [l["id"] for l in db.listar(estado="ativo")]

    def executar():
        for i, lead_id in enumerate(ids, 1):
            if tarefa.parar:
                tarefa.escrever("⏹ Interrompido.")
                break
            tarefa.escrever(f"[{i}/{len(ids)}] {db.buscar(lead_id)['nome']}")
            _analisar_e_contar(lead_id, entrada.usar_ia)
        tarefa.escrever(f"🏁 {len(ids)} leads analisados.")
    tarefa.iniciar("reanalise", executar)
    return {"ok": True, "total": len(ids)}


@app.post("/api/leads/{lead_id}/recoletar")
def recoletar(lead_id: str):
    """Busca de novo no Maps os dados deste lead e analisa outra vez."""
    lead = _lead_ou_404(lead_id)
    nicho = nichos.carregar_nicho(lead["nicho"]) or {"id": lead["nicho"], "nome": lead["nicho"]}

    def executar():
        tarefa.escrever(f"🔄 Buscando de novo no Maps: {lead['nome']}")
        try:
            _rodar_async(recoletar_lead(lead, nicho, tarefa.escrever))
        except Exception as erro:
            tarefa.escrever(f"❌ Não consegui abrir a ficha no Maps: {str(erro).splitlines()[0][:160]}")
            return
        _analisar_e_contar(lead_id, True)
    tarefa.iniciar("recoleta", executar)
    return {"ok": True}


@app.post("/api/leads/{lead_id}/diagnostico")
def diagnostico(lead_id: str):
    """Abre a ficha do lead no Maps e salva prints + relatório do que o bot achou."""
    lead = _lead_ou_404(lead_id)

    def executar():
        nome = _rodar_async(diagnosticar(lead, tarefa.escrever))
        tarefa.resultado = {"download": f"/api/diagnostico/{nome}", "nome": nome}
        tarefa.escrever("Baixe o arquivo pelo link abaixo e mande para o Claude.")
    tarefa.iniciar("diagnostico", executar)
    return {"ok": True}


@app.get("/api/diagnostico/{nome}")
def baixar_diagnostico(nome: str):
    if not re.fullmatch(r"diagnostico-[a-z0-9-]+\.zip", nome) or not (PASTA_DIAGNOSTICO / nome).exists():
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(PASTA_DIAGNOSTICO / nome, filename=nome)


# -------------------------------- Pacote -----------------------------------
@app.get("/api/leads/{lead_id}/pacote")
def ver_pacote(lead_id: str, formato: str = "md", baixar: bool = False):
    """O pacote do cliente em Markdown (para ler e copiar) ou JSON (para outra ferramenta)."""
    lead = _lead_ou_404(lead_id)
    dados = pacote.montar(lead)
    nome = f"pacote-{re.sub(r'[^a-z0-9]+', '-', lead['nome'].lower()).strip('-')[:50] or 'lead'}"
    if formato == "json":
        if baixar:
            import json
            return PlainTextResponse(json.dumps(dados, ensure_ascii=False, indent=2), media_type="application/json",
                                     headers={"Content-Disposition": f'attachment; filename="{nome}.json"'})
        return dados
    texto = pacote.para_markdown(dados)
    if baixar:
        return PlainTextResponse(texto, media_type="text/markdown; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{nome}.md"'})
    return {"texto": texto}


@app.get("/api/exportar")
def exportar_leads(formato: str = "xlsx", nicho: str = "", estado: str = "ativo", classe: str = ""):
    leads = db.listar(nicho or None, None, estado or None, classe or None)
    nome = f"leads_{nicho or 'todos'}"
    caminho = exportar.para_json(leads, nome) if formato == "json" else exportar.para_excel(leads, nome)
    return FileResponse(caminho, filename=Path(caminho).name)


# ------------------------------ Painel (React) ------------------------------
PAGINA_SEM_BUILD = """<!doctype html><meta charset="utf-8"><title>Prospecta</title>
<body style="font-family:system-ui;max-width:640px;margin:48px auto;padding:0 16px;line-height:1.5">
<h1>O painel ainda não foi montado</h1>
<p>A API está funcionando, mas falta gerar o painel em React. No terminal, na pasta do projeto:</p>
<pre style="background:#f2f4f7;padding:12px;border-radius:8px">cd painel
npm install
npm run build</pre>
<p>Depois recarregue esta página. Para programar o painel com recarga automática, use
<code>npm run dev</code> e abra o endereço que ele mostrar.</p></body>"""

if (config.PASTA_PAINEL / "assets").exists():
    app.mount("/assets", StaticFiles(directory=config.PASTA_PAINEL / "assets"), name="assets")


@app.get("/{caminho:path}", include_in_schema=False)
def painel(caminho: str):
    """Qualquer endereço que não é da API abre o painel (o React cuida das telas)."""
    if caminho.startswith("api/"):
        raise HTTPException(404, "Rota da API não encontrada")
    arquivo = (config.PASTA_PAINEL / caminho).resolve()
    if caminho and arquivo.is_file() and config.PASTA_PAINEL.resolve() in arquivo.parents:
        return FileResponse(arquivo)
    indice = config.PASTA_PAINEL / "index.html"
    if indice.exists():
        return FileResponse(indice, headers={"Cache-Control": "no-store"})
    return HTMLResponse(PAGINA_SEM_BUILD)


if __name__ == "__main__":
    print(f"\n  Painel aberto em: http://localhost:{config.PORTA}")
    if config.HOST not in ("127.0.0.1", "localhost"):
        print(f"  Também aceita conexões em {config.HOST} (VPN/rede). Não deixe aberto na internet.")
    print()
    uvicorn.run(app, host=config.HOST, port=config.PORTA)
