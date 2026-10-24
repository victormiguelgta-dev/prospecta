"""
Bot de busca no Google Maps (Playwright).

Recebe o nicho e as regiões escolhidos no painel. Para cada local ele:
  1. pula se já está no banco (pelo ID do Maps);
  2. pega nome, categoria, endereço, telefone, site, nota, avaliações, horário e descrição;
  3. junta os links de redes sociais que aparecem na ficha;
  4. vê se o negócio está fechado e se tem botão de agendar ou de pedido online;
  5. classifica o site e, se existir, abre para ver se está no ar, tem HTTPS e versão de celular;
  6. lê as avaliações mais recentes (só para classificar: dores, respostas do dono);
  7. pega os links das fotos e da logo (para o pacote do site; nada é baixado);
  8. lê no Instagram o total de posts e de seguidores (sem login);
  9. salva no banco e manda analisar (nota, classe e oportunidades).

ATENÇÃO: o Google muda o HTML do Maps de vez em quando. Se algum campo parar
de vir, o problema quase sempre é um seletor daqui. Eles estão todos juntos
em SELETORES para facilitar a manutenção. Use o botão "Diagnóstico" do painel
para ver o que o bot está enxergando.
"""
import asyncio
import random
import re
import time
from hashlib import md5

from playwright.async_api import async_playwright

from . import db
from .cores import parece_logo
from .limpeza import (
    achar_redes, achar_whatsapp_em_link, classificar_site, coordenadas, dias_atras,
    eh_celular, id_do_maps, juntar_redes, ler_resumo_instagram, limpar_texto, normalizar_whatsapp,
    numero_br, slugify, SITUACOES,
)

SELETORES = {
    "feed": 'div[role="feed"]',
    "links_locais": 'a[href*="/maps/place/"]',
    "painel": 'div[role="main"]',
    "nome": "h1",
    "categoria": 'button[jsaction*="category"]',
    "endereco": 'button[data-item-id="address"]',
    "telefone": 'button[data-item-id^="phone:tel:"]',
    "site": 'a[data-item-id="authority"]',
    "nota": 'div.F7nice span[aria-hidden="true"]',
    "avaliacoes": 'div.F7nice span[aria-label]',
    "horario": '[aria-label*="segunda-feira"], [aria-label*="Segunda-feira"]',
    "foto": [
        'button[jsaction*="heroHeaderImage"] img',
        'img[src*="googleusercontent.com/p/"]',
        'img[src*="googleusercontent.com/gps-cs"]',
    ],
    # Descrição escrita pelo dono ("Do proprietário" / resumo do Google)
    "descricao": ['div.PYvSYb', 'div[aria-label^="Sobre"] .PYvSYb', 'div.WeS02d div.PYvSYb'],
    # Aba de avaliações e cada avaliação dentro dela
    "aba_avaliacoes": 'button[role="tab"][aria-label*="Avalia"], button[role="tab"]:has-text("Avaliações")',
    "aba_visao_geral": 'button[role="tab"][aria-label^="Visão geral"], button[role="tab"]:has-text("Visão geral")',
    "ordenar_avaliacoes": 'button[aria-label*="Classificar"], button[aria-label*="Ordenar"], button[data-value="Classificar"]',
    "mais_recentes": 'div[role="menuitemradio"]:has-text("Mais recentes"), [role="menuitem"]:has-text("Mais recentes")',
    "avaliacao": 'div[data-review-id][aria-label]',
    "avaliacao_estrelas": 'span[role="img"][aria-label*="estrela"]',
    "avaliacao_texto": 'span.wiI7pd',
    "avaliacao_data": 'span.rsqaWe',
    "ver_mais": 'button[aria-label="Ver mais"], button.w8nwRe',
    # Botão que abre a galeria de fotos
    "abrir_galeria": 'button[jsaction*="heroHeaderImage"]',
    # Painel da galeria que rola (a lista de miniaturas fica do lado esquerdo)
    "galeria_rolagem": 'div.m6QErb.DxyBCb',
    # Quem postou a foto aberta na galeria (link para o perfil + avatar redondo)
    "autor_foto": 'h1 a[href*="/maps/contrib/"]',
}

