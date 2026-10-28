-- Ajustes do painel (ex.: o seu nome, usado na mensagem de WhatsApp)
create table public.ajustes (
  chave text primary key,
  valor text not null default ''
);
alter table public.ajustes enable row level security;
create policy "acesso_painel_ajustes" on public.ajustes for all to anon, authenticated using (true) with check (true);
grant select, insert, update, delete on public.ajustes to anon, authenticated;
insert into public.ajustes (chave, valor) values ('seu_nome', 'Victor Miguel');
