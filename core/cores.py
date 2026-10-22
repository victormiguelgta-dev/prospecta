"""
Extrai a cor principal da logo e monta a paleta do site.

Não usa IA: o Pillow reduz a imagem a poucas cores e escolhemos a
mais "viva" (saturada) que apareça bastante. Depois derivamos todos os
tons do site a partir dela e corrigimos o contraste para o texto ficar legível.
"""
import colorsys
import io
import statistics

from PIL import Image


def _hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(c))) for c in rgb))


def _rgb(cor_hex):
    cor_hex = cor_hex.lstrip("#")
    return tuple(int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))


def _luminancia(rgb):
    def canal(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    """Razão de contraste WCAG entre duas cores hex (4.5 = mínimo para texto)."""
    la, lb = sorted((_luminancia(_rgb(a)), _luminancia(_rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hls(cor_hex):
    r, g, b = (c / 255 for c in _rgb(cor_hex))
    return colorsys.rgb_to_hls(r, g, b)


def _de_hls(h, l, s):
    return _hex(c * 255 for c in colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s))))


def parece_logo(conteudo: bytes) -> bool:
    """
    Logo quase sempre fica sobre um fundo liso, então as bordas da imagem têm
    uma cor só. Foto (selfie, fachada) tem bordas variadas. Medimos o desvio
    padrão do brilho num anel de 3 px em volta da imagem reduzida.
    Ajustado com logos reais do Instagram (0 a 33) contra fotos (63 a 73).
    """
    try:
        img = Image.open(io.BytesIO(conteudo)).convert("L").resize((64, 64))
    except Exception:
        return False
    px = img.load()
    borda = [px[x, y] for x in range(64) for y in range(64) if min(x, y, 63 - x, 63 - y) < 3]
    return statistics.pstdev(borda) < 45


def cor_da_imagem(caminho) -> str:
    """Devolve a cor mais marcante da imagem, ou None se ela for só cinza/preto/branco."""
    try:
        img = Image.open(caminho).convert("RGBA")
    except Exception:
        return None
    img.thumbnail((160, 160))
    # Pixels transparentes (fundo de PNG) não contam
    fundo = Image.new("RGBA", img.size, (255, 255, 255, 0))
    img = Image.alpha_composite(fundo, img)
    pixels = [p[:3] for p in img.getdata() if p[3] > 200]
    if not pixels:
        return None
    amostra = Image.new("RGB", (len(pixels), 1))
    amostra.putdata(pixels)
    reduzida = amostra.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    paleta = reduzida.getpalette()[:24]
    contagem = sorted(reduzida.getcolors(), reverse=True)

    melhor, melhor_nota = None, 0
    total = len(pixels)
    for quantidade, indice in contagem:
        rgb = tuple(paleta[indice * 3: indice * 3 + 3])
        h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
        if s < 0.25 or l < 0.12 or l > 0.9:   # ignora cinzas, preto e branco
            continue
        presenca = quantidade / total
        if presenca < 0.03:                    # ignora pontinhos isolados
            continue
        nota = s * (presenca ** 0.5)
        if nota > melhor_nota:
            melhor, melhor_nota = rgb, nota
    return _hex(melhor) if melhor else None


def _ajustar_luz(cor_hex, fundo_hex, minimo, escurecer):
    """Escurece (ou clareia) a cor até ter o contraste mínimo com o fundo."""
    h, l, s = _hls(cor_hex)
    cor = cor_hex
    for _ in range(60):
        if contraste(cor, fundo_hex) >= minimo:
            break
        l = l - 0.02 if escurecer else l + 0.02
        cor = _de_hls(h, l, s)
    return cor


def montar_paleta(cor_base: str, tema: str = "claro") -> dict:
    """
    A partir de UMA cor, cria todas as cores do site.
    tema "claro": fundo branco; "escuro": fundo bem escuro no tom da marca.
    """
    h, l, s = _hls(cor_base)
    s = max(s, 0.35)

    if tema == "escuro":
        fundo = _de_hls(h, 0.07, min(s, 0.35))
        superficie = _de_hls(h, 0.11, min(s, 0.30))
        texto = _de_hls(h, 0.95, 0.15)
        texto_suave = _de_hls(h, 0.74, 0.12)
        destaque = _ajustar_luz(_de_hls(h, max(l, 0.5), s), fundo, 4.5, escurecer=False)
    else:
        fundo = "#ffffff"
        superficie = _de_hls(h, 0.96, min(s, 0.5))
        texto = _de_hls(h, 0.13, min(s, 0.35))
        texto_suave = _de_hls(h, 0.36, min(s, 0.18))
        destaque = _ajustar_luz(_de_hls(h, l, s), fundo, 4.5, escurecer=True)

    # Texto dentro dos botões: branco ou escuro, o que tiver mais contraste
    sobre_destaque = "#ffffff" if contraste("#ffffff", destaque) >= contraste(texto if tema == "claro" else fundo, destaque) else (texto if tema == "claro" else fundo)
    return {
        "base": cor_base,
        "destaque": destaque,
        "sobre_destaque": sobre_destaque,
        "fundo": fundo,
        "superficie": superficie,
        "texto": texto,
        "texto_suave": texto_suave,
        "profundo": _de_hls(h, 0.16, min(s, 0.55)),  # faixas de cor sólida
        "tema": tema,
    }
