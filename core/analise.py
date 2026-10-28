"""
Análise de um lead, logo depois da coleta (ou quando você clica em "Analisar de novo").

Ordem:
  1. Descarte automático: fechado, sem telefone ou rede/franquia (só para leads novos).
  2. Redes sociais: se o Maps e o site não mostraram nenhuma, a IA pesquisa o nome na web.
  3. Regras: saúde do Maps, oportunidades, nota de 0 a 100 e classe.
  4. IA: dores com prova, o que vender e a primeira frase da conversa.
     O que a IA sugerir entra nas oportunidades e a nota é recalculada.

Sem chave do Gemini, os passos 2 e 4 são pulados e tudo funciona só com as regras.
No fim, as cores da logo são calculadas uma vez (para o pacote do site).
"""
from . import db, ia
from .cores import cores_da_logo
from .limpeza import juntar_redes
from .potencial import calcular, carregar_pesos, motivo_descarte

# Redes que, se faltarem, fazem valer a pena pesquisar na web
REDES_PRINCIPAIS = ("instagram", "facebook")


def _completar_redes(lead: dict, log) -> dict:
    """Pesquisa as redes na web quando faltam. Devolve os campos que mudaram."""
    if any(r in (lead.get("redes") or {}) for r in REDES_PRINCIPAIS):
        return {}
    try:
        achado = ia.buscar_redes_na_web(lead, log=log)
    except Exception as erro:
        log(f"    pesquisa de redes na web falhou: {str(erro)[:100]}")
        return {}
    campos = {}
    if achado["redes"]:
        campos["redes"] = juntar_redes(lead.get("redes"), achado["redes"])
        origem = [o for o in (lead.get("redes_origem") or "").split(", ") if o] + ["busca na web"]
        campos["redes_origem"] = ", ".join(origem)
        if not lead.get("instagram") and achado["redes"].get("instagram"):
            campos["instagram"] = achado["redes"]["instagram"]
        log(f"    redes achadas na web: {', '.join(achado['redes'])}")
    if achado["site"] and lead.get("situacao_site") in ("sem_site", "so_rede_social"):
        # Tem site, mas ele não aparece no Maps: isso vira problema do perfil, não falta de site
        sinais = dict(lead.get("sinais") or {})
        sinais["site_fora_do_maps"] = achado["site"]
        campos.update({"site": achado["site"], "situacao_site": "site_proprio", "sinais": sinais})
        log(f"    site achado na web (não está no Maps): {achado['site']}")
    return campos


def analisar(lead_id: str, usar_ia: bool = True, log=print) -> dict:
    lead = db.buscar(lead_id)
    if not lead:
        raise ValueError("Lead não encontrado")
    nicho = db.carregar_nicho(lead.get("nicho") or "") or {}
    pesos = carregar_pesos()
    campos = {}

    # 1. Descarte automático: só para quem ainda está no começo do quadro
    if lead.get("estado") in ("ativo", "descartado") and lead.get("etapa") == "lead_novo":
        motivo = motivo_descarte(lead, pesos, db.nome_em_varias_regioes(lead["nome"], lead.get("regiao") or ""))
        if motivo:
            campos.update({"estado": "descartado", "motivo": motivo})
        elif lead.get("estado") == "descartado":
            campos.update({"estado": "ativo", "motivo": ""})   # o motivo deixou de valer

    usar_ia = usar_ia and ia.ia_disponivel() and campos.get("estado") != "descartado"

    # 2. Redes sociais pela web
    if usar_ia:
        campos.update(_completar_redes(lead, log))
        lead.update(campos)

    # 3. Regras
    resultado = calcular(lead, nicho, pesos)
    lead.update(resultado)

    # 4. IA
    if usar_ia:
        try:
            analise = ia.analisar_lead(lead, log=log)
            campos["analise_ia"] = analise
            resultado = calcular(lead, nicho, pesos, sugestoes_ia=analise.get("o_que_vender"))
            log(f"    análise da IA pronta ({analise.get('_tokens')} tokens)")
        except Exception as erro:
            log(f"    IA não analisou ({str(erro)[:100]}): ficam só as regras")

    # Cores da logo, para o pacote do site (uma vez só por logo)
    if lead.get("logo_url") and not lead.get("cores"):
        cores = cores_da_logo(lead["logo_url"])
        if cores:
            campos["cores"] = cores

    campos.update(resultado)
    campos["analisado_em"] = db.agora()
    db.atualizar(lead_id, campos)
    return db.buscar(lead_id)
