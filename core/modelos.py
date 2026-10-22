"""
Modelo de site por nicho.

Você envia um site pronto (.html ou .zip com CSS/imagens) na aba do nicho.
Ele vira um template em  templates_sites/modelo-<nicho>/index.html.j2,
onde os textos, fotos e contatos fixos são trocados por variáveis do objeto `s`.

A conversão pode ser feita:
  - pela IA (uma vez só por modelo; depois cada site gerado custa o mesmo de sempre);
  - à mão: baixe o template, edite no VS Code e envie de volta.
Se o arquivo que você enviar já tiver variáveis ({{ s.nome }} etc.), ele é usado direto.
"""
import io
import json
import re
import shutil
import zipfile
from datetime import datetime

import requests
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError, select_autoescape
from PIL import Image, ImageDraw

from .config import GEMINI_API_KEY, GEMINI_MODELO, PASTA_SITES, PASTA_TEMPLATES
from .limpeza import slugify
from .nichos import carregar_nicho, salvar_nicho

LIMITE_ARQUIVO = 20 * 1024 * 1024    # 20 MB por envio
LIMITE_HTML_IA = 180_000              # caracteres de HTML que a IA aceita converter

# A mesma lista aparece no painel e no README. Mantenha as três iguais.
VARIAVEIS = """\
s.nome, s.categoria, s.regiao, s.endereco, s.telefone, s.instagram
s.slogan, s.subtitulo, s.sobre            textos (IA ou padrão do nicho)
s.servicos      lista de {titulo, descricao}
s.diferenciais  lista de textos curtos
s.cta_texto     texto do botão principal
s.cta_link      link do botão principal (WhatsApp ou telefone; pode ser vazio)
s.cta_tipo      "whatsapp", "telefone" ou vazio
s.link_whatsapp, s.link_telefone, s.link_maps, s.mapa_embed (URL para <iframe>)
s.nota          ex.: "4,7" (vazio se não tiver)
s.avaliacoes    número de avaliações no Google
s.horarios      lista de {dia, horas}
s.depoimentos   lista de {autor, estrelas, texto} (avaliações reais do Google)
s.logo          arquivo da logo (pode ser vazio: use s.iniciais no lugar)
s.foto_principal  foto do topo (pode ser vazia)
s.foto_real     true se a foto_principal é do próprio negócio
s.galeria       lista de arquivos de fotos do negócio
s.imagem_detalhe, s.imagem_textura   imagens do seu banco do nicho (podem ser vazias)
s.imagens_pessoas  lista de imagens de pessoas do seu banco (slides/destaques; nunca como foto do lugar)
s.horas_semana, s.dias_abertos       horas e dias de funcionamento por semana (0 se não houver horário)
s.cor.destaque, s.cor.sobre_destaque, s.cor.fundo, s.cor.superficie,
s.cor.texto, s.cor.texto_suave, s.cor.profundo   cores tiradas da logo do cliente
s.iniciais, s.ano"""

PROMPT_CONVERSAO = """Transforme o site HTML abaixo em um TEMPLATE Jinja2 reutilizável para pequenos negócios do nicho "{nicho}".

DESIGN: mantenha o HTML, o CSS, as fontes, o layout e as animações como estão. Troque só o CONTEÚDO.

CONTEÚDO:
- Todo texto, imagem e contato específico do negócio original vira variável do objeto `s` (lista abaixo).
- Remova o que seria falso para outro negócio e não tem variável: preços, nomes de pessoas, depoimentos
  escritos à mão, números ("10 anos", "+500 alunos"), prêmios, CNPJ, links de redes do negócio original.
- Seção que depende de dado opcional fica dentro de {{% if ... %}}. Listas usam {{% for ... %}}.
- Formulários de contato viram um botão/link para {{{{ s.cta_link }}}} com o texto {{{{ s.cta_texto }}}}.
- Depoimentos: use s.depoimentos (avaliações reais), mostrando "autor, no Google".

CORES: a cor de destaque principal (botões, links, realces) vira {{{{ s.cor.destaque }}}} e o texto sobre ela
{{{{ s.cor.sobre_destaque }}}}. As outras cores ficam como estão.

IMAGENS: a imagem principal vira {{{{ s.foto_principal }}}} (pode ser vazia: use {{% if %}} com um fundo
{{{{ s.cor.profundo }}}} no lugar). Galerias usam um for em s.galeria. A logo vira {{{{ s.logo }}}}, com
{{{{ s.iniciais }}}} quando não houver logo. Ícones, SVGs e texturas decorativas podem ficar.

NÃO inclua faixa de "prévia" nem <meta name="robots"> (o sistema adiciona).
Use apenas sintaxe Jinja2 válida. Responda SOMENTE com o template completo, sem explicações e sem ```.

VARIÁVEIS DISPONÍVEIS:
{variaveis}

SITE ORIGINAL:
{html}"""


