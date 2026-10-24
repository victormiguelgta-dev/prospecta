"""
Funções pequenas de limpeza e classificação de dados.

Ficam separadas do bot porque não dependem do navegador:
dá pra testar cada uma sozinha (veja testes/test_limpeza.py).
"""
import re
import unicodedata
from urllib.parse import urlparse

# O Google coloca ícones (caracteres da "área de uso privado" do Unicode,
# de U+E000 a U+F8FF) antes do endereço e do telefone. Era isso que aparecia
# como '' e '' na planilha antiga.
_ICONES = re.compile(r"[-]")

# ---------------------------------------------------------------------------
# Classificação do campo "site" do Maps
# ---------------------------------------------------------------------------
# Muita gente coloca o Instagram ou o WhatsApp no campo "site".
# Esses negócios NÃO têm site, então são leads.
DOMINIOS_REDE_SOCIAL = {
    "instagram.com", "facebook.com", "fb.com", "fb.me", "m.facebook.com",
    "wa.me", "api.whatsapp.com", "whatsapp.com", "chat.whatsapp.com",
    "linktr.ee", "linkin.bio", "beacons.ai", "bio.link", "lnk.bio", "campsite.bio",
    "tiktok.com", "youtube.com", "youtu.be", "twitter.com", "x.com", "linkedin.com",
    "ifood.com.br", "goo.gl", "maps.app.goo.gl", "t.me", "msha.ke",
}
# Sites gratuitos/genéricos: o negócio tem "algo", mas dá pra oferecer melhor.
DOMINIOS_SITE_FRACO = {
    "business.site", "negocio.site", "sites.google.com", "wixsite.com",
    "webnode.page", "webnode.com.br", "blogspot.com", "wordpress.com",
    "carrd.co", "my.canva.site", "canva.site", "godaddysites.com", "comunidades.net",
    "ueniweb.com", "site123.me", "yolasite.com", "jimdosite.com",
}

SITUACOES = {
    "sem_site": "Sem site",
    "so_rede_social": "Só rede social",
    "site_fraco": "Site gratuito/fraco",
    "fora_do_ar": "Site fora do ar",
    "site_proprio": "Tem site próprio",
}


def limpar_texto(texto) -> str:
    """Tira ícones do Google, quebras de linha e espaços repetidos."""
    if not texto:
        return ""
    texto = _ICONES.sub("", str(texto))
    texto = texto.replace("\n", " ").replace("\r", " ")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip(" ,·-").strip()


