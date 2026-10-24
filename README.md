# Prospecta

CRM de prospecção. Um bot encontra negócios no Google Maps, junta as informações de cada um (Maps, site e todas as redes sociais), classifica o potencial e diz o que cada cliente pode comprar de você: **Google Maps**, **site** ou **desenvolvimento** (automação ou ferramenta sob medida). Você trabalha os leads num quadro e, para cada cliente, tem um **pacote** com tudo para a conversa ou para mandar a uma IA fazer o serviço.

O sistema **não gera sites**. Ele pesquisa, classifica e organiza; quem decide e faz é você.

```
Maps ──► bot (Playwright) ──► banco (SQLite) ──► regras + IA ──► quadro (React) ──► você liga ou chama no WhatsApp
```

## Como funciona

1. **Busca**: você escolhe o nicho e as regiões. O bot visita cada negócio no Maps e coleta nome, telefone, endereço, nota, avaliações, horário, descrição, fotos (só os links), links de redes sociais e o site.
2. **Site**: se existe, o bot abre e vê se está no ar, se tem HTTPS e versão para celular.
3. **Redes sociais**: junta as que aparecem no Maps e no site. Se não achar Instagram nem Facebook, a IA pesquisa o nome da marca no Google. Do Instagram, lê o total de posts e de seguidores (sem login).
4. **Avaliações**: lê as mais recentes, só para classificar (reclamações, respostas do dono). Nenhum nome de cliente é guardado.
5. **Classificação**: a nota de 0 a 100 sai de regras fixas; a IA lê os dados e diz as dores, o que vender e a primeira frase da conversa.
6. **Quadro**: o lead entra em "Lead novo". Você arrasta pelas etapas até "Fechado".

### As três classes

| Nota | Classe |
|---|---|
| 70 a 100 | **Potencial** |
| 40 a 69 | **Talvez** |
| 0 a 39 | **Pouco potencial** |

Todos aparecem no quadro, ordenados da maior nota para a menor; use os filtros para ver só uma classe.

### O que cada cliente pode comprar (a escada)

1. **Google Maps**: o perfil está fraco (poucas fotos, sem descrição, sem horário, avaliações negativas sem resposta, poucas avaliações). Negócio novo, com poucas avaliações, cai aqui.
2. **Site**: não tem site, só tem rede social, o site é gratuito, está fora do ar ou não tem versão de celular.
3. **Desenvolvimento**: já tem Maps ou site. Avaliações reclamando de atendimento, nicho que agenda sem botão de agendar, nicho de comida sem pedido online, muito movimento e só telefone fixo.

Cada oportunidade vem com a **prova** (ex.: "3 avaliações negativas sem resposta"). O serviço principal é o primeiro degrau que o cliente ainda não tem.

### Quem sai do quadro sozinho

O bot descarta (e manda para "Arquivados") quem está **fechado** no Google, quem **não tem telefone** e **redes e franquias** (o contato do Maps não é o dono). Poucas avaliações nunca eliminam ninguém.

### Etapas do quadro e o que fica fora dele

- **Lead novo → Em contato → Cliente interessado → Fechado**: arraste o cartão (no celular, segure meio segundo antes de arrastar) ou troque a etapa na ficha.
- **Congelar**: para quem demonstrou interesse e parou de responder. Você escolhe o dia de ligar de novo e ele aparece em **Ligar hoje** nesse dia.
- **Arquivar**: sem interesse agora. Fica guardado com o motivo e dá para voltar ao quadro depois.
- **Ligar hoje**: todo lead (do quadro ou congelado) com próximo passo para hoje ou atrasado.

### O pacote do cliente

Na ficha do lead, **Pacote do cliente** mostra um documento com classificação, contato, redes sociais, o que vender com as provas, dores, primeira frase da conversa, informações para o site (descrição, público, diferencial, horário, logo, cores da logo, links das fotos), situação do site atual, saúde do Maps, o que falta pegar com o cliente e o histórico. Dá para copiar ou baixar em `.md` (para ler e colar numa IA) ou `.json`.

## Instalação (uma vez só)

Precisa de **Python 3.11 ou mais novo**, **Node.js 20 ou mais novo** e **Git**.

```bash
git clone https://github.com/victormiguelgta-dev/prospecta.git
cd prospecta

# Python
python -m venv .venv
.venv\Scripts\activate             # no Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Painel (React)
cd painel
npm install
npm run build
cd ..

# Configuração
copy .env.example .env             # no Linux/Mac: cp .env.example .env
```

Abra o `.env` e coloque a chave do Gemini (grátis em aistudio.google.com/apikey). Sem ela tudo funciona, mas só com as regras.

