# Prospecta Sites

Um bot encontra no Google Maps negócios sem site, monta uma prévia do site de cada um com template, cores da logo e textos de IA, e prepara a mensagem de WhatsApp. Você só entra na conversa e na venda.

```
Maps ──► bot (Playwright) ──► banco (SQLite) ──► gerador (template + IA) ──► Netlify ──► WhatsApp
```

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate          # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env               # e preencha o que quiser (nada é obrigatório)
python app.py
```

Abra **http://localhost:8000**.

## Como usar

1. **Nichos e roteiros**: confira ou crie o nicho, por exemplo "Academias", com o termo "Academia". O roteiro diz à IA o tom e o que ela nunca pode inventar.
2. **Nova busca**: escolha o nicho, as regiões e quantos locais novos por região. Na primeira vez, desmarque "Rodar o navegador escondido" para ver o bot trabalhando.
3. **Leads**: por padrão só aparecem os potenciais clientes, ou seja, quem não tem site próprio. Selecione vários e clique em "Gerar sites dos selecionados", ou gere um por um.
4. Clique no nome do lead para ver a prévia, os dados e a mensagem.
5. **Publicar demos no Netlify** sobe todos os demos de uma vez.
6. **Enviar no WhatsApp** abre a conversa com a mensagem pronta. Você confere e aperta enviar. O lead passa para "Mensagem enviada".
7. Vá movendo cada lead pelo funil (Respondeu, Fechou, Não quis). Os números do topo mostram como está cada etapa.

## Template de academia

O template `academia` é um modelo completo para academias, com:
- slides no topo (primeiro as fotos reais, depois as imagens de pessoas do nicho);
- contadores animados só com números reais;
- modalidades, uma seção de destaque, estrutura (só fotos reais), planos sem preço, avaliações do Google, horários e mapa.

Para usar:
1. Em **Nichos e roteiros → Academias**, escolha `academia` em **Template** e salve.
2. Em **Imagens do nicho**, envie as fotos de pessoas treinando com a função **Pessoas (slides)**.

Use fotos com licença livre (Unsplash, Pexels) ou geradas por IA. Imagens de banco pago tiradas do Google não podem ser usadas.

## Modelo de site do nicho

Na aba **Nichos e roteiros**, a área **Modelo de site** recebe um site pronto para servir de base a todos os sites daquele nicho:

1. Envie um `.html` (com o CSS dentro) ou um `.zip` com o HTML, o CSS e as imagens, mantendo as pastas como estão.
2. Escolha se o fundo do modelo é **claro** ou **escuro**. Isso decide como as cores da logo do cliente se encaixam.
3. Clique em **Converter com IA**. Ela troca textos, fotos e contatos fixos por variáveis e tira o que seria falso para outro negócio: preços, "+500 alunos", depoimentos escritos à mão, CNPJ. É feito **uma vez só**, e o painel mostra quantos tokens vai custar.
4. Clique em **Ver prévia com dados de exemplo** e confira. Se algo ficou errado, **baixe o template**, corrija no VS Code e use **Enviar template editado**.
5. A partir daí, todo site do nicho usa o modelo. **Parar de usar** volta para o template padrão.

Sem chave do Gemini, dá para converter à mão: baixe o original, troque o conteúdo pelas variáveis abaixo e envie o template editado. Um arquivo que já tem `{{ s.nome }}` é aceito direto.

A faixa "Prévia criada por..." e o `noindex` são colocados automaticamente em todo site gerado por modelo.

Variáveis do objeto `s`:

```
s.nome, s.categoria, s.regiao, s.endereco, s.telefone, s.instagram
s.slogan, s.subtitulo, s.sobre            textos (IA ou padrão do nicho)
s.servicos      lista de {titulo, descricao}
s.diferenciais  lista de textos curtos
s.cta_texto     texto do botão principal
s.cta_link      link do botão principal (WhatsApp ou telefone; pode ser vazio)
s.cta_tipo      "whatsapp", "telefone" ou vazio
s.link_whatsapp, s.link_telefone, s.link_maps, s.mapa_embed (URL para <iframe>)
s.nota          ex.: "4,7" (vazio se não tiver)
s.avaliacoes    número de avaliações no Google
s.horarios      lista de {dia, horas}
s.depoimentos   lista de {autor, estrelas, texto} (avaliações reais do Google)
s.logo          arquivo da logo (pode ser vazio: use s.iniciais no lugar)
s.foto_principal  foto do topo (pode ser vazia)
s.foto_real     true se a foto_principal é do próprio negócio
s.galeria       lista de arquivos de fotos do negócio
s.imagem_detalhe, s.imagem_textura   imagens do seu banco do nicho (podem ser vazias)
s.cor.destaque, s.cor.sobre_destaque, s.cor.fundo, s.cor.superficie,
s.cor.texto, s.cor.texto_suave, s.cor.profundo   cores tiradas da logo do cliente
s.iniciais, s.ano
```

Exemplo: `<h1>{{ s.nome }}</h1>`, `{% for f in s.galeria %}<img src="{{ f }}">{% endfor %}`,
`{% if s.nota %}{{ s.nota }} no Google{% endif %}`.

## Galeria, avaliações e nota de dados

Para cada lead sem site, o bot também pega **até 8 fotos** da galeria do Maps, **até 5 avaliações reais** com texto (só de 4 ou 5 estrelas, e só o primeiro nome do autor) e a **descrição do dono**. O site ganha as seções de galeria e "O que dizem no Google". A IA usa a descrição e o que os clientes elogiam para escrever textos específicos daquele negócio.

Cada lead recebe uma nota de **Dados de 0 a 10**:
- **Completo** (6 ou mais): gera normalmente.
- **Médio** (3 a 5): gera, mas confira antes de enviar.
- **Fraco** (menos de 3): a geração em lote pula, a não ser que você marque "Incluir leads com poucos dados".

Passe o mouse sobre o selo para ver o que falta. A coleta extra deixa cada local uns segundos mais lento; dá para desligar na tela de busca.

## Imagens e material de consulta por nicho

Na aba **Nichos e roteiros**, embaixo do formulário, cada nicho tem duas áreas:

**Imagens do nicho**: imagens suas (Unsplash, Pexels ou feitas por você) que podem entrar nos sites. Cada uma tem uma função, e só aparece no lugar daquela função:

| Função | Onde aparece |
|---|---|
| Topo (sem foto real) | No topo, **só** quando o negócio não tem nenhuma foto no Maps |
| Entre as seções | Imagem ilustrativa ao lado do "Quem somos" ou entre as seções |
| Fundo da chamada | Atrás da chamada final, escurecida |

Elas nunca ocupam o lugar das fotos do próprio negócio. Prefira detalhes do ramo (halteres, massa de pizza, bíblia aberta) a fotos de recepção, fachada ou pessoas: o dono sabe que aquele lugar não é o dele. Com várias imagens da mesma função, cada lead recebe uma diferente, e sempre a mesma se você gerar de novo.

**Material de consulta da IA**: arquivos .txt, .md, .csv, .json ou .pdf que a IA lê antes de escrever, como serviços comuns do ramo, palavras que o público usa, regras do conselho da profissão ou textos que você gosta. Vão até 6.000 caracteres por site (cerca de 1.500 tokens). O que passar disso é cortado, então coloque o mais importante primeiro.

Tudo fica em `dados/arquivos_nicho/<nicho>/`.

## Configuração do `.env`

| Variável | Para quê |
|---|---|
| `GEMINI_API_KEY` | Textos personalizados por IA. É grátis em aistudio.google.com/apikey. Sem chave, usa os textos padrão do nicho. |
| `NETLIFY_TOKEN` / `NETLIFY_SITE_ID` | Publicar os demos. Crie **um** site vazio no Netlify só para os demos. |
| `URL_DEMOS` | Endereço desse site, ex.: `https://victor-demos.netlify.app`. É o link que vai na mensagem. |
| `SEU_WHATSAPP` | Coloca o botão "Quero este site" na faixa de prévia, que manda o cliente para você. |

