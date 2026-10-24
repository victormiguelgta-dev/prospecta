"""
Configurações centrais do projeto.

Tudo que é caminho de pasta ou chave de API fica aqui, num lugar só.
As chaves vêm do arquivo .env (copie o .env.example e preencha).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Pasta raiz do projeto (a pasta onde está o app.py)
RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

# Pastas de dados
PASTA_DADOS = RAIZ / "dados"
PASTA_NICHOS = PASTA_DADOS / "nichos"           # um .json por nicho
ARQUIVO_REGIOES = PASTA_DADOS / "regioes.json"  # lista de regiões editável no painel
ARQUIVO_PESOS = PASTA_DADOS / "potencial.json"  # pesos da nota de potencial (edite à vontade)
ARQUIVO_BANCO = Path(os.getenv("PROSPECTA_DB", PASTA_DADOS / "prospeccao.db"))

# Saídas (planilhas, pacotes e diagnósticos)
PASTA_SAIDA = RAIZ / "saida"
PASTA_PLANILHAS = PASTA_SAIDA / "planilhas"

# Painel em React: depois do "npm run build" ele fica em painel/dist
PASTA_PAINEL = RAIZ / "painel" / "dist"

# IA (Gemini). Sem chave, a classificação usa só as regras (custo zero).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODELO = os.getenv("GEMINI_MODELO", "gemini-3.8-flash").strip()

# Seus dados, usados na mensagem de WhatsApp
SEU_NOME = os.getenv("SEU_NOME", "Victor Miguel").strip()

# Endereço em que o painel fica aberto. 127.0.0.1 = só neste computador.
# Para abrir pelo celular via VPN (ex.: Tailscale), use o IP da VPN ou 0.0.0.0.
HOST = os.getenv("HOST", "127.0.0.1").strip()
PORTA = int(os.getenv("PORTA", "8000"))

for pasta in (PASTA_DADOS, PASTA_NICHOS, PASTA_PLANILHAS):
    pasta.mkdir(parents=True, exist_ok=True)
