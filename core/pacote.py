"""
Pacote do cliente: um documento só com tudo o que o sistema sabe sobre o lead.

Serve para duas coisas:
  - você chegar na conversa com argumento (o que vender, dores com prova, primeira frase);
  - mandar para uma IA fazer o site, o perfil do Maps ou outro serviço, se o cliente se interessar.

Sai em Markdown (para ler, copiar e colar) e em JSON (para outra ferramenta ler).
Nada é inventado: o que não foi encontrado aparece em "O que falta pegar com o cliente".
Nenhuma imagem é baixada: fotos e logo vão como links.
"""
import io
from datetime import datetime

import requests

from . import db
from .cores import cor_da_imagem, montar_paleta
from .limpeza import NOMES_REDES, SITUACOES
from .oportunidades import NOMES_SERVICOS

NOMES_FORCA = {"alta": "alta", "media": "média", "baixa": "baixa"}


def cores_da_logo(url: str) -> dict:
    """Cor principal da logo e uma paleta sugerida para o site. {} se não der."""
    if not url:
        return {}
    try:
        resposta = requests.get(url, timeout=10)
        resposta.raise_for_status()
        base = cor_da_imagem(io.BytesIO(resposta.content))
    except Exception:
        return {}
    if not base:
        return {}
    paleta = montar_paleta(base)
    return {"principal": base, "destaque": paleta["destaque"], "fundo": paleta["fundo"],
            "superficie": paleta["superficie"], "texto": paleta["texto"]}


def o_que_falta(lead: dict) -> list:
    falta = []
    if not lead.get("logo_url"):
        falta.append("Logo")
    if len(lead.get("fotos") or []) < 3:
        falta.append("Fotos do negócio (o Maps tem poucas)")
    if not lead.get("descricao"):
        falta.append("Descrição do negócio e lista de serviços")
    if not lead.get("horario"):
        falta.append("Horário de funcionamento")
    if not lead.get("email"):
        falta.append("E-mail")
    if not lead.get("whatsapp"):
        falta.append("WhatsApp (só há telefone fixo ou nenhum)")
    if not lead.get("redes"):
        falta.append("Redes sociais (nenhuma encontrada)")
    return falta


def montar(lead: dict, com_cores: bool = True) -> dict:
    """Junta o pacote como dicionário (a base do Markdown e do JSON)."""
    analise = lead.get("analise_ia") or {}
    auditoria = (lead.get("sinais") or {}).get("site") or {}
    return {
        "gerado_em": datetime.now().isoformat(timespec="minutes"),
        "negocio": {
            "nome": lead.get("nome"),
            "categoria": lead.get("categoria"),
            "regiao": lead.get("regiao"),
            "endereco": lead.get("endereco"),
            "descricao_do_dono": lead.get("descricao"),
            "publico": analise.get("publico"),
            "diferencial": analise.get("diferencial"),
            "resumo": analise.get("resumo"),
        },
        "classificacao": {
            "nota": lead.get("nota_potencial"),
            "classe": db.NOMES_CLASSES.get(lead.get("classe"), ""),
            "servico_principal": NOMES_SERVICOS.get(lead.get("servico_principal"), ""),
            "etapa": db.NOMES_ETAPAS.get(lead.get("etapa"), ""),
            "conta": lead.get("nota_detalhe") or [],
        },
        "contato": {
            "telefone": lead.get("telefone"),
            "whatsapp": lead.get("whatsapp"),
            "email": lead.get("email"),
            "maps": lead.get("maps_url"),
        },
        "redes": lead.get("redes") or {},
        "instagram": {"seguidores": lead.get("instagram_seguidores"), "posts": lead.get("instagram_posts")},
        "google": {
            "nota": lead.get("nota"),
            "avaliacoes": lead.get("avaliacoes"),
            "horario": lead.get("horario") or [],
            "saude_maps": lead.get("saude_maps"),
            "problemas_maps": lead.get("problemas_maps") or [],
        },
        "site_atual": {
            "endereco": lead.get("site"),
            "situacao": SITUACOES.get(lead.get("situacao_site"), ""),
            "https": auditoria.get("https"),
            "versao_celular": auditoria.get("celular"),
            "tempo_para_abrir_ms": auditoria.get("tempo_ms"),
        },
        "oportunidades": lead.get("oportunidades") or [],
        "dores": analise.get("dores") or [],
        "angulo_de_abordagem": analise.get("angulo"),
        "identidade_visual": {
            "logo": lead.get("logo_url"),
            "cores": cores_da_logo(lead.get("logo_url")) if com_cores else {},
            "fotos": lead.get("fotos") or [],
        },
        "o_que_falta": o_que_falta(lead),
        "historico": db.listar_contatos(lead["id"]) if lead.get("id") else [],
    }


def _linha(rotulo, valor):
    return f"- **{rotulo}:** {valor}\n" if valor not in (None, "", []) else ""