# Textos que o bot procura na ficha (em português e inglês)
TEXTOS_FECHADO = {"permanentemente": ("Fechado permanentemente", "Permanently closed"),
                  "temporariamente": ("Fechado temporariamente", "Temporarily closed")}
TEXTOS_AGENDAR = ("agendar", "reservar", "fazer uma reserva", "marcar horário", "marcar consulta")
TEXTOS_PEDIDO = ("fazer pedido", "pedir on-line", "pedir online", "peça on-line", "pedido on-line", "cardápio",
                 "order online")
TEXTOS_RESPOSTA = ("resposta do proprietário", "response from the owner")

MAX_FOTOS = 10
MAX_AVALIACOES = 12

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
EMAILS_IGNORADOS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", "wixpress.com",
                    "domain.com", "example.com", "sentry.io", "seudominio")
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


async def _pausa(minimo=0.8, maximo=1.8):
    """Espera aleatória: parece mais humano e reduz o risco de bloqueio."""
    await asyncio.sleep(random.uniform(minimo, maximo))


async def _texto(page, seletor):
    el = page.locator(seletor)
    if await el.count() == 0:
        return ""
    try:
        return limpar_texto(await el.first.inner_text(timeout=2000))
    except Exception:
        return ""


async def _atributo(page, seletor, atributo):
    el = page.locator(seletor)
    if await el.count() == 0:
        return ""
    try:
        return (await el.first.get_attribute(atributo, timeout=2000)) or ""
    except Exception:
        return ""


def _foto_grande(url: str) -> str:
    """As fotos do Google aceitam tamanho na URL: troca a miniatura por uma maior."""
    if "googleusercontent.com" not in url:
        return url
    return re.sub(r"=[^/?#]*$", "", url) + "=w1600-h1000-k-no"


# Pega URLs de fotos do Google em <img> e em background-image (a galeria usa os dois).
# Ignora as fotos anexadas às avaliações: na ficha elas lotariam as vagas da galeria.
JS_FOTOS = r"""() => {
  const urls = [];
  document.querySelectorAll('img').forEach(i => { if (!i.closest('[data-review-id]')) urls.push(i.src || ''); });
  document.querySelectorAll('[style*="background-image"]').forEach(e => {
    if (e.closest('[data-review-id]')) return;
    const m = (e.getAttribute('style') || '').match(/url\(["']?(https:[^"')]+)/);
    if (m) urls.push(m[1]);
  });
  return urls.filter(u => /googleusercontent\.com\/(p\/|gps-cs|gps-proxy|geougc|grass-cs)/.test(u));
}"""

# Texto visível da ficha + todos os links e rótulos de botões, numa ida só ao navegador
JS_FICHA = r"""() => {
  const painel = document.querySelector('div[role="main"]') || document.body;
  const links = [...painel.querySelectorAll('a[href]')].map(a => a.href);
  const rotulos = [...painel.querySelectorAll('a, button')]
    .map(e => ((e.getAttribute('aria-label') || '') + ' ' + (e.innerText || '')).trim().toLowerCase())
    .filter(t => t);
  return {texto: (painel.innerText || '').slice(0, 20000), links, rotulos, achou_painel: !!document.querySelector('div[role="main"]')};
}"""


def _juntar_fotos(atuais: list, novas: list, limite=MAX_FOTOS) -> list:
    """Junta sem repetir: a mesma foto vem com tamanhos diferentes na URL."""
    vistas = {re.sub(r"=[^/]*$", "", u) for u in atuais}
    for url in novas:
        base = re.sub(r"=[^/]*$", "", url)
        if base not in vistas and len(atuais) < limite:
            vistas.add(base)
            atuais.append(_foto_grande(url))
    return atuais


def sinais_da_ficha(ficha: dict) -> dict:
    """
    Lê o texto e os botões da ficha e devolve os sinais que interessam.
    Quando o bot não enxergou o painel, os sinais ficam None ("não sei"),
    para a nota não punir o lead por uma falha do bot.
    """
    if not ficha.get("achou_painel"):
        return {"fechado": None, "tem_agendar": None, "tem_pedido": None}
    texto = ficha.get("texto", "")
    fechado = None
    for tipo, frases in TEXTOS_FECHADO.items():
        if any(f in texto for f in frases):
            fechado = tipo
    rotulos = ficha.get("rotulos", [])
    links = " ".join(ficha.get("links", [])).lower()
    tem_agendar = any(any(t in r for t in TEXTOS_AGENDAR) for r in rotulos)
    tem_pedido = any(any(t in r for t in TEXTOS_PEDIDO) for r in rotulos) or "ifood.com.br" in links
    return {"fechado": fechado, "tem_agendar": tem_agendar, "tem_pedido": tem_pedido}


