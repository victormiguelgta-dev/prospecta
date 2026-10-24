"""
Banco de dados dos leads (SQLite: um arquivo só, sem instalar nada).

Cada negócio encontrado no Maps vira uma linha na tabela `leads`.
A chave é o ID do local no Google Maps, por isso o mesmo negócio
nunca é salvo duas vezes, mesmo aparecendo em buscas diferentes.

O histórico de contatos (ligações, mensagens, anotações) fica na tabela
`contatos`, uma linha por contato, ligada ao lead pelo id.
"""
import json
import sqlite3
from datetime import date, datetime

from . import config

# Etapas do quadro (CRM), na ordem das colunas
ETAPAS = ["lead_novo", "em_contato", "interessado", "fechado"]
NOMES_ETAPAS = {
    "lead_novo": "Lead novo",
    "em_contato": "Em contato",
    "interessado": "Cliente interessado",
    "fechado": "Fechado",
}

# Fora do quadro: congelado (parou de responder), arquivado (sem interesse agora)
# e descartado (o próprio bot tirou: fechado, franquia, sem telefone).
ESTADOS = ["ativo", "congelado", "arquivado", "descartado"]

CLASSES = ["potencial", "talvez", "pouco"]
NOMES_CLASSES = {"potencial": "Potencial", "talvez": "Talvez", "pouco": "Pouco potencial"}

TIPOS_CONTATO = ["ligacao", "whatsapp", "visita", "email", "anotacao"]

# Campos guardados como JSON (listas/dicionários) dentro de colunas de texto
CAMPOS_JSON = {
    "horario", "fotos", "depoimentos", "redes", "sinais", "avaliacoes_lidas", "nota_detalhe",
    "problemas_maps", "oportunidades", "analise_ia",
}

COLUNAS = {
    # Identidade e contato (coleta)
    "id": "TEXT PRIMARY KEY",       # ID do local no Google Maps
    "nicho": "TEXT",
    "regiao": "TEXT",
    "nome": "TEXT NOT NULL",
    "categoria": "TEXT",
    "endereco": "TEXT",
    "telefone": "TEXT",
    "whatsapp": "TEXT",             # número pronto pro wa.me (ex.: 5561999998888)
    "email": "TEXT",
    "site": "TEXT",
    "situacao_site": "TEXT",        # sem_site | so_rede_social | site_fraco | fora_do_ar | site_proprio
    "instagram": "TEXT",
    "redes": "TEXT",                # JSON {instagram, facebook, tiktok, ...: url}
    "redes_origem": "TEXT",         # onde as redes foram achadas: maps, site, busca na web
    "instagram_seguidores": "INTEGER",
    "instagram_posts": "INTEGER",
    "logo_url": "TEXT",
    "maps_url": "TEXT",
    "lat": "REAL",
    "lng": "REAL",
    # Dados do Maps (coleta)
    "nota": "REAL",
    "avaliacoes": "INTEGER",
    "horario": "TEXT",              # JSON
    "fotos": "TEXT",                # JSON (lista de URLs)
    "descricao": "TEXT",            # descrição escrita pelo dono no Maps
    "depoimentos": "TEXT",          # JSON (versão antiga; não é mais coletado)
    "avaliacoes_lidas": "TEXT",     # JSON [{estrelas, texto, respondida, quando}], só para classificar
    "sinais": "TEXT",               # JSON com o que o bot viu na ficha (fechado, agendar, pedido...)
    # Análise (regras + IA)
    "nota_potencial": "INTEGER",
    "classe": "TEXT",               # potencial | talvez | pouco
    "nota_detalhe": "TEXT",         # JSON [{sinal, pontos}]
    "saude_maps": "INTEGER",
    "problemas_maps": "TEXT",       # JSON [texto]
    "oportunidades": "TEXT",        # JSON [{servico, forca, motivo, evidencias}]
    "servico_principal": "TEXT",    # maps | site | desenvolvimento
    "analise_ia": "TEXT",           # JSON {resumo, dores, o_que_vender, angulo}
    "analisado_em": "TEXT",
    # CRM
    "etapa": "TEXT DEFAULT 'lead_novo'",
    "estado": "TEXT DEFAULT 'ativo'",
    "motivo": "TEXT",               # por que foi arquivado, congelado ou descartado
    "proximo_passo": "TEXT",
    "data_proximo_passo": "TEXT",   # AAAA-MM-DD (ou com hora)
    "observacoes": "TEXT",
    # Controle
    "status": "TEXT",               # versão antiga do funil (mantido só para converter)
    "criado_em": "TEXT",
    "atualizado_em": "TEXT",
    "etapa_em": "TEXT",             # quando entrou na etapa atual
}