def para_markdown(p: dict) -> str:
    n, c, ct, g, s = p["negocio"], p["classificacao"], p["contato"], p["google"], p["site_atual"]
    md = [f"# {n['nome']}\n\n"]
    md.append(f"{n.get('categoria') or ''} · {n.get('regiao') or ''} · pacote gerado em "
              f"{p['gerado_em'].replace('T', ' ')}\n\n")

    md.append("## Classificação\n\n")
    md.append(_linha("Classe", f"{c['classe']} ({c['nota']}/100)" if c["nota"] is not None else ""))
    md.append(_linha("Serviço principal", c["servico_principal"]))
    md.append(_linha("Etapa", c["etapa"]))
    if n.get("resumo"):
        md.append(f"\n{n['resumo']}\n")
    md.append("\n")

    md.append("## Contato\n\n")
    md.append(_linha("Telefone", ct["telefone"]))
    if ct["whatsapp"]:
        md.append(_linha("WhatsApp", f"https://wa.me/{ct['whatsapp']}"))
    md.append(_linha("E-mail", ct["email"]))
    md.append(_linha("Endereço", n.get("endereco")))
    md.append(_linha("Google Maps", ct["maps"]))
    md.append("\n")

    md.append("## Redes sociais\n\n")
    if p["redes"]:
        for rede, url in p["redes"].items():
            extra = ""
            if rede == "instagram" and p["instagram"]["posts"] is not None:
                extra = f" ({p['instagram']['seguidores'] or '?'} seguidores, {p['instagram']['posts']} posts)"
            md.append(f"- **{NOMES_REDES.get(rede, rede)}:** {url}{extra}\n")
    else:
        md.append("Nenhuma rede social encontrada.\n")
    md.append("\n")

    md.append("## O que vender\n\n")
    if p["oportunidades"]:
        for o in p["oportunidades"]:
            md.append(f"### {NOMES_SERVICOS.get(o['servico'], o['servico'])} (força {NOMES_FORCA.get(o['forca'], o['forca'])})\n\n")
            md.append(f"{o['motivo']}\n\n")
            md.extend(f"- {e}\n" for e in o["evidencias"])
            md.append("\n")
    else:
        md.append("Nenhuma oportunidade encontrada pelas regras.\n\n")

    if p["dores"]:
        md.append("## Dores do negócio\n\n")
        md.extend(f"- **{d['dor']}** — prova: {d['prova']}\n" for d in p["dores"])
        md.append("\n")
    if p["angulo_de_abordagem"]:
        md.append(f"## Primeira frase da conversa\n\n> {p['angulo_de_abordagem']}\n\n")

    md.append("## Informações para o site\n\n")
    md.append(_linha("Descrição escrita pelo dono", n.get("descricao_do_dono")))
    md.append(_linha("Público", n.get("publico")))
    md.append(_linha("Diferencial", n.get("diferencial")))
    if g["nota"]:
        md.append(_linha("Google", f"nota {str(g['nota']).replace('.', ',')} com {g['avaliacoes'] or 0} avaliações"))
    if g["horario"]:
        md.append("- **Horário:**\n")
        md.extend(f"  - {h}\n" for h in g["horario"])
    v = p["identidade_visual"]
    md.append(_linha("Logo", v["logo"]))
    if v["cores"]:
        cores = v["cores"]
        md.append(_linha("Cores da logo", f"principal {cores['principal']}, destaque {cores['destaque']}, "
                                          f"fundo {cores['fundo']}, superfície {cores['superficie']}, texto {cores['texto']}"))
    if v["fotos"]:
        md.append(f"- **Fotos do negócio no Maps ({len(v['fotos'])}):**\n")
        md.extend(f"  - {f}\n" for f in v["fotos"])
    md.append("\n")

    md.append("## Site atual\n\n")
    if s["endereco"]:
        md.append(_linha("Endereço", s["endereco"]))
    md.append(_linha("Situação", s["situacao"]))
    if s["https"] is not None:
        md.append(_linha("HTTPS", "sim" if s["https"] else "não"))
    if s["versao_celular"] is not None:
        md.append(_linha("Versão para celular", "sim" if s["versao_celular"] else "não"))
    if s["tempo_para_abrir_ms"]:
        md.append(_linha("Tempo para abrir", f"{s['tempo_para_abrir_ms'] / 1000:.1f} s".replace(".", ",")))
    md.append("\n")

    md.append(f"## Saúde do Google Maps: {g['saude_maps'] if g['saude_maps'] is not None else '?'}/100\n\n")
    if g["problemas_maps"]:
        md.extend(f"- {problema}\n" for problema in g["problemas_maps"])
    else:
        md.append("Sem problemas encontrados.\n")
    md.append("\n")

    if p["o_que_falta"]:
        md.append("## O que falta pegar com o cliente\n\n")
        md.extend(f"- [ ] {item}\n" for item in p["o_que_falta"])
        md.append("\n")

    if p["historico"]:
        md.append("## Histórico de contatos\n\n")
        md.extend(f"- {h['data'][:16].replace('T', ' ')} · {h['tipo']} · {h.get('anotacao') or ''}\n"
                  for h in p["historico"])
        md.append("\n")
    return "".join(md).rstrip() + "\n"
