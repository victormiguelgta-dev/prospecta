"""
Nota de completude: quanto de informação REAL o lead tem para virar um bom site.

Site com pouca informação fica genérico e passa a impressão de
"alguém tentando me vender algo". Por isso:
  - completo: gera normalmente;
  - medio:    gera, mas confira antes de enviar;
  - fraco:    a geração em lote pula (dá para gerar um a um, se você quiser).
"""

PESOS = [
    # (pontos, descrição, teste)
    (2, "foto do lugar", lambda l: len(l.get("fotos") or []) >= 1),
    (2, "galeria (3+ fotos)", lambda l: len(l.get("fotos") or []) >= 3),
    (2, "avaliações com texto", lambda l: len(l.get("depoimentos") or []) >= 2),
    (1, "logo", lambda l: bool(l.get("logo_url"))),
    (1, "nota boa no Google", lambda l: (l.get("nota") or 0) >= 4 and (l.get("avaliacoes") or 0) >= 10),
    (1, "horário", lambda l: bool(l.get("horario"))),
    (1, "descrição do dono", lambda l: bool(l.get("descricao"))),
]
MAXIMO = sum(p for p, _, _ in PESOS)


def avaliar(lead: dict) -> dict:
    pontos, tem, falta = 0, [], []
    for peso, nome, teste in PESOS:
        if teste(lead):
            pontos += peso
            tem.append(nome)
        else:
            falta.append(nome)
    nivel = "completo" if pontos >= 6 else "medio" if pontos >= 3 else "fraco"
    return {"pontos": pontos, "maximo": MAXIMO, "nivel": nivel, "tem": tem, "falta": falta}