SQL_CONTATOS = """
CREATE TABLE IF NOT EXISTS contatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    data TEXT NOT NULL,
    tipo TEXT NOT NULL,
    anotacao TEXT
);
CREATE INDEX IF NOT EXISTS idx_contatos_lead ON contatos(lead_id);
"""

# Funil da versão antiga -> (etapa, estado) da nova
_STATUS_ANTIGO = {
    "novo": ("lead_novo", "ativo"),
    "site_gerado": ("lead_novo", "ativo"),
    "enviado": ("em_contato", "ativo"),
    "respondeu": ("interessado", "ativo"),
    "fechado": ("fechado", "ativo"),
    "perdido": ("lead_novo", "arquivado"),
}


def conectar():
    con = sqlite3.connect(config.ARQUIVO_BANCO)
    con.row_factory = sqlite3.Row
    return con


def iniciar():
    """Cria as tabelas e, num banco antigo, acrescenta as colunas novas e converte o funil."""
    with conectar() as con:
        definicoes = ", ".join(f"{nome} {tipo}" for nome, tipo in COLUNAS.items())
        con.execute(f"CREATE TABLE IF NOT EXISTS leads ({definicoes})")
        existentes = {linha["name"] for linha in con.execute("PRAGMA table_info(leads)")}
        for nome, tipo in COLUNAS.items():
            if nome not in existentes:
                con.execute(f"ALTER TABLE leads ADD COLUMN {nome} {tipo.replace(' PRIMARY KEY', '')}")
        con.executescript(SQL_CONTATOS)
        con.execute("CREATE INDEX IF NOT EXISTS idx_leads_etapa ON leads(etapa, estado)")
        _converter_funil_antigo(con)


def _converter_funil_antigo(con):
    """Leads da versão antiga ganham etapa e estado a partir do status que tinham."""
    for linha in con.execute("SELECT id, status, situacao_site FROM leads WHERE etapa_em IS NULL").fetchall():
        status = linha["status"] or "novo"
        if status == "descartado":
            # Antes, quem tinha site era descartado. Agora quem tem site pode comprar
            # desenvolvimento, então volta para o quadro e é classificado de novo.
            etapa, estado = ("lead_novo", "ativo")
        else:
            etapa, estado = _STATUS_ANTIGO.get(status, ("lead_novo", "ativo"))
        con.execute("UPDATE leads SET etapa = ?, estado = ?, etapa_em = ? WHERE id = ?",
                    (etapa, estado, _agora(), linha["id"]))


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
    """Insere um lead novo. Se o ID já existir, não faz nada (não sobrescreve o CRM)."""
    dados = _para_banco(lead)
    dados.setdefault("criado_em", _agora())
    dados.setdefault("etapa", "lead_novo")
    dados.setdefault("estado", "ativo")
    dados["etapa_em"] = dados["atualizado_em"] = _agora()
    colunas = ", ".join(dados)
    marcadores = ", ".join("?" for _ in dados)
    with conectar() as con:
        con.execute(f"INSERT OR IGNORE INTO leads ({colunas}) VALUES ({marcadores})", list(dados.values()))


def atualizar(lead_id: str, campos: dict):
    dados = _para_banco(campos)
    dados.pop("id", None)
    if not dados:
        return
    if "etapa" in dados:
        dados["etapa_em"] = _agora()
    dados["atualizado_em"] = _agora()
    atribuicoes = ", ".join(f"{c} = ?" for c in dados)
    with conectar() as con:
        con.execute(f"UPDATE leads SET {atribuicoes} WHERE id = ?", [*dados.values(), lead_id])


def buscar(lead_id: str) -> dict:
    with conectar() as con:
        return _do_banco(con.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone())


