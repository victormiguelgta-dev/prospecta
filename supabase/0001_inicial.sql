-- Prospecta: banco no Supabase (Postgres)
-- Tabelas: leads, contatos (histórico), nichos, regioes, pedidos (fila de tarefas para o PC)
-- e trabalhador (sinal de "PC ligado").

create table public.leads (
  id text primary key,                -- ID do local no Google Maps
  nicho text,
  regiao text,
  nome text not null,
  categoria text,
  endereco text,
  telefone text,
  whatsapp text,                      -- número pronto pro wa.me (ex.: 5561999998888)
  email text,
  site text,
  situacao_site text,                 -- sem_site | so_rede_social | site_fraco | fora_do_ar | site_proprio
  instagram text,
  redes jsonb not null default '{}'::jsonb,
  redes_origem text,
  instagram_seguidores integer,
  instagram_posts integer,
  logo_url text,
  cores jsonb,                        -- cores tiradas da logo (para o pacote)
  maps_url text,
  lat double precision,
  lng double precision,
  nota real,
  avaliacoes integer,
  horario jsonb,
  fotos jsonb,
  descricao text,
  avaliacoes_lidas jsonb,             -- só para classificar
  sinais jsonb,
  nota_potencial integer,
  classe text check (classe in ('potencial', 'talvez', 'pouco')),
  nota_detalhe jsonb,
  saude_maps integer,
  problemas_maps jsonb,
  oportunidades jsonb,
  servico_principal text,
  analise_ia jsonb,
  analisado_em timestamptz,
  etapa text not null default 'lead_novo'
    check (etapa in ('lead_novo', 'em_contato', 'interessado', 'fechado')),
  estado text not null default 'ativo'
    check (estado in ('ativo', 'congelado', 'arquivado', 'descartado')),
  motivo text,
  proximo_passo text,
  data_proximo_passo date,
  observacoes text,
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  etapa_em timestamptz not null default now()
);
create index leads_estado_etapa on public.leads (estado, etapa);
create index leads_nota on public.leads (nota_potencial desc nulls last);
create index leads_nome on public.leads (lower(nome));

create table public.contatos (
  id bigint generated always as identity primary key,
  lead_id text not null references public.leads (id) on delete cascade,
  data timestamptz not null default now(),
  tipo text not null check (tipo in ('ligacao', 'whatsapp', 'visita', 'email', 'anotacao')),
  anotacao text
);
create index contatos_lead on public.contatos (lead_id, data desc);

create table public.nichos (
  id text primary key,
  nome text not null,
  termo_busca text not null,
  icone text not null default '✦',
  agenda boolean not null default false,
  pedido_online boolean not null default false
);

create table public.regioes (
  nome text primary key,
  ordem integer not null default 0
);

create table public.pedidos (
  id bigint generated always as identity primary key,
  tipo text not null check (tipo in ('busca', 'analisar', 'recoletar', 'diagnostico')),
  parametros jsonb not null default '{}'::jsonb,
  status text not null default 'pendente'
    check (status in ('pendente', 'rodando', 'concluido', 'erro', 'cancelado')),
  parar boolean not null default false,
  log jsonb not null default '[]'::jsonb,
  resultado jsonb,
  criado_em timestamptz not null default now(),
  iniciado_em timestamptz,
  concluido_em timestamptz
);
create index pedidos_status on public.pedidos (status, criado_em);

create table public.trabalhador (
  id text primary key,
  visto_em timestamptz not null default now(),
  ia boolean not null default false,
  modelo_ia text
);

-- O PC acrescenta linhas ao log de um pedido sem reescrever o log inteiro
create function public.adicionar_log(pedido bigint, linhas text[])
returns void language sql security invoker set search_path = '' as $$
  update public.pedidos set log = log || to_jsonb(linhas) where id = pedido;
$$;

