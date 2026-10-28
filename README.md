# Prospecta

CRM de prospecção. Um bot encontra negócios no Google Maps, junta as informações de cada um (Maps, site e todas as redes sociais), classifica o potencial e diz o que cada cliente pode comprar de você: **Google Maps**, **site** ou **desenvolvimento** (automação ou ferramenta sob medida). Você trabalha os leads num quadro e, para cada cliente, tem um **pacote** com tudo para a conversa ou para mandar a uma IA fazer o serviço.

O sistema **não gera sites**. Ele pesquisa, classifica e organiza; quem decide e faz é você.

```
            painel (React, no Netlify) ◄──────► banco (Supabase) ◄──────► trabalhador (seu PC)
            celular ou PC, de qualquer lugar        leads, histórico,        busca no Maps (Playwright),
            quadro, fichas, ligar hoje              fila de pedidos          regras + IA, backup diário
```

- O **painel** fica no Netlify e conversa direto com o **Supabase**: o CRM (quadro, fichas, congelar, ligar hoje) funciona no celular mesmo com o PC desligado.
- O trabalho pesado (buscar no Maps, analisar com IA, diagnóstico) vira um **pedido** numa fila. O **trabalhador** (`python trabalhador.py`), no seu PC, pega os pedidos e escreve o progresso de volta. Com o PC desligado, os pedidos esperam na fila.

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

O banco já está criado no Supabase (projeto **Prospecta**, região São Paulo). As tabelas estão em `supabase/0001_inicial.sql` e `supabase/0002_ajustes.sql`.

Precisa de **Python 3.11 ou mais novo**, **Node.js 20 ou mais novo** (só para mexer no painel) e **Git**.

```bash
git clone https://github.com/victormiguelgta-dev/prospecta.git
cd prospecta

python -m venv .venv
.venv\Scripts\activate             # no Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

copy .env.example .env             # no Linux/Mac: cp .env.example .env
```

Abra o `.env` e preencha:

- `SUPABASE_CHAVE`: no Supabase, **Project Settings → API Keys → Secret keys** (começa com `sb_secret_`). Ela fica **só no seu PC**: nunca no painel, no Netlify ou no GitHub.
- `GEMINI_API_KEY`: grátis em aistudio.google.com/apikey. Sem ela tudo funciona, mas só com as regras.

### Levar os leads antigos para o Supabase (uma vez)

Se você já usava a versão antiga, o banco dela está em `dados/prospeccao.db`. Com o `.env` preenchido:

```bash
python migrar_para_supabase.py
```

Pode rodar de novo sem medo: quem já está no Supabase não é copiado outra vez. Depois, no painel, use **Configurações → Reanalisar todos**. Guarde o `prospeccao.db` como cópia de segurança (ele não vai para o GitHub).

## Rodar o trabalhador (no PC)

```bash
.venv\Scripts\activate
python trabalhador.py
```

Deixe a janela aberta. O painel mostra **PC ligado** enquanto ele roda. Ele também salva um **backup** de todos os leads por dia em `saida/backups/` (guarda os últimos 30).

### Ligar sozinho com o PC (Linux Mint)

Crie o arquivo `~/.config/systemd/user/prospecta.service` (troque o caminho da pasta):

```ini
[Unit]
Description=Prospecta - trabalhador
After=network-online.target

[Service]
WorkingDirectory=/home/SEU_USUARIO/prospecta
ExecStart=/home/SEU_USUARIO/prospecta/.venv/bin/python trabalhador.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
```

e rode `systemctl --user enable --now prospecta` (para ver o que ele está fazendo: `journalctl --user -u prospecta -f`).

## O painel

### No Netlify (para usar no celular)

1. No Netlify: **Add new project → Import an existing project → GitHub →** `prospecta`. O arquivo `netlify.toml` já diz o que fazer (pasta `painel`, `npm run build`, publica `dist`).
2. Em **Project configuration → Environment variables**, cadastre `VITE_SUPABASE_URL` e `VITE_SUPABASE_CHAVE` com os valores de `painel/.env.example` (a chave **publishable**, que é pública).
3. Troque o nome do site por um difícil de adivinhar (ex.: `prospecta-k7q2x`). O painel não aparece no Google (`noindex`).

Cada publicação gasta créditos do Netlify: junte várias alterações antes de publicar.

### Sem login: o que isso quer dizer

