"""
Banco de dados dos leads, agora no Supabase (Postgres na nuvem).

As tabelas são criadas pelo arquivo supabase/0001_inicial.sql. Aqui ficam as
funções que o bot e a análise usam; o painel (React) conversa direto com o Supabase.

A chave de cada lead é o ID do local no Google Maps, por isso o mesmo negócio
nunca é salvo duas vezes, mesmo aparecendo em buscas diferentes.
"""
import json
import socket
from datetime import datetime, timezone

from . import config
from .supabase import cliente

ETAPAS = ["lead_novo", "em_contato", "interessado", "fechado"]
NOMES_ETAPAS = {
    "lead_novo": "Lead novo",
    "em_contato": "Em contato",
    "interessado": "Cliente interessado",
    "fechado": "Fechado",
}
ESTADOS = ["ativo", "congelado", "arquivado", "descartado"]
CLASSES = ["potencial", "talvez", "pouco"]
NOMES_CLASSES = {"potencial": "Potencial", "talvez": "Talvez", "pouco": "Pouco potencial"}
TIPOS_CONTATO = ["ligacao", "whatsapp", "visita", "email", "anotacao"]

# Colunas da tabela leads (o que não estiver aqui não é enviado ao banco)
COLUNAS = {
    "id", "nicho", "regiao", "nome", "categoria", "endereco", "telefone", "whatsapp", "email", "site",
    "situacao_site", "instagram", "redes", "redes_origem", "instagram_seguidores", "instagram_posts",
    "logo_url", "cores", "maps_url", "lat", "lng", "nota", "avaliacoes", "horario", "fotos", "descricao",
    "avaliacoes_lidas", "sinais", "nota_potencial", "classe", "nota_detalhe", "saude_maps", "problemas_maps",
    "oportunidades", "servico_principal", "analise_ia", "analisado_em", "etapa", "estado", "motivo",
    "proximo_passo", "data_proximo_passo", "observacoes", "criado_em",
}