-- atualizado_em sempre em dia; etapa_em muda quando a etapa muda
create function public.marcar_atualizacao()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  new.atualizado_em := now();
  if new.etapa is distinct from old.etapa then
    new.etapa_em := now();
  end if;
  return new;
end;
$$;
create trigger leads_atualizacao before update on public.leads
  for each row execute function public.marcar_atualizacao();

-- Acesso: o painel não tem login (decisão do dono). As políticas abaixo liberam
-- leitura e escrita para quem tiver a chave pública. Para ligar o login depois,
-- troque "to anon, authenticated" por "to authenticated" nas políticas.
alter table public.leads enable row level security;
alter table public.contatos enable row level security;
alter table public.nichos enable row level security;
alter table public.regioes enable row level security;
alter table public.pedidos enable row level security;
alter table public.trabalhador enable row level security;
create policy "acesso_painel_leads" on public.leads for all to anon, authenticated using (true) with check (true);
create policy "acesso_painel_contatos" on public.contatos for all to anon, authenticated using (true) with check (true);
create policy "acesso_painel_nichos" on public.nichos for all to anon, authenticated using (true) with check (true);
create policy "acesso_painel_regioes" on public.regioes for all to anon, authenticated using (true) with check (true);
create policy "acesso_painel_pedidos" on public.pedidos for all to anon, authenticated using (true) with check (true);
create policy "acesso_painel_trabalhador" on public.trabalhador for all to anon, authenticated using (true) with check (true);
grant select, insert, update, delete on public.leads, public.contatos, public.nichos, public.regioes, public.pedidos, public.trabalhador to anon, authenticated;
grant execute on function public.adicionar_log(bigint, text[]) to anon, authenticated;

-- Nichos e regiões iniciais
insert into public.nichos (id, nome, termo_busca, icone, agenda, pedido_online) values
  ('academias', 'Academias', 'Academia', '🏋', true, false),
  ('advocacia', 'Escritórios de advocacia', 'Escritório de advocacia', '⚖', true, false),
  ('barbearias', 'Barbearias', 'Barbearia', '✂', true, false),
  ('clinicas-odontologicas', 'Clínicas odontológicas', 'Clínica odontológica', '🦷', true, false),
  ('igrejas', 'Igrejas', 'Igreja Evangélica', '✝', false, false),
  ('pizzarias', 'Pizzarias', 'Pizzaria', '🍕', false, true);
insert into public.regioes (nome, ordem) values
  ('Ceilândia, DF', 0),
  ('Taguatinga, DF', 1),
  ('Samambaia, DF', 2),
  ('Plano Piloto, DF', 3),
  ('Asa Sul, DF', 4),
  ('Asa Norte, DF', 5),
  ('Gama, DF', 6),
  ('Planaltina, DF', 7),
  ('Santa Maria, DF', 8),
  ('Recanto das Emas, DF', 9),
  ('Vicente Pires, DF', 10),
  ('Águas Claras, DF', 11),
  ('Riacho Fundo, DF', 12),
  ('Riacho Fundo II, DF', 13),
  ('Sobradinho, DF', 14),
  ('Sobradinho II, DF', 15),
  ('São Sebastião, DF', 16),
  ('Guará, DF', 17),
  ('Paranoá, DF', 18),
  ('Itapoã, DF', 19),
  ('Sudoeste, DF', 20),
  ('Brazlândia, DF', 21),
  ('Candangolândia, DF', 22),
  ('Núcleo Bandeirante, DF', 23),
  ('Cruzeiro, DF', 24),
  ('Jardim Botânico, DF', 25),
  ('Sol Nascente, DF', 26),
  ('Luziânia, GO', 27),
  ('Valparaíso de Goiás, GO', 28),
  ('Águas Lindas de Goiás, GO', 29),
  ('Novo Gama, GO', 30),
  ('Formosa, GO', 31),
  ('Planaltina, GO', 32),
  ('Santo Antônio do Descoberto, GO', 33),
  ('Cidade Ocidental, GO', 34);