## Rodar

```bash
.venv\Scripts\activate
python app.py
```

Abra **http://localhost:8000**.

### Programar o painel (React)

Com o `python app.py` rodando, abra outro terminal:

```bash
cd painel
npm run dev
```

e abra o endereço que ele mostrar (normalmente http://localhost:5173). Cada alteração em `painel/src/` aparece na hora. Quando terminar, rode `npm run build` para o `python app.py` servir a versão nova.

### Abrir pelo celular (VPN)

1. Instale o **Tailscale** no PC e no celular e entre com a mesma conta.
2. No `.env`, coloque em `HOST` o IP do Tailscale do PC (aparece no aplicativo, começa com 100.).
3. Rode `python app.py` e, no celular, abra `http://<ip-do-tailscale>:8000`.

O painel não tem senha. Nunca deixe a porta aberta na internet: use só pela VPN.

## Ajustar a classificação

Os pesos ficam em `dados/potencial.json`:

- `faixas`: onde começa cada classe (70 e 40);
- `pontos`: quanto vale cada sinal (avaliações, nota, Instagram, WhatsApp, força da oportunidade);
- `franquias`: nomes de redes que o bot descarta;
- `palavras_queixa`: palavras que, numa avaliação ruim, indicam problema de atendimento.

Os nichos ficam em `dados/nichos/` e no painel em **Configurações**. Marque se o ramo **agenda horário** e se **vende por pedido**: isso liga as oportunidades de desenvolvimento.

Depois de mudar os pesos, use **Configurações → Reanalisar todos os leads**. Anote quem fecha e quem não fecha: depois de 20 a 30 leads, dá para ver quais sinais acertaram e ajustar os pesos.

## Quanto custa

- **Busca**: grátis (o bot usa um navegador no seu PC).
- **IA**: uma análise por lead, com poucos tokens. A pesquisa de redes na web usa a busca do Google dentro do Gemini, que tem uma cota grátis própria. Os limites do plano grátis mudam: confira em ai.google.dev/pricing.

## Estrutura

```
app.py                  servidor (FastAPI): API do CRM + serve o painel
core/
  scraper.py            bot do Maps (Playwright), com os seletores no topo
  limpeza.py            limpa texto, classifica o site, acha redes sociais e WhatsApp
  analise.py            junta tudo depois da coleta: descarte, redes na web, regras e IA
  potencial.py          nota de 0 a 100, classe e descarte (lê dados/potencial.json)
  oportunidades.py      saúde do Maps e o que vender (maps, site, desenvolvimento)
  ia.py                 Gemini: análise do lead e pesquisa de redes na web
  pacote.py             o documento de cada cliente (Markdown e JSON)
  mensagem.py           mensagem inicial de WhatsApp e links de ligar
  db.py                 banco SQLite: leads e histórico de contatos
  nichos.py             nichos e regiões
  cores.py              cores da logo
  exportar.py           Excel e JSON
  diagnostico.py        prints do que o bot vê no Maps (para ajustar seletores)
dados/nichos/*.json     um arquivo por nicho
dados/potencial.json    pesos da classificação
dados/regioes.json      lista de regiões
painel/                 painel em React (Vite); src/ é o código, dist/ é gerado pelo build
testes/                 testes (python -m pytest testes)
```

## Testes

```bash
pip install pytest httpx
python -m pytest testes
```

## Vindo da versão antiga

O banco antigo (`dados/prospeccao.db`) é convertido sozinho na primeira vez: os status viram etapas do quadro e quem tinha sido descartado por ter site volta para análise (agora pode comprar desenvolvimento). Os leads antigos não têm os dados novos (redes, avaliações lidas, sinais): use **Reanalisar todos** e, para os melhores, **Buscar de novo no Maps** na ficha.

## Cuidados

- **O Google muda o Maps.** Se algum dado parar de vir, use **Diagnóstico do bot** na ficha do lead e ajuste o seletor em `SELETORES` no topo de `core/scraper.py`. Raspar o Maps e o Instagram vai contra os termos de uso: use limites baixos por região, porque é isso que evita bloqueio.
- **WhatsApp**: o envio é sempre com um clique seu. Disparo automático em massa é o jeito mais rápido de ter o número banido.
- **LGPD**: dados públicos de empresas, para uma abordagem comercial pontual. Quem pedir para não ser contatado vai para Arquivados e não recebe mais mensagens.
- **Promessas**: nunca prometa "primeiro lugar no Google". Para mexer no perfil do Maps, o dono precisa te dar acesso de gerente.
