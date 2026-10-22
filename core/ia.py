"""
Geração dos textos do site com IA (Gemini), gastando o mínimo de tokens.

A IA NÃO cria o site. Ela recebe um resumo curto do negócio + o roteiro
do nicho e devolve só um JSON pequeno com os textos. O HTML vem do template.
Custo típico: ~600 tokens de entrada e ~400 de saída por site.

Se não houver chave ou a chamada falhar, usamos os textos padrão do nicho.
Ou seja: o sistema funciona 100% sem IA, só fica menos personalizado.
"""
import base64
import json
import re
import time

import requests

from .config import GEMINI_API_KEY, GEMINI_MODELO

REGRAS = """Você escreve textos curtos para o site de um pequeno negócio brasileiro.
Regras obrigatórias:
- Português do Brasil, frases curtas, sem clichês de marketing e sem emojis.
- Use SOMENTE os fatos fornecidos. NÃO invente preços, promoções, anos de mercado,
  prêmios, nomes de pessoas, depoimentos, números de registro ou horários.
- Não use superlativos absolutos ("o melhor", "número 1").
- Se houver "descricao_do_dono" ou "o_que_clientes_elogiam", baseie o texto nisso: é o que torna o site
  específico deste negócio. Não copie as avaliações literalmente e não as apresente como depoimento.
- Responda apenas com o JSON no formato pedido."""

FORMATO = {
    "slogan": "frase de até 8 palavras",
    "subtitulo": "frase de até 18 palavras",
    "sobre": "parágrafo de 2 a 3 frases",
    "servicos": [{"titulo": "até 4 palavras", "descricao": "até 14 palavras"}],
    "diferenciais": ["até 5 palavras cada, 3 itens"],
    "cta": "texto do botão principal, até 4 palavras",
}


def ia_disponivel() -> bool:
    return bool(GEMINI_API_KEY)


def _resumo_do_negocio(lead: dict) -> dict:
    """Só o que a IA precisa saber: quanto menos texto, menos tokens."""
    resumo = {
        "nome": lead.get("nome"),
        "categoria": lead.get("categoria"),
        "regiao": lead.get("regiao"),
    }
    if lead.get("nota"):
        resumo["nota_google"] = f"{lead['nota']} ({lead.get('avaliacoes') or '?'} avaliações)"
    if lead.get("horario"):
        resumo["horario"] = lead["horario"]
    if lead.get("descricao"):
        resumo["descricao_do_dono"] = lead["descricao"][:400]
    if lead.get("depoimentos"):
        # O que os clientes elogiam ajuda a IA a escolher o que destacar (sem inventar)
        resumo["o_que_clientes_elogiam"] = [d["texto"][:180] for d in lead["depoimentos"][:3]]
    if lead.get("observacoes"):
        resumo["info_extra"] = lead["observacoes"][:300]
    return resumo


def montar_prompt(lead: dict, nicho: dict) -> str:
    from .arquivos_nicho import texto_para_ia
    consulta = texto_para_ia(nicho["id"]) if nicho.get("id") else ""
    bloco_consulta = (
        "Material de consulta do nicho (referência de vocabulário, serviços comuns e tom; "
        "NÃO afirme que este negócio oferece algo só porque aparece aqui, e nunca copie preços):\n"
        f"{consulta}\n\n"
    ) if consulta else ""
    return (
        f"{REGRAS}\n\n"
        f"Roteiro do nicho ({nicho['nome']}):\n{nicho.get('roteiro') or 'Tom profissional e acolhedor.'}\n\n"
        f"{bloco_consulta}"
        f"Dados do negócio:\n{json.dumps(_resumo_do_negocio(lead), ensure_ascii=False)}\n\n"
        f"Entre 3 e 4 serviços. Formato da resposta:\n{json.dumps(FORMATO, ensure_ascii=False)}"
    )