def agora() -> str:
    """Data e hora com fuso, para o banco gravar a hora certa."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def iniciar():
    """As tabelas já existem no Supabase; nada a fazer (mantido para compatibilidade)."""


def _para_banco(dados: dict) -> dict:
    saida = {}
    for chave, valor in dados.items():
        if chave not in COLUNAS:
            continue
        if valor == "" and chave in ("data_proximo_passo", "analisado_em"):
            valor = None     # data vazia vira "sem data"
        saida[chave] = valor
    return saida


def existe(lead_id: str) -> bool:
    return bool(cliente().selecionar("leads", {"id": f"eq.{lead_id}"}, colunas="id"))


def salvar(lead: dict):
    """Insere um lead novo. Se o ID já existir, não faz nada (não sobrescreve o CRM)."""
    dados = _para_banco(lead)
    dados.setdefault("etapa", "lead_novo")
    dados.setdefault("estado", "ativo")
    cliente().inserir("leads", dados, ignorar_duplicados=True, devolver=False)


def atualizar(lead_id: str, campos: dict):
    dados = _para_banco(campos)
    dados.pop("id", None)
    if dados:
        cliente().atualizar("leads", {"id": f"eq.{lead_id}"}, dados)


def buscar(lead_id: str) -> dict:
    linhas = cliente().selecionar("leads", {"id": f"eq.{lead_id}"})
    return linhas[0] if linhas else None


def listar(estado=None, ids=None) -> list:
    """Leads do maior potencial para o menor (o bot usa para reanalisar)."""
    filtros = {}
    if estado:
        filtros["estado"] = f"eq.{estado}"
    if ids:
        filtros["id"] = "in.(" + ",".join(f'"{i}"' for i in ids) + ")"
    return _todas_as_paginas("leads", filtros, ordem="nota_potencial.desc.nullslast,criado_em.desc")


def _todas_as_paginas(tabela, filtros=None, ordem=None, colunas="*", tamanho=1000) -> list:
    """O Supabase devolve no máximo 1000 linhas por vez: busca de 1000 em 1000."""
    linhas, inicio = [], 0
    while True:
        pagina = cliente().selecionar(tabela, filtros, colunas=colunas, ordem=ordem, limite=tamanho, inicio=inicio)
        linhas += pagina
        if len(pagina) < tamanho:
            return linhas
        inicio += tamanho


def nome_em_varias_regioes(nome: str, regiao: str) -> int:
    """Em quantas regiões diferentes já existe um negócio com este nome (para achar redes e franquias)."""
    nome_seguro = (nome or "").replace("*", "").replace(",", "").replace("(", "").replace(")", "")
    linhas = cliente().selecionar("leads", {"nome": f"ilike.{nome_seguro}"}, colunas="regiao")
    return len({l["regiao"] for l in linhas} | {regiao})


def adicionar_contato(lead_id: str, tipo: str, anotacao: str = "") -> dict:
    linhas = cliente().inserir("contatos", {"lead_id": lead_id, "tipo": tipo, "anotacao": anotacao})
    return linhas[0] if linhas else {}


def listar_contatos(lead_id: str) -> list:
    return cliente().selecionar("contatos", {"lead_id": f"eq.{lead_id}"}, ordem="data.desc,id.desc")


# ------------------------------- Nichos --------------------------------
def carregar_nicho(nicho_id: str) -> dict:
    if not nicho_id:
        return None
    linhas = cliente().selecionar("nichos", {"id": f"eq.{nicho_id}"})
    return linhas[0] if linhas else None


# ----------------------- Pedidos (fila do painel) -----------------------
def pegar_proximo_pedido() -> dict:
    """
    Pega o pedido pendente mais antigo e marca como "rodando".
    A marcação só vale se ele ainda estiver pendente, então dois PCs nunca pegam o mesmo pedido.
    """
    pendentes = cliente().selecionar("pedidos", {"status": "eq.pendente"}, ordem="criado_em.asc", limite=1)
    if not pendentes:
        return None
    marcados = cliente().atualizar("pedidos", {"id": f"eq.{pendentes[0]['id']}", "status": "eq.pendente"},
                                   {"status": "rodando", "iniciado_em": agora()}, devolver=True)
    return marcados[0] if marcados else None


def escrever_no_pedido(pedido_id: int, linhas: list):
    if linhas:
        cliente().rpc("adicionar_log", {"pedido": pedido_id, "linhas": linhas})


def pediu_para_parar(pedido_id: int) -> bool:
    linhas = cliente().selecionar("pedidos", {"id": f"eq.{pedido_id}"}, colunas="parar")
    return bool(linhas and linhas[0]["parar"])


def concluir_pedido(pedido_id: int, status: str, resultado: dict = None):
    cliente().atualizar("pedidos", {"id": f"eq.{pedido_id}"},
                        {"status": status, "resultado": resultado, "concluido_em": agora()})


def avisar_que_estou_ligado(ia: bool, modelo_ia: str):
    """O painel mostra "PC ligado" enquanto este sinal for recente."""
    cliente().inserir("trabalhador", {"id": socket.gethostname(), "visto_em": agora(), "ia": ia,
                                      "modelo_ia": modelo_ia}, juntar_duplicados=True, devolver=False)


# ------------------------------- Backup --------------------------------
def fazer_backup(manter: int = 30) -> str:
    """Salva todos os leads e o histórico num arquivo JSON neste computador. Guarda os últimos `manter`."""
    dados = {
        "feito_em": agora(),
        "leads": _todas_as_paginas("leads", ordem="criado_em.asc"),
        "contatos": _todas_as_paginas("contatos", ordem="id.asc"),
        "nichos": _todas_as_paginas("nichos", ordem="id.asc"),
        "regioes": _todas_as_paginas("regioes", ordem="ordem.asc"),
    }
    arquivo = config.PASTA_BACKUPS / f"backup-{datetime.now():%Y-%m-%d_%H%M%S}.json"
    arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    for antigo in sorted(config.PASTA_BACKUPS.glob("backup-*.json"))[:-manter]:
        antigo.unlink()
    return str(arquivo)