def listar(nicho=None, etapa=None, estado=None, classe=None, servico=None, texto=None) -> list:
    """Lista os leads, do maior potencial para o menor."""
    sql = "SELECT * FROM leads WHERE 1=1"
    params = []
    for coluna, valor in (("nicho", nicho), ("etapa", etapa), ("estado", estado), ("classe", classe)):
        if valor:
            sql += f" AND {coluna} = ?"
            params.append(valor)
    if servico:
        # O serviço aparece dentro da lista de oportunidades (JSON)
        sql += " AND oportunidades LIKE ?"
        params.append(f'%"servico": "{servico}"%')
    if texto:
        sql += " AND (nome LIKE ? OR regiao LIKE ? OR categoria LIKE ? OR endereco LIKE ?)"
        params += [f"%{texto}%"] * 4
    sql += " ORDER BY COALESCE(nota_potencial, -1) DESC, criado_em DESC"
    with conectar() as con:
        return [_do_banco(l) for l in con.execute(sql, params).fetchall()]


def ligar_hoje(dia: str = None) -> list:
    """Leads ativos ou congelados com próximo passo marcado para hoje ou atrasado."""
    dia = dia or date.today().isoformat()
    with conectar() as con:
        linhas = con.execute(
            "SELECT * FROM leads WHERE estado IN ('ativo', 'congelado') AND data_proximo_passo IS NOT NULL "
            "AND data_proximo_passo != '' AND substr(data_proximo_passo, 1, 10) <= ? "
            "ORDER BY data_proximo_passo", (dia,)).fetchall()
    return [_do_banco(l) for l in linhas]


def nome_em_varias_regioes(nome: str, regiao: str) -> int:
    """Em quantas regiões diferentes já existe um negócio com este nome (para achar redes e franquias)."""
    with conectar() as con:
        linhas = con.execute("SELECT DISTINCT regiao FROM leads WHERE lower(nome) = lower(?)", (nome,)).fetchall()
    regioes = {l["regiao"] for l in linhas} | {regiao}
    return len(regioes)


def excluir(lead_id: str):
    with conectar() as con:
        con.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        con.execute("DELETE FROM contatos WHERE lead_id = ?", (lead_id,))


def resumo() -> dict:
    """Números do topo do painel."""
    with conectar() as con:
        por_etapa = {l["etapa"]: l["n"] for l in con.execute(
            "SELECT etapa, COUNT(*) AS n FROM leads WHERE estado = 'ativo' GROUP BY etapa")}
        por_classe = {l["classe"]: l["n"] for l in con.execute(
            "SELECT classe, COUNT(*) AS n FROM leads WHERE estado = 'ativo' GROUP BY classe")}
        por_estado = {l["estado"]: l["n"] for l in con.execute(
            "SELECT estado, COUNT(*) AS n FROM leads GROUP BY estado")}
    return {
        "por_etapa": {e: por_etapa.get(e, 0) for e in ETAPAS},
        "por_classe": {c: por_classe.get(c, 0) for c in CLASSES},
        "por_estado": {e: por_estado.get(e, 0) for e in ESTADOS},
        "ligar_hoje": len(ligar_hoje()),
    }


# ------------------------------- Contatos -------------------------------
def adicionar_contato(lead_id: str, tipo: str, anotacao: str = "", data: str = None) -> dict:
    data = data or _agora()
    with conectar() as con:
        cursor = con.execute("INSERT INTO contatos (lead_id, data, tipo, anotacao) VALUES (?, ?, ?, ?)",
                             (lead_id, data, tipo, anotacao))
        contato_id = cursor.lastrowid
        con.execute("UPDATE leads SET atualizado_em = ? WHERE id = ?", (_agora(), lead_id))
    return {"id": contato_id, "lead_id": lead_id, "data": data, "tipo": tipo, "anotacao": anotacao}


def listar_contatos(lead_id: str) -> list:
    with conectar() as con:
        return [dict(l) for l in con.execute(
            "SELECT * FROM contatos WHERE lead_id = ? ORDER BY data DESC, id DESC", (lead_id,)).fetchall()]


def excluir_contato(contato_id: int):
    with conectar() as con:
        con.execute("DELETE FROM contatos WHERE id = ?", (contato_id,))
