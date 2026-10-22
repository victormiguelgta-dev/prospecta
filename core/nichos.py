"""
Nichos e regiões.

Cada nicho é um arquivo JSON em dados/nichos/. Ele é o "roteiro" do nicho:
o que buscar no Maps, qual template usar, o que a IA deve escrever e
os textos padrão (usados quando não há IA ou quando ela falha).
O painel cria, edita e apaga esses arquivos.
"""
import json

from .config import ARQUIVO_REGIOES, PASTA_NICHOS, PASTA_TEMPLATES
from .limpeza import slugify

NICHO_VAZIO = {
    "id": "",
    "nome": "",
    "termo_busca": "",
    "template": "padrao",
    "cor_padrao": "#2563eb",
    "icone": "✦",
    "roteiro": "",
    "textos_padrao": {
        "slogan": "{nome}",
        "subtitulo": "Atendimento de qualidade em {regiao}.",
        "sobre": "",
        "cta": "Fale com a gente no WhatsApp",
    },
    "servicos_padrao": [],
    "imagens": [],          # [{"arquivo", "uso", "descricao"}], gerenciada pelos uploads
    "diferenciais_padrao": [],
    "mensagem_whatsapp": (
        "Olá, {nome}! Tudo bem? Meu nome é {meu_nome}, faço sites para negócios aqui da região. "
        "Vi vocês no Google Maps e montei uma prévia de como poderia ficar o site de vocês: {link}\n\n"
        "É só uma demonstração, consigo deixar ainda melhor e do jeito de vocês. Posso te explicar como funciona?"
    ),
}


def _caminho(nicho_id: str):
    return PASTA_NICHOS / f"{slugify(nicho_id)}.json"


def listar_nichos() -> list:
    nichos = []
    for arquivo in sorted(PASTA_NICHOS.glob("*.json")):
        try:
            nichos.append(json.loads(arquivo.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return nichos


def carregar_nicho(nicho_id: str) -> dict:
    arquivo = _caminho(nicho_id)
    if not arquivo.exists():
        return None
    nicho = json.loads(arquivo.read_text(encoding="utf-8"))
    # Preenche campos que faltarem (nichos antigos continuam funcionando)
    completo = json.loads(json.dumps(NICHO_VAZIO))
    completo.update(nicho)
    completo["textos_padrao"] = {**NICHO_VAZIO["textos_padrao"], **nicho.get("textos_padrao", {})}
    return completo


def salvar_nicho(nicho: dict) -> dict:
    if not nicho.get("nome"):
        raise ValueError("O nicho precisa de um nome.")
    nicho["id"] = slugify(nicho.get("id") or nicho["nome"])
    nicho.setdefault("termo_busca", nicho["nome"])
    # A lista de imagens é gerenciada pelos uploads, não pelo formulário:
    # mantém a que já estava salva para o formulário não apagá-la.
    if "imagens" not in nicho and _caminho(nicho["id"]).exists():
        anterior = json.loads(_caminho(nicho["id"]).read_text(encoding="utf-8"))
        nicho["imagens"] = anterior.get("imagens", [])
    _caminho(nicho["id"]).write_text(json.dumps(nicho, ensure_ascii=False, indent=2), encoding="utf-8")
    return nicho


def excluir_nicho(nicho_id: str):
    import shutil
    from .config import PASTA_ARQUIVOS_NICHO
    arquivo = _caminho(nicho_id)
    if arquivo.exists():
        arquivo.unlink()
    shutil.rmtree(PASTA_ARQUIVOS_NICHO / slugify(nicho_id), ignore_errors=True)


def listar_templates() -> list:
    """Cada pasta em templates_sites/ com um index.html.j2 é um template."""
    return sorted(p.name for p in PASTA_TEMPLATES.iterdir() if (p / "index.html.j2").exists())


def listar_regioes() -> list:
    if not ARQUIVO_REGIOES.exists():
        return []
    return json.loads(ARQUIVO_REGIOES.read_text(encoding="utf-8"))


def salvar_regioes(regioes: list):
    limpas = []
    for r in regioes:
        r = str(r).strip()
        if r and r not in limpas:
            limpas.append(r)
    ARQUIVO_REGIOES.write_text(json.dumps(limpas, ensure_ascii=False, indent=2), encoding="utf-8")
    return limpas
