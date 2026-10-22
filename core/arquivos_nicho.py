"""
Imagens e material de consulta de cada nicho.

    dados/arquivos_nicho/<nicho>/imagens/     imagens que podem entrar nos sites
    dados/arquivos_nicho/<nicho>/consulta/    textos que a IA lê antes de escrever

IMAGENS: cada uma tem um "uso", que diz ONDE ela pode aparecer.
Nenhum uso é "foto do negócio": esse lugar é só das fotos reais do Maps/Instagram.
  - fundo:   topo do site, quando o negócio não tem nenhuma foto própria
  - detalhe: imagem ilustrativa entre as seções (ex.: close de halteres, massa de pizza)
  - textura: fundo da chamada final, sempre escurecido por cima
  - pessoas: pessoas usando o serviço (ex.: treinando). Entram nos slides do topo
             DEPOIS das fotos reais e em destaques, nunca na galeria "por dentro"

CONSULTA: .txt, .md, .csv, .json ou .pdf. O texto é extraído no upload e
entra no pedido da IA (com limite de tamanho, para não gastar token à toa).
"""
import hashlib
import io
import json
import re

from PIL import Image

from .config import PASTA_ARQUIVOS_NICHO
from .limpeza import slugify
from .nichos import _caminho, carregar_nicho

USOS = {
    "fundo": "Topo, quando o negócio não tem foto própria",
    "detalhe": "Ilustração entre as seções",
    "textura": "Fundo da chamada final (fica escurecida)",
    "pessoas": "Pessoas treinando/usando o serviço (slides do topo e destaques)",
}
# Usos em que o site recebe TODAS as imagens (em ordem diferente por lead), não só uma
USOS_LISTA = {"pessoas"}
EXTENSOES_CONSULTA = {".txt", ".md", ".csv", ".json", ".pdf"}
LIMITE_CONSULTA = 6000   # caracteres enviados à IA no total (~1.500 tokens)
LADO_MAXIMO = 1920       # imagens maiores são reduzidas (site mais leve)


def _pasta(nicho_id: str, tipo: str):
    pasta = PASTA_ARQUIVOS_NICHO / slugify(nicho_id) / tipo
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


_NOME_VALIDO = re.compile(r"^[a-z0-9-]+\.(?:txt|jpg|png)$")


def _seguro(arquivo: str) -> str:
    """Impede nomes como '../../.env' vindos da URL: só aceita nomes que nós mesmos geramos."""
    return arquivo if _NOME_VALIDO.match(arquivo or "") else "nome-invalido.txt"


def _salvar_nicho_json(nicho: dict):
    _caminho(nicho["id"]).write_text(json.dumps(nicho, ensure_ascii=False, indent=2), encoding="utf-8")


def _nome_seguro(nome: str, extensao: str) -> str:
    base = slugify(re.sub(r"\.[^.]+$", "", nome))[:40]
    return f"{base}{extensao}"


# ------------------------------------------------------------------ imagens
def adicionar_imagem(nicho_id: str, nome_original: str, conteudo: bytes, uso: str, descricao: str = "") -> dict:
    nicho = carregar_nicho(nicho_id)
    if not nicho:
        raise ValueError("Salve o nicho antes de adicionar imagens.")
    if uso not in USOS:
        raise ValueError(f"Uso inválido. Opções: {', '.join(USOS)}")
    try:
        img = Image.open(io.BytesIO(conteudo))
        img.load()
    except Exception:
        raise ValueError(f"{nome_original} não é uma imagem válida.")

    img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    tem_transparencia = img.mode in ("RGBA", "LA") or "transparency" in img.info
    extensao = ".png" if tem_transparencia else ".jpg"
    # hash curto no nome: duas imagens com o mesmo nome não se sobrescrevem
    nome = _nome_seguro(nome_original, f"-{hashlib.md5(conteudo).hexdigest()[:6]}{extensao}")
    destino = _pasta(nicho_id, "imagens") / nome
    if tem_transparencia:
        img.save(destino, optimize=True)
    else:
        img.convert("RGB").save(destino, quality=84, optimize=True, progressive=True)

    item = {"arquivo": nome, "uso": uso, "descricao": descricao.strip(),
            "largura": img.width, "altura": img.height}
    nicho["imagens"] = [i for i in nicho.get("imagens", []) if i["arquivo"] != nome] + [item]
    _salvar_nicho_json(nicho)
    return item


def editar_imagem(nicho_id: str, arquivo: str, uso: str = None, descricao: str = None) -> dict:
    nicho = carregar_nicho(nicho_id)
    for item in nicho.get("imagens", []):
        if item["arquivo"] == arquivo:
            if uso:
                if uso not in USOS:
                    raise ValueError("Uso inválido")
                item["uso"] = uso
            if descricao is not None:
                item["descricao"] = descricao.strip()
            _salvar_nicho_json(nicho)
            return item
    raise ValueError("Imagem não encontrada")


