"""
Mensagem inicial de WhatsApp e links de contato de cada lead.

A mensagem usa a primeira frase sugerida pela IA (o "ângulo", baseado na evidência
mais forte). Sem IA, usa um texto curto do serviço principal. Você sempre confere
e pode editar antes de enviar: o painel nunca manda nada sozinho.
"""
from urllib.parse import quote

from .config import SEU_NOME
from .limpeza import eh_celular, normalizar_whatsapp

TEXTOS_SERVICO = {
    "maps": "vi o perfil de vocês no Google Maps e tenho algumas ideias para ele aparecer melhor para quem procura na região.",
    "site": "vi vocês no Google Maps e reparei que ainda não têm um site próprio. Trabalho justamente com isso aqui na região.",
    "desenvolvimento": "vi vocês no Google Maps e trabalho com automações de atendimento e agendamento para negócios da região.",
}


def mensagem_inicial(lead: dict) -> str:
    angulo = ((lead.get("analise_ia") or {}).get("angulo") or "").strip()
    corpo = angulo or TEXTOS_SERVICO.get(lead.get("servico_principal"), "vi vocês no Google Maps e queria conversar rapidinho.")
    if corpo and not angulo:
        corpo = corpo[0].upper() + corpo[1:]
    return f"Olá, {lead.get('nome', '')}! Tudo bem? Meu nome é {SEU_NOME}. {corpo}\n\nPosso te explicar como funciona?"


def numero_contato(lead: dict) -> str:
    return lead.get("whatsapp") or normalizar_whatsapp(lead.get("telefone"))


def link_whatsapp(lead: dict, texto: str = None) -> str:
    numero = lead.get("whatsapp") or (numero_contato(lead) if eh_celular(numero_contato(lead)) else "")
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={quote(texto if texto is not None else mensagem_inicial(lead))}"


def link_ligar(lead: dict) -> str:
    numero = numero_contato(lead)
    return f"tel:+{numero}" if numero else ""
