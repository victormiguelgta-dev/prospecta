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
    achar_instagram, achar_redes, achar_whatsapp_em_link, classificar_site, dias_atras, eh_celular, id_do_maps,
    juntar_redes, ler_resumo_instagram, limpar_texto, normalizar_whatsapp, numero_br, slugify,
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


def test_redes_sociais():
    html = ('<a href="https://www.instagram.com/p/abc">post</a> <a href="https://instagram.com/barbearia.ze/">ig</a>'
            '<a href="https://www.facebook.com/sharer.php?u=x">share</a> <a href="https://facebook.com/barbeariaze">fb</a>'
            '<a href="https://www.tiktok.com/@barbeariaze?lang=pt">tt</a> <a href="https://linktr.ee/ze">lt</a>')
    redes = achar_redes(html)
    assert redes["instagram"] == "https://www.instagram.com/barbearia.ze/"
    assert redes["facebook"] == "https://www.facebook.com/barbeariaze"
    assert redes["tiktok"] == "https://www.tiktok.com/@barbeariaze"
    assert redes["linktree"] == "https://linktr.ee/ze"
    assert "youtube" not in redes
    assert juntar_redes({"instagram": "a"}, {"instagram": "b", "facebook": "c"}) == {"instagram": "a", "facebook": "c"}


def test_resumo_do_instagram():
    assert ler_resumo_instagram("1.234 seguidores, 56 seguindo, 789 publicações - Veja") == {"seguidores": 1234, "posts": 789}
    assert ler_resumo_instagram("12,5 mil seguidores, 3 seguindo, 1.002 publicações") == {"seguidores": 12500, "posts": 1002}
    assert ler_resumo_instagram("5K Followers, 10 Following, 300 Posts") == {"seguidores": 5000, "posts": 300}
    assert ler_resumo_instagram("") == {"seguidores": None, "posts": None}


def test_dias_atras():
    assert dias_atras("há 2 semanas") == 14
    assert dias_atras("há um mês") == 30
    assert dias_atras("há 3 meses") == 90
    assert dias_atras("Editado há 2 anos") == 730
    assert dias_atras("há 5 horas") == 0
    assert dias_atras("ontem?") is None
