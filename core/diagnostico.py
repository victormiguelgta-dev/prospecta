"""
Diagnóstico do bot: abre a ficha de UM lead no Maps de verdade e registra
o que cada seletor encontrou, com prints e o HTML de cada etapa.

Serve para ajustar o bot quando o Google muda a página: em vez de adivinhar,
olhamos exatamente o que o navegador viu.

Resultado: saida/diagnostico/diagnostico-<slug>-<data>.zip
"""
import json
import shutil
import zipfile
from datetime import datetime

from playwright.async_api import async_playwright

from .config import PASTA_SAIDA
from .limpeza import slugify
from .cores import parece_logo
from .scraper import JS_FOTOS, SELETORES, USER_AGENT, _aceitar_cookies, _avatar_do_dono, _rolar_galeria

PASTA_DIAGNOSTICO = PASTA_SAIDA / "diagnostico"


async def _contar(page, seletor):
    """Quantos elementos o seletor achou e uma amostra do conteúdo de cada um."""
    try:
        el = page.locator(seletor)
        qtd = await el.count()
        amostras = []
        for i in range(min(qtd, 3)):
            item = el.nth(i)
            texto = (await item.inner_text(timeout=1500))[:120] if await item.is_visible() else ""
            atributos = await item.evaluate(
                "e => ({src: e.getAttribute('src'), href: e.getAttribute('href'), "
                "aria: e.getAttribute('aria-label'), dataid: e.getAttribute('data-item-id')})")
            amostras.append({"texto": texto.strip(), **{k: (v or "")[:160] for k, v in atributos.items() if v}})
        return {"seletor": seletor, "encontrados": qtd, "amostras": amostras}
    except Exception as erro:
        return {"seletor": seletor, "erro": str(erro)[:200]}


async def _registrar(page, pasta, nome, relatorio, log):
    await page.screenshot(path=str(pasta / f"{nome}.png"), full_page=False)
    (pasta / f"{nome}.html").write_text(await page.content(), encoding="utf-8")
    fotos = await page.evaluate(JS_FOTOS)
    relatorio[nome] = {"url": page.url, "fotos_do_google_na_pagina": len(set(fotos)), "exemplos_fotos": list(dict.fromkeys(fotos))[:5]}
    log(f"  {nome}: {len(set(fotos))} fotos do Google visíveis")


async def diagnosticar(lead: dict, log=print) -> str:
    if not lead.get("maps_url"):
        raise ValueError("Esse lead não tem o link do Maps salvo.")
    PASTA_DIAGNOSTICO.mkdir(parents=True, exist_ok=True)
    nome = f"diagnostico-{slugify(lead['nome'])}-{datetime.now():%Y%m%d-%H%M%S}"
    pasta = PASTA_DIAGNOSTICO / nome
    pasta.mkdir()
    relatorio = {"lead": lead["nome"], "maps_url": lead["maps_url"], "instagram": lead.get("instagram"),
                 "quando": datetime.now().isoformat(timespec="seconds")}

    async with async_playwright() as p:
        navegador = await p.chromium.launch(headless=True)
        context = await navegador.new_context(locale="pt-BR", user_agent=USER_AGENT, viewport={"width": 1366, "height": 900})
        page = await context.new_page()
        try:
            log("🩺 1/4 Abrindo a ficha no Maps...")
            await page.goto(lead["maps_url"], timeout=45000)
            await _aceitar_cookies(page)
            await page.wait_for_timeout(4000)
            await _registrar(page, pasta, "1-ficha", relatorio, log)
            relatorio["seletores_ficha"] = {}
            for chave, seletor in SELETORES.items():
                for s in (seletor if isinstance(seletor, list) else [seletor]):
                    relatorio["seletores_ficha"][f"{chave}: {s}"] = await _contar(page, s)

            log("🩺 2/4 Abrindo a aba de avaliações...")
            aba = page.locator(SELETORES["aba_avaliacoes"])
            relatorio["aba_avaliacoes_encontrada"] = await aba.count()
            if await aba.count():
                await aba.first.click(timeout=5000)
                await page.wait_for_timeout(3000)
                await _registrar(page, pasta, "2-avaliacoes", relatorio, log)
                relatorio["seletores_avaliacoes"] = {s: await _contar(page, SELETORES[s]) for s in
                                                    ("avaliacao", "avaliacao_estrelas", "avaliacao_texto", "ver_mais")}
                # Lista todas as abas que existem, caso o nome tenha mudado
            relatorio["abas_da_ficha"] = await page.locator('button[role="tab"]').evaluate_all(
                "els => els.map(e => (e.getAttribute('aria-label') || e.innerText || '').trim())")

            log("🩺 3/4 Abrindo a galeria de fotos...")
            await page.goto(lead["maps_url"], timeout=45000)
            await page.wait_for_timeout(3500)
            galeria = page.locator(SELETORES["abrir_galeria"])
            relatorio["botao_galeria_encontrado"] = await galeria.count()
            # Botões com "foto" no nome, caso o seletor da galeria tenha mudado
            relatorio["botoes_com_foto"] = await page.locator('button[aria-label*="oto"], button[jsaction*="photo"]').evaluate_all(
                "els => els.slice(0, 15).map(e => ({aria: e.getAttribute('aria-label'), jsaction: (e.getAttribute('jsaction')||'').slice(0,80)}))")
            if await galeria.count():
                await galeria.first.click(timeout=5000)
                await page.wait_for_timeout(3500)
                avatar = await _avatar_do_dono(page, lead["nome"])
                relatorio["avatar_da_empresa_no_google"] = avatar or "autor da 1ª foto não é a empresa"
                if avatar:
                    resposta = await context.request.get(avatar)
                    (pasta / "3-avatar-google.jpg").write_bytes(await resposta.body())
                    relatorio["avatar_parece_logo"] = parece_logo(await resposta.body())
                for _ in range(6):
                    await _rolar_galeria(page)
                    await page.wait_for_timeout(1200)
                await _registrar(page, pasta, "3-galeria", relatorio, log)

            if lead.get("instagram"):
                log("🩺 4/4 Abrindo o Instagram...")
                insta = await context.new_page()
                try:
                    await insta.goto(lead["instagram"], timeout=30000, wait_until="domcontentloaded")
                    await insta.wait_for_timeout(3000)
                    await insta.screenshot(path=str(pasta / "4-instagram.png"))
                    relatorio["instagram_og_image"] = await insta.locator('meta[property="og:image"]').get_attribute("content") if await insta.locator('meta[property="og:image"]').count() else None
                    relatorio["instagram_url_final"] = insta.url
                except Exception as erro:
                    relatorio["instagram_erro"] = str(erro)[:200]
            else:
                relatorio["instagram"] = "lead sem Instagram encontrado"
                log("🩺 4/4 Lead sem Instagram: pulando")
        except Exception as erro:
            relatorio["erro"] = str(erro)[:400]
            try:
                await page.screenshot(path=str(pasta / "erro.png"))
            except Exception:
                pass
        finally:
            await navegador.close()

    (pasta / "relatorio.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    arquivo_zip = PASTA_DIAGNOSTICO / f"{nome}.zip"
    with zipfile.ZipFile(arquivo_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo in pasta.iterdir():
            z.write(arquivo, arquivo.name)
    shutil.rmtree(pasta, ignore_errors=True)
    log(f"✅ Diagnóstico pronto: {arquivo_zip.name}")
    return arquivo_zip.name
