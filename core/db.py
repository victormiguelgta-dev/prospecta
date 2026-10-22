"""
Banco de dados dos leads (SQLite: um arquivo só, sem instalar nada).

Cada negócio encontrado no Maps vira uma linha na tabela `leads`.
A chave é o ID do local no Google Maps, por isso o mesmo negócio
nunca é salvo (nem recebe site) duas vezes, mesmo aparecendo em buscas diferentes.
"""
import json
import sqlite3
from datetime import datetime

from .config import ARQUIVO_BANCO

# Etapas do funil. O painel usa essa mesma lista.
STATUS = ["novo", "site_gerado", "enviado", "respondeu", "fechado", "perdido", "descartado"]

# Campos guardados como JSON (listas/dicionários) dentro de colunas de texto
CAMPOS_JSON = {"horario", "fotos", "textos", "cores", "depoimentos"}

COLUNAS = [
    "id", "nicho", "regiao", "nome", "categoria", "endereco", "telefone", "whatsapp",
    "email", "site", "situacao_site", "instagram", "nota", "avaliacoes", "horario",
    "fotos", "descricao", "depoimentos", "logo_url", "lat", "lng", "maps_url", "status", "slug", "textos", "cores",
    "observacoes", "criado_em", "atualizado_em", "site_gerado_em", "enviado_em",
]

SQL_CRIAR = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,          -- ID do local no Google Maps
    nicho TEXT,
    regiao TEXT,
    nome TEXT NOT NULL,
    categoria TEXT,
    endereco TEXT,
    telefone TEXT,
    whatsapp TEXT,                -- número pronto pro wa.me (ex.: 5561999998888)
    email TEXT,
    site TEXT,
    situacao_site TEXT,           -- sem_site | so_rede_social | site_fraco | fora_do_ar | site_proprio
    instagram TEXT,
    nota REAL,
    avaliacoes INTEGER,
    horario TEXT,                 -- JSON
    fotos TEXT,                   -- JSON (lista de URLs, até 8)
    descricao TEXT,               -- descrição escrita pelo dono no Maps
    depoimentos TEXT,             -- JSON: avaliações reais com texto [{autor, estrelas, texto}]
    logo_url TEXT,
    lat REAL,
    lng REAL,
    maps_url TEXT,
    status TEXT DEFAULT 'novo',
    slug TEXT,                    -- nome da pasta do site demo
    textos TEXT,                  -- JSON com os textos gerados
    cores TEXT,                   -- JSON com a paleta usada
    observacoes TEXT,
    criado_em TEXT,
    atualizado_em TEXT,
    site_gerado_em TEXT,
    enviado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_nicho ON leads(nicho);
"""


def conectar():
    con = sqlite3.connect(ARQUIVO_BANCO)
    con.row_factory = sqlite3.Row
    return con


# Colunas que entraram depois da primeira versão. Bancos antigos ganham
# essas colunas automaticamente, sem perder os leads que já existem.
COLUNAS_NOVAS = {"descricao": "TEXT", "depoimentos": "TEXT"}


def iniciar():
    with conectar() as con:
        con.executescript(SQL_CRIAR)
        existentes = {linha["name"] for linha in con.execute("PRAGMA table_info(leads)")}
        for coluna, tipo in COLUNAS_NOVAS.items():
            if coluna not in existentes:
                con.execute(f"ALTER TABLE leads ADD COLUMN {coluna} {tipo}")


def _agora():
    return datetime.now().isoformat(timespec="seconds")


def _para_banco(dados: dict) -> dict:
    """Converte listas/dicionários em texto JSON antes de salvar."""
    saida = {}
    for chave, valor in dados.items():
        if chave not in COLUNAS:
            continue
        if chave in CAMPOS_JSON and valor is not None and not isinstance(valor, str):
            valor = json.dumps(valor, ensure_ascii=False)
        saida[chave] = valor
    return saida


def _do_banco(linha) -> dict:
    """Converte uma linha do banco de volta em dicionário Python."""
    if linha is None:
        return None
    lead = dict(linha)
    for chave in CAMPOS_JSON:
        if lead.get(chave):
            try:
                lead[chave] = json.loads(lead[chave])
            except (TypeError, ValueError):
                pass
    return lead


def existe(lead_id: str) -> bool:
    with conectar() as con:
        return con.execute("SELECT 1 FROM leads WHERE id = ?", (lead_id,)).fetchone() is not None


def salvar(lead: dict):
    """Insere um lead novo. Se o ID já existir, não faz nada (não sobrescreve status)."""
    dados = _para_banco(lead)
    dados.setdefault("criado_em", _agora())
    dados["atualizado_em"] = _agora()
    colunas = ", ".join(dados)
    marcadores = ", ".join("?" for _ in dados)
    with conectar() as con:
        con.execute(
            f"INSERT OR IGNORE INTO leads ({colunas}) VALUES ({marcadores})",
            list(dados.values()),
        )


def atualizar(lead_id: str, campos: dict):
    dados = _para_banco(campos)
    dados.pop("id", None)
    if not dados:
        return
    dados["atualizado_em"] = _agora()
    atribuicoes = ", ".join(f"{c} = ?" for c in dados)
    with conectar() as con:
        con.execute(f"UPDATE leads SET {atribuicoes} WHERE id = ?", [*dados.values(), lead_id])


def buscar(lead_id: str) -> dict:
    with conectar() as con:
        return _do_banco(con.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone())


def listar(nicho=None, status=None, situacao=None, texto=None) -> list:
    sql = "SELECT * FROM leads WHERE 1=1"
    params = []
    if nicho:
        sql += " AND nicho = ?"
        params.append(nicho)
    if status:
        sql += " AND status = ?"
        params.append(status)
    if situacao == "leads":
        # "leads" = todo mundo que NÃO tem site próprio funcionando
        sql += " AND situacao_site != 'site_proprio'"
    elif situacao:
        sql += " AND situacao_site = ?"
        params.append(situacao)
    if texto:
        sql += " AND (nome LIKE ? OR regiao LIKE ? OR categoria LIKE ?)"
        params += [f"%{texto}%"] * 3
    sql += " ORDER BY criado_em DESC"
    with conectar() as con:
        return [_do_banco(l) for l in con.execute(sql, params).fetchall()]


def excluir(lead_id: str):
    with conectar() as con:
        con.execute("DELETE FROM leads WHERE id = ?", (lead_id,))


def resumo() -> dict:
    """Contagem por status, para os números do topo do painel."""
    with conectar() as con:
        linhas = con.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
        total = con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        sem_site = con.execute(
            "SELECT COUNT(*) FROM leads WHERE situacao_site != 'site_proprio'"
        ).fetchone()[0]
    contagem = {s: 0 for s in STATUS}
    contagem.update({l["status"]: l["n"] for l in linhas})
    return {"total": total, "potenciais": sem_site, "por_status": contagem}
