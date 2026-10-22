"""
Bot de busca no Google Maps (Playwright).

Evolução do script original: em vez de "Igreja Evangélica" fixo, recebe
o nicho e as regiões escolhidos no painel. Para cada local ele:
  1. pula se já está no banco (pelo ID do Maps);
  2. pega nome, categoria, endereço, telefone, site, nota, avaliações, horário e foto;
  3. classifica o site (sem site / só rede social / site fraco / fora do ar / próprio);
  4. procura Instagram, WhatsApp e e-mail;
  5. logo: foto de perfil do Instagram (opcional) ou, se não tiver, a foto de
     perfil da própria empresa no Google (quando parece mesmo uma logo);
  6. salva no banco.

ATENÇÃO: o Google muda o HTML do Maps de vez em quando. Se algum campo parar
de vir, o problema quase sempre é um seletor daqui. Eles estão todos juntos
em SELETORES para facilitar a manutenção.
"""
import asyncio
import io
import random
import re

from PIL import Image
from playwright.async_api import async_playwright

from . import db
from .cores import parece_logo
from .ia import escolher_fotos, ia_disponivel
from .limpeza import (
    achar_instagram, achar_whatsapp_em_link, classificar_site, coordenadas, eh_celular,
    id_do_maps, limpar_texto, normalizar_whatsapp, numero_br, slugify, SITUACOES,
)

SELETORES = {
    "feed": 'div[role="feed"]',
    "links_locais": 'a[href*="/maps/place/"]',
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
    "instagram": 'a[href*="instagram.com"]',
    # Descrição escrita pelo dono ("Do proprietário" / resumo do Google)
    "descricao": ['div.PYvSYb', 'div[aria-label^="Sobre"] .PYvSYb', 'div.WeS02d div.PYvSYb'],
    # Aba de avaliações e cada avaliação dentro dela
    "aba_avaliacoes": 'button[role="tab"][aria-label*="Avalia"], button[role="tab"]:has-text("Avaliações")',
    "aba_visao_geral": 'button[role="tab"][aria-label^="Visão geral"], button[role="tab"]:has-text("Visão geral")',
    "avaliacao": 'div[data-review-id][aria-label]',
    "avaliacao_estrelas": 'span[role="img"][aria-label*="estrela"]',
    "avaliacao_texto": 'span.wiI7pd',
    "ver_mais": 'button[aria-label="Ver mais"], button.w8nwRe',
    # Botão que abre a galeria de fotos
    "abrir_galeria": 'button[jsaction*="heroHeaderImage"]',
    # Painel da galeria que rola (a lista de miniaturas fica do lado esquerdo)
    "galeria_rolagem": 'div.m6QErb.DxyBCb',
    # Quem postou a foto aberta na galeria (link para o perfil + avatar redondo)
    "autor_foto": 'h1 a[href*="/maps/contrib/"]',
}

MAX_FOTOS = 8
MAX_CANDIDATAS = 20  # quantas fotos da galeria a IA avalia para escolher as MAX_FOTOS
MAX_DEPOIMENTOS = 5

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


def _juntar_fotos(atuais: list, novas: list, limite=MAX_FOTOS) -> list:
    """Junta sem repetir: a mesma foto vem com tamanhos diferentes na URL."""
    vistas = {re.sub(r"=[^/]*$", "", u) for u in atuais}
    for url in novas:
        base = re.sub(r"=[^/]*$", "", url)
        if base not in vistas and len(atuais) < limite:
            vistas.add(base)
            atuais.append(_foto_grande(url))
    return atuais


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
    """Baixa o avatar da empresa e só aceita se parecer logo (e não selfie ou fachada)."""
    try:
        resposta = await context.request.get(url, timeout=10000)
        if resposta.ok and parece_logo(await resposta.body()):
            log("    logo encontrada no perfil do Google")
            return url
        log("    foto de perfil do Google não parece logo: ignorada")
    except Exception:
        pass
    return ""


