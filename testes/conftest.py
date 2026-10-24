"""
Configuração comum dos testes: cada teste que usa o banco ganha um banco novo e vazio.
Rode todos com:  python -m pytest testes
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config, db  # noqa: E402


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ARQUIVO_BANCO", tmp_path / "teste.db")
    db.iniciar()
    return db


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
