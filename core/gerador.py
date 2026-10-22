"""
Gera o site demo de um lead: baixa imagens, escolhe as cores, pega os textos
(IA ou padrão) e preenche o template HTML do nicho.

Resultado: saida/sites/<slug>/index.html  (+ logo.jpg, foto.jpg, galeria-N.jpg)
"""
import json
import re
import shutil
from datetime import datetime
from html import escape
from urllib.parse import quote, quote_plus

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import db
from .config import PASTA_SITES, PASTA_TEMPLATES, SEU_NOME, SEU_WHATSAPP, URL_DEMOS
from .arquivos_nicho import caminho_imagem, escolher_imagens
from .cores import cor_da_imagem, montar_paleta
from .ia import gerar_textos
from .limpeza import normalizar_whatsapp, slugify
from .nichos import carregar_nicho

TEMAS = {"escuro": "escuro", "academia": "escuro"}  # templates de fundo escuro; o resto é claro

_ambiente = Environment(
    loader=FileSystemLoader(str(PASTA_TEMPLATES)),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _baixar(url: str, destino) -> bool:
    if not url:
        return False
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            destino.write_bytes(r.content)
            return True
    except requests.RequestException:
        pass
    return False


def _slug_unico(lead: dict) -> str:
    if lead.get("slug"):
        return lead["slug"]
    bairro = (lead.get("regiao") or "").split(",")[0]
    base = slugify(lead["nome"])
    if bairro and slugify(bairro) not in base:
        base = f"{base}-{slugify(bairro)}"
    slug, n = base, 2
    with db.conectar() as con:
        while con.execute("SELECT 1 FROM leads WHERE slug = ? AND id != ?", (slug, lead["id"])).fetchone():
            slug, n = f"{base}-{n}", n + 1
    return slug


def link_demo(slug: str, local_base: str = "http://localhost:8000") -> str:
    if URL_DEMOS:
        return f"{URL_DEMOS}/{slug}/"
    return f"{local_base}/demos/{slug}/"


def mensagem_whatsapp(lead: dict, nicho: dict = None) -> str:
    nicho = nicho or carregar_nicho(lead["nicho"]) or {}
    modelo = nicho.get("mensagem_whatsapp") or "Olá, {nome}! Fiz uma prévia de site para vocês: {link}"
    try:
        return modelo.format(nome=lead["nome"], meu_nome=SEU_NOME,
                             link=link_demo(lead["slug"]) if lead.get("slug") else "",
                             regiao=(lead.get("regiao") or "").split(",")[0])
    except (KeyError, IndexError, ValueError):
        return modelo


def link_whatsapp(lead: dict) -> str:
    numero = lead.get("whatsapp") or normalizar_whatsapp(lead.get("telefone"))
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={quote(mensagem_whatsapp(lead))}"


def tema_do_template(template: str) -> str:
    """Claro ou escuro. Modelos enviados guardam o tema no meta.json."""
    meta = PASTA_TEMPLATES / template / "meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8")).get("tema", "claro")
        except ValueError:
            pass
    return TEMAS.get(template, "claro")


def _horas_por_semana(lead: dict):
    """Soma as horas abertas na semana a partir do horário do Maps (ex.: '05:00 a 23:00')."""
    total, dias = 0.0, 0
    for h in lead.get("horario") or []:
        texto = h.lower()
        if "fechado" in texto:
            continue
        if "24 horas" in texto or "aberto 24" in texto:
            total, dias = total + 24, dias + 1
            continue
        abertos = False
        for ini_h, ini_m, fim_h, fim_m in re.findall(r"(\d{1,2})[:h](\d{2})?\s*(?:a|às|-|–)\s*(\d{1,2})[:h]?(\d{2})?", texto):
            inicio = int(ini_h) + int(ini_m or 0) / 60
            fim = int(fim_h) + int(fim_m or 0) / 60
            if fim <= inicio:
                fim += 24  # passa da meia-noite (ex.: 18:00 a 00:00)
            total += fim - inicio
            abertos = True
        dias += abertos
    return round(total), dias


def _horarios(lead: dict) -> list:
    saida = []
    for h in lead.get("horario") or []:
        dia, _, horas = h.partition(",")
        saida.append({"dia": dia.strip().capitalize(), "horas": horas.strip()})
    return saida