async def _rolar_galeria(page):
    """
    Rola o painel de miniaturas da galeria. (O mouse.wheel não serve: ele rola
    o que estiver debaixo do cursor, que normalmente é o mapa.)
    """
    await page.locator(SELETORES["galeria_rolagem"]).evaluate_all(
        "els => els.filter(e => e.scrollHeight > e.clientHeight + 50).forEach(e => e.scrollTop += 1500)")


async def _avatar_do_dono(page, nome: str) -> str:
    """
    Na galeria, cada foto mostra quem a postou. Quando o autor tem o mesmo nome
    do local, é a conta da própria empresa e o avatar dela costuma ser a logo.
    """
    autores = await page.locator(SELETORES["autor_foto"]).evaluate_all("""els => els.map(a => {
        const bg = a.querySelector('[style*="background-image"]');
        const m = bg && (bg.getAttribute('style') || '').match(/url\\(["']?([^"')]+)/);
        return {perfil: a.getAttribute('href'), nome: a.innerText.trim(), avatar: m ? m[1] : ''};
    })""")
    # O avatar e o nome vêm em dois links separados para o mesmo perfil
    nomes = {a["perfil"]: a["nome"] for a in autores if a["nome"]}
    for autor in autores:
        if autor["avatar"] and slugify(nomes.get(autor["perfil"], "")) == slugify(nome):
            url = "https:" + autor["avatar"] if autor["avatar"].startswith("//") else autor["avatar"]
            return re.sub(r"=[^/]*$", "=s400", url)
    return ""


async def _logo_do_google(context, url: str, log) -> str:
    """Confere o avatar da empresa e só aceita se parecer logo (e não selfie ou fachada)."""
    try:
        resposta = await context.request.get(url, timeout=10000)
        if resposta.ok and parece_logo(await resposta.body()):
            log("    logo encontrada no perfil do Google")
            return url
    except Exception:
        pass
    return ""


async def _coletar_galeria(page, fotos: list, nome: str) -> tuple:
    """
    Abre a galeria de fotos do local e pega os links de até MAX_FOTOS (melhor esforço).
    Devolve (fotos, avatar da empresa no Google ou "", conseguiu_abrir).

    A ficha mostra só algumas fotos da galeria, mas com outro ID na URL
    (grass-cs na ficha, gps-cs-s na galeria), então juntar as duas listas
    repete fotos. Se a galeria trouxer algo, ela substitui as fotos da ficha.
    """
    avatar = ""
    da_ficha, fotos = fotos, []
    try:
        botao = page.locator(SELETORES["abrir_galeria"])
        if await botao.count() == 0:
            # Na aba de avaliações o botão some: volta para a visão geral.
            # Clique via DOM: depois das avaliações sobra uma camada invisível
            # por cima do painel que bloqueia o clique normal do Playwright.
            aba = page.locator(SELETORES["aba_visao_geral"])
            if await aba.count():
                await aba.first.evaluate("e => e.click()")
                await page.wait_for_timeout(1500)
        if await botao.count() == 0:
            return da_ficha, avatar, False
        await botao.first.evaluate("e => e.click()")
        await page.wait_for_timeout(2500)
        avatar = await _avatar_do_dono(page, nome)
        for _ in range(4):  # rola a galeria para carregar mais miniaturas
            # A capa da ficha (grass-cs) continua no HTML atrás da galeria: ignora
            novas = [u for u in await page.evaluate(JS_FOTOS) if "/grass-cs/" not in u]
            fotos = _juntar_fotos(fotos, novas, MAX_FOTOS)
            if len(fotos) >= MAX_FOTOS:
                break
            await _rolar_galeria(page)
            await page.wait_for_timeout(1200)
    except Exception:
        return fotos or da_ficha, avatar, False
    return fotos or da_ficha, avatar, True


