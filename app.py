"""
Servidor do painel. Rode com:   python app.py
e abra http://localhost:8000 no navegador.

Ele junta tudo: serve o painel (pasta painel/), expõe uma API simples
para o painel conversar com o bot, e mostra os demos em /demos/<slug>/.
"""
import asyncio
import sys
import threading
import zipfile
from datetime import datetime

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import arquivos_nicho, config, db, deploy, exportar, gerador, modelos, nichos, qualidade
from core.ia import ia_disponivel, modelo_em_uso
from core.limpeza import SITUACOES, eh_celular, normalizar_whatsapp
from core.scraper import recoletar_lead, rodar_busca
from core.diagnostico import PASTA_DIAGNOSTICO, diagnosticar

app = FastAPI(title="Prospecta Sites")
db.iniciar()


@app.middleware("http")
async def sem_cache(request, chamar):
    """
    O navegador não guarda cópia do painel nem dos demos: depois de atualizar
    o código ou refazer um site, a versão nova aparece no próximo carregamento.
    """
    resposta = await chamar(request)
    caminho = request.url.path
    if caminho == "/" or caminho.startswith(("/painel", "/demos", "/api", "/arquivos-nicho")):
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


# ---------------------------------------------------------------------------
# Tarefas longas (busca, geração em lote, publicação) rodam numa thread
# separada. O painel consulta o progresso a cada segundo.
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
    numero = lead.get("whatsapp") or normalizar_whatsapp(lead.get("telefone"))
    lead["situacao_rotulo"] = SITUACOES.get(lead.get("situacao_site"), "")
    lead["telefone_tipo"] = "whatsapp" if lead.get("whatsapp") else ("celular" if eh_celular(numero) else ("fixo" if numero else ""))
    lead["link_whatsapp"] = gerador.link_whatsapp(lead) if numero else ""
    lead["mensagem"] = gerador.mensagem_whatsapp(lead) if lead.get("slug") else ""
    lead["demo_local"] = f"/demos/{lead['slug']}/" if lead.get("slug") else ""
    lead["demo_publico"] = f"{config.URL_DEMOS}/{lead['slug']}/" if lead.get("slug") and config.URL_DEMOS else ""
    lead["qualidade"] = qualidade.avaliar(lead)
    return lead


# ------------------------------- Estado geral ------------------------------
@app.get("/api/estado")
def estado():
    return {
        "ia": ia_disponivel(),
        "modelo_ia": modelo_em_uso(),
        "netlify": deploy.netlify_configurado(),
        "url_demos": config.URL_DEMOS,
        "seu_nome": config.SEU_NOME,
        "seu_whatsapp": bool(config.SEU_WHATSAPP),
        "resumo": db.resumo(),
        "status": db.STATUS,
        "situacoes": SITUACOES,
        "templates": nichos.listar_templates(),
    }


# ---------------------------------- Nichos ---------------------------------
class NichoEntrada(BaseModel):
    id: str = ""
    nome: str
    termo_busca: str = ""
    template: str = "padrao"
    cor_padrao: str = "#2563eb"
    icone: str = ""
    roteiro: str = ""
    textos_padrao: dict = {}
    servicos_padrao: list = []
    diferenciais_padrao: list = []
    mensagem_whatsapp: str = ""


@app.get("/api/nichos")
def listar_nichos():
    return nichos.listar_nichos()


@app.get("/api/nichos/{nicho_id}")
def ver_nicho(nicho_id: str):
    n = nichos.carregar_nicho(nicho_id)
    if not n:
        raise HTTPException(404, "Nicho não encontrado")
    return n


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


# ------------------- Imagens e material de consulta do nicho -------------------
@app.get("/api/nichos/{nicho_id}/arquivos")
def arquivos_do_nicho(nicho_id: str):
    return arquivos_nicho.resumo(nicho_id)


@app.post("/api/nichos/{nicho_id}/imagens")
async def enviar_imagens(nicho_id: str, arquivos: list[UploadFile] = File(...),
                         uso: str = Form("detalhe"), descricao: str = Form("")):
    erros = []
    for arquivo in arquivos:
        try:
            arquivos_nicho.adicionar_imagem(nicho_id, arquivo.filename, await arquivo.read(), uso, descricao)
        except ValueError as erro:
            erros.append(str(erro))
    return {**arquivos_nicho.resumo(nicho_id), "erros": erros}


class ImagemEdicao(BaseModel):
    uso: str | None = None
    descricao: str | None = None


