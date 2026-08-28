-- =====================================================================
-- Givora — migration 0002
-- Deux ajouts produit :
--   1. deadline : « precisa chegar até quando ? ». C'est la vraie
--      angoisse du cadeau, et ça change ce que le moteur propose.
--   2. votes   : le lien /resultado/[id] partagé dans le groupe WhatsApp
--      devient un sondage. C'est la boucle de croissance et ça multiplie
--      les sessions par demande — donc les clics sortants.
-- =====================================================================

-- --- 1. deadline ------------------------------------------------------
-- Nombre de jours disponibles avant l'événement. null = pas de contrainte.
alter table public.requests
  add column if not exists deadline_days integer;

comment on column public.requests.deadline_days is
  'Jours restants avant l''événement. null = sans pressa. Sert au moteur : '
  'sous 2 jours il privilégie le numérique/vale-presente.';

-- --- 2. votes ---------------------------------------------------------
-- Un vote = une personne du groupe qui réagit à une carte.
-- La contrainte unique fait du re-vote une mise à jour, pas un doublon :
-- on veut un avis par personne et par carte, pas du bourrage d'urne.
create table if not exists public.votes (
  id            uuid primary key default gen_random_uuid(),
  suggestion_id uuid not null references public.suggestions(id) on delete cascade,
  request_id    uuid not null references public.requests(id) on delete cascade,
  session_id    text not null,
  value         smallint not null check (value in (-1, 1)),
  created_at    timestamptz not null default now(),
  unique (suggestion_id, session_id)
);

create index if not exists votes_request_id_idx on public.votes (request_id);
create index if not exists votes_suggestion_id_idx on public.votes (suggestion_id);

alter table public.votes enable row level security;

-- --- 3. compteur de partages -----------------------------------------
-- Sur combien de demandes le bouton WhatsApp est-il réellement utilisé ?
-- C'est la métrique qui dit si la boucle virale existe ou si on se raconte
-- des histoires.
alter table public.requests
  add column if not exists shared_at timestamptz;