async def _ler_avaliacoes(page, log) -> list:
    """
    Abre a aba de avaliações, tenta ordenar pelas mais recentes e lê até MAX_AVALIACOES.
    Serve só para classificar: estrelas, texto, se o dono respondeu e há quanto tempo.
    Nenhum nome de cliente é guardado.
    """
    avaliacoes = []
    try:
        aba = page.locator(SELETORES["aba_avaliacoes"])
        if await aba.count() == 0:
            return []
        await aba.first.click(timeout=4000)
        await page.wait_for_timeout(2500)
        try:  # mais recentes primeiro (melhor esforço: se não achar, fica a ordem do Google)
            ordenar = page.locator(SELETORES["ordenar_avaliacoes"])
            if await ordenar.count():
                await ordenar.first.click(timeout=2000)
                await page.wait_for_timeout(800)
                opcao = page.locator(SELETORES["mais_recentes"])
                if await opcao.count():
                    await opcao.first.click(timeout=2000)
                    await page.wait_for_timeout(2000)
        except Exception:
            pass
        botoes = page.locator(SELETORES["ver_mais"])
        for i in range(min(await botoes.count(), MAX_AVALIACOES)):
            try:
                await botoes.nth(i).click(timeout=800)
            except Exception:
                pass
        itens = page.locator(SELETORES["avaliacao"])
        vistos = set()
        for i in range(min(await itens.count(), MAX_AVALIACOES * 2)):
            item = itens.nth(i)
            chave = await item.get_attribute("data-review-id")
            if chave in vistos:
                continue
            vistos.add(chave)
            estrelas_el = item.locator(SELETORES["avaliacao_estrelas"])
            estrelas = numero_br(await estrelas_el.first.get_attribute("aria-label")) if await estrelas_el.count() else None
            texto_el = item.locator(SELETORES["avaliacao_texto"])
            texto = limpar_texto(await texto_el.first.inner_text()) if await texto_el.count() else ""
            data_el = item.locator(SELETORES["avaliacao_data"])
            quando = limpar_texto(await data_el.first.inner_text()) if await data_el.count() else ""
            conteudo = (await item.inner_text()).lower()
            avaliacoes.append({
                "estrelas": int(estrelas) if estrelas else None,
                "texto": texto[:500],
                "respondida": any(t in conteudo for t in TEXTOS_RESPOSTA),
                "quando": quando,
                "dias": dias_atras(quando),
            })
            if len(avaliacoes) >= MAX_AVALIACOES:
                break
        if avaliacoes:
            log(f"    {len(avaliacoes)} avaliações lidas")
    except Exception:
        pass
    return avaliacoes


async def _aceitar_cookies(page):
    """Em alguns países o Google mostra uma tela de consentimento antes do Maps."""
    if "consent." in page.url:
        for texto in ("Aceitar tudo", "Accept all", "Rejeitar tudo"):
            botao = page.get_by_role("button", name=texto)
            if await botao.count():
                await botao.first.click()
                await page.wait_for_timeout(2000)
                return


def auditar_html(html: str, url_final: str, tempo_ms: int) -> dict:
    """O que dá para saber do site só pelo HTML: HTTPS, versão de celular, contatos e redes."""
    emails = {e for e in EMAIL_REGEX.findall(html) if not e.lower().endswith(EMAILS_IGNORADOS)}
    return {
        "online": True,
        "https": url_final.lower().startswith("https://"),
        "celular": bool(re.search(r'<meta[^>]+name=["\']viewport["\']', html, re.I)),
        "whatsapp_no_site": bool(achar_whatsapp_em_link(html)),
        "tempo_ms": tempo_ms,
        "lento": tempo_ms > 4000,
        "email": ", ".join(sorted(emails)[:3]),
        "whatsapp": achar_whatsapp_em_link(html),
        "redes": achar_redes(html),
    }


