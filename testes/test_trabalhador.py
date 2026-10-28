"""
Testes do lado do PC: análise, fila de pedidos, trabalhador, backup e migração do banco antigo.
Tudo roda com o Supabase de mentira do conftest e a IA simulada (nenhuma chamada de verdade é feita).
"""
import json
import sqlite3

import pytest
from conftest import lead_exemplo

import migrar_para_supabase as migracao
import trabalhador
from core import analise, config, db, ia
from core.scraper import auditar_html, sinais_da_ficha

ID = "0x1:0x2"


@pytest.fixture
def sem_ia(monkeypatch):
    monkeypatch.setattr(ia, "ia_disponivel", lambda: False)
    monkeypatch.setattr(analise, "cores_da_logo", lambda url: {})


def _pedido(banco, tipo, parametros):
    return db.cliente().inserir("pedidos", {"tipo": tipo, "parametros": parametros})[0]


def test_lead_novo_e_classificado(banco, sem_ia):
    banco.salvar(lead_exemplo())
    banco.salvar(lead_exemplo(nome="Outro nome"))   # mesmo ID: não sobrescreve
    lead = analise.analisar(ID, usar_ia=False)
    assert lead["nome"] == "Barbearia do Zé"
    assert lead["etapa"] == "lead_novo" and lead["estado"] == "ativo"
    assert lead["classe"] == "potencial"
    assert {o["servico"] for o in lead["oportunidades"]} >= {"site", "desenvolvimento"}
    assert lead["analisado_em"]


def test_analise_com_ia_simulada(banco, monkeypatch):
    banco.salvar(lead_exemplo(id="0x9:0x9", redes={}, instagram="", site="", situacao_site="sem_site",
                              logo_url="https://exemplo/logo.png"))
    monkeypatch.setattr(ia, "ia_disponivel", lambda: True)
    monkeypatch.setattr(analise, "cores_da_logo", lambda url: {"principal": "#123456"})
    monkeypatch.setattr(ia, "buscar_redes_na_web", lambda lead, log=print: {
        "redes": {"instagram": "https://www.instagram.com/ze/", "facebook": "https://www.facebook.com/ze"},
        "site": "", "_tokens": 10})
    monkeypatch.setattr(ia, "analisar_lead", lambda lead, log=print: {
        "resumo": "Barbearia cheia", "publico": "", "diferencial": "corte rápido",
        "angulo": "Vi que muita gente elogia o corte.",
        "dores": [{"dor": "Demora no WhatsApp", "prova": "ninguém respondeu"}],
        "o_que_vender": [{"servico": "site", "motivo": "clientes perguntam preço"}], "_tokens": 50})
    lead = analise.analisar("0x9:0x9", log=lambda *a: None)
    assert lead["redes"]["facebook"] == "https://www.facebook.com/ze"
    assert "busca na web" in lead["redes_origem"]
    assert lead["analise_ia"]["angulo"] == "Vi que muita gente elogia o corte."
    assert lead["cores"] == {"principal": "#123456"}
    site = next(o for o in lead["oportunidades"] if o["servico"] == "site")
    assert "IA: clientes perguntam preço" in site["evidencias"]


def test_descartado_pelo_bot(banco, sem_ia):
    banco.salvar(lead_exemplo(id="0x5:0x5", nome="Barbearia Fechada", sinais={"fechado": "permanentemente"}))
    lead = analise.analisar("0x5:0x5", usar_ia=False)
    assert lead["estado"] == "descartado" and lead["motivo"].startswith("Fechado")


def test_franquia_em_varias_regioes(banco):
    for i, regiao in enumerate(["Asa Norte", "Asa Sul", "Guará"]):
        banco.salvar(lead_exemplo(id=f"x{i}", nome="Barbearia Rede", regiao=regiao))
    assert db.nome_em_varias_regioes("barbearia rede", "Taguatinga") == 4


def test_fila_um_pedido_por_vez(banco):
    primeiro = _pedido(banco, "analisar", {})
    _pedido(banco, "analisar", {})
    pego = db.pegar_proximo_pedido()
    assert pego["id"] == primeiro["id"] and pego["status"] == "rodando"
    # O primeiro já está rodando: o próximo a sair é o segundo
    assert db.pegar_proximo_pedido()["id"] != primeiro["id"]
    assert db.pegar_proximo_pedido() is None


def test_trabalhador_reanalisa_e_escreve_o_log(banco, sem_ia):
    banco.salvar(lead_exemplo())
    pedido = _pedido(banco, "analisar", {"ids": [ID], "usar_ia": False})
    trabalhador.executar(db.pegar_proximo_pedido())
    final = db.cliente().selecionar("pedidos", {"id": f"eq.{pedido['id']}"})[0]
    assert final["status"] == "concluido" and final["resultado"] == {"analisados": 1}
    texto = "\n".join(final["log"])
    assert "Barbearia do Zé" in texto and "Potencial" in texto and "1 leads analisados" in texto
    assert db.buscar(ID)["classe"] == "potencial"