def _validar(dados: dict) -> dict:
    """Garante que o JSON tem o formato certo; descarta o que vier estranho."""
    limpo = {}
    for campo in ("slogan", "subtitulo", "sobre", "cta"):
        if isinstance(dados.get(campo), str) and dados[campo].strip():
            limpo[campo] = dados[campo].strip()
    servicos = [
        {"titulo": str(s.get("titulo", "")).strip(), "descricao": str(s.get("descricao", "")).strip()}
        for s in dados.get("servicos", []) if isinstance(s, dict) and s.get("titulo")
    ]
    if servicos:
        limpo["servicos"] = servicos[:6]
    diferenciais = [str(d).strip() for d in dados.get("diferenciais", []) if str(d).strip()]
    if diferenciais:
        limpo["diferenciais"] = diferenciais[:4]
    return limpo


# Se o Google aposentar o modelo configurado, ele mesmo sugere o substituto na
# mensagem de erro. Guardamos aqui para as próximas chamadas não errarem de novo.
_modelo_substituto = None
URL_API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def modelo_em_uso() -> str:
    return _modelo_substituto or GEMINI_MODELO


def _config_raciocinio(modelo: str, nivel: str) -> dict:
    """
    Os modelos "pensam" antes de responder, e isso também gasta token.
    Os 2.5 aceitam um orçamento em tokens; os mais novos, um nível (low/high).
    nivel: "minimo" para textos curtos, "medio" para converter modelos.
    """
    if modelo.startswith("gemini-2.5"):
        return {"thinkingBudget": 0 if nivel == "minimo" else 1024}
    return {"thinkingLevel": "low"}


def chamar_gemini(prompt: str, json_saida=False, max_tokens=4096, temperatura=0.8,
                  nivel="minimo", timeout=60, log=print, imagens=None):
    """
    Chamada única ao Gemini usada pelo sistema todo. Devolve (texto, tokens, modelo).
    `imagens`: lista opcional de JPEGs (bytes) enviados junto com o texto.
    """
    global _modelo_substituto
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")
    modelo = modelo_em_uso()
    partes_imagem = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(img).decode()}}
                     for img in (imagens or [])]
    usar_raciocinio = True
    for _tentativa in range(3):
        config = {"temperature": temperatura, "maxOutputTokens": max_tokens}
        if json_saida:
            config["responseMimeType"] = "application/json"
        if usar_raciocinio:
            config["thinkingConfig"] = _config_raciocinio(modelo, nivel)
        resposta = requests.post(
            URL_API.format(modelo),
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}, *partes_imagem]}], "generationConfig": config},
            timeout=timeout,
        )
        if resposta.status_code == 200:
            break
        erro = resposta.text
        # Modelo aposentado: o próprio Google diz qual usar ("use models/xxx")
        sugerido = re.search(r"use models/([\w.\-]+)", erro)
        if resposta.status_code == 404 and sugerido and sugerido.group(1) != modelo:
            modelo = _modelo_substituto = sugerido.group(1).rstrip(".")
            log(f"  ⚠ o modelo do .env foi aposentado; usando {modelo}. Atualize GEMINI_MODELO={modelo} no .env")
            continue
        # Google sobrecarregado ou limite por minuto: espera um pouco e tenta de novo
        if resposta.status_code in (429, 500, 503) and _tentativa < 2:
            log(f"  Gemini ocupado ({resposta.status_code}), tentando de novo...")
            time.sleep(5 * (_tentativa + 1))
            continue
        # Configuração de raciocínio não aceita por este modelo: tenta sem ela
        if resposta.status_code == 400 and "thinking" in erro.lower() and usar_raciocinio:
            usar_raciocinio = False
            continue
        raise RuntimeError(f"Gemini respondeu {resposta.status_code}: {erro[:300]}")
    else:
        raise RuntimeError("Gemini não respondeu depois de 3 tentativas")

    corpo = resposta.json()
    candidato = corpo["candidates"][0]
    if candidato.get("finishReason") == "MAX_TOKENS":
        raise RuntimeError("A resposta da IA foi cortada por limite de tamanho.")
    texto = "".join(p.get("text", "") for p in candidato.get("content", {}).get("parts", []) if not p.get("thought"))
    return texto, corpo.get("usageMetadata", {}).get("totalTokenCount"), modelo


def gerar_textos_ia(lead: dict, nicho: dict, log=print) -> dict:
    """Chama o Gemini. Levanta exceção se der erro (o gerador cai no padrão)."""
    texto, tokens, modelo = chamar_gemini(montar_prompt(lead, nicho), json_saida=True, log=log)
    textos = _validar(json.loads(texto))
    textos["_tokens"] = tokens
    textos["_origem"] = f"ia:{modelo}"
    return textos