def montar_contexto(lead: dict, nicho: dict, textos: dict, paleta: dict, arquivos: dict, slug: str) -> dict:
    """
    Tudo que um template pode usar. Os templates antigos usam as variáveis soltas
    (lead, t, cor...); os modelos que você envia usam o objeto `s`, mais simples.
    A lista completa do `s` está no README (seção "Modelo de site do nicho").
    """
    whatsapp = lead.get("whatsapp")
    telefone = normalizar_whatsapp(lead.get("telefone"))
    endereco_busca = lead.get("endereco") or f"{lead['nome']} {lead.get('regiao', '')}"
    if lead.get("lat") and lead.get("lng"):
        mapa = f"https://maps.google.com/maps?q={lead['lat']},{lead['lng']}&z=16&output=embed"
    else:
        mapa = f"https://maps.google.com/maps?q={quote_plus(endereco_busca)}&z=16&output=embed"
    link_whats = f"https://wa.me/{whatsapp}?text={quote('Olá! Vi o site de vocês e gostaria de mais informações.')}" if whatsapp else None
    link_tel = f"tel:+{telefone}" if telefone else None
    link_maps = lead.get("maps_url") or f"https://www.google.com/maps/search/?api=1&query={quote_plus(endereco_busca)}"
    img = arquivos["img"]
    previa_link = (f"https://wa.me/{SEU_WHATSAPP}?text={quote('Olá! Vi a prévia do site de ' + lead['nome'] + '.')}"
                   if SEU_WHATSAPP else None)
    url_site = f"{URL_DEMOS}/{slug}/" if URL_DEMOS else ""
    iniciais = "".join(p[0] for p in lead["nome"].split()[:2] if p).upper()
    depoimentos = lead.get("depoimentos") or []

    s = {
        "nome": lead["nome"],
        "categoria": lead.get("categoria") or nicho["nome"],
        "regiao": (lead.get("regiao") or "").split(",")[0],
        "endereco": lead.get("endereco") or "",
        "telefone": lead.get("telefone") or "",
        "instagram": lead.get("instagram") or "",
        "slogan": textos.get("slogan", ""),
        "subtitulo": textos.get("subtitulo", ""),
        "sobre": textos.get("sobre", ""),
        "servicos": textos.get("servicos", []),
        "diferenciais": textos.get("diferenciais", []),
        "cta_texto": textos.get("cta", "Fale com a gente"),
        "cta_link": link_whats or link_tel,
        "cta_tipo": "whatsapp" if link_whats else ("telefone" if link_tel else None),
        "link_whatsapp": link_whats,
        "link_telefone": link_tel,
        "link_maps": link_maps,
        "mapa_embed": mapa,
        "nota": f"{lead['nota']:.1f}".replace(".", ",") if lead.get("nota") else "",
        "avaliacoes": lead.get("avaliacoes") or 0,
        "horarios": _horarios(lead),
        "horas_semana": _horas_por_semana(lead)[0],
        "dias_abertos": _horas_por_semana(lead)[1],
        "depoimentos": depoimentos,
        "logo": arquivos["logo"],
        "foto_real": bool(arquivos["foto"]),
        "foto_principal": arquivos["foto"] or (img["fundo"]["arquivo"] if img.get("fundo") else None),
        "galeria": arquivos["galeria"],
        "imagem_detalhe": img["detalhe"]["arquivo"] if img.get("detalhe") else None,
        "imagem_textura": img["textura"]["arquivo"] if img.get("textura") else None,
        "imagens_pessoas": [i["arquivo"] for i in img.get("pessoas", [])],
        "cor": paleta,
        "iniciais": iniciais,
        "ano": datetime.now().year,
        "previa_nome": SEU_NOME,
        "previa_link": previa_link,
        "url_site": url_site,
    }
    return {
        "s": s,
        "lead": lead,
        "nicho": nicho,
        "t": textos,
        "cor": paleta,
        "logo": arquivos["logo"],
        "foto": arquivos["foto"],
        "galeria": arquivos["galeria"],
        "depoimentos": depoimentos,
        "img": img,
        "iniciais": iniciais,
        "link_whatsapp": link_whats,
        "link_telefone": link_tel,
        "link_maps": link_maps,
        "mapa_embed": mapa,
        "previa": {"nome": SEU_NOME, "link": previa_link},
        # Endereço público do demo: o WhatsApp só mostra a foto da prévia do link com URL completa
        "url_site": url_site,
        "ano": s["ano"],
    }


def _injetar_previa(html: str, contexto: dict) -> str:
    """
    Modelos enviados por você podem não ter a faixa de prévia nem o noindex.
    Aqui eles são colocados automaticamente (os templates prontos já têm).
    """
    if 'data-previa' in html or 'class="previa"' in html:
        return html
    s = contexto["s"]
    meta = '<meta name="robots" content="noindex, nofollow">'
    if "noindex" not in html:
        html = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + "\n" + meta, html, count=1, flags=re.I)
    link = f' <a href="{s["previa_link"]}" target="_blank" rel="noopener" style="color:inherit;font-weight:700">Quero este site</a>' if s["previa_link"] else ""
    faixa = (f'<div data-previa style="background:{s["cor"]["profundo"]};color:#fff;font:500 14px/1.4 system-ui,sans-serif;'
             f'text-align:center;padding:9px 16px;position:relative;z-index:9999">'
             f'Prévia de site criada por {escape(s["previa_nome"])} para {escape(s["nome"])}.{link}</div>')
    return re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + faixa, html, count=1, flags=re.I)


def renderizar(template: str, contexto: dict) -> str:
    html = _ambiente.get_template(f"{template}/index.html.j2").render(**contexto)
    return _injetar_previa(html, contexto)


