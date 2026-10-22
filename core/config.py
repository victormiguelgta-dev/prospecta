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
PASTA_NICHOS = PASTA_DADOS / "nichos"          # um .json por nicho (roteiro da IA)
PASTA_ARQUIVOS_NICHO = PASTA_DADOS / "arquivos_nicho"  # imagens e material de consulta de cada nicho
ARQUIVO_REGIOES = PASTA_DADOS / "regioes.json"  # lista de regiões editável no painel
ARQUIVO_BANCO = PASTA_DADOS / "prospeccao.db"   # banco SQLite com os leads

# Templates HTML dos sites e saída
PASTA_TEMPLATES = RAIZ / "templates_sites"
PASTA_SAIDA = RAIZ / "saida"
PASTA_SITES = PASTA_SAIDA / "sites"             # cada lead vira saida/sites/<slug>/index.html
PASTA_PLANILHAS = PASTA_SAIDA / "planilhas"

# IA (Gemini). Sem chave, o gerador usa os textos padrão do nicho (custo zero).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODELO = os.getenv("GEMINI_MODELO", "gemini-3.8-flash").strip()

# Netlify (publicação dos demos)
NETLIFY_TOKEN = os.getenv("NETLIFY_TOKEN", "").strip()
NETLIFY_SITE_ID = os.getenv("NETLIFY_SITE_ID", "").strip()
# Endereço público dos demos, ex.: https://meus-demos.netlify.app
URL_DEMOS = os.getenv("URL_DEMOS", "").strip().rstrip("/")

# Seus dados, que aparecem na faixa "prévia criada por..." e na mensagem
SEU_NOME = os.getenv("SEU_NOME", "Victor Miguel").strip()
SEU_WHATSAPP = os.getenv("SEU_WHATSAPP", "").strip()  # só números, ex.: 5561999999999

for pasta in (PASTA_DADOS, PASTA_NICHOS, PASTA_ARQUIVOS_NICHO, PASTA_SITES, PASTA_PLANILHAS):
    pasta.mkdir(parents=True, exist_ok=True)