O painel **não tem senha**, por escolha. Quem descobrir o endereço do site consegue ver e mudar os leads. Para diminuir o risco: endereço difícil, `noindex`, não compartilhar o link e o backup diário no PC. Se um dia quiser senha, dá para ligar o login do Supabase (Authentication) e trocar as regras de acesso das tabelas de `anon` para `authenticated`: o resto do sistema não muda.

### Programar o painel (React)

```bash
cd painel
copy .env.example .env             # no Linux/Mac: cp .env.example .env
npm install
npm run dev
```

e abra o endereço que ele mostrar (normalmente http://localhost:5173). Cada alteração em `painel/src/` aparece na hora. Ele usa o mesmo banco de verdade do Supabase.

## Ajustar a classificação

Os pesos ficam em `dados/potencial.json`:

- `faixas`: onde começa cada classe (70 e 40);
- `pontos`: quanto vale cada sinal (avaliações, nota, Instagram, WhatsApp, força da oportunidade);
- `franquias`: nomes de redes que o bot descarta;
- `palavras_queixa`: palavras que, numa avaliação ruim, indicam problema de atendimento.

Os nichos e as regiões ficam no banco e são editados no painel em **Configurações**. Marque se o ramo **agenda horário** e se **vende por pedido**: isso liga as oportunidades de desenvolvimento.

Depois de mudar os pesos, use **Configurações → Reanalisar todos os leads**. Anote quem fecha e quem não fecha: depois de 20 a 30 leads, dá para ver quais sinais acertaram e ajustar os pesos.

## Quanto custa

- **Busca**: grátis (o bot usa um navegador no seu PC).
- **IA**: uma análise por lead, com poucos tokens. A pesquisa de redes na web usa a busca do Google dentro do Gemini, que tem uma cota grátis própria. Os limites do plano grátis mudam: confira em ai.google.dev/pricing.

## Estrutura

```
trabalhador.py          roda no PC: pega os pedidos da fila, faz backup diário
migrar_para_supabase.py leva o banco antigo (SQLite) para o Supabase
supabase/*.sql          tabelas do banco (leads, contatos, nichos, regiões, pedidos, trabalhador, ajustes)
core/
  supabase.py           cliente da API do Supabase (só com requests)
  db.py                 funções do banco usadas pelo bot, pela análise e pela fila
  scraper.py            bot do Maps (Playwright), com os seletores no topo
  limpeza.py            limpa texto, classifica o site, acha redes sociais e WhatsApp
  analise.py            junta tudo depois da coleta: descarte, redes na web, regras, IA e cores da logo
  potencial.py          nota de 0 a 100, classe e descarte (lê dados/potencial.json)
  oportunidades.py      saúde do Maps e o que vender (maps, site, desenvolvimento)
  ia.py                 Gemini: análise do lead e pesquisa de redes na web
  cores.py              cores da logo
  diagnostico.py        prints do que o bot vê no Maps (para ajustar seletores)
dados/potencial.json    pesos da classificação
painel/                 painel em React (Vite)
  src/api.js            leituras e gravações no Supabase, e os pedidos para o PC
  src/regras.js         nomes, links de WhatsApp e ligação, mensagem inicial
  src/pacote.js         o documento de cada cliente (Markdown e JSON)
  src/exportar.js       planilha (CSV) e JSON
netlify.toml            como o Netlify monta e publica o painel
testes/                 testes (python -m pytest testes), com um Supabase de mentira
```

## Testes

```bash
pip install pytest
python -m pytest testes
```

## Cuidados

- **O Google muda o Maps.** Se algum dado parar de vir, use **Diagnóstico do bot** na ficha do lead e ajuste o seletor em `SELETORES` no topo de `core/scraper.py`. Raspar o Maps e o Instagram vai contra os termos de uso: use limites baixos por região, porque é isso que evita bloqueio.
- **WhatsApp**: o envio é sempre com um clique seu. Disparo automático em massa é o jeito mais rápido de ter o número banido.
- **Dados**: o banco fica no Supabase (plano grátis: 500 MB, o que dá dezenas de milhares de leads). Projeto grátis sem uso por 7 dias é pausado; o trabalhador ligado e o uso do painel evitam isso, e dá para reativar no site do Supabase.
- **LGPD**: dados públicos de empresas, para uma abordagem comercial pontual. Quem pedir para não ser contatado vai para Arquivados e não recebe mais mensagens.
- **Promessas**: nunca prometa "primeiro lugar no Google". Para mexer no perfil do Maps, o dono precisa te dar acesso de gerente.