def _copiar_arquivos_do_template(template: str, pasta):
    """CSS, imagens e fontes que vieram junto com o modelo (mantém as subpastas)."""
    origem = PASTA_TEMPLATES / template
    for arquivo in origem.rglob("*"):
        if arquivo.is_dir() or arquivo.suffix == ".j2" or arquivo.name in ("meta.json", "original.html"):
            continue
        destino = pasta / arquivo.relative_to(origem)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(arquivo, destino)


def gerar_site(lead_id: str, usar_ia: bool = True, refazer_textos: bool = False, log=print) -> dict:
    lead = db.buscar(lead_id)
    if not lead:
        raise ValueError("Lead não encontrado")
    nicho = carregar_nicho(lead["nicho"])
    if not nicho:
        raise ValueError(f"Nicho '{lead['nicho']}' não existe mais")

    log(f"🛠 Gerando site: {lead['nome']}")
    slug = _slug_unico(lead)
    pasta = PASTA_SITES / slug
    pasta.mkdir(parents=True, exist_ok=True)

    # 1. Imagens do negócio (baixadas para o site funcionar sozinho no Netlify)
    tem_logo = (pasta / "logo.jpg").exists() or _baixar(lead.get("logo_url"), pasta / "logo.jpg")
    fotos = lead.get("fotos") or []
    tem_foto = (pasta / "foto.jpg").exists() or (bool(fotos) and _baixar(fotos[0], pasta / "foto.jpg"))
    galeria = []
    for i, url in enumerate(fotos[1:7], 1):
        nome = f"galeria-{i}.jpg"
        if (pasta / nome).exists() or _baixar(url, pasta / nome):
            galeria.append(nome)
    if galeria:
        log(f"  {len(galeria) + int(tem_foto)} fotos do negócio")

    # 2. Template e cores: da logo, se tiver; senão a cor padrão do nicho
    template = nicho.get("template") or "padrao"
    if not (PASTA_TEMPLATES / template / "index.html.j2").exists():
        log(f"  template '{template}' não encontrado, usando o padrão")
        template = "padrao"
    cor = (cor_da_imagem(pasta / "logo.jpg") if tem_logo else None) or nicho.get("cor_padrao") or "#2563eb"
    paleta = montar_paleta(cor, tema_do_template(template))
    paleta["origem"] = "logo" if tem_logo and cor != nicho.get("cor_padrao") else "nicho"

    # 2b. Imagens do SEU banco do nicho: uma de cada uso (fundo/detalhe/textura).
    # Nunca substituem foto do negócio; só preenchem os lugares feitos para elas.
    for antiga in pasta.glob("nicho-*"):
        antiga.unlink()
    img = {}
    for uso, escolha in escolher_imagens(nicho, lead["id"]).items():
        itens = escolha if isinstance(escolha, list) else [escolha]
        copiadas = []
        for n, item in enumerate(itens, 1):
            origem = caminho_imagem(nicho["id"], item["arquivo"])
            destino = f"nicho-{uso}-{n}{origem.suffix}" if isinstance(escolha, list) else f"nicho-{uso}{origem.suffix}"
            shutil.copy(origem, pasta / destino)
            copiadas.append({"arquivo": destino, "descricao": item.get("descricao") or ""})
        img[uso] = copiadas if isinstance(escolha, list) else copiadas[0]

    # 3. Textos: reaproveita os que já existem (não gasta token de novo)
    textos = lead.get("textos") if (lead.get("textos") and not refazer_textos) else None
    if not textos:
        textos = gerar_textos(lead, nicho, usar_ia=usar_ia, log=log)

    # 4. Preenche o template
    arquivos = {"logo": "logo.jpg" if tem_logo else None, "foto": "foto.jpg" if tem_foto else None,
                "galeria": galeria, "img": img}
    contexto = montar_contexto(lead, nicho, textos, paleta, arquivos, slug)
    (pasta / "index.html").write_text(renderizar(template, contexto), encoding="utf-8")
    _copiar_arquivos_do_template(template, pasta)

    campos = {"slug": slug, "textos": textos, "cores": paleta,
              "site_gerado_em": datetime.now().isoformat(timespec="seconds")}
    if lead.get("status") in ("novo", None):
        campos["status"] = "site_gerado"
    db.atualizar(lead_id, campos)
    log(f"  ✅ pronto: saida/sites/{slug}/ (template {template})")
    return db.buscar(lead_id)


def limpar_fotos_baixadas(lead: dict):
    """Apaga as fotos já baixadas do site, para a próxima geração usar a lista nova."""
    if lead and lead.get("slug"):
        pasta = PASTA_SITES / lead["slug"]
        for nome in ["foto.jpg", "logo.jpg", *[f"galeria-{i}.jpg" for i in range(1, 10)]]:
            (pasta / nome).unlink(missing_ok=True)


def apagar_site(lead_id: str):
    """Remove o demo (use para quem não fechou: a prévia usa a marca do cliente)."""
    lead = db.buscar(lead_id)
    if lead and lead.get("slug"):
        shutil.rmtree(PASTA_SITES / lead["slug"], ignore_errors=True)
        db.atualizar(lead_id, {"slug": None, "site_gerado_em": None})
