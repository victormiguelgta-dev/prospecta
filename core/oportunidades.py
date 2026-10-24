"""
O que cada cliente pode comprar de você, sempre com a prova.

São três serviços, avaliados nesta ordem (a "escada"):
  1. maps            - o perfil do Google Maps está fraco ou mal cuidado;
  2. site            - não tem site, só tem rede social, ou o site é fraco;
  3. desenvolvimento - já tem Maps e/ou site: automação ou ferramenta sob medida.

Cada oportunidade sai com a força (alta, média, baixa), o motivo em uma frase
e as evidências que o bot viu na ficha. Sem evidência, não há oportunidade.
Tudo aqui são regras em Python: grátis e sempre com o mesmo resultado.
"""
from .limpeza import NOMES_REDES, dominio, eh_celular, normalizar_whatsapp

SERVICOS = ["maps", "site", "desenvolvimento"]
NOMES_SERVICOS = {"maps": "Google Maps", "site": "Site", "desenvolvimento": "Desenvolvimento"}
FORCAS = {"alta": 3, "media": 2, "baixa": 1}

# Penalidades da Saúde do Maps (0 a 100). Um sinal desconhecido nunca tira pontos.
PENALIDADES = {
    "negativas_sem_resposta": 20,
    "poucas_avaliacoes": 15,
    "poucas_fotos": 15,
    "dono_nao_responde": 10,
    "sem_horario": 10,
    "sem_descricao": 10,
    "sem_site": 10,
    "nota_baixa": 10,
}


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def saude_maps(lead: dict) -> tuple:
    """
    Nota de 0 a 100 de quão bem cuidado está o perfil do Maps, e a lista de problemas.
    Começa em 100 e cada problema tira pontos.
    """
    problemas = []   # (penalidade, texto)
    total = lead.get("avaliacoes")
    if total is not None and total < 10:
        texto = "Nenhuma avaliação no Google" if total == 0 else f"Só {_plural(total, 'avaliação', 'avaliações')} no Google"
        problemas.append((PENALIDADES["poucas_avaliacoes"], texto))
    nota = lead.get("nota")
    if nota is not None and nota < 4.0 and (total or 0) >= 10:
        problemas.append((PENALIDADES["nota_baixa"], f"Nota {str(nota).replace('.', ',')} no Google"))

    fotos = (lead.get("sinais") or {}).get("total_fotos")
    if fotos is None and lead.get("fotos") is not None:
        fotos = len(lead.get("fotos") or [])
    if fotos is not None and fotos < 5:
        problemas.append((PENALIDADES["poucas_fotos"],
                          "Nenhuma foto na ficha" if fotos == 0 else f"Só {_plural(fotos, 'foto', 'fotos')} na ficha"))
    if not lead.get("horario"):
        problemas.append((PENALIDADES["sem_horario"], "Sem horário de funcionamento"))
    if not lead.get("descricao"):
        problemas.append((PENALIDADES["sem_descricao"], "Sem descrição do negócio"))
    if lead.get("situacao_site") in ("sem_site", "fora_do_ar"):
        problemas.append((PENALIDADES["sem_site"],
                          "Sem site no perfil" if lead["situacao_site"] == "sem_site" else "Link de site quebrado no perfil"))
    elif (lead.get("sinais") or {}).get("site_fora_do_maps"):
        problemas.append((PENALIDADES["sem_site"], "Tem site, mas ele não aparece no perfil do Maps"))

    lidas = lead.get("avaliacoes_lidas") or []
    if lidas:
        negativas = [a for a in lidas if (a.get("estrelas") or 5) <= 2 and a.get("respondida") is False]
        if negativas:
            problemas.append((PENALIDADES["negativas_sem_resposta"],
                              f"{_plural(len(negativas), 'avaliação negativa', 'avaliações negativas')} sem resposta"))
        sabidas = [a for a in lidas if a.get("respondida") is not None]
        if len(sabidas) >= 5 and not any(a["respondida"] for a in sabidas):
            problemas.append((PENALIDADES["dono_nao_responde"],
                              f"Nenhuma das últimas {len(sabidas)} avaliações tem resposta do dono"))

    nota_saude = max(0, 100 - sum(p for p, _ in problemas))
    return nota_saude, [texto for _, texto in sorted(problemas, key=lambda p: -p[0])]


def queixas_de_atendimento(lead: dict, palavras: list) -> list:
    """Avaliações que reclamam de atendimento, demora ou de não conseguir falar com o negócio."""
    achadas = []
    for avaliacao in lead.get("avaliacoes_lidas") or []:
        texto = (avaliacao.get("texto") or "").lower()
        if (avaliacao.get("estrelas") or 5) <= 3 and any(p in texto for p in palavras):
            achadas.append(avaliacao)
    return achadas


def _rede_do_link(url: str) -> str:
    host = dominio(url)
    for rede, nome in NOMES_REDES.items():
        if rede in host or (rede == "x" and host in ("x.com", "twitter.com")):
            return nome
    return "WhatsApp" if "wa.me" in host or "whatsapp" in host else "uma rede social"


