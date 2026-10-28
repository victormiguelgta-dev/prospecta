"""
Configurações centrais do projeto.

Tudo que é caminho de pasta ou chave de API fica aqui, num lugar só.
As chaves vêm do arquivo .env (copie o .env.example e preencha).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Pasta raiz do projeto (a pasta onde está o trabalhador.py)
RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

# Banco de dados (Supabase). A chave pode ser a "publishable" ou, melhor, a "secret".
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_CHAVE = os.getenv("SUPABASE_CHAVE", "").strip()

# Pesos da nota de potencial (edite à vontade)
PASTA_DADOS = RAIZ / "dados"
ARQUIVO_PESOS = PASTA_DADOS / "potencial.json"

# Saídas locais deste computador (backups e diagnósticos)
PASTA_SAIDA = RAIZ / "saida"
PASTA_BACKUPS = PASTA_SAIDA / "backups"

# IA (Gemini). Sem chave, a classificação usa só as regras (custo zero).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODELO = os.getenv("GEMINI_MODELO", "gemini-3.8-flash").strip()

for pasta in (PASTA_DADOS, PASTA_BACKUPS):
    pasta.mkdir(parents=True, exist_ok=True)
