"""
Leva os leads e o histórico do banco antigo (dados/prospeccao.db, no seu PC) para o Supabase.

Rode uma vez, com o .env já preenchido:   python migrar_para_supabase.py
Pode rodar de novo sem medo: lead que já está no Supabase não é copiado outra vez.
Outro arquivo:   python migrar_para_supabase.py caminho/do/arquivo.db
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from core import config, db
from core.supabase import cliente

ARQUIVO_PADRAO = config.RAIZ / "dados" / "prospeccao.db"

# Funil da versão antiga -> (etapa, estado) da nova
STATUS_ANTIGO = {
    "novo": ("lead_novo", "ativo"),
    "site_gerado": ("lead_novo", "ativo"),
    "enviado": ("em_contato", "ativo"),
    "respondeu": ("interessado", "ativo"),
    "fechado": ("fechado", "ativo"),
    "perdido": ("lead_novo", "arquivado"),
    "descartado": ("lead_novo", "ativo"),   # antes, quem tinha site era descartado; agora é analisado de novo
}
CAMPOS_JSON = {"horario", "fotos", "redes", "sinais", "avaliacoes_lidas", "nota_detalhe", "problemas_maps",
               "oportunidades", "analise_ia", "cores"}
CAMPOS_DATA_HORA = {"criado_em", "analisado_em"}


def _data_hora(texto):
    """Datas do SQLite vinham sem fuso: assume o fuso deste computador."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(str(texto)).astimezone().isoformat(timespec="seconds")
    except ValueError:
        return None


def converter_lead(linha: dict) -> dict:
    lead = {}
    for chave, valor in linha.items():
        if chave not in db.COLUNAS or valor is None:
            continue
        if chave in CAMPOS_JSON and isinstance(valor, str):
            try:
                valor = json.loads(valor)
            except ValueError:
                continue
        elif chave in CAMPOS_DATA_HORA:
            valor = _data_hora(valor)
        elif chave == "data_proximo_passo":
            valor = str(valor)[:10] or None
        lead[chave] = valor
    if not linha.get("etapa"):   # banco da primeira versão (só tinha "status")
        lead["etapa"], lead["estado"] = STATUS_ANTIGO.get(linha.get("status") or "novo", ("lead_novo", "ativo"))
    if lead.get("classe") not in (None, "potencial", "talvez", "pouco"):
        lead.pop("classe")
    return lead


def migrar(arquivo: Path):
    if not arquivo.exists():
        print(f"Não achei o banco antigo em {arquivo}. Nada para levar.")
        return
    con = sqlite3.connect(arquivo)
    con.row_factory = sqlite3.Row
    linhas = [dict(l) for l in con.execute("SELECT * FROM leads")]
    tem_contatos = con.execute("SELECT name FROM sqlite_master WHERE name = 'contatos'").fetchone()
    contatos = [dict(l) for l in con.execute("SELECT * FROM contatos")] if tem_contatos else []
    con.close()

    ja_no_supabase = {l["id"] for l in db._todas_as_paginas("leads", colunas="id")}
    novos = [converter_lead(l) for l in linhas if l["id"] not in ja_no_supabase]
    print(f"{len(linhas)} leads no banco antigo; {len(linhas) - len(novos)} já estavam no Supabase; "
          f"{len(novos)} para levar.")

    for inicio in range(0, len(novos), 200):
        lote = novos[inicio:inicio + 200]
        # Todas as linhas de um lote precisam ter as mesmas colunas
        colunas = set().union(*(l.keys() for l in lote))
        cliente().inserir("leads", [{c: l.get(c) for c in colunas} for l in lote],
                          ignorar_duplicados=True, devolver=False)
        print(f"  {min(inicio + 200, len(novos))}/{len(novos)} leads enviados")

    ids_novos = {l["id"] for l in novos}
    historico = [{"lead_id": c["lead_id"], "data": _data_hora(c["data"]) or db.agora(), "tipo": c["tipo"],
                  "anotacao": c.get("anotacao") or ""}
                 for c in contatos if c["lead_id"] in ids_novos]
    for inicio in range(0, len(historico), 500):
        cliente().inserir("contatos", historico[inicio:inicio + 500], devolver=False)
    print(f"  {len(historico)} contatos do histórico enviados")
    print("Pronto. Abra o painel e, em Configurações, use \"Reanalisar todos\" para atualizar as notas.")


if __name__ == "__main__":
    migrar(Path(sys.argv[1]) if len(sys.argv) > 1 else ARQUIVO_PADRAO)