@app.patch("/api/nichos/{nicho_id}/imagens/{arquivo}")
def editar_imagem(nicho_id: str, arquivo: str, edicao: ImagemEdicao):
    try:
        return arquivos_nicho.editar_imagem(nicho_id, arquivo, edicao.uso, edicao.descricao)
    except ValueError as erro:
        raise HTTPException(400, str(erro))


@app.delete("/api/nichos/{nicho_id}/imagens/{arquivo}")
def remover_imagem(nicho_id: str, arquivo: str):
    arquivos_nicho.remover_imagem(nicho_id, arquivo)
    return arquivos_nicho.resumo(nicho_id)


@app.get("/arquivos-nicho/{nicho_id}/{arquivo}")
def ver_imagem_nicho(nicho_id: str, arquivo: str):
    caminho = arquivos_nicho.caminho_imagem(nicho_id, arquivo)
    if "/" in arquivo or "\\" in arquivo or not caminho.exists():
        raise HTTPException(404, "Imagem não encontrada")
    return FileResponse(caminho)


@app.post("/api/nichos/{nicho_id}/consulta")
async def enviar_consulta(nicho_id: str, arquivos: list[UploadFile] = File(...)):
    erros = []
    for arquivo in arquivos:
        try:
            arquivos_nicho.adicionar_consulta(nicho_id, arquivo.filename, await arquivo.read())
        except ValueError as erro:
            erros.append(str(erro))
    return {**arquivos_nicho.resumo(nicho_id), "erros": erros}


@app.get("/api/nichos/{nicho_id}/consulta/{arquivo}")
def ler_consulta(nicho_id: str, arquivo: str):
    return {"arquivo": arquivo, "texto": arquivos_nicho.ler_consulta(nicho_id, arquivo)}


@app.delete("/api/nichos/{nicho_id}/consulta/{arquivo}")
def remover_consulta(nicho_id: str, arquivo: str):
    arquivos_nicho.remover_consulta(nicho_id, arquivo)
    return arquivos_nicho.resumo(nicho_id)


# ------------------------------ Modelo de site ------------------------------
@app.get("/api/nichos/{nicho_id}/modelo")
def status_modelo(nicho_id: str):
    return modelos.status(nicho_id)


@app.post("/api/nichos/{nicho_id}/modelo")
async def enviar_modelo(nicho_id: str, arquivo: UploadFile = File(...), tema: str = Form("claro")):
    try:
        return modelos.importar(nicho_id, arquivo.filename, await arquivo.read(), tema)
    except (ValueError, zipfile.BadZipFile) as erro:
        raise HTTPException(400, str(erro))


@app.post("/api/nichos/{nicho_id}/modelo/template")
async def enviar_template_editado(nicho_id: str, arquivo: UploadFile = File(...)):
    """Template editado à mão (com as variáveis {{ s.... }})."""
    try:
        return modelos.salvar_template(nicho_id, (await arquivo.read()).decode("utf-8", errors="ignore"))
    except ValueError as erro:
        raise HTTPException(400, str(erro))


@app.post("/api/nichos/{nicho_id}/modelo/converter")
def converter_modelo(nicho_id: str):
    tarefa.iniciar("conversao", lambda: modelos.converter_com_ia(nicho_id, log=tarefa.escrever))
    return {"ok": True}


class ModeloEdicao(BaseModel):
    tema: str | None = None
    em_uso: bool | None = None


@app.patch("/api/nichos/{nicho_id}/modelo")
def editar_modelo(nicho_id: str, edicao: ModeloEdicao):
    try:
        if edicao.tema:
            modelos.definir_tema(nicho_id, edicao.tema)
        if edicao.em_uso is not None:
            modelos.usar(nicho_id, edicao.em_uso)
    except ValueError as erro:
        raise HTTPException(400, str(erro))
    return modelos.status(nicho_id)


@app.post("/api/nichos/{nicho_id}/modelo/previa")
def previa_modelo(nicho_id: str):
    try:
        return {"url": modelos.gerar_previa(nicho_id)}
    except Exception as erro:
        raise HTTPException(400, str(erro))


@app.get("/api/nichos/{nicho_id}/modelo/baixar")
def baixar_modelo(nicho_id: str, qual: str = "template"):
    caminho = modelos.caminho_template(nicho_id) if qual == "template" else modelos.caminho_original(nicho_id)
    if not caminho.exists():
        raise HTTPException(404, "Arquivo não encontrado")
    nome = f"{modelos.nome_template(nicho_id)}{'.html.j2' if qual == 'template' else '-original.html'}"
    return FileResponse(caminho, filename=nome, media_type="text/plain")


