"""
Testes da classificação: saúde do Maps, oportunidades (a escada), nota de potencial e descarte.
Nenhum teste abre o Maps nem chama a IA.
"""
from conftest import lead_exemplo

from core.oportunidades import detectar, juntar_com_ia, saude_maps, servico_principal
from core.potencial import PESOS_PADRAO, calcular, motivo_descarte

BARBEARIA = {"id": "barbearias", "nome": "Barbearias", "agenda": True, "pedido_online": False}
PIZZARIA = {"id": "pizzarias", "nome": "Pizzarias", "agenda": False, "pedido_online": True}


def test_saude_do_maps_conta_os_problemas():
    nota, problemas = saude_maps(lead_exemplo())
    assert "1 avaliação negativa sem resposta" in problemas
    assert "Só 2 fotos na ficha" in problemas
    assert "Sem descrição do negócio" in problemas
    assert any("Nenhuma das últimas 6 avaliações" in p for p in problemas)
    assert nota == 100 - 20 - 15 - 10 - 10


def test_sinal_desconhecido_nao_tira_ponto():
    # O bot não conseguiu ler fotos nem avaliações: nada disso pode virar problema
    lead = lead_exemplo(sinais={}, fotos=None, avaliacoes_lidas=None, descricao="Cortes clássicos")
    nota, problemas = saude_maps(lead)
    assert nota == 100 and problemas == []


def test_negocio_novo_vira_oportunidade_de_maps():
    lead = lead_exemplo(avaliacoes=0, nota=None, avaliacoes_lidas=[])
    _, problemas = saude_maps(lead)
    assert "Nenhuma avaliação no Google" in problemas
    assert motivo_descarte(lead, PESOS_PADRAO) == ""   # poucas avaliações nunca eliminam


def test_escada_maps_site_desenvolvimento():
    oportunidades = detectar(lead_exemplo(), BARBEARIA, PESOS_PADRAO["palavras_queixa"])
    assert [o["servico"] for o in oportunidades] == ["maps", "site", "desenvolvimento"]
    site = oportunidades[1]
    assert site["forca"] == "alta"
    assert "O link de site do Maps leva para Instagram" in site["evidencias"]
    assert "4.800 seguidores e 250 posts no Instagram" in site["evidencias"]
    dev = oportunidades[2]
    assert any("reclama" in e for e in dev["evidencias"])
    assert any("agendamento" in e for e in dev["evidencias"])
    assert servico_principal(oportunidades) == "maps"


def test_quem_tem_site_bom_vai_para_desenvolvimento():
    lead = lead_exemplo(situacao_site="site_proprio", site="https://barbeariaze.com.br", descricao="Cortes",
                        fotos=["f"] * 10, avaliacoes_lidas=[], sinais={"tem_agendar": True, "total_fotos": None,
                                                                         "site": {"https": True, "celular": True}})
    oportunidades = detectar(lead, BARBEARIA, [])
    assert [o["servico"] for o in oportunidades] == ["desenvolvimento"]
    assert oportunidades[0]["forca"] == "baixa"


def test_site_com_problemas_e_pizzaria_sem_pedido():
    lead = lead_exemplo(situacao_site="site_proprio", site="http://pizzaria.com.br", descricao="Pizzas",
                        avaliacoes_lidas=[], fotos=["f"] * 10,
                        sinais={"tem_pedido": False, "site": {"https": False, "celular": False}})
    oportunidades = {o["servico"]: o for o in detectar(lead, PIZZARIA, [])}
    assert oportunidades["site"]["forca"] == "media"
    assert "Site sem versão para celular" in oportunidades["site"]["evidencias"]
    assert "Sem pedido online nem cardápio digital" in oportunidades["desenvolvimento"]["evidencias"]


def test_ia_soma_evidencias_e_servicos():
    regras = [{"servico": "site", "forca": "alta", "motivo": "Não tem site", "evidencias": ["Não tem site"]}]
    juntas = juntar_com_ia(regras, [{"servico": "site", "motivo": "6 avaliações perguntam preço"},
                                    {"servico": "desenvolvimento", "motivo": "pedem agendamento pelo WhatsApp"},
                                    {"servico": "inventado", "motivo": "x"}])
    assert [o["servico"] for o in juntas] == ["site", "desenvolvimento"]
    assert "IA: 6 avaliações perguntam preço" in juntas[0]["evidencias"]
    assert juntas[1]["forca"] == "media"


def test_nota_e_classe():
    resultado = calcular(lead_exemplo(), BARBEARIA, PESOS_PADRAO)
    assert resultado["classe"] == "potencial"
    assert resultado["nota_potencial"] == sum(d["pontos"] for d in resultado["nota_detalhe"])
    fraco = calcular(lead_exemplo(avaliacoes=2, nota=3.0, whatsapp="", telefone="(61) 3333-4444", redes={},
                                  instagram_posts=None, horario=[], situacao_site="site_proprio",
                                  site="https://x.com.br", descricao="d", avaliacoes_lidas=[],
                                  sinais={"site": {"https": True, "celular": True}}), {}, PESOS_PADRAO)
    assert fraco["classe"] == "pouco"


def test_faixas_das_classes():
    pesos = {**PESOS_PADRAO, "faixas": {"potencial": 70, "talvez": 40}}
    talvez = calcular(lead_exemplo(instagram_posts=None, redes={}, avaliacoes=15, nota=4.2, avaliacoes_lidas=[],
                                   sinais={}, fotos=None, descricao="d", situacao_site="site_fraco",
                                   site="https://ze.wixsite.com/a"), {}, pesos)
    assert 40 <= talvez["nota_potencial"] < 70 and talvez["classe"] == "talvez"


def test_descarte():
    assert motivo_descarte(lead_exemplo(sinais={"fechado": "permanentemente"}), PESOS_PADRAO).startswith("Fechado")
    assert motivo_descarte(lead_exemplo(telefone="", whatsapp=""), PESOS_PADRAO) == "Sem telefone na ficha"
    assert "franquia" in motivo_descarte(lead_exemplo(nome="Smart Fit Taguatinga"), PESOS_PADRAO)
    assert "3 regiões" in motivo_descarte(lead_exemplo(), PESOS_PADRAO, regioes_com_mesmo_nome=3)
    assert motivo_descarte(lead_exemplo(), PESOS_PADRAO) == ""