def _pasta(nicho_id: str):
    return PASTA_TEMPLATES / f"modelo-{slugify(nicho_id)}"


def nome_template(nicho_id: str) -> str:
    return f"modelo-{slugify(nicho_id)}"


def _meta(nicho_id: str) -> dict:
    arquivo = _pasta(nicho_id) / "meta.json"
    if arquivo.exists():
        try:
            return json.loads(arquivo.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def _salvar_meta(nicho_id: str, **campos):
    meta = {**_meta(nicho_id), **campos}
    (_pasta(nicho_id) / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def status(nicho_id: str) -> dict:
    pasta = _pasta(nicho_id)
    original = pasta / "original.html"
    template = pasta / "index.html.j2"
    meta = _meta(nicho_id)
    tamanho = len(original.read_text(encoding="utf-8", errors="ignore")) if original.exists() else 0
    extras = [a for a in pasta.rglob("*") if a.is_file() and a.name not in ("meta.json", "original.html", "index.html.j2")] if pasta.exists() else []
    nicho = carregar_nicho(nicho_id) or {}
    return {
        "existe": pasta.exists(),
        "tem_original": original.exists(),
        "convertido": template.exists(),
        "em_uso": nicho.get("template") == nome_template(nicho_id),
        "template": nome_template(nicho_id),
        "tema": meta.get("tema", "claro"),
        "origem": meta.get("origem"),
        "nome_enviado": meta.get("nome_enviado"),
        "enviado_em": meta.get("enviado_em"),
        "tokens_conversao": meta.get("tokens_conversao"),
        "arquivos_extras": len(extras),
        "caracteres": tamanho,
        # estimativa: ~3,5 caracteres por token, entrada + saída de tamanho parecido
        "tokens_estimados": round(tamanho / 3.5 * 2) if tamanho else 0,
        "ia_disponivel": bool(GEMINI_API_KEY),
        # o arquivo enviado já tem as variáveis? então não precisa (nem deve) converter
        "ja_e_template": original.exists() and "{{ s." in original.read_text(encoding="utf-8", errors="ignore"),
        "variaveis": VARIAVEIS,
    }


# ------------------------------------------------------------------ envio
def _extrair_zip(conteudo: bytes, destino) -> str:
    """Extrai com segurança e devolve o HTML principal. Ignora caminhos perigosos."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        nomes = [n for n in z.namelist() if not n.endswith("/") and "__MACOSX" not in n and not n.split("/")[-1].startswith(".")]
        htmls = sorted((n for n in nomes if n.lower().endswith((".html", ".htm"))),
                       key=lambda n: (n.count("/"), not n.lower().endswith("index.html")))
        if not htmls:
            raise ValueError("O .zip não tem nenhum arquivo .html.")
        principal = htmls[0]
        raiz = principal.rsplit("/", 1)[0] + "/" if "/" in principal else ""
        total = 0
        for nome in nomes:
            if not nome.startswith(raiz):
                continue
            relativo = nome[len(raiz):]
            if relativo.startswith("/") or ".." in relativo.split("/"):
                continue
            info = z.getinfo(nome)
            total += info.file_size
            if total > 60 * 1024 * 1024:
                raise ValueError("O .zip descompactado passa de 60 MB.")
            alvo = destino / relativo
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(z.read(nome))
        html_principal = destino / principal[len(raiz):]
        texto = html_principal.read_text(encoding="utf-8", errors="ignore")
        html_principal.unlink()
        return texto


def importar(nicho_id: str, nome_arquivo: str, conteudo: bytes, tema: str = "claro") -> dict:
    if not carregar_nicho(nicho_id):
        raise ValueError("Salve o nicho antes de enviar um modelo.")
    if len(conteudo) > LIMITE_ARQUIVO:
        raise ValueError("Arquivo grande demais (máximo 20 MB).")
    nome = nome_arquivo.lower()
    pasta = _pasta(nicho_id)
    temporaria = pasta.with_name(pasta.name + "-novo")
    shutil.rmtree(temporaria, ignore_errors=True)
    temporaria.mkdir(parents=True)
    try:
        if nome.endswith(".zip"):
            html = _extrair_zip(conteudo, temporaria)
        elif nome.endswith((".html", ".htm", ".j2")):
            html = conteudo.decode("utf-8", errors="ignore")
        else:
            raise ValueError("Envie um .html ou um .zip (com o .html, CSS e imagens).")
        (temporaria / "original.html").write_text(html, encoding="utf-8")
    except Exception:
        shutil.rmtree(temporaria, ignore_errors=True)
        raise

    # O modelo pode dizer o próprio fundo com um comentário: {# tema: escuro #}
    marcado = re.search(r"tema:\s*(claro|escuro)", html[:3000])
    if marcado:
        tema = marcado.group(1)

    # Troca o modelo antigo pelo novo só depois que deu tudo certo
    anterior = _meta(nicho_id).get("template_anterior")
    shutil.rmtree(pasta, ignore_errors=True)
    temporaria.rename(pasta)
    _salvar_meta(nicho_id, tema=tema if tema in ("claro", "escuro") else "claro", origem="enviado",
                 nome_enviado=nome_arquivo, enviado_em=datetime.now().isoformat(timespec="seconds"))
    if anterior:
        _salvar_meta(nicho_id, template_anterior=anterior)

    # Já veio com variáveis? Então é um template pronto.
    if "{{ s." in html or "{{s." in html:
        salvar_template(nicho_id, html, origem="manual")
    return status(nicho_id)


# ------------------------------------------------------------------ template
def _ambiente():
    return Environment(loader=FileSystemLoader(str(PASTA_TEMPLATES)),
                       autoescape=select_autoescape(["html", "j2"]), trim_blocks=True, lstrip_blocks=True)


def validar(texto: str):
    """Confere se o Jinja é válido e se renderiza com dados de exemplo."""
    try:
        template = _ambiente().from_string(texto)
    except TemplateSyntaxError as erro:
        raise ValueError(f"Erro de sintaxe no template, linha {erro.lineno}: {erro.message}")
    try:
        html = template.render(**_contexto_exemplo(nicho_id=None))
    except Exception as erro:
        raise ValueError(f"O template não renderizou com dados de exemplo: {erro}")
    if "Exemplo" not in html:
        raise ValueError("O template não usa {{ s.nome }}: parece que nenhum conteúdo foi trocado por variável.")
    return html


def salvar_template(nicho_id: str, texto: str, origem: str = "manual", tokens: int = None) -> dict:
    texto = re.sub(r"^\s*```[a-zA-Z0-9]*\s*\n|\n?```\s*$", "", texto.strip())
    validar(texto)
    (_pasta(nicho_id) / "index.html.j2").write_text(texto, encoding="utf-8")
    campos = {"origem": origem, "convertido_em": datetime.now().isoformat(timespec="seconds")}
    if tokens:
        campos["tokens_conversao"] = tokens
    _salvar_meta(nicho_id, **campos)
    usar(nicho_id)
    return status(nicho_id)


def converter_com_ia(nicho_id: str, log=print) -> dict:
    if not GEMINI_API_KEY:
        raise ValueError("Sem GEMINI_API_KEY: converta à mão (baixe, edite e envie de volta).")
    original = _pasta(nicho_id) / "original.html"
    if not original.exists():
        raise ValueError("Envie um modelo primeiro.")
    html = original.read_text(encoding="utf-8", errors="ignore")
    if len(html) > LIMITE_HTML_IA:
        raise ValueError(f"O HTML tem {len(html):,} caracteres; o limite para a IA é {LIMITE_HTML_IA:,}. "
                         "Tire scripts e SVGs gigantes, ou converta à mão.".replace(",", "."))
    nicho = carregar_nicho(nicho_id)
    prompt = PROMPT_CONVERSAO.format(nicho=nicho["nome"], variaveis=VARIAVEIS, html=html)
    from .ia import chamar_gemini, modelo_em_uso
    log(f"🤖 Convertendo o modelo de {nicho['nome']} com {modelo_em_uso()}...")
    try:
        texto, tokens, _ = chamar_gemini(prompt, max_tokens=65536, temperatura=0.2, nivel="medio", timeout=300, log=log)
    except RuntimeError as erro:
        raise ValueError(str(erro))
    resultado = salvar_template(nicho_id, texto, origem="ia", tokens=tokens)
    log(f"  ✅ modelo convertido ({tokens} tokens, uma vez só)")
    return resultado


def usar(nicho_id: str, ativo: bool = True):
    nicho = carregar_nicho(nicho_id)
    if not nicho:
        return
    if ativo and (_pasta(nicho_id) / "index.html.j2").exists():
        if nicho.get("template") != nome_template(nicho_id):
            # guarda o template de antes, para voltar a ele em "Parar de usar"
            _salvar_meta(nicho_id, template_anterior=nicho.get("template") or "padrao")
        nicho["template"] = nome_template(nicho_id)
    elif not ativo and nicho.get("template") == nome_template(nicho_id):
        anterior = _meta(nicho_id).get("template_anterior") or "padrao"
        nicho["template"] = anterior if (PASTA_TEMPLATES / anterior / "index.html.j2").exists() else "padrao"
    salvar_nicho(nicho)


def definir_tema(nicho_id: str, tema: str):
    if tema not in ("claro", "escuro"):
        raise ValueError("Tema deve ser claro ou escuro")
    # Sem modelo enviado ainda: nada a salvar (o tema vai junto no envio)
    if _pasta(nicho_id).exists():
        _salvar_meta(nicho_id, tema=tema)
    return status(nicho_id)


def remover(nicho_id: str):
    usar(nicho_id, ativo=False)
    shutil.rmtree(_pasta(nicho_id), ignore_errors=True)
    shutil.rmtree(PASTA_SITES / f"_previa-{nome_template(nicho_id)}", ignore_errors=True)


def caminho_template(nicho_id: str):
    return _pasta(nicho_id) / "index.html.j2"


def caminho_original(nicho_id: str):
    return _pasta(nicho_id) / "original.html"


# ------------------------------------------------------------------ prévia
def _imagem_exemplo(destino, texto, tamanho=(1600, 1000), cor=(120, 128, 138)):
    img = Image.new("RGB", tamanho, cor)
    d = ImageDraw.Draw(img)
    for i in range(0, tamanho[0] + tamanho[1], 60):  # listras para parecer "lugar de foto"
        d.line((i, 0, i - tamanho[1], tamanho[1]), fill=tuple(c + 8 for c in cor), width=22)
    d.text((40, tamanho[1] - 70), texto, fill=(255, 255, 255))
    img.save(destino, quality=80)


def _contexto_exemplo(nicho_id=None, pasta=None) -> dict:
    """Dados falsos, só para ver onde cada coisa aparece no modelo."""
    from .cores import montar_paleta
    nicho = carregar_nicho(nicho_id) if nicho_id else None
    tema = _meta(nicho_id).get("tema", "claro") if nicho_id else "claro"
    paleta = montar_paleta((nicho or {}).get("cor_padrao") or "#2563eb", tema)
    textos = (nicho or {}).get("textos_padrao", {})
    servicos = (nicho or {}).get("servicos_padrao") or [
        {"titulo": "Serviço um", "descricao": "Descrição curta do serviço."},
        {"titulo": "Serviço dois", "descricao": "Descrição curta do serviço."},
        {"titulo": "Serviço três", "descricao": "Descrição curta do serviço."},
    ]
    if pasta is not None:
        _imagem_exemplo(pasta / "foto.jpg", "FOTO PRINCIPAL DO NEGOCIO (Maps)")
        for i in range(1, 5):
            _imagem_exemplo(pasta / f"galeria-{i}.jpg", f"GALERIA {i}", (1200, 900), (100 + i * 12, 110, 120))
    s = {
        "nome": "Exemplo do Negócio", "categoria": (nicho or {}).get("nome", "Negócio"), "regiao": "Taguatinga",
        "endereco": "QNA 10 Lote 5 - Taguatinga, Brasília - DF", "telefone": "(61) 99999-0000",
        "instagram": "https://www.instagram.com/exemplo/",
        "slogan": (textos.get("slogan") or "Slogan do negócio").replace("{nome}", "Exemplo do Negócio"),
        "subtitulo": (textos.get("subtitulo") or "Subtítulo com a região.").replace("{regiao}", "Taguatinga"),
        "sobre": (textos.get("sobre") or "Texto sobre o negócio.").replace("{nome}", "Exemplo do Negócio").replace("{regiao}", "Taguatinga"),
        "servicos": servicos, "diferenciais": (nicho or {}).get("diferenciais_padrao") or ["Diferencial um", "Diferencial dois", "Diferencial três"],
        "cta_texto": textos.get("cta") or "Fale com a gente", "cta_link": "https://wa.me/5561999990000", "cta_tipo": "whatsapp",
        "link_whatsapp": "https://wa.me/5561999990000", "link_telefone": "tel:+5561999990000",
        "link_maps": "https://www.google.com/maps", "mapa_embed": "https://maps.google.com/maps?q=-15.83,-48.05&z=16&output=embed",
        "nota": "4,8", "avaliacoes": 132,
        "horarios": [{"dia": "Segunda-feira", "horas": "08:00 a 18:00"}, {"dia": "Sábado", "horas": "08:00 a 12:00"}],
        "depoimentos": [
            {"autor": "Ana", "estrelas": 5, "texto": "Avaliação real do Google aparece aqui, com o primeiro nome de quem escreveu."},
            {"autor": "Carlos", "estrelas": 5, "texto": "Segunda avaliação de exemplo, para ver como fica com mais de uma."},
        ],
        "logo": None, "foto_real": True, "foto_principal": "foto.jpg",
        "galeria": [f"galeria-{i}.jpg" for i in range(1, 5)],
        "imagem_detalhe": None, "imagem_textura": None, "imagens_pessoas": [],
        "horas_semana": 104, "dias_abertos": 6,
        "cor": paleta, "iniciais": "EN", "ano": datetime.now().year,
        "previa_nome": "Você", "previa_link": None, "url_site": "",
    }
    return {"s": s}


def gerar_previa(nicho_id: str) -> str:
    """Renderiza o modelo com dados de exemplo e devolve o endereço local para abrir."""
    from .gerador import _copiar_arquivos_do_template, _injetar_previa
    if not caminho_template(nicho_id).exists():
        raise ValueError("O modelo ainda não foi convertido em template.")
    template = nome_template(nicho_id)
    pasta = PASTA_SITES / f"_previa-{template}"   # pastas com "_" não vão para o Netlify
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    contexto = _contexto_exemplo(nicho_id, pasta)
    html = _ambiente().get_template(f"{template}/index.html.j2").render(**contexto)
    (pasta / "index.html").write_text(_injetar_previa(html, contexto), encoding="utf-8")
    _copiar_arquivos_do_template(template, pasta)
    return f"/demos/_previa-{template}/"