def remover_imagem(nicho_id: str, arquivo: str):
    nicho = carregar_nicho(nicho_id)
    nicho["imagens"] = [i for i in nicho.get("imagens", []) if i["arquivo"] != arquivo]
    _salvar_nicho_json(nicho)
    caminho = _pasta(nicho_id, "imagens") / _seguro(arquivo)
    if caminho.exists():
        caminho.unlink()


def caminho_imagem(nicho_id: str, arquivo: str):
    return _pasta(nicho_id, "imagens") / _seguro(arquivo)


def escolher_imagens(nicho: dict, semente: str) -> dict:
    """
    Escolhe UMA imagem de cada uso para um lead.
    A escolha depende do ID do lead: o mesmo lead sempre recebe as mesmas
    imagens, e leads diferentes recebem combinações diferentes.
    """
    escolhidas = {}
    for uso in USOS:
        opcoes = [i for i in nicho.get("imagens", [])
                  if i["uso"] == uso and caminho_imagem(nicho["id"], i["arquivo"]).exists()]
        if not opcoes:
            continue
        if uso in USOS_LISTA:
            # todas, embaralhadas de um jeito fixo para cada lead
            escolhidas[uso] = sorted(opcoes, key=lambda i: hashlib.md5(f"{semente}:{i['arquivo']}".encode()).hexdigest())
        else:
            indice = int(hashlib.md5(f"{semente}:{uso}".encode()).hexdigest(), 16) % len(opcoes)
            escolhidas[uso] = opcoes[indice]
    return escolhidas


# ------------------------------------------------------------------ consulta
def _extrair_texto(nome: str, conteudo: bytes) -> str:
    if nome.lower().endswith(".pdf"):
        from pypdf import PdfReader
        leitor = PdfReader(io.BytesIO(conteudo))
        return "\n".join((pagina.extract_text() or "") for pagina in leitor.pages)
    for codificacao in ("utf-8", "latin-1"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return ""


def adicionar_consulta(nicho_id: str, nome_original: str, conteudo: bytes) -> dict:
    if not carregar_nicho(nicho_id):
        raise ValueError("Salve o nicho antes de adicionar arquivos.")
    extensao = "." + nome_original.rsplit(".", 1)[-1].lower() if "." in nome_original else ""
    if extensao not in EXTENSOES_CONSULTA:
        raise ValueError(f"Formato não aceito. Use: {', '.join(sorted(EXTENSOES_CONSULTA))}")
    texto = _extrair_texto(nome_original, conteudo)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    if not texto:
        raise ValueError(f"Não consegui ler texto de {nome_original} (PDF escaneado?).")
    # Guarda sempre como .txt: a extração do PDF acontece uma vez só
    nome = _nome_seguro(nome_original, ".txt")
    (_pasta(nicho_id, "consulta") / nome).write_text(texto, encoding="utf-8")
    return {"arquivo": nome, "original": nome_original, "caracteres": len(texto)}


def listar_consulta(nicho_id: str) -> list:
    return [{"arquivo": a.name, "caracteres": len(a.read_text(encoding="utf-8"))}
            for a in sorted(_pasta(nicho_id, "consulta").glob("*.txt"))]


def ler_consulta(nicho_id: str, arquivo: str) -> str:
    caminho = _pasta(nicho_id, "consulta") / _seguro(arquivo)
    return caminho.read_text(encoding="utf-8") if caminho.exists() else ""


def remover_consulta(nicho_id: str, arquivo: str):
    caminho = _pasta(nicho_id, "consulta") / _seguro(arquivo)
    if caminho.exists():
        caminho.unlink()


def texto_para_ia(nicho_id: str) -> str:
    """Junta o material de consulta, respeitando o limite de tamanho."""
    partes, total = [], 0
    for item in listar_consulta(nicho_id):
        texto = ler_consulta(nicho_id, item["arquivo"])
        espaco = LIMITE_CONSULTA - total
        if espaco <= 200:
            break
        trecho = texto[:espaco]
        partes.append(f"[{item['arquivo']}]\n{trecho}")
        total += len(trecho)
    return "\n\n".join(partes)


def resumo(nicho_id: str) -> dict:
    nicho = carregar_nicho(nicho_id) or {}
    consulta = listar_consulta(nicho_id)
    total = sum(c["caracteres"] for c in consulta)
    return {
        "imagens": nicho.get("imagens", []),
        "usos": USOS,
        "consulta": consulta,
        "consulta_caracteres": total,
        "consulta_enviada": min(total, LIMITE_CONSULTA),
        "limite_consulta": LIMITE_CONSULTA,
    }