def dominio(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _pertence(host: str, conjunto: set) -> bool:
    """True se o host é um dos domínios (ou subdomínio dele: loja.wixsite.com)."""
    return any(host == d or host.endswith("." + d) for d in conjunto)


def classificar_site(url: str) -> str:
    """
    Classifica sem acessar a internet (só olhando o endereço).
    A checagem de "fora do ar" é feita depois, no bot, acessando o link.
    """
    if not url or url == "N/A":
        return "sem_site"
    host = dominio(url)
    if not host:
        return "sem_site"
    if _pertence(host, DOMINIOS_REDE_SOCIAL):
        return "so_rede_social"
    if _pertence(host, DOMINIOS_SITE_FRACO):
        return "site_fraco"
    return "site_proprio"


# ---------------------------------------------------------------------------
# Redes sociais
# ---------------------------------------------------------------------------
# Cada rede: (nome no painel, regex que pega o perfil, caminhos que não são perfil)
_REDES = {
    "instagram": (r"instagram\.com/([A-Za-z0-9_.]{2,30})", {"p", "reel", "reels", "explore", "accounts",
                                                             "stories", "tv", "about", "developer"}),
    "facebook": (r"(?:facebook|fb)\.com/([A-Za-z0-9_.\-]{2,80}(?:/[0-9]{5,})?)", {
        "sharer", "sharer.php", "share", "tr", "plugins", "dialog", "login", "groups", "events",
        "watch", "photo", "photo.php", "story.php", "permalink.php", "help", "policies", "privacy", "pages"}),
    "tiktok": (r"tiktok\.com/(@[A-Za-z0-9_.]{2,30})", set()),
    "youtube": (r"youtube\.com/((?:@|channel/|c/|user/)[A-Za-z0-9_.\-]{2,80})", set()),
    "linkedin": (r"linkedin\.com/((?:company|in|school)/[A-Za-z0-9_.\-%]{2,100})", set()),
    "linktree": (r"linktr\.ee/([A-Za-z0-9_.\-]{2,60})", set()),
    "ifood": (r"ifood\.com\.br/(delivery/[A-Za-z0-9_\-/]{3,160})", set()),
    "x": (r"(?:twitter|x)\.com/([A-Za-z0-9_]{2,30})", {"share", "intent", "home", "search", "i"}),
}
_URL_REDE = {
    "instagram": "https://www.instagram.com/{}/",
    "facebook": "https://www.facebook.com/{}",
    "tiktok": "https://www.tiktok.com/{}",
    "youtube": "https://www.youtube.com/{}",
    "linkedin": "https://www.linkedin.com/{}",
    "linktree": "https://linktr.ee/{}",
    "ifood": "https://www.ifood.com.br/{}",
    "x": "https://x.com/{}",
}
NOMES_REDES = {
    "instagram": "Instagram", "facebook": "Facebook", "tiktok": "TikTok", "youtube": "YouTube",
    "linkedin": "LinkedIn", "linktree": "Linktree", "ifood": "iFood", "x": "X (Twitter)",
}


def achar_redes(texto: str) -> dict:
    """
    Procura perfis de redes sociais num texto ou HTML.
    Devolve {rede: url limpa}, só com as redes encontradas (o primeiro perfil de cada).
    """
    redes = {}
    if not texto:
        return redes
    for rede, (padrao, invalidos) in _REDES.items():
        for perfil in re.findall(padrao, texto, re.I):
            perfil = perfil.rstrip("./")
            if perfil.lower().split("/")[0] in invalidos:
                continue
            redes[rede] = _URL_REDE[rede].format(perfil)
            break
    return redes


def juntar_redes(*fontes: dict) -> dict:
    """Junta várias listas de redes; a primeira fonte que trouxer uma rede ganha."""
    redes = {}
    for fonte in fontes:
        for rede, url in (fonte or {}).items():
            if url and rede not in redes:
                redes[rede] = url
    return redes


def numero_curto(texto: str):
    """'1.234' -> 1234 ; '12,5 mil' -> 12500 ; '3K' -> 3000 ; '1,2M' -> 1200000"""
    if not texto:
        return None
    achado = re.search(r"(\d+(?:[.,]\d+)*)\s*(mil|k|m|mi)?\b", str(texto).strip(), re.I)
    if not achado:
        return None
    numero, unidade = achado.group(1), (achado.group(2) or "").lower()
    if unidade:
        valor = float(numero.replace(".", "").replace(",", ".")) if "," in numero else float(numero)
        return int(round(valor * (1_000_000 if unidade in ("m", "mi") else 1_000)))
    return int(re.sub(r"[.,]", "", numero))


def ler_resumo_instagram(texto: str) -> dict:
    """
    O Instagram mostra, sem login, um resumo do perfil na tag og:description:
    "1.234 seguidores, 56 seguindo, 789 publicações - Veja as fotos..." (ou em inglês).
    Devolve {seguidores, posts} com o que conseguir ler (None se não achar).
    """
    texto = texto or ""
    seguidores = re.search(r"([\d.,]+\s*(?:mil|k|m|mi)?)\s*(?:seguidores|followers)", texto, re.I)
    posts = re.search(r"([\d.,]+\s*(?:mil|k|m|mi)?)\s*(?:publica[çc][õo]es|posts)", texto, re.I)
    return {
        "seguidores": numero_curto(seguidores.group(1)) if seguidores else None,
        "posts": numero_curto(posts.group(1)) if posts else None,
    }


# ---------------------------------------------------------------------------
# Instagram e WhatsApp
# ---------------------------------------------------------------------------
_RE_INSTAGRAM = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I)
_RE_WA = re.compile(r"(?:wa\.me/|whatsapp\.com/send\?phone=|phone=)\+?(\d{10,13})", re.I)
_PERFIS_INVALIDOS = {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "about", "developer"}