def detectar(lead: dict, nicho: dict = None, palavras_queixa: list = None) -> list:
    """Devolve a lista de oportunidades {servico, forca, motivo, evidencias}, na ordem da escada."""
    nicho = nicho or {}
    oportunidades = []

    # 1. Google Maps ------------------------------------------------------
    nota_saude, problemas = saude_maps(lead)
    if problemas and nota_saude < 85:
        forca = "alta" if nota_saude < 50 else "media" if nota_saude < 70 else "baixa"
        oportunidades.append({"servico": "maps", "forca": forca,
                              "motivo": f"Perfil do Maps com saúde {nota_saude}/100",
                              "evidencias": problemas[:4]})

    # 2. Site -------------------------------------------------------------
    situacao = lead.get("situacao_site")
    seguidores = lead.get("instagram_seguidores") or 0
    posts = lead.get("instagram_posts") or 0
    insta_forte = seguidores >= 1000 or posts >= 100
    evidencias_insta = []
    if insta_forte and situacao != "site_proprio":
        evidencias_insta.append(f"{seguidores:,} seguidores e {posts} posts no Instagram".replace(",", "."))
    if situacao == "sem_site":
        avaliacoes = lead.get("avaliacoes") or 0
        prova = f"Não tem site; {_plural(avaliacoes, 'avaliação', 'avaliações')} no Google" if avaliacoes else "Não tem site"
        oportunidades.append({"servico": "site", "forca": "alta", "motivo": "Não tem site",
                              "evidencias": [prova, *evidencias_insta]})
    elif situacao == "so_rede_social":
        oportunidades.append({"servico": "site", "forca": "alta", "motivo": "Só tem rede social",
                              "evidencias": [f"O link de site do Maps leva para {_rede_do_link(lead.get('site'))}",
                                             *evidencias_insta]})
    elif situacao == "fora_do_ar":
        oportunidades.append({"servico": "site", "forca": "alta", "motivo": "Site fora do ar",
                              "evidencias": [f"O site {dominio(lead.get('site'))} não abre"]})
    elif situacao == "site_fraco":
        oportunidades.append({"servico": "site", "forca": "media", "motivo": "Site gratuito ou genérico",
                              "evidencias": [f"Usa site gratuito ({dominio(lead.get('site'))})", *evidencias_insta]})
    elif situacao == "site_proprio":
        auditoria = (lead.get("sinais") or {}).get("site") or {}
        falhas = []
        if auditoria.get("https") is False:
            falhas.append("Site sem HTTPS (aparece como \"não seguro\")")
        if auditoria.get("celular") is False:
            falhas.append("Site sem versão para celular")
        if auditoria.get("lento"):
            falhas.append(f"Site lento ({auditoria.get('tempo_ms', 0) / 1000:.1f} s para abrir)".replace(".", ","))
        if falhas:
            oportunidades.append({"servico": "site", "forca": "media", "motivo": "Site com problemas",
                                  "evidencias": falhas})

    # 3. Desenvolvimento (automação ou ferramenta) -----------------------
    sinais = lead.get("sinais") or {}
    evidencias_dev, forca_dev = [], None
    queixas = queixas_de_atendimento(lead, palavras_queixa or [])
    if queixas:
        evidencias_dev.append(f"{_plural(len(queixas), 'avaliação reclama', 'avaliações reclamam')} de atendimento ou demora")
        forca_dev = "alta"
    if nicho.get("agenda") and sinais.get("tem_agendar") is False:
        evidencias_dev.append("Sem agendamento online na ficha (o ramo costuma agendar)")
        forca_dev = "alta"
    if nicho.get("pedido_online") and sinais.get("tem_pedido") is False and "ifood" not in (lead.get("redes") or {}):
        evidencias_dev.append("Sem pedido online nem cardápio digital")
        forca_dev = forca_dev or "media"
    numero = lead.get("whatsapp") or normalizar_whatsapp(lead.get("telefone"))
    if (lead.get("avaliacoes") or 0) >= 100 and not lead.get("whatsapp") and not eh_celular(numero):
        evidencias_dev.append(f"{lead['avaliacoes']} avaliações e só telefone fixo para atender")
        forca_dev = forca_dev or "media"
    site_ok = situacao == "site_proprio" and not any(o["servico"] == "site" for o in oportunidades)
    if not evidencias_dev and site_ok:
        evidencias_dev.append("Já tem site funcionando: o próximo passo é automatizar o atendimento")
        forca_dev = "baixa"
    if evidencias_dev:
        oportunidades.append({"servico": "desenvolvimento", "forca": forca_dev,
                              "motivo": "Automação ou ferramenta sob medida", "evidencias": evidencias_dev})
    return oportunidades


def juntar_com_ia(oportunidades: list, sugestoes_ia: list) -> list:
    """
    A IA pode ver o que as regras não veem (ex.: "6 avaliações perguntam preço").
    O motivo dela entra como evidência; um serviço que as regras não acharam entra com força média.
    """
    por_servico = {o["servico"]: o for o in oportunidades}
    for sugestao in sugestoes_ia or []:
        servico, motivo = sugestao.get("servico"), (sugestao.get("motivo") or "").strip()
        if servico not in SERVICOS or not motivo:
            continue
        if servico in por_servico:
            if motivo not in por_servico[servico]["evidencias"]:
                por_servico[servico]["evidencias"].append(f"IA: {motivo}")
        else:
            por_servico[servico] = {"servico": servico, "forca": "media", "motivo": "Sugerido pela IA",
                                    "evidencias": [f"IA: {motivo}"]}
    return [por_servico[s] for s in SERVICOS if s in por_servico]


def servico_principal(oportunidades: list) -> str:
    """O primeiro degrau da escada com força alta ou média; senão, o primeiro que existir."""
    for oportunidade in oportunidades:
        if oportunidade["forca"] in ("alta", "media"):
            return oportunidade["servico"]
    return oportunidades[0]["servico"] if oportunidades else ""
