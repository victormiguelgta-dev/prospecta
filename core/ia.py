"""
IA (Gemini) do Prospecta, gastando o mínimo de tokens. Ela faz só duas coisas:

1. analisar_lead: lê os dados do Maps e as avaliações e diz quais as dores do
   negócio (com a prova), o que você pode vender e a primeira frase da conversa.
   Também anota o público e o diferencial, que vão para o pacote do site.
2. buscar_redes_na_web: quando o Maps não mostra as redes sociais, pesquisa o
   nome da marca no Google (pela própria API do Gemini) e traz os links.

A nota de potencial NÃO é da IA: ela vem das regras em potencial.py, que são
grátis e dão sempre o mesmo resultado. Sem chave, o sistema funciona só com as regras.
Para trocar de provedor de IA, basta reescrever chamar_ia() mantendo a mesma resposta.
"""
import json
import re
import time

import requests

from .config import GEMINI_API_KEY, GEMINI_MODELO
from .limpeza import achar_redes, classificar_site

# Se o Google aposentar o modelo configurado, ele mesmo sugere o substituto na
# mensagem de erro. Guardamos aqui para as próximas chamadas não errarem de novo.
_modelo_substituto = None
URL_API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def ia_disponivel() -> bool:
    return bool(GEMINI_API_KEY)


def modelo_em_uso() -> str:
    return _modelo_substituto or GEMINI_MODELO


def _config_raciocinio(modelo: str) -> dict:
    """Os modelos "pensam" antes de responder, e isso gasta token: deixamos no mínimo."""
    if modelo.startswith("gemini-2.5"):
        return {"thinkingBudget": 0}
    return {"thinkingLevel": "low"}


