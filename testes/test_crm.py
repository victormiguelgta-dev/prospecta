"""
Testes do CRM pela API: quadro, congelar, arquivar, histórico, ligar hoje, pacote
e a análise com a IA simulada (nenhuma chamada de verdade é feita).
"""
from datetime import date

import pytest
from conftest import lead_exemplo
from fastapi.testclient import TestClient

import app as servidor
from core import analise, ia
from core.scraper import auditar_html, sinais_da_ficha


@pytest.fixture
def cliente(banco, monkeypatch):
    monkeypatch.setattr(ia, "ia_disponivel", lambda: False)
    banco.salvar(lead_exemplo())
    analise.analisar("0x1:0x2", usar_ia=False)
    return TestClient(servidor.app)


def test_lead_novo_entra_no_quadro_classificado(cliente):
    leads = cliente.get("/api/leads").json()
    assert len(leads) == 1
    lead = leads[0]
    assert lead["etapa"] == "lead_novo" and lead["estado"] == "ativo"
    assert lead["classe"] == "potencial"
    assert lead["link_whatsapp"].startswith("https://wa.me/5561998765432?text=")
    assert lead["link_ligar"] == "tel:+5561998765432"
    assert "avaliacoes_lidas" not in lead   # só servem para classificar
    assert cliente.get("/api/leads?classe=talvez").json() == []
    assert len(cliente.get("/api/leads?servico=desenvolvimento").json()) == 1


def test_mover_etapa_guarda_no_historico(cliente):
    lead = cliente.patch("/api/leads/0x1:0x2", json={"etapa": "interessado"}).json()
    assert lead["etapa"] == "interessado"
    assert lead["contatos"][0]["anotacao"] == "Movido para Cliente interessado"
    assert cliente.patch("/api/leads/0x1:0x2", json={"etapa": "inventada"}).status_code == 400


def test_congelar_e_ligar_hoje(cliente):
    hoje = date.today().isoformat()
    lead = cliente.post("/api/leads/0x1:0x2/congelar", json={"data_ligar": hoje}).json()
    assert lead["estado"] == "congelado"
    assert cliente.get("/api/leads").json() == []   # sai do quadro
    assert [l["nome"] for l in cliente.get("/api/leads?estado=congelado").json()] == ["Barbearia do Zé"]
    assert len(cliente.get("/api/ligar-hoje").json()) == 1
    assert cliente.post("/api/leads/0x1:0x2/reativar").json()["estado"] == "ativo"


def test_arquivar_e_historico(cliente):
    cliente.post("/api/leads/0x1:0x2/contatos", json={"tipo": "ligacao", "anotacao": "Pediu para ligar semana que vem"})
    lead = cliente.post("/api/leads/0x1:0x2/arquivar", json={"motivo": "Sem dinheiro agora"}).json()
    assert lead["estado"] == "arquivado" and lead["motivo"] == "Sem dinheiro agora"
    tipos = [c["tipo"] for c in lead["contatos"]]
    assert tipos == ["anotacao", "ligacao"]
    assert cliente.post("/api/leads/0x1:0x2/contatos", json={"tipo": "pombo"}).status_code == 400


def test_pacote(cliente, monkeypatch):
    from core import pacote
    monkeypatch.setattr(pacote, "cores_da_logo", lambda url: {})
    texto = cliente.get("/api/leads/0x1:0x2/pacote").json()["texto"]
    for trecho in ("# Barbearia do Zé", "## Redes sociais", "4800 seguidores, 250 posts", "## O que vender",
                   "### Site (força alta)", "## O que falta pegar com o cliente", "- [ ] Logo"):
        assert trecho in texto
    dados = cliente.get("/api/leads/0x1:0x2/pacote?formato=json").json()
    assert dados["redes"]["instagram"].endswith("/barbeariaze/")
    baixado = cliente.get("/api/leads/0x1:0x2/pacote?baixar=true")
    assert "attachment" in baixado.headers["content-disposition"]


def test_analise_com_ia_simulada(banco, monkeypatch):
    banco.salvar(lead_exemplo(id="0x9:0x9", redes={}, instagram="", site="", situacao_site="sem_site"))
    monkeypatch.setattr(ia, "ia_disponivel", lambda: True)
    monkeypatch.setattr(ia, "buscar_redes_na_web", lambda lead, log=print: {
        "redes": {"instagram": "https://www.instagram.com/ze/", "facebook": "https://www.facebook.com/ze"},
        "site": "", "_tokens": 10})
    monkeypatch.setattr(ia, "analisar_lead", lambda lead, log=print: {
        "resumo": "Barbearia cheia", "publico": "", "diferencial": "corte rápido", "angulo": "Vi que muita gente elogia o corte.",
        "dores": [{"dor": "Demora no WhatsApp", "prova": "ninguém respondeu"}],
        "o_que_vender": [{"servico": "site", "motivo": "clientes perguntam preço"}], "_tokens": 50})
    lead = analise.analisar("0x9:0x9", log=lambda *a: None)
    assert lead["redes"]["facebook"] == "https://www.facebook.com/ze"
    assert "busca na web" in lead["redes_origem"]
    assert lead["analise_ia"]["angulo"] == "Vi que muita gente elogia o corte."
    site = next(o for o in lead["oportunidades"] if o["servico"] == "site")
    assert "IA: clientes perguntam preço" in site["evidencias"]


def test_descartado_pelo_bot_e_volta_se_voce_mover(banco):
    banco.salvar(lead_exemplo(id="0x5:0x5", nome="Barbearia Fechada", sinais={"fechado": "permanentemente"}))
    lead = analise.analisar("0x5:0x5", usar_ia=False)
    assert lead["estado"] == "descartado" and lead["motivo"].startswith("Fechado")
    cliente = TestClient(servidor.app)
    assert cliente.patch("/api/leads/0x5:0x5", json={"etapa": "em_contato"}).json()["estado"] == "ativo"


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


def test_painel_sem_build_mostra_instrucao(cliente, monkeypatch, tmp_path):
    from core import config
    monkeypatch.setattr(config, "PASTA_PAINEL", tmp_path / "nao-existe")
    resposta = cliente.get("/")
    assert "npm run build" in resposta.text
    assert cliente.get("/api/rota-que-nao-existe").status_code == 404
