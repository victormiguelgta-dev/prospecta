"""
Nichos e regiões.

Cada nicho é um arquivo JSON em dados/nichos/ com:
  nome           ex.: "Barbearias"
  termo_busca    o que o bot digita no Maps, ex.: "Barbearia"
  icone          um emoji para o painel
  agenda         true se o ramo costuma agendar (barbearia, clínica...): liga a regra
                 "sem agendamento online" das oportunidades de desenvolvimento
  pedido_online  true se o ramo vende por pedido (pizzaria, lanchonete...): liga a regra
                 "sem pedido online nem cardápio digital"
O painel cria, edita e apaga esses arquivos.
"""
import json

from .config import ARQUIVO_REGIOES, PASTA_NICHOS
from .limpeza import slugify

NICHO_VAZIO = {
    "id": "",
    "nome": "",
    "termo_busca": "",
    "icone": "✦",
    "agenda": False,
    "pedido_online": False,
}


def _caminho(nicho_id: str):
    return PASTA_NICHOS / f"{slugify(nicho_id)}.json"


def _completar(nicho: dict) -> dict:
    """Só os campos atuais; nichos da versão antiga continuam funcionando."""
    completo = dict(NICHO_VAZIO)
    completo.update({k: v for k, v in nicho.items() if k in NICHO_VAZIO})
    completo["termo_busca"] = completo["termo_busca"] or completo["nome"]
    return completo


def listar_nichos() -> list:
    nichos = []
    for arquivo in sorted(PASTA_NICHOS.glob("*.json")):
        try:
            nichos.append(_completar(json.loads(arquivo.read_text(encoding="utf-8"))))
        except ValueError:
            continue
    return nichos


def carregar_nicho(nicho_id: str) -> dict:
    if not nicho_id:
        return None
    arquivo = _caminho(nicho_id)
    if not arquivo.exists():
        return None
    return _completar(json.loads(arquivo.read_text(encoding="utf-8")))


def salvar_nicho(nicho: dict) -> dict:
    if not (nicho.get("nome") or "").strip():
        raise ValueError("O nicho precisa de um nome.")
    nicho = _completar(nicho)
    nicho["id"] = slugify(nicho.get("id") or nicho["nome"])
    _caminho(nicho["id"]).write_text(json.dumps(nicho, ensure_ascii=False, indent=2), encoding="utf-8")
    return nicho


def excluir_nicho(nicho_id: str):
    arquivo = _caminho(nicho_id)
    if arquivo.exists():
        arquivo.unlink()


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
