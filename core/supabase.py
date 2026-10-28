"""
Cliente simples da API do Supabase (PostgREST), feito só com o `requests`.

O Supabase expõe cada tabela como um endereço:  https://<projeto>.supabase.co/rest/v1/<tabela>
Os filtros vão na URL no formato do PostgREST, por exemplo  {"id": "eq.0x1:0x2"}
(eq = igual, in = está na lista, ilike = parecido, ignorando maiúsculas).
"""
import requests

from . import config


class ErroSupabase(RuntimeError):
    pass


class Supabase:
    def __init__(self, url: str, chave: str, timeout: int = 30):
        if not url or not chave:
            raise ErroSupabase(
                "Faltam SUPABASE_URL e SUPABASE_CHAVE no arquivo .env (veja o .env.example).")
        self.base = url.rstrip("/") + "/rest/v1"
        self.timeout = timeout
        self.sessao = requests.Session()
        self.sessao.headers.update({"apikey": chave, "Content-Type": "application/json"})

    def _pedir(self, metodo, caminho, params=None, json=None, prefer=None):
        headers = {"Prefer": prefer} if prefer else {}
        resposta = self.sessao.request(metodo, f"{self.base}/{caminho}", params=params, json=json,
                                       headers=headers, timeout=self.timeout)
        if resposta.status_code >= 400:
            raise ErroSupabase(f"Supabase respondeu {resposta.status_code}: {resposta.text[:300]}")
        if resposta.status_code == 204 or not resposta.content:
            return None
        return resposta.json()

    def selecionar(self, tabela, filtros=None, colunas="*", ordem=None, limite=None, inicio=None) -> list:
        params = {"select": colunas, **(filtros or {})}
        if ordem:
            params["order"] = ordem
        if limite is not None:
            params["limit"] = limite
        if inicio is not None:
            params["offset"] = inicio
        return self._pedir("GET", tabela, params=params) or []

    def inserir(self, tabela, dados, ignorar_duplicados=False, juntar_duplicados=False, devolver=True):
        prefer = ["return=representation" if devolver else "return=minimal"]
        if ignorar_duplicados:
            prefer.append("resolution=ignore-duplicates")
        if juntar_duplicados:
            prefer.append("resolution=merge-duplicates")
        return self._pedir("POST", tabela, json=dados, prefer=",".join(prefer)) or []

    def atualizar(self, tabela, filtros, dados, devolver=False):
        return self._pedir("PATCH", tabela, params=filtros, json=dados,
                           prefer="return=representation" if devolver else "return=minimal") or []

    def apagar(self, tabela, filtros):
        return self._pedir("DELETE", tabela, params=filtros, prefer="return=minimal")

    def rpc(self, funcao, argumentos):
        return self._pedir("POST", f"rpc/{funcao}", json=argumentos)


_cliente = None


def cliente() -> Supabase:
    """O cliente do projeto, criado na primeira vez que alguém precisa dele."""
    global _cliente
    if _cliente is None:
        _cliente = Supabase(config.SUPABASE_URL, config.SUPABASE_CHAVE)
    return _cliente


def usar(novo):
    """Troca o cliente (os testes usam um banco de mentira)."""
    global _cliente
    _cliente = novo