@app.delete("/api/nichos/{nicho_id}/modelo")
def remover_modelo(nicho_id: str):
    modelos.remover(nicho_id)
    return modelos.status(nicho_id)


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


@app.post("/api/busca")
def iniciar_busca(busca: BuscaEntrada):
    nicho = nichos.carregar_nicho(busca.nicho)
    if not nicho:
        raise HTTPException(404, "Nicho não encontrado")
    if not busca.regioes:
        raise HTTPException(400, "Escolha pelo menos uma região")
    opcoes = {"limite": max(1, min(busca.limite, 60)), "headless": busca.headless,
              "buscar_instagram": busca.buscar_instagram, "coletar_extras": busca.coletar_extras}
    tarefa.iniciar("busca", lambda: _rodar_async(
        rodar_busca(nicho, busca.regioes, opcoes, tarefa.escrever, lambda: tarefa.parar)))
    return {"ok": True}


@app.get("/api/tarefa")
def ver_tarefa(desde: int = 0):
    return {"tipo": tarefa.tipo, "rodando": tarefa.rodando, "total": len(tarefa.log), "log": tarefa.log[desde:],
            "resultado": tarefa.resultado}


@app.post("/api/tarefa/parar")
def parar_tarefa():
    tarefa.parar = True
    tarefa.escrever("⏸ Parando depois do item atual...")
    return {"ok": True}


# ---------------------------------- Leads ----------------------------------
@app.get("/api/leads")
def listar_leads(nicho: str = "", status: str = "", situacao: str = "", texto: str = "", dados: str = ""):
    leads = [_enriquecer(l) for l in db.listar(nicho or None, status or None, situacao or None, texto or None)]
    if dados:
        leads = [l for l in leads if l["qualidade"]["nivel"] == dados]
    return leads


class LeadEdicao(BaseModel):
    status: str | None = None
    observacoes: str | None = None
    whatsapp: str | None = None
    nome: str | None = None
    fotos: list[str] | None = None   # nova ordem (a primeira vai para o topo) ou sem as removidas


@app.patch("/api/leads/{lead_id}")
def editar_lead(lead_id: str, edicao: LeadEdicao):
    campos = {k: v for k, v in edicao.model_dump().items() if v is not None}
    if "status" in campos and campos["status"] not in db.STATUS:
        raise HTTPException(400, "Status inválido")
    if "whatsapp" in campos:
        campos["whatsapp"] = normalizar_whatsapp(campos["whatsapp"])
    if campos.get("status") == "enviado":
        campos["enviado_em"] = datetime.now().isoformat(timespec="seconds")
    if "fotos" in campos:
        anteriores = db.buscar(lead_id).get("fotos") or []
        campos["fotos"] = [f for f in campos["fotos"] if f in anteriores]  # só fotos que já eram do lead
        gerador.limpar_fotos_baixadas(db.buscar(lead_id))
    db.atualizar(lead_id, campos)
    return _enriquecer(db.buscar(lead_id))


@app.delete("/api/leads/{lead_id}")
def excluir_lead(lead_id: str):
    gerador.apagar_site(lead_id)
    db.excluir(lead_id)
    return {"ok": True}


@app.post("/api/leads/{lead_id}/recoletar")
def recoletar(lead_id: str):
    """Busca de novo no Maps as fotos, avaliações e descrição deste lead."""
    lead = db.buscar(lead_id)
    if not lead:
        raise HTTPException(404, "Lead não encontrado")
    nicho = nichos.carregar_nicho(lead["nicho"]) or {"id": lead["nicho"], "nome": lead["nicho"]}

    def executar():
        tarefa.escrever(f"🔄 Buscando de novo no Maps: {lead['nome']}")
        try:
            _rodar_async(recoletar_lead(lead, nicho, tarefa.escrever))
        except Exception as erro:
            tarefa.escrever(f"❌ Não consegui abrir a ficha no Maps: {str(erro).splitlines()[0][:160]}")
            return
        gerador.limpar_fotos_baixadas(db.buscar(lead_id))
        tarefa.escrever("Agora clique em Refazer para o site usar os dados novos.")
    tarefa.iniciar("recoleta", executar)
    return {"ok": True}


@app.post("/api/leads/{lead_id}/diagnostico")
def diagnostico(lead_id: str):
    """Abre a ficha do lead no Maps e salva prints + relatório do que o bot achou."""
    lead = db.buscar(lead_id)
    if not lead:
        raise HTTPException(404, "Lead não encontrado")

    def executar():
        nome = _rodar_async(diagnosticar(lead, tarefa.escrever))
        tarefa.resultado = {"download": f"/api/diagnostico/{nome}", "nome": nome}
        tarefa.escrever("Baixe o arquivo pelo link abaixo e mande para o Claude.")
    tarefa.iniciar("diagnostico", executar)
    return {"ok": True}


