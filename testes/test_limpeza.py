"""
Testes das funções de limpeza. Rode com:  python -m pytest testes
(instale antes: pip install pytest)

Bom lugar para treinar: quando achar um caso novo no Maps que o bot
classificou errado, escreva o teste aqui primeiro e depois corrija a função.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.limpeza import (  # noqa: E402
    achar_instagram, achar_whatsapp_em_link, classificar_site, eh_celular, id_do_maps,
    limpar_texto, normalizar_whatsapp, numero_br, slugify,
)


def test_limpar_icones_do_google():
    assert limpar_texto("\n(61) 3352-0313") == "(61) 3352-0313"
    assert limpar_texto(", St. B Sul QSB 12") == "St. B Sul QSB 12"


def test_classificar_site():
    assert classificar_site("") == "sem_site"
    assert classificar_site("N/A") == "sem_site"
    assert classificar_site("https://www.instagram.com/pizzaria/") == "so_rede_social"
    assert classificar_site("https://wa.me/5561999998888") == "so_rede_social"
    assert classificar_site("https://linktr.ee/barbearia") == "so_rede_social"
    assert classificar_site("https://m.facebook.com/igreja") == "so_rede_social"
    assert classificar_site("http://minhaloja.wixsite.com/home") == "site_fraco"
    assert classificar_site("https://pizzaria.business.site") == "site_fraco"
    assert classificar_site("http://www.ibftonline.com/") == "site_proprio"


def test_whatsapp():
    assert normalizar_whatsapp("(61) 99876-5432") == "5561998765432"
    assert normalizar_whatsapp("+55 61 99876-5432") == "5561998765432"
    assert normalizar_whatsapp("061 3352-0313") == "556133520313"
    assert normalizar_whatsapp("123") == ""
    assert eh_celular("(61) 99876-5432")
    assert not eh_celular("(61) 3352-0313")
    assert achar_whatsapp_em_link("https://api.whatsapp.com/send?phone=5561998765432") == "5561998765432"


def test_instagram():
    html = '<a href="https://www.instagram.com/p/abc">post</a> <a href="https://instagram.com/forno.de.minas/">perfil</a>'
    assert achar_instagram(html) == "https://www.instagram.com/forno.de.minas/"


def test_dados_da_url_do_maps():
    url = "https://www.google.com/maps/place/X/data=!4m7!3m6!1s0x935a3:0xabc12!8m2!3d-15.83!4d-48.05"
    assert id_do_maps(url) == "0x935a3:0xabc12"


def test_numeros_e_slug():
    assert numero_br("4,7") == 4.7
    assert numero_br("1.234 avaliações") == 1234
    assert slugify("Pizzaria do Zé - Taguatinga") == "pizzaria-do-ze-taguatinga"


def test_nota_de_dados():
    from core.qualidade import avaliar
    vazio = avaliar({"nome": "X"})
    assert vazio["nivel"] == "fraco"
    cheio = avaliar({"fotos": ["a", "b", "c"], "depoimentos": [{}, {}], "logo_url": "x", "nota": 4.8,
                     "avaliacoes": 50, "horario": ["seg"], "descricao": "d"})
    assert cheio["pontos"] == cheio["maximo"] and cheio["nivel"] == "completo"
