"""
Configuração comum dos testes. Os testes não usam o Supabase de verdade: o fixture `banco`
troca o cliente por um banco de mentira, na memória, que entende os mesmos filtros.
Rode todos com:  python -m pytest testes
"""
import copy
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db, supabase  # noqa: E402

PADROES = {
    "leads": {"etapa": "lead_novo", "estado": "ativo", "redes": {}},
    "pedidos": {"status": "pendente", "parar": False, "log": [], "parametros": {}, "resultado": None},
    "contatos": {"anotacao": ""},
}
CHAVES = {"regioes": "nome", "ajustes": "chave"}


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _confere(valor, filtro: str) -> bool:
    operador, _, alvo = filtro.partition(".")
    if operador == "eq":
        return str(valor) == alvo if not isinstance(valor, bool) else str(valor).lower() == alvo
    if operador == "in":
        itens = [i.strip().strip('"') for i in alvo.strip("()").split(",")]
        return str(valor) in itens
    if operador == "ilike":
        return valor is not None and str(valor).lower() == alvo.replace("*", "").lower()
    raise NotImplementedError(filtro)


class SupabaseFalso:
    """Faz o papel do Supabase nos testes (só o que o bot usa)."""

    def __init__(self):
        self.tabelas = {}
        self.proximo_id = 1

    def _tabela(self, nome):
        return self.tabelas.setdefault(nome, [])

    def _filtrar(self, tabela, filtros):
        return [l for l in self._tabela(tabela) if all(_confere(l.get(c), f) for c, f in (filtros or {}).items())]

    def selecionar(self, tabela, filtros=None, colunas="*", ordem=None, limite=None, inicio=None):
        linhas = self._filtrar(tabela, filtros)
        for parte in reversed((ordem or "").split(",")):
            if not parte:
                continue
            coluna, *mods = parte.split(".")
            decrescente = "desc" in mods
            linhas.sort(key=lambda l: (l.get(coluna) is None, l.get(coluna) or 0), reverse=False)
            if decrescente:
                com = [l for l in linhas if l.get(coluna) is not None][::-1]
                linhas = com + [l for l in linhas if l.get(coluna) is None]
        linhas = linhas[inicio or 0:]
        if limite is not None:
            linhas = linhas[:limite]
        if colunas != "*":
            linhas = [{c: l.get(c) for c in colunas.split(",")} for l in linhas]
        return copy.deepcopy(linhas)

    def inserir(self, tabela, dados, ignorar_duplicados=False, juntar_duplicados=False, devolver=True):
        chave = CHAVES.get(tabela, "id")
        novos = []
        for item in dados if isinstance(dados, list) else [dados]:
            linha = {**copy.deepcopy(PADROES.get(tabela, {})), **copy.deepcopy(item)}
            if chave == "id" and "id" not in linha:
                linha["id"] = self.proximo_id
                self.proximo_id += 1
            linha.setdefault("criado_em", _agora())
            if tabela == "contatos":
                linha.setdefault("data", _agora())
            existente = next((l for l in self._tabela(tabela) if l[chave] == linha[chave]), None)
            if existente:
                if juntar_duplicados:
                    existente.update(item)
                    novos.append(existente)
                elif not ignorar_duplicados:
                    raise supabase.ErroSupabase("409 duplicado")
                continue
            self._tabela(tabela).append(linha)
            novos.append(linha)
        return copy.deepcopy(novos) if devolver else []

    def atualizar(self, tabela, filtros, dados, devolver=False):
        linhas = self._filtrar(tabela, filtros)
        for l in linhas:
            l.update(copy.deepcopy(dados))
        return copy.deepcopy(linhas) if devolver else []

    def apagar(self, tabela, filtros):
        apagar = self._filtrar(tabela, filtros)
        self.tabelas[tabela] = [l for l in self._tabela(tabela) if l not in apagar]

    def rpc(self, funcao, argumentos):
        assert funcao == "adicionar_log"
        for l in self._filtrar("pedidos", {"id": f"eq.{argumentos['pedido']}"}):
            l["log"] = l["log"] + list(argumentos["linhas"])


@pytest.fixture
def banco():
    falso = SupabaseFalso()
    falso.inserir("nichos", [
        {"id": "barbearias", "nome": "Barbearias", "termo_busca": "Barbearia", "icone": "✂", "agenda": True,
         "pedido_online": False},
    ])
    supabase.usar(falso)
    yield db
    supabase.usar(None)


def lead_exemplo(**mudancas) -> dict:
    """Uma barbearia movimentada, só com Instagram e sem agendamento online."""
    lead = {
        "id": "0x1:0x2", "nicho": "barbearias", "regiao": "Taguatinga, DF", "nome": "Barbearia do Zé",
        "categoria": "Barbearia", "telefone": "(61) 99876-5432", "whatsapp": "5561998765432",
        "site": "https://www.instagram.com/barbeariaze/", "situacao_site": "so_rede_social",
        "redes": {"instagram": "https://www.instagram.com/barbeariaze/"},
        "instagram": "https://www.instagram.com/barbeariaze/", "instagram_posts": 250, "instagram_seguidores": 4800,
        "nota": 4.8, "avaliacoes": 180, "horario": ["Segunda-feira, 09:00 a 19:00"], "fotos": ["f1", "f2"],
        "descricao": "", "sinais": {"fechado": None, "tem_agendar": False, "tem_pedido": False, "total_fotos": 2},
        "avaliacoes_lidas": [
            {"estrelas": 1, "texto": "Mandei mensagem no WhatsApp e ninguém respondeu", "respondida": False,
             "quando": "há 2 semanas", "dias": 14},
            *[{"estrelas": 5, "texto": "Ótimo corte", "respondida": False, "quando": "há 1 mês", "dias": 30}] * 5,
        ],
    }
    lead.update(mudancas)
    return lead