PROMPT_FOTOS = """Você escolhe fotos para o site de um(a) {nicho} chamado(a) "{nome}".
As {qtd} fotos vieram do Google Maps, postadas pelo dono e por clientes. Elas vêm na ordem,
numeradas de 1 a {qtd}. Orientação de cada uma: {orientacoes}.

Uma foto BOA para o site mostra o próprio negócio de forma atraente: ambiente, estrutura,
equipamentos, fachada com o nome, serviço sendo feito, turma/equipe posando de propósito.
Uma foto RUIM: selfie ou foto pessoal, produto/embalagem em destaque, cardápio ou panfleto,
print de tela, foto escura, borrada ou torta, foto sem relação com o negócio (céu, carro, rua),
pessoas de máscara ou em pose constrangedora, quadro de vídeo com legenda.
Na dúvida, reprove: o site usa imagens do nicho quando faltam fotos boas.

Para a capa (topo do site), prefira foto horizontal, bem iluminada, que mostre o espaço.

Responda só o JSON:
{{"fotos": [{{"n": 1, "o_que_mostra": "até 6 palavras", "nota": 0-10, "usar": true}}], "capa": n ou null}}"""


def escolher_fotos(imagens: list, orientacoes: list, lead: dict, nicho: dict, log=print) -> list:
    """
    Mostra as fotos para o Gemini e devolve os índices (base 0) das aprovadas,
    a capa primeiro e depois as outras da melhor nota para a pior.
    Levanta exceção se a IA falhar (quem chama decide o que fazer).
    """
    prompt = PROMPT_FOTOS.format(
        nicho=nicho.get("nome", "negócio"), nome=lead.get("nome", ""), qtd=len(imagens),
        orientacoes=", ".join(f"{i}: {o}" for i, o in enumerate(orientacoes, 1)))
    texto, tokens, _ = chamar_gemini(prompt, json_saida=True, temperatura=0.2, imagens=imagens, log=log)
    dados = json.loads(texto)
    aprovadas = [f for f in dados.get("fotos", [])
                 if f.get("usar") and isinstance(f.get("n"), int) and 1 <= f["n"] <= len(imagens)]
    aprovadas.sort(key=lambda f: -(f.get("nota") or 0))
    ordem = [f["n"] - 1 for f in aprovadas]
    capa = dados.get("capa")
    if isinstance(capa, int) and capa - 1 in ordem:
        ordem.remove(capa - 1)
        ordem.insert(0, capa - 1)
    log(f"    IA aprovou {len(ordem)} de {len(imagens)} fotos ({tokens} tokens)")
    return ordem


def textos_padrao(lead: dict, nicho: dict) -> dict:
    """Textos do nicho com {nome} e {regiao} trocados pelos dados do lead. Custo zero."""
    valores = {
        "nome": lead.get("nome", ""),
        "regiao": (lead.get("regiao") or "").split(",")[0],
        "categoria": lead.get("categoria") or nicho["nome"],
    }

    def preencher(texto):
        try:
            return texto.format(**valores)
        except (KeyError, IndexError, ValueError):
            return texto

    base = nicho.get("textos_padrao", {})
    return {
        "slogan": preencher(base.get("slogan", "{nome}")),
        "subtitulo": preencher(base.get("subtitulo", "")),
        "sobre": preencher(base.get("sobre", "")),
        "cta": preencher(base.get("cta", "Fale com a gente")),
        "servicos": nicho.get("servicos_padrao", []),
        "diferenciais": nicho.get("diferenciais_padrao", []),
        "_origem": "padrao",
    }


def gerar_textos(lead: dict, nicho: dict, usar_ia: bool = True, log=print) -> dict:
    padrao = textos_padrao(lead, nicho)
    if not (usar_ia and ia_disponivel()):
        return padrao
    try:
        textos = gerar_textos_ia(lead, nicho, log=log)
        log(f"  textos gerados pela IA ({textos.get('_tokens')} tokens)")
        return {**padrao, **textos}  # o que a IA não mandou, vem do padrão
    except Exception as erro:
        log(f"  IA falhou, usando textos padrão: {str(erro)[:120]}")
        return padrao