def test_busca_pelo_trabalhador(banco, sem_ia, monkeypatch):
    async def busca_falsa(nicho, regioes, opcoes, log, deve_parar, ao_salvar):
        assert nicho["termo_busca"] == "Barbearia" and opcoes["limite"] == 60   # limite máximo
        db.salvar(lead_exemplo())
        await ao_salvar(ID)
        return 1

    monkeypatch.setattr(trabalhador, "rodar_busca", busca_falsa)
    _pedido(banco, "busca", {"nicho": "barbearias", "regioes": ["Taguatinga, DF"], "limite": 500})
    trabalhador.executar(db.pegar_proximo_pedido())
    final = db.cliente().selecionar("pedidos")[0]
    assert final["status"] == "concluido" and final["resultado"] == {"leads_novos": 1}
    assert db.buscar(ID)["nota_potencial"] is not None


def test_pedido_com_erro_e_parado(banco, sem_ia):
    _pedido(banco, "busca", {"nicho": "nao-existe", "regioes": ["X"]})
    trabalhador.executar(db.pegar_proximo_pedido())
    final = db.cliente().selecionar("pedidos")[0]
    assert final["status"] == "erro" and "Nicho não encontrado" in final["log"][-1]

    banco.salvar(lead_exemplo())
    pedido = _pedido(banco, "analisar", {"usar_ia": False})
    db.cliente().atualizar("pedidos", {"id": f"eq.{pedido['id']}"}, {"parar": True})
    trabalhador.executar(db.pegar_proximo_pedido())
    final = db.cliente().selecionar("pedidos", {"id": f"eq.{pedido['id']}"})[0]
    assert final["status"] == "cancelado" and any("Interrompido" in l for l in final["log"])


def test_aviso_de_pc_ligado(banco):
    db.avisar_que_estou_ligado(True, "gemini-x")
    db.avisar_que_estou_ligado(False, "")
    linhas = db.cliente().selecionar("trabalhador")
    assert len(linhas) == 1 and linhas[0]["ia"] is False


def test_backup(banco, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PASTA_BACKUPS", tmp_path)
    banco.salvar(lead_exemplo())
    db.adicionar_contato(ID, "ligacao", "Atendeu")
    for _ in range(3):
        db.fazer_backup(manter=2)
    arquivos = sorted(tmp_path.glob("backup-*.json"))
    assert 1 <= len(arquivos) <= 2
    dados = json.loads(arquivos[-1].read_text(encoding="utf-8"))
    assert dados["leads"][0]["id"] == ID and dados["contatos"][0]["anotacao"] == "Atendeu"


def test_migracao_do_banco_antigo(banco, tmp_path):
    arquivo = tmp_path / "antigo.db"
    con = sqlite3.connect(arquivo)
    con.execute("CREATE TABLE leads (id TEXT, nome TEXT, status TEXT, redes TEXT, criado_em TEXT, "
                "data_proximo_passo TEXT, coluna_velha TEXT)")
    con.execute("CREATE TABLE contatos (id INTEGER, lead_id TEXT, data TEXT, tipo TEXT, anotacao TEXT)")
    con.execute("INSERT INTO leads VALUES ('a', 'Pizzaria A', 'respondeu', '{\"instagram\": \"https://i/a\"}', "
                "'2025-01-02T10:00:00', '2025-02-01', 'x')")
    con.execute("INSERT INTO leads VALUES ('b', 'Pizzaria B', 'perdido', NULL, '2025-01-03 11:00:00', '', NULL)")
    con.execute("INSERT INTO contatos VALUES (1, 'a', '2025-01-05T09:00:00', 'ligacao', 'Atendeu')")
    con.commit()
    con.close()

    migracao.migrar(arquivo)
    migracao.migrar(arquivo)   # rodar de novo não duplica nada
    a, b = db.buscar("a"), db.buscar("b")
    assert a["etapa"] == "interessado" and a["estado"] == "ativo" and a["redes"] == {"instagram": "https://i/a"}
    assert a["data_proximo_passo"] == "2025-02-01"
    assert a["criado_em"].startswith("2025-01-02T10:00:00") and len(a["criado_em"]) > 19   # ganhou o fuso
    assert "coluna_velha" not in a
    assert b["estado"] == "arquivado" and b.get("data_proximo_passo") is None
    assert len(db.listar_contatos("a")) == 1


def test_sinais_da_ficha_e_auditoria_do_site():
    ficha = {"achou_painel": True, "texto": "Barbearia\nFechado permanentemente", "links": ["https://ifood.com.br/x"],
             "rotulos": ["agendar horário", "rotas"]}
    assert sinais_da_ficha(ficha) == {"fechado": "permanentemente", "tem_agendar": True, "tem_pedido": True}
    assert sinais_da_ficha({"achou_painel": False}) == {"fechado": None, "tem_agendar": None, "tem_pedido": None}
    html = '<meta name="viewport" content="width=device-width"><a href="https://wa.me/5561998765432">zap</a>' \
           '<a href="https://instagram.com/ze">ig</a> contato@ze.com.br'
    auditoria = auditar_html(html, "http://ze.com.br/", 5200)
    assert auditoria["https"] is False and auditoria["celular"] is True and auditoria["lento"] is True
    assert auditoria["whatsapp"] == "5561998765432" and auditoria["email"] == "contato@ze.com.br"
    assert auditoria["redes"] == {"instagram": "https://www.instagram.com/ze/"}