async def _checar_site(context, url: str, log) -> dict:
    """
    Abre o site informado no Maps (requisição simples, sem renderizar a página)
    e devolve a auditoria. online=False se não abrir.
    """
    inicio = time.monotonic()
    try:
        resposta = await context.request.get(url, timeout=12000, max_redirects=5)
        if resposta.status >= 400:
            log(f"    site respondeu {resposta.status}: considerado fora do ar")
            return {"online": False}
        html = await resposta.text()
    except Exception:
        log("    site não abriu: considerado fora do ar")
        return {"online": False}
    return auditar_html(html, resposta.url, int((time.monotonic() - inicio) * 1000))


async def _ler_instagram(context, url_instagram: str, log) -> dict:
    """
    Pega a foto de perfil (og:image) e o resumo do perfil (seguidores e total de posts).
    É "melhor esforço": o Instagram às vezes pede login e aí não vem nada.
    Uma visita por lead, sem login, para não ter o IP bloqueado.
    """
    dados = {"logo_url": "", "seguidores": None, "posts": None}
    page = await context.new_page()
    try:
        await page.goto(url_instagram, timeout=15000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        dados["logo_url"] = await _atributo(page, 'meta[property="og:image"]', "content")
        resumo = ler_resumo_instagram(await _atributo(page, 'meta[property="og:description"]', "content"))
        dados.update(resumo)
        if resumo["posts"] is not None:
            log(f"    Instagram: {resumo['posts']} posts, {resumo['seguidores']} seguidores")
    except Exception:
        log("    Instagram não abriu (normal às vezes)")
    finally:
        await page.close()
    return dados


async def _coletar_local(context, page, url_local, nicho, regiao, opcoes, log):
    await page.goto(url_local, timeout=30000)
    await page.wait_for_timeout(1500)

    nome = await _texto(page, SELETORES["nome"])
    if not nome:
        return None

    telefone_attr = await _atributo(page, SELETORES["telefone"], "data-item-id")  # "phone:tel:+5561..."
    telefone = limpar_texto(await _texto(page, SELETORES["telefone"]))
    site = await _atributo(page, SELETORES["site"], "href")

    # Nota e quantidade de avaliações
    nota = numero_br(await _texto(page, SELETORES["nota"]))
    avaliacoes = None
    for rotulo in await page.locator(SELETORES["avaliacoes"]).evaluate_all(
        "els => els.map(e => e.getAttribute('aria-label'))"
    ):
        if rotulo and "avalia" in rotulo.lower():
            avaliacoes = numero_br(rotulo)
            break

    # Horário: o Google guarda a tabela inteira num aria-label
    horario = []
    rotulo_horario = await _atributo(page, SELETORES["horario"], "aria-label")
    if rotulo_horario:
        rotulo_horario = re.sub(r"\.?\s*(Ocultar|Mostrar).*$", "", rotulo_horario)
        horario = [limpar_texto(p) for p in re.split(r"[;.]\s*", rotulo_horario) if limpar_texto(p)]

    # Fotos que já aparecem na ficha (a galeria completa vem depois)
    fotos = []
    for seletor in SELETORES["foto"]:
        src = await _atributo(page, seletor, "src")
        if src and src.startswith("http"):
            fotos = _juntar_fotos(fotos, [src])
            break
    fotos = _juntar_fotos(fotos, await page.evaluate(JS_FOTOS))

    descricao = ""
    for seletor in SELETORES["descricao"]:
        descricao = await _texto(page, seletor)
        if descricao:
            break

    # Texto, links e botões da ficha: redes sociais e sinais (fechado, agendar, pedido)
    ficha = await page.evaluate(JS_FICHA)
    sinais = sinais_da_ficha(ficha)
    redes_maps = achar_redes(" ".join([site or "", *ficha.get("links", [])]))

    lat, lng = coordenadas(page.url) if coordenadas(page.url)[0] else coordenadas(url_local)
    lead = {
        "id": id_do_maps(url_local) or id_do_maps(page.url),
        "nicho": nicho["id"],
        "regiao": regiao,
        "nome": nome,
        "categoria": await _texto(page, SELETORES["categoria"]),
        "endereco": await _texto(page, SELETORES["endereco"]),
        "telefone": telefone,
        "site": site or "",
        "nota": nota if isinstance(nota, float) else (float(nota) if isinstance(nota, int) else None),
        "avaliacoes": avaliacoes if avaliacoes is not None else (0 if nota is None else None),
        "horario": horario,
        "fotos": fotos,
        "descricao": descricao,
        "lat": lat,
        "lng": lng,
        "maps_url": url_local.split("?")[0] if url_local.startswith("http") else url_local,
    }

    # ---- Site --------------------------------------------------------------
    situacao = classificar_site(site)
    whatsapp = achar_whatsapp_em_link(site)
    redes_site = {}
    if situacao in ("site_proprio", "site_fraco"):
        auditoria = await _checar_site(context, site, log)
        if not auditoria.get("online"):
            situacao = "fora_do_ar"
        else:
            lead["email"] = auditoria.pop("email", "")
            whatsapp = whatsapp or auditoria.pop("whatsapp", "")
            redes_site = auditoria.pop("redes", {})
        sinais["site"] = auditoria

    # WhatsApp: link wa.me tem prioridade; senão, o telefone se for celular
    numero_maps = normalizar_whatsapp(telefone_attr.replace("phone:tel:", "")) or normalizar_whatsapp(telefone)
    if not whatsapp and eh_celular(numero_maps):
        whatsapp = numero_maps

    redes = juntar_redes(redes_maps, redes_site)
    origem = [o for o, r in (("maps", redes_maps), ("site", redes_site)) if r]
    lead.update({"situacao_site": situacao, "whatsapp": whatsapp, "redes": redes,
                 "redes_origem": ", ".join(origem), "instagram": redes.get("instagram", "")})

    # ---- Coleta extra (não vale a pena para quem está fechado) --------------
    if not sinais.get("fechado") and opcoes.get("coletar_extras", True):
        lead["avaliacoes_lidas"] = await _ler_avaliacoes(page, log)
        lead["fotos"], avatar_google, abriu = await _coletar_galeria(page, lead["fotos"], nome)
        if abriu:
            # Menos fotos do que o limite = o negócio tem só essas fotos
            sinais["total_fotos"] = len(lead["fotos"]) if len(lead["fotos"]) < MAX_FOTOS else None
        if lead["instagram"] and opcoes.get("buscar_instagram", True):
            insta = await _ler_instagram(context, lead["instagram"], log)
            lead["instagram_seguidores"], lead["instagram_posts"] = insta["seguidores"], insta["posts"]
            if insta["logo_url"]:
                lead["logo_url"] = insta["logo_url"]
        if not lead.get("logo_url") and avatar_google:
            lead["logo_url"] = await _logo_do_google(context, avatar_google, log)
    lead["sinais"] = sinais

    if not lead["id"]:
        lead["id"] = "h_" + md5(f"{nome}|{lead['endereco']}".encode()).hexdigest()[:16]
    return lead


async def _buscar_regiao(context, page, nicho, regiao, opcoes, log, deve_parar, ao_salvar):
    termo = f"{nicho['termo_busca']} em {regiao}"
    log(f"🔎 Buscando: {termo}")
    limite = int(opcoes.get("limite", 10))

    try:
        await page.goto(f"https://www.google.com/maps/search/{termo.replace(' ', '+')}?hl=pt-BR", timeout=60000)
        await _aceitar_cookies(page)
        await page.wait_for_timeout(3000)
    except Exception as erro:
        log(f"  erro ao abrir a busca: {erro}")
        return 0

    painel = page.locator(SELETORES["feed"])
    if await painel.count() == 0:
        # Às vezes a busca abre direto em um único local (sem lista)
        if "/maps/place/" in page.url:
            urls = [page.url]
        else:
            log("  nenhum resultado nesta região")
            return 0
    else:
        # Rola a lista até ter locais NOVOS suficientes (pula os que já estão no banco)
        urls, vistos, sem_novidade = [], set(), 0
        for _ in range(25):
            if deve_parar():
                break
            hrefs = await page.locator(SELETORES["links_locais"]).evaluate_all("els => els.map(e => e.href)")
            antes = len(vistos)
            for href in hrefs:
                if href in vistos:
                    continue
                vistos.add(href)
                lead_id = id_do_maps(href)
                if lead_id and db.existe(lead_id):
                    continue
                urls.append(href)
            if len(urls) >= limite:
                break
            sem_novidade = sem_novidade + 1 if len(vistos) == antes else 0
            if sem_novidade >= 3:
                break
            await painel.evaluate("el => el.scrollTop = el.scrollHeight")
            await _pausa(1.2, 2.0)
        urls = urls[:limite]

    log(f"  {len(urls)} locais novos para visitar")
    salvos = 0
    for i, url in enumerate(urls, 1):
        if deve_parar():
            break
        try:
            lead = await _coletar_local(context, page, url, nicho, regiao, opcoes, log)
        except Exception as erro:
            log(f"  [{i}/{len(urls)}] erro: {str(erro)[:80]}")
            continue
        if not lead or db.existe(lead["id"]):
            continue
        db.salvar(lead)
        salvos += 1
        log(f"  [{i}/{len(urls)}] {lead['nome']} · {SITUACOES[lead['situacao_site']]}")
        await ao_salvar(lead["id"])
        await _pausa()
    return salvos


async def rodar_busca(nicho: dict, regioes: list, opcoes: dict, log, deve_parar=lambda: False,
                      ao_salvar=None):
    """
    Função principal do bot. O painel chama esta função.
    `log` recebe cada linha de progresso; `deve_parar` permite o botão "Parar";
    `ao_salvar(lead_id)` (async) roda depois de cada lead salvo, para analisar na hora.
    """
    async def nada(_):
        return None

    ao_salvar = ao_salvar or nada
    db.iniciar()
    total = 0
    async with async_playwright() as p:
        navegador = await p.chromium.launch(headless=bool(opcoes.get("headless", True)))
        context = await navegador.new_context(locale="pt-BR", user_agent=USER_AGENT,
                                              viewport={"width": 1366, "height": 900})
        page = await context.new_page()
        try:
            for regiao in regioes:
                if deve_parar():
                    log("⏹ Busca interrompida.")
                    break
                total += await _buscar_regiao(context, page, nicho, regiao, opcoes, log, deve_parar, ao_salvar)
        finally:
            await navegador.close()
    log(f"🏁 Fim. {total} locais novos salvos.")
    return total


async def recoletar_lead(lead: dict, nicho: dict, log=print) -> dict:
    """
    Abre de novo a ficha de UM lead no Maps e atualiza os dados da coleta.
    Não mexe no CRM (etapa, histórico, próximo passo).
    """
    if not lead.get("maps_url"):
        raise ValueError("Esse lead não tem o link do Maps salvo.")
    async with async_playwright() as p:
        navegador = await p.chromium.launch(headless=True)
        context = await navegador.new_context(locale="pt-BR", user_agent=USER_AGENT,
                                              viewport={"width": 1366, "height": 900})
        page = await context.new_page()
        try:
            novo = await _coletar_local(context, page, lead["maps_url"], nicho, lead.get("regiao") or "",
                                        {"coletar_extras": True, "buscar_instagram": True}, log)
        finally:
            await navegador.close()
    if not novo:
        raise ValueError("Não consegui ler a ficha no Maps (a página mudou ou bloqueou).")
    campos = {}
    for campo in ("fotos", "descricao", "nota", "avaliacoes", "horario", "categoria", "endereco", "telefone",
                  "site", "situacao_site", "avaliacoes_lidas", "sinais", "instagram_seguidores", "instagram_posts"):
        if novo.get(campo) not in (None, "", []):
            campos[campo] = novo[campo]
    campos["redes"] = juntar_redes(novo.get("redes"), lead.get("redes"))
    for campo in ("logo_url", "instagram", "whatsapp", "email"):  # só preenche se antes estava vazio
        if novo.get(campo) and not lead.get(campo):
            campos[campo] = novo[campo]
    db.atualizar(lead["id"], campos)
    log(f"  ✅ {lead['nome']}: dados do Maps atualizados")
    return db.buscar(lead["id"])


# Também dá pra rodar sem o painel:  python -m core.scraper barbearias "Taguatinga, DF"
if __name__ == "__main__":
    import sys
    from .nichos import carregar_nicho

    nicho_escolhido = carregar_nicho(sys.argv[1] if len(sys.argv) > 1 else "barbearias")
    regioes_escolhidas = sys.argv[2:] or ["Taguatinga, DF"]
    asyncio.run(rodar_busca(nicho_escolhido, regioes_escolhidas,
                            {"limite": 5, "headless": False}, print))