async def _coletar_galeria(page, fotos: list, nome: str, log) -> tuple:
    """
    Abre a galeria de fotos do local e pega até MAX_CANDIDATAS (melhor esforço).
    Devolve (fotos, avatar da empresa no Google ou "").

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
            return da_ficha, avatar
        await botao.first.evaluate("e => e.click()")
        await page.wait_for_timeout(2500)
        avatar = await _avatar_do_dono(page, nome)
        for _ in range(10):  # rola a galeria para carregar mais miniaturas
            # A capa da ficha (grass-cs) continua no HTML atrás da galeria: ignora
            novas = [u for u in await page.evaluate(JS_FOTOS) if "/grass-cs/" not in u]
            fotos = _juntar_fotos(fotos, novas, MAX_CANDIDATAS)
            if len(fotos) >= MAX_CANDIDATAS:
                break
            await _rolar_galeria(page)
            await page.wait_for_timeout(1200)
    except Exception:
        pass
    return fotos or da_ficha, avatar


async def _selecionar_fotos(context, fotos: list, lead: dict, nicho: dict, log) -> list:
    """
    A IA olha as fotos candidatas e fica só com as que servem para o site
    (sem selfie, produto, foto escura...), com a melhor capa primeiro.
    Sem IA, ou se ela falhar, ficam as primeiras MAX_FOTOS como antes.
    """
    if not fotos or not ia_disponivel():
        return fotos[:MAX_FOTOS]
    imagens, orientacoes, urls = [], [], []
    for url in fotos:
        try:  # versão pequena: gasta menos token e chega rápido
            resposta = await context.request.get(re.sub(r"=[^/]*$", "", url) + "=s512", timeout=10000)
            img = Image.open(io.BytesIO(await resposta.body())).convert("RGB")
        except Exception:
            continue
        saida = io.BytesIO()
        img.save(saida, "JPEG", quality=70)
        imagens.append(saida.getvalue())
        orientacoes.append("horizontal" if img.width > img.height * 1.1 else
                           "vertical" if img.height > img.width * 1.1 else "quadrada")
        urls.append(url)
    try:
        ordem = await asyncio.to_thread(escolher_fotos, imagens, orientacoes, lead, nicho, log)
    except Exception as erro:
        log(f"    IA não escolheu as fotos ({str(erro)[:80]}): ficam as primeiras")
        return fotos[:MAX_FOTOS]
    return [urls[i] for i in ordem][:MAX_FOTOS]


async def _coletar_avaliacoes(page, log) -> list:
    """
    Abre a aba de avaliações e pega as melhores com texto (4 ou 5 estrelas).
    Só o primeiro nome do autor vai para o site.
    """
    depoimentos = []
    try:
        aba = page.locator(SELETORES["aba_avaliacoes"])
        if await aba.count() == 0:
            return []
        await aba.first.click(timeout=4000)
        await page.wait_for_timeout(2500)
        # Abre os textos cortados ("Mais")
        botoes = page.locator(SELETORES["ver_mais"])
        for i in range(min(await botoes.count(), 8)):
            try:
                await botoes.nth(i).click(timeout=1000)
            except Exception:
                pass
        itens = page.locator(SELETORES["avaliacao"])
        vistos = set()
        for i in range(min(await itens.count(), 20)):
            item = itens.nth(i)
            autor = (await item.get_attribute("aria-label") or "").strip()
            if autor in vistos:
                continue
            vistos.add(autor)
            estrelas_el = item.locator(SELETORES["avaliacao_estrelas"])
            estrelas = numero_br(await estrelas_el.first.get_attribute("aria-label")) if await estrelas_el.count() else None
            texto_el = item.locator(SELETORES["avaliacao_texto"])
            texto = limpar_texto(await texto_el.first.inner_text()) if await texto_el.count() else ""
            if not texto or len(texto) < 40 or (estrelas and estrelas < 4):
                continue
            depoimentos.append({
                "autor": autor.split()[0].title() if autor else "Cliente",
                "estrelas": int(estrelas or 5),
                "texto": texto[:420],
            })
            if len(depoimentos) >= MAX_DEPOIMENTOS:
                break
        if depoimentos:
            log(f"    {len(depoimentos)} avaliações com texto")
    except Exception:
        pass
    return depoimentos


async def _aceitar_cookies(page):
    """Em alguns países o Google mostra uma tela de consentimento antes do Maps."""
    if "consent." in page.url:
        for texto in ("Aceitar tudo", "Accept all", "Rejeitar tudo"):
            botao = page.get_by_role("button", name=texto)
            if await botao.count():
                await botao.first.click()
                await page.wait_for_timeout(2000)
                return


async def _checar_site(context, url: str, log) -> dict:
    """
    Abre o site informado no Maps e devolve:
    online (bool), e-mails, Instagram e WhatsApp encontrados no HTML.
    Usa requisição simples (sem renderizar a página), é rápido.
    """
    resultado = {"online": False, "email": "", "instagram": "", "whatsapp": ""}
    try:
        resposta = await context.request.get(url, timeout=12000, max_redirects=5)
        if resposta.status >= 400:
            log(f"    site respondeu {resposta.status}: considerado fora do ar")
            return resultado
        html = await resposta.text()
    except Exception:
        log("    site não abriu: considerado fora do ar")
        return resultado

    resultado["online"] = True
    emails = {e for e in EMAIL_REGEX.findall(html) if not e.lower().endswith(EMAILS_IGNORADOS)}
    resultado["email"] = ", ".join(sorted(emails)[:3])
    resultado["instagram"] = achar_instagram(html)
    resultado["whatsapp"] = achar_whatsapp_em_link(html)
    return resultado


async def _logo_do_instagram(context, url_instagram: str, log) -> dict:
    """
    Tenta pegar a foto de perfil (og:image) e a bio do Instagram.
    É "melhor esforço": o Instagram às vezes pede login e aí não vem nada.
    Faça poucas consultas por vez para não ter o IP bloqueado.
    """
    dados = {"logo_url": "", "bio": ""}
    page = await context.new_page()
    try:
        await page.goto(url_instagram, timeout=15000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        dados["logo_url"] = await _atributo(page, 'meta[property="og:image"]', "content")
        dados["bio"] = limpar_texto(await _atributo(page, 'meta[property="og:description"]', "content"))
        if dados["logo_url"]:
            log("    logo encontrada no Instagram")
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

    # Fotos: a principal (topo da ficha) primeiro, depois as outras que já aparecem
    fotos = []
    for seletor in SELETORES["foto"]:
        src = await _atributo(page, seletor, "src")
        if src and src.startswith("http"):
            fotos = _juntar_fotos(fotos, [src])
            break
    fotos = _juntar_fotos(fotos, await page.evaluate(JS_FOTOS))

    # Descrição do proprietário
    descricao = ""
    for seletor in SELETORES["descricao"]:
        descricao = await _texto(page, seletor)
        if descricao:
            break

    # Instagram que aparece na própria ficha do Maps
    instagram = achar_instagram(" ".join(
        await page.locator(SELETORES["instagram"]).evaluate_all("els => els.map(e => e.href)")
    ))

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
        "nota": nota if isinstance(nota, float) else None,
        "avaliacoes": avaliacoes,
        "horario": horario,
        "fotos": fotos,
        "descricao": descricao,
        "lat": lat,
        "lng": lng,
        "maps_url": url_local.split("?")[0] if url_local.startswith("http") else url_local,
        "status": "novo",
    }

    # ---- Classificação do site ---------------------------------------------
    situacao = classificar_site(site)
    whatsapp = achar_whatsapp_em_link(site)
    if situacao == "so_rede_social":
        instagram = instagram or achar_instagram(site)
    elif situacao in ("site_proprio", "site_fraco"):
        checagem = await _checar_site(context, site, log)
        if not checagem["online"]:
            situacao = "fora_do_ar"
        lead["email"] = checagem["email"]
        instagram = instagram or checagem["instagram"]
        whatsapp = whatsapp or checagem["whatsapp"]

    # WhatsApp: link wa.me tem prioridade; senão, o telefone se for celular
    numero_maps = normalizar_whatsapp(telefone_attr.replace("phone:tel:", "")) or normalizar_whatsapp(telefone)
    if not whatsapp and eh_celular(numero_maps):
        whatsapp = numero_maps

    lead.update({"situacao_site": situacao, "instagram": instagram, "whatsapp": whatsapp})

    # Sem site próprio = lead. Quem tem site é salvo como "descartado" só
    # para o bot não visitar de novo nas próximas buscas.
    if situacao == "site_proprio":
        lead["status"] = "descartado"
    else:
        # Só gasta tempo com galeria/avaliações em quem é lead de verdade
        if opcoes.get("coletar_extras", True):
            lead["depoimentos"] = await _coletar_avaliacoes(page, log)
            lead["fotos"], avatar_google = await _coletar_galeria(page, lead["fotos"], nome, log)
            lead["fotos"] = await _selecionar_fotos(context, lead["fotos"], lead, nicho, log)
            if len(lead["fotos"]) > 1:
                log(f"    {len(lead['fotos'])} fotos")
        else:
            avatar_google = ""
        if instagram and opcoes.get("buscar_instagram"):
            extra = await _logo_do_instagram(context, instagram, log)
            lead["logo_url"] = extra["logo_url"]
            if extra["bio"]:
                lead["observacoes"] = f"Bio do Instagram: {extra['bio']}"
        # Sem logo do Instagram: tenta a foto de perfil da empresa no Google
        if not lead.get("logo_url") and avatar_google:
            lead["logo_url"] = await _logo_do_google(context, avatar_google, log)

    if not lead["id"]:
        from hashlib import md5
        lead["id"] = "h_" + md5(f"{nome}|{lead['endereco']}".encode()).hexdigest()[:16]
    return lead


async def _buscar_regiao(context, page, nicho, regiao, opcoes, log, deve_parar):
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
        if not lead:
            continue
        if db.existe(lead["id"]):
            continue
        db.salvar(lead)
        salvos += 1
        marca = "✅ LEAD" if lead["situacao_site"] != "site_proprio" else "— tem site"
        log(f"  [{i}/{len(urls)}] {lead['nome']} · {SITUACOES[lead['situacao_site']]} {marca}")
        await _pausa()
    return salvos


async def rodar_busca(nicho: dict, regioes: list, opcoes: dict, log, deve_parar=lambda: False):
    """
    Função principal do bot. O painel chama esta função.
    `log` recebe cada linha de progresso; `deve_parar` permite o botão "Parar".
    """
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
                total += await _buscar_regiao(context, page, nicho, regiao, opcoes, log, deve_parar)
        finally:
            await navegador.close()
    log(f"🏁 Fim. {total} locais novos salvos no banco.")
    return total


async def recoletar_lead(lead: dict, nicho: dict, log=print) -> dict:
    """
    Abre de novo a ficha de UM lead no Maps e atualiza fotos, avaliações,
    descrição, nota e horário. Útil para leads coletados antes de uma melhoria
    do bot. Não mexe em status, textos nem site gerado.
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
                                        {"coletar_extras": True, "buscar_instagram": not lead.get("logo_url")}, log)
        finally:
            await navegador.close()
    if not novo:
        raise ValueError("Não consegui ler a ficha no Maps (a página mudou ou bloqueou).")
    campos = {}
    for campo in ("fotos", "depoimentos", "descricao", "nota", "avaliacoes", "horario", "categoria", "endereco"):
        if novo.get(campo):
            campos[campo] = novo[campo]
    for campo in ("logo_url", "instagram", "whatsapp"):  # só preenche se antes estava vazio
        if novo.get(campo) and not lead.get(campo):
            campos[campo] = novo[campo]
    db.atualizar(lead["id"], campos)
    log(f"  ✅ {lead['nome']}: {len(campos.get('fotos', []))} fotos, {len(campos.get('depoimentos', []))} avaliações")
    return db.buscar(lead["id"])


# Também dá pra rodar sem o painel:  python -m core.scraper pizzarias "Taguatinga, DF"
if __name__ == "__main__":
    import sys
    from .nichos import carregar_nicho

    nicho_escolhido = carregar_nicho(sys.argv[1] if len(sys.argv) > 1 else "igrejas")
    regioes_escolhidas = sys.argv[2:] or ["Taguatinga, DF"]
    asyncio.run(rodar_busca(nicho_escolhido, regioes_escolhidas,
                            {"limite": 5, "headless": False}, print))