def achar_instagram(texto: str) -> str:
    """Procura um perfil do Instagram dentro de um texto/HTML e devolve a URL limpa."""
    if not texto:
        return ""
    for usuario in _RE_INSTAGRAM.findall(texto):
        usuario = usuario.rstrip(".")
        if usuario.lower() not in _PERFIS_INVALIDOS:
            return f"https://www.instagram.com/{usuario}/"
    return ""


def achar_whatsapp_em_link(texto: str) -> str:
    """Extrai o número de links wa.me / api.whatsapp.com."""
    if not texto:
        return ""
    achado = _RE_WA.search(texto)
    return normalizar_whatsapp(achado.group(1)) if achado else ""


def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def normalizar_whatsapp(telefone: str) -> str:
    """
    Transforma qualquer telefone brasileiro no formato do wa.me: 55 + DDD + número.
    Devolve "" se não parecer um número válido.
    """
    numero = so_digitos(telefone).lstrip("0")
    if numero.startswith("55") and len(numero) in (12, 13):
        numero = numero[2:]
    if len(numero) not in (10, 11):
        return ""
    return "55" + numero


def eh_celular(telefone: str) -> bool:
    """
    Celular no Brasil: DDD + 9 dígitos começando com 9 (11 dígitos no total).
    Fixo (10 dígitos) até pode ter WhatsApp Business, mas é menos garantido.
    """
    numero = normalizar_whatsapp(telefone)
    return len(numero) == 13 and numero[4] == "9"


# ---------------------------------------------------------------------------
# Dados que vêm na URL do Maps
# ---------------------------------------------------------------------------
_RE_ID_MAPS = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", re.I)
_RE_COORDS = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")


def id_do_maps(url: str) -> str:
    """O ID fixo do local no Google (não muda mesmo se o nome mudar)."""
    achado = _RE_ID_MAPS.search(url or "")
    return achado.group(1).lower() if achado else ""


def coordenadas(url: str):
    achado = _RE_COORDS.search(url or "")
    if not achado:
        return None, None
    return float(achado.group(1)), float(achado.group(2))


def numero_br(texto: str):
    """'4,7' -> 4.7 ; '(1.234)' -> 1234"""
    if not texto:
        return None
    achado = re.search(r"\d+(?:[.,]\d+)*", texto)
    if not achado:
        return None
    valor = achado.group()
    if "," in valor:  # decimal brasileiro
        return float(valor.replace(".", "").replace(",", "."))
    return int(valor.replace(".", ""))


_UNIDADES_TEMPO = {"hora": 0, "minuto": 0, "segundo": 0, "dia": 1, "semana": 7, "mês": 30, "mes": 30,
                   "meses": 30, "ano": 365}


def dias_atras(texto: str):
    """'há 2 semanas' -> 14 ; 'há um mês' -> 30 ; 'Editado há 3 anos' -> 1095 ; não entendeu -> None"""
    achado = re.search(r"(\d+|um|uma)\s+(hora|minuto|segundo|dia|semana|m[eê]s|meses|ano)", (texto or "").lower())
    if not achado:
        return None
    quantidade = 1 if achado.group(1) in ("um", "uma") else int(achado.group(1))
    unidade = achado.group(2).replace("ê", "e")
    return quantidade * _UNIDADES_TEMPO.get(unidade, _UNIDADES_TEMPO.get(unidade.rstrip("s"), 1))


def slugify(texto: str) -> str:
    """'Pizzaria do Zé - Taguatinga' -> 'pizzaria-do-ze-taguatinga'"""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto.lower()).strip("-")
    return texto[:60].strip("-") or "negocio"
