"""
Publica TODOS os demos de uma vez num único site do Netlify.

Cada lead vira uma pasta:  https://seus-demos.netlify.app/<slug>/
Um deploy só, em vez de um site por cliente: mais simples e sem limite de sites.

O deploy por ZIP substitui o conteúdo anterior inteiro, então demos
apagados no painel também somem do ar no próximo deploy.
"""
import io
import zipfile

import requests

from .config import NETLIFY_SITE_ID, NETLIFY_TOKEN, PASTA_SITES

API = "https://api.netlify.com/api/v1"

# Página da raiz: não lista os clientes (um demo não deve achar o outro)
INDEX_RAIZ = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="robots" content="noindex, nofollow"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prévias</title></head><body style="font-family:system-ui;display:grid;place-items:center;min-height:100vh;margin:0">
<p>Página de prévias.</p></body></html>"""

# Nenhum demo deve aparecer no Google: eles usam a marca de negócios que ainda não são clientes
ROBOTS = "User-agent: *\nDisallow: /\n"
HEADERS = "/*\n  X-Robots-Tag: noindex, nofollow\n"


def netlify_configurado() -> bool:
    return bool(NETLIFY_TOKEN and NETLIFY_SITE_ID)


def montar_zip() -> bytes:
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", INDEX_RAIZ)
        z.writestr("robots.txt", ROBOTS)
        z.writestr("_headers", HEADERS)
        for arquivo in PASTA_SITES.rglob("*"):
            relativo = arquivo.relative_to(PASTA_SITES)
            # pastas que começam com "_" são prévias internas (ex.: prévia do modelo)
            if arquivo.is_file() and not relativo.parts[0].startswith("_"):
                z.write(arquivo, relativo.as_posix())
    return memoria.getvalue()


def publicar(log=print) -> dict:
    if not netlify_configurado():
        raise RuntimeError("Preencha NETLIFY_TOKEN e NETLIFY_SITE_ID no arquivo .env")
    pastas = [p for p in PASTA_SITES.iterdir() if p.is_dir() and not p.name.startswith("_")]
    log(f"📦 Empacotando {len(pastas)} demos...")
    corpo = montar_zip()
    log(f"🚀 Enviando para o Netlify ({len(corpo) // 1024} KB)...")
    resposta = requests.post(
        f"{API}/sites/{NETLIFY_SITE_ID}/deploys",
        headers={"Authorization": f"Bearer {NETLIFY_TOKEN}", "Content-Type": "application/zip"},
        data=corpo,
        timeout=180,
    )
    if resposta.status_code >= 300:
        raise RuntimeError(f"Netlify respondeu {resposta.status_code}: {resposta.text[:200]}")
    dados = resposta.json()
    url = dados.get("ssl_url") or dados.get("url")
    log(f"✅ Publicado: {url}")
    return {"url": url, "deploy_id": dados.get("id"), "estado": dados.get("state"), "demos": len(pastas)}