def chamar_ia(prompt: str, json_saida=False, pesquisar_na_web=False, max_tokens=2048,
              temperatura=0.3, timeout=60, log=print):
    """
    Chamada única ao Gemini usada pelo sistema todo. Devolve (texto, tokens).
    pesquisar_na_web: liga a busca do Google dentro do Gemini (para achar redes sociais).
    """
    global _modelo_substituto
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")
    modelo = modelo_em_uso()
    usar_raciocinio = True
    for tentativa in range(3):
        configuracao = {"temperature": temperatura, "maxOutputTokens": max_tokens}
        if json_saida and not pesquisar_na_web:   # a busca na web não aceita resposta forçada em JSON
            configuracao["responseMimeType"] = "application/json"
        if usar_raciocinio:
            configuracao["thinkingConfig"] = _config_raciocinio(modelo)
        corpo = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": configuracao}
        if pesquisar_na_web:
            corpo["tools"] = [{"google_search": {}}]
        resposta = requests.post(URL_API.format(modelo), json=corpo, timeout=timeout,
                                 headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"})
        if resposta.status_code == 200:
            break
        erro = resposta.text
        sugerido = re.search(r"use models/([\w.\-]+)", erro)
        if resposta.status_code == 404 and sugerido and sugerido.group(1) != modelo:
            modelo = _modelo_substituto = sugerido.group(1).rstrip(".")
            log(f"  ⚠ o modelo do .env foi aposentado; usando {modelo}. Atualize GEMINI_MODELO={modelo} no .env")
            continue
        if resposta.status_code in (429, 500, 503) and tentativa < 2:
            log(f"  Gemini ocupado ({resposta.status_code}), tentando de novo...")
            time.sleep(5 * (tentativa + 1))
            continue
        if resposta.status_code == 400 and "thinking" in erro.lower() and usar_raciocinio:
            usar_raciocinio = False
            continue
        raise RuntimeError(f"Gemini respondeu {resposta.status_code}: {erro[:300]}")
    else:
        raise RuntimeError("Gemini não respondeu depois de 3 tentativas")

    dados = resposta.json()
    candidato = dados["candidates"][0]
    if candidato.get("finishReason") == "MAX_TOKENS":
        raise RuntimeError("A resposta da IA foi cortada por limite de tamanho.")
    texto = "".join(p.get("text", "") for p in candidato.get("content", {}).get("parts", []) if not p.get("thought"))
    return texto, dados.get("usageMetadata", {}).get("totalTokenCount")


def ler_json(texto: str) -> dict:
    """Pega o JSON da resposta, mesmo que venha dentro de ```json ... ``` ou com texto em volta."""
    achado = re.search(r"\{.*\}", texto or "", re.S)
    if not achado:
        raise ValueError("A IA não devolveu JSON")
    return json.loads(achado.group())


# ---------------------------------------------------------------------------
# 1. Análise do lead
# ---------------------------------------------------------------------------
REGRAS_ANALISE = """Você ajuda um vendedor de serviços digitais (otimização do Google Maps, sites e
desenvolvimento de automações ou ferramentas sob medida) a entender um pequeno negócio brasileiro.
Regras obrigatórias:
- Use SOMENTE os dados fornecidos. Não invente números, serviços, preços nem fatos.
- Cada dor precisa de uma prova real tirada dos dados (ex.: trecho curto de uma avaliação, um número).
- Serviços possíveis: "maps", "site", "desenvolvimento". Siga a escada: primeiro veja se o Maps está bom,
  depois se tem site; desenvolvimento (automação de atendimento, agendamento, pedidos, ferramenta) vale
  para quem já tem Maps ou site. Só sugira o que os dados justificam.
- O ângulo é a frase que vem logo depois de "Olá, <nome>! Tudo bem? Meu nome é <vendedor>.": educada,
  específica deste negócio, baseada na evidência mais forte, sem prometer resultado e sem dizer
  "primeiro lugar no Google". Não comece com saudação nem com apresentação.
- Português do Brasil, frases curtas, sem emojis. Responda apenas com o JSON pedido."""

FORMATO_ANALISE = {
    "resumo": "1 ou 2 frases sobre o que é o negócio e como ele está",
    "publico": "para quem é o negócio, se der para saber pelos dados; senão vazio",
    "diferencial": "o que os clientes mais elogiam ou o que o diferencia, 1 frase; senão vazio",
    "dores": [{"dor": "até 8 palavras", "prova": "trecho real curto ou número dos dados"}],
    "o_que_vender": [{"servico": "maps | site | desenvolvimento", "motivo": "até 20 palavras, com a prova"}],
    "angulo": "primeira frase da mensagem, até 30 palavras",
}


def _dados_para_analise(lead: dict) -> dict:
    """Só o que a IA precisa ver: quanto menos texto, menos tokens."""
    dados = {
        "nome": lead.get("nome"),
        "categoria": lead.get("categoria"),
        "regiao": lead.get("regiao"),
        "nota_google": lead.get("nota"),
        "total_avaliacoes": lead.get("avaliacoes"),
        "situacao_do_site": lead.get("situacao_site"),
        "site": lead.get("site") or None,
        "redes_sociais": list((lead.get("redes") or {}).keys()),
        "instagram": {"seguidores": lead.get("instagram_seguidores"), "posts": lead.get("instagram_posts")},
        "problemas_do_maps": lead.get("problemas_maps") or [],
        "oportunidades_achadas_pelas_regras": [
            {"servico": o["servico"], "evidencias": o["evidencias"]} for o in lead.get("oportunidades") or []],
        "tem_horario": bool(lead.get("horario")),
        "descricao_do_dono": (lead.get("descricao") or "")[:400] or None,
    }
    sinais = lead.get("sinais") or {}
    for chave in ("tem_agendar", "tem_pedido"):
        if sinais.get(chave) is not None:
            dados[chave] = sinais[chave]
    avaliacoes = lead.get("avaliacoes_lidas") or []
    if avaliacoes:
        dados["avaliacoes_recentes"] = [
            {"estrelas": a.get("estrelas"), "texto": (a.get("texto") or "")[:220],
             "dono_respondeu": a.get("respondida"), "quando": a.get("quando")}
            for a in avaliacoes[:12] if a.get("texto")]
    return {k: v for k, v in dados.items() if v not in (None, "", [], {})}


def montar_prompt_analise(lead: dict) -> str:
    return (f"{REGRAS_ANALISE}\n\nDados do negócio:\n{json.dumps(_dados_para_analise(lead), ensure_ascii=False)}\n\n"
            f"Até 3 dores. Formato da resposta:\n{json.dumps(FORMATO_ANALISE, ensure_ascii=False)}")


def _validar_analise(dados: dict) -> dict:
    """Garante o formato; descarta o que vier estranho."""
    def texto(valor, limite):
        return str(valor).strip()[:limite] if isinstance(valor, str) else ""

    dores = [{"dor": texto(d.get("dor"), 80), "prova": texto(d.get("prova"), 240)}
             for d in dados.get("dores") or [] if isinstance(d, dict) and d.get("dor")][:3]
    vender = [{"servico": d["servico"].strip().lower(), "motivo": texto(d.get("motivo"), 240)}
              for d in dados.get("o_que_vender") or []
              if isinstance(d, dict) and isinstance(d.get("servico"), str)
              and d["servico"].strip().lower() in ("maps", "site", "desenvolvimento")]
    return {
        "resumo": texto(dados.get("resumo"), 400),
        "publico": texto(dados.get("publico"), 200),
        "diferencial": texto(dados.get("diferencial"), 240),
        "dores": dores,
        "o_que_vender": vender,
        "angulo": texto(dados.get("angulo"), 300),
    }


def analisar_lead(lead: dict, log=print) -> dict:
    """Chama o Gemini e devolve a análise validada. Levanta exceção se der erro."""
    texto, tokens = chamar_ia(montar_prompt_analise(lead), json_saida=True, log=log)
    analise = _validar_analise(ler_json(texto))
    analise["_tokens"] = tokens
    analise["_modelo"] = modelo_em_uso()
    return analise


# ---------------------------------------------------------------------------
# 2. Redes sociais pela busca do Google
# ---------------------------------------------------------------------------
PROMPT_REDES = """Pesquise na web os perfis OFICIAIS deste negócio:
nome: {nome}
endereço: {endereco}
categoria: {categoria}

Procure: Instagram, Facebook, TikTok, YouTube, LinkedIn, Linktree, iFood e site próprio.
Só inclua um link se tiver certeza de que é ESTE negócio (mesmo nome e mesma cidade).
Na dúvida, deixe null. Responda só com o JSON, sem explicações:
{{"instagram": null, "facebook": null, "tiktok": null, "youtube": null, "linkedin": null,
"linktree": null, "ifood": null, "site": null}}"""


def buscar_redes_na_web(lead: dict, log=print) -> dict:
    """
    Devolve {"redes": {rede: url}, "site": url ou ""} achados pela busca do Google no Gemini.
    Os links passam pelo mesmo filtro das redes achadas no Maps, então lixo não entra.
    """
    prompt = PROMPT_REDES.format(nome=lead.get("nome", ""), endereco=lead.get("endereco") or lead.get("regiao", ""),
                                 categoria=lead.get("categoria") or "")
    texto, tokens = chamar_ia(prompt, json_saida=True, pesquisar_na_web=True, temperatura=0.1, log=log)
    dados = ler_json(texto)
    links = " ".join(str(v) for v in dados.values() if isinstance(v, str))
    site = dados.get("site") if isinstance(dados.get("site"), str) else ""
    if site and classificar_site(site) != "site_proprio":
        site = ""   # um "site" que na verdade é rede social já entra pelas redes
    return {"redes": achar_redes(links), "site": site.strip(), "_tokens": tokens}