@app.get("/api/diagnostico/{nome}")
def baixar_diagnostico(nome: str):
    import re as _re
    if not _re.fullmatch(r"diagnostico-[a-z0-9-]+\.zip", nome) or not (PASTA_DIAGNOSTICO / nome).exists():
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(PASTA_DIAGNOSTICO / nome, filename=nome)


class GerarEntrada(BaseModel):
    usar_ia: bool = True
    refazer_textos: bool = False


@app.post("/api/leads/{lead_id}/gerar")
def gerar_um(lead_id: str, opcoes: GerarEntrada):
    try:
        lead = gerador.gerar_site(lead_id, opcoes.usar_ia, opcoes.refazer_textos, log=tarefa.escrever)
    except ValueError as erro:
        raise HTTPException(400, str(erro))
    return _enriquecer(lead)


@app.delete("/api/leads/{lead_id}/site")
def apagar_demo(lead_id: str):
    gerador.apagar_site(lead_id)
    return _enriquecer(db.buscar(lead_id))


class LoteEntrada(BaseModel):
    ids: list[str]
    usar_ia: bool = True
    incluir_fracos: bool = False


@app.post("/api/gerar-lote")
def gerar_lote(lote: LoteEntrada):
    def executar():
        for i, lead_id in enumerate(lote.ids, 1):
            if tarefa.parar:
                tarefa.escrever("⏹ Geração interrompida.")
                break
            lead = db.buscar(lead_id)
            nota = qualidade.avaliar(lead or {})
            if lead and nota["nivel"] == "fraco" and not lote.incluir_fracos:
                tarefa.escrever(f"⏭ {lead['nome']}: poucos dados ({nota['pontos']}/{nota['maximo']}), pulado. Falta: {', '.join(nota['falta'][:3])}")
                continue
            try:
                gerador.gerar_site(lead_id, lote.usar_ia, log=tarefa.escrever)
            except Exception as erro:
                tarefa.escrever(f"  erro no lead {lead_id}: {erro}")
        tarefa.escrever(f"🏁 Fim da geração ({len(lote.ids)} leads).")
    tarefa.iniciar("geracao", executar)
    return {"ok": True}


@app.post("/api/nichos/{nicho_id}/refazer-sites")
def refazer_sites_do_nicho(nicho_id: str):
    """Refaz todos os sites já gerados do nicho (ex.: depois de trocar o modelo). Reaproveita os textos."""
    leads = [l for l in db.listar(nicho=nicho_id) if l.get("slug")]
    if not leads:
        raise HTTPException(400, "Nenhum site gerado neste nicho ainda.")

    def executar():
        for i, lead in enumerate(leads, 1):
            if tarefa.parar:
                tarefa.escrever("⏹ Interrompido.")
                break
            try:
                gerador.gerar_site(lead["id"], usar_ia=False, log=tarefa.escrever)
            except Exception as erro:
                tarefa.escrever(f"  erro em {lead['nome']}: {erro}")
        tarefa.escrever(f"🏁 {len(leads)} sites refeitos. Publique no Netlify para atualizar os links.")
    tarefa.iniciar("refazer", executar)
    return {"ok": True, "total": len(leads)}


@app.post("/api/publicar")
def publicar():
    if not deploy.netlify_configurado():
        raise HTTPException(400, "Preencha NETLIFY_TOKEN e NETLIFY_SITE_ID no arquivo .env e reinicie o painel.")
    tarefa.iniciar("publicacao", lambda: deploy.publicar(log=tarefa.escrever))
    return {"ok": True}


@app.get("/api/exportar")
def exportar_leads(formato: str = "xlsx", nicho: str = "", situacao: str = ""):
    leads = db.listar(nicho or None, None, situacao or None)
    nome = f"leads_{nicho or 'todos'}"
    caminho = exportar.para_json(leads, nome) if formato == "json" else exportar.para_excel(leads, nome)
    return FileResponse(caminho, filename=caminho.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])


# ------------------------------ Arquivos ------------------------------------
app.mount("/demos", StaticFiles(directory=config.PASTA_SITES, html=True), name="demos")
app.mount("/painel", StaticFiles(directory=config.RAIZ / "painel"), name="painel")


@app.get("/")
def inicio():
    return FileResponse(config.RAIZ / "painel" / "index.html")


if __name__ == "__main__":
    print("\n  Painel aberto em: http://localhost:8000\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