## Quanto custa

- **Busca**: grátis, porque o bot usa seu navegador.
- **IA**: cerca de 1.000 tokens por site, com o "pensamento" do modelo desligado. O plano grátis do Gemini cobre bem o começo. Os limites mudam, então confira em ai.google.dev/pricing. A IA só escreve os textos; o HTML vem pronto do template. Os textos ficam salvos, então "Gerar de novo" não gasta token, só "Gerar com textos novos".
- **Netlify**: o plano grátis basta. Todos os demos ficam num site só, cada um numa pasta.

## Estrutura

```
app.py                  servidor do painel (FastAPI) + API
core/
  scraper.py            bot do Maps (Playwright), com os seletores no topo
  limpeza.py            limpa texto, classifica site, acha WhatsApp/Instagram
  db.py                 banco SQLite dos leads
  nichos.py             lê e salva nichos e regiões
  ia.py                 chamada ao Gemini com fallback sem IA
  arquivos_nicho.py     uploads de imagens e material de consulta
  modelos.py            modelo de site do nicho (upload, conversão, prévia)
  qualidade.py          nota de dados de cada lead
  cores.py              pega a cor da logo e monta a paleta
  gerador.py            junta tudo e gera o site
  deploy.py             publica no Netlify
  exportar.py           Excel e JSON
dados/nichos/*.json     um roteiro por nicho (edite pelo painel)
dados/arquivos_nicho/   imagens e material de consulta de cada nicho
dados/regioes.json      lista de regiões
templates_sites/        padrao (claro), escuro, academia e os modelo-<nicho> que você enviar
painel/                 o painel (HTML, CSS e JS puros)
saida/sites/            os demos gerados
testes/                 testes (python -m pytest testes)
```

### Criar um template novo

Copie `templates_sites/padrao` para `templates_sites/meu-template`, edite o `index.html.j2` e ele aparece no select de templates do nicho. As variáveis disponíveis são `lead` (dados do Maps), `t` (textos), `cor` (paleta), `logo`, `foto` e `link_whatsapp`. Veja os dois templates como exemplo.

## Cuidados

- **O Google muda o Maps.** Se algum campo parar de vir (nota, horário, foto), ajuste o seletor em `SELETORES` no topo do `core/scraper.py`. Raspar o Maps vai contra os termos do Google: use limites baixos por região, porque é isso que evita bloqueio. O mesmo vale para o Instagram.
- **WhatsApp**: o envio fica de propósito com um clique seu por lead. Disparo automático em massa é o jeito mais rápido de ter o número banido. Mande poucas mensagens por dia, ajuste o texto e responda rápido.
- **LGPD**: você usa dados públicos de empresas para uma abordagem comercial pontual. Se alguém pedir para não ser contatado, marque o lead como "Não quis" e não insista.
- **Os demos usam a marca de outra empresa.** Por isso eles têm `noindex` e não aparecem no Google, e trazem a faixa "Prévia criada por...". Apague o demo de quem não fechou: botão "Apagar demo" e depois publique de novo.
- O template nunca inventa depoimentos. Ele mostra só a nota real do Google.

## Próximos passos

- Mais templates por nicho (ex.: um específico para igrejas com agenda de cultos)
- Rodar a busca agendada (ex.: toda segunda, 3 regiões novas)
- Extensão do Chrome ou integração com WhatsApp Business para registrar respostas automaticamente
- Página de "proposta" com preços para enviar depois que o lead responder
# prospecta
