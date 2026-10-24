"""
Nota de potencial (0 a 100) e classe de cada lead.

  70 a 100  Potencial
  40 a 69   Talvez
  0 a 39    Pouco potencial

A nota soma três grupos de sinais:
  - Movimento (até 45): avaliações, nota no Google, avaliação recente, Instagram, ficha completa;
  - Contato (até 15): WhatsApp e redes sociais para chegar no dono;
  - Oportunidade (até 40): o quanto ele precisa do que você vende (veja oportunidades.py).

Os pesos e faixas ficam em dados/potencial.json. Ajuste depois de ver quem fecha de verdade.
Ninguém é eliminado por ter poucas avaliações: negócio novo vira oportunidade de Maps.
"""
import copy
import json

from . import config
from .limpeza import eh_celular, normalizar_whatsapp
from .oportunidades import FORCAS, detectar, juntar_com_ia, saude_maps, servico_principal

PESOS_PADRAO = {
    "faixas": {"potencial": 70, "talvez": 40},
    "pontos": {
        # [a partir de, pontos]: vale a primeira linha que o lead alcançar
        "avaliacoes": [[200, 20], [50, 15], [20, 10], [10, 6], [1, 3]],
        "nota_google": [[4.5, 10], [4.0, 7], [3.5, 4]],
        "avaliacao_recente_dias": [[30, 5], [90, 3]],
        "instagram_posts": [[100, 5], [30, 3], [1, 1]],
        "horario": 2,
        "cinco_fotos": 3,
        "whatsapp": 10,
        "rede_social": 5,
        "oportunidade": {"alta": 25, "media": 15, "baixa": 5},
        "oportunidade_extra": 5,
        "oportunidade_extra_maximo": 15,
    },
    # Nomes que indicam rede ou franquia (o dono não é o contato do Maps)
    "franquias": [
        "smart fit", "smartfit", "bodytech", "bluefit", "selfit", "pratique fitness", "panobianco",
        "domino's", "dominos", "pizza hut", "subway", "mcdonald", "burger king", "bob's", "habib's",
        "odontocompany", "oral sin", "sorridents", "odonto excellence",
        "barbearia corleone", "dom barbudo", "o boticário", "cacau show", "kopenhagen",
    ],
    # Em quantas regiões diferentes o mesmo nome precisa aparecer para ser tratado como rede
    "regioes_para_rede": 3,
    # Palavras que, numa avaliação de 1 a 3 estrelas, indicam problema de atendimento
    "palavras_queixa": [
        "atend", "demora", "demor", "não respond", "nao respond", "ninguém respond", "ninguem respond",
        "não atende", "nao atende", "telefone", "whatsapp", "zap", "agendar", "agendamento", "marcar horário",
        "marcar horario", "esper", "fila", "sem resposta",
    ],
}


def carregar_pesos() -> dict:
    """Lê dados/potencial.json; o que faltar lá vem do padrão acima."""
    pesos = copy.deepcopy(PESOS_PADRAO)
    if config.ARQUIVO_PESOS.exists():
        try:
            salvos = json.loads(config.ARQUIVO_PESOS.read_text(encoding="utf-8"))
        except ValueError:
            salvos = {}
        for chave, valor in salvos.items():
            if isinstance(valor, dict) and isinstance(pesos.get(chave), dict):
                pesos[chave].update(valor)
            else:
                pesos[chave] = valor
    return pesos


def _faixa(valor, tabela):
    if valor is None:
        return 0
    for minimo, pontos in tabela:
        if valor >= minimo:
            return pontos
    return 0


def motivo_descarte(lead: dict, pesos: dict, regioes_com_mesmo_nome: int = 1) -> str:
    """Devolve o motivo se o lead não deve nem entrar no quadro; senão, ''."""
    fechado = (lead.get("sinais") or {}).get("fechado")
    if fechado:
        return f"Fechado {fechado} no Google"
    numero = lead.get("whatsapp") or normalizar_whatsapp(lead.get("telefone"))
    if not numero:
        return "Sem telefone na ficha"
    nome = (lead.get("nome") or "").lower()
    if any(marca in nome for marca in pesos.get("franquias", [])):
        return "Rede ou franquia: o contato do Maps não é o dono"
    if regioes_com_mesmo_nome >= pesos.get("regioes_para_rede", 3):
        return f"Rede ou franquia: o mesmo nome aparece em {regioes_com_mesmo_nome} regiões"
    return ""


def calcular(lead: dict, nicho: dict = None, pesos: dict = None, sugestoes_ia: list = None) -> dict:
    """
    Calcula tudo o que é regra: saúde do Maps, oportunidades, nota e classe.
    Devolve só os campos de análise (para salvar no lead).
    """
    pesos = pesos or carregar_pesos()
    pontos = pesos["pontos"]
    detalhe = []

    def somar(sinal, valor):
        if valor:
            detalhe.append({"sinal": sinal, "pontos": valor})

    # Movimento
    total = lead.get("avaliacoes")
    somar(f"{total or 0} avaliações no Google", _faixa(total, pontos["avaliacoes"]))
    nota = lead.get("nota")
    if nota:
        somar(f"Nota {str(nota).replace('.', ',')} no Google", _faixa(nota, pontos["nota_google"]))
    dias = [a.get("dias") for a in lead.get("avaliacoes_lidas") or [] if a.get("dias") is not None]
    if dias:
        recente = min(dias)
        # Para "dias", quanto MENOR melhor: vale a primeira faixa cujo limite o lead não passou
        for limite, valor in pontos["avaliacao_recente_dias"]:
            if recente <= limite:
                somar(f"Avaliação recente (há {recente} dias)", valor)
                break
    posts = lead.get("instagram_posts")
    somar(f"{posts} posts no Instagram", _faixa(posts, pontos["instagram_posts"]))
    if lead.get("horario"):
        somar("Horário cadastrado", pontos["horario"])
    fotos = (lead.get("sinais") or {}).get("total_fotos")
    if fotos is None:
        fotos = len(lead.get("fotos") or [])
    if fotos >= 5:
        somar("5 ou mais fotos na ficha", pontos["cinco_fotos"])

    # Contato
    numero = lead.get("whatsapp") or normalizar_whatsapp(lead.get("telefone"))
    if lead.get("whatsapp") or eh_celular(numero):
        somar("Tem WhatsApp", pontos["whatsapp"])
    if lead.get("redes"):
        somar("Redes sociais encontradas", pontos["rede_social"])

    # Oportunidade
    oportunidades = juntar_com_ia(detectar(lead, nicho, pesos.get("palavras_queixa")), sugestoes_ia)
    if oportunidades:
        melhor = max(oportunidades, key=lambda o: FORCAS[o["forca"]])
        somar(f"Oportunidade {melhor['forca']}: {melhor['motivo']}", pontos["oportunidade"][melhor["forca"]])
        extras = min((len(oportunidades) - 1) * pontos["oportunidade_extra"], pontos["oportunidade_extra_maximo"])
        somar(f"{len(oportunidades) - 1} oportunidade(s) a mais", extras)

    nota_final = min(100, sum(d["pontos"] for d in detalhe))
    faixas = pesos["faixas"]
    classe = "potencial" if nota_final >= faixas["potencial"] else "talvez" if nota_final >= faixas["talvez"] else "pouco"
    nota_saude, problemas = saude_maps(lead)
    return {
        "nota_potencial": nota_final,
        "classe": classe,
        "nota_detalhe": detalhe,
        "saude_maps": nota_saude,
        "problemas_maps": problemas,
        "oportunidades": oportunidades,
        "servico_principal": servico_principal(oportunidades),
    }
