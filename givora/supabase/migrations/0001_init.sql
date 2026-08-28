-- =====================================================================
-- Givora — schéma initial (phase 1)
-- Tout est versionné ici. Pour appliquer : coller dans le SQL editor
-- Supabase, ou `supabase db push` si tu utilises la CLI.
-- =====================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------
-- recipients : la personne à qui on offre. Jamais de compte, jamais de
-- donnée identifiante — juste un surnom libre saisi par l'utilisateur.
-- ---------------------------------------------------------------------
create table if not exists public.recipients (
  id          uuid primary key default gen_random_uuid(),
  nickname    text,
  relation    text not null,              -- mae, pai, namorada, amigo...
  age_range   text,                       -- "25-34", saisi via le formulaire
  interests   text[] not null default '{}',
  notes       text,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- requests : une demande = un passage dans le formulaire.
-- recipient_id nullable : on veut pouvoir logger une demande même si
-- l'insert du recipient échoue.
-- ---------------------------------------------------------------------
create table if not exists public.requests (
  id            uuid primary key default gen_random_uuid(),
  recipient_id  uuid references public.recipients(id) on delete set null,
  occasion      text not null,            -- aniversario, natal, dia-das-maes...
  budget_min    integer not null,         -- en BRL, entier
  budget_max    integer,                  -- null = "R$300+", pas de plafond
  raw_input     text,                     -- le texte libre tel que tapé
  created_at    timestamptz not null default now()
);

create index if not exists requests_created_at_idx
  on public.requests (created_at desc);

-- ---------------------------------------------------------------------
-- suggestions : les 3 cartes renvoyées par le moteur (phase 2).
-- position 1..3 = ordre d'affichage, utile pour mesurer quel rang clique.
-- ---------------------------------------------------------------------
create table if not exists public.suggestions (
  id            uuid primary key default gen_random_uuid(),
  request_id    uuid not null references public.requests(id) on delete cascade,
  title         text not null,
  reason        text not null,            -- UNE phrase
  category      text not null,
  search_query  text not null,            -- requête marketplace, 2-5 mots
  price_range   text not null,            -- "R$ 80 - R$ 140"
  marketplace   text not null,            -- amazon_br | mercado_livre | magalu | shopee
  position      smallint not null check (position between 1 and 3),
  created_at    timestamptz not null default now(),
  unique (request_id, position)
);

create index if not exists suggestions_request_id_idx
  on public.suggestions (request_id);

-- ---------------------------------------------------------------------
-- clicks : LA table qui compte. Un clic sortant = /go/[suggestionId].
-- (Écrite en phase 3, créée dès maintenant pour ne pas migrer deux fois.)
-- ---------------------------------------------------------------------
create table if not exists public.clicks (
  id             uuid primary key default gen_random_uuid(),
  suggestion_id  uuid not null references public.suggestions(id) on delete cascade,
  clicked_at     timestamptz not null default now(),
  referrer       text,
  user_agent     text,
  session_id     text
);

create index if not exists clicks_clicked_at_idx on public.clicks (clicked_at desc);
create index if not exists clicks_session_id_idx on public.clicks (session_id);

-- ---------------------------------------------------------------------
-- sessions : dénominateur du taux de clic. Posée par le middleware (phase 3).
-- ---------------------------------------------------------------------
create table if not exists public.sessions (
  id           uuid primary key default gen_random_uuid(),
  session_id   text not null unique,
  first_seen   timestamptz not null default now(),
  source       jsonb not null default '{}'::jsonb,   -- utm_source, utm_medium...
  pages_viewed integer not null default 0
);

create index if not exists sessions_first_seen_idx on public.sessions (first_seen desc);

-- ---------------------------------------------------------------------
-- reminders : "je te rappelle avant l'anniversaire" (phase ultérieure).
-- ---------------------------------------------------------------------
create table if not exists public.reminders (
  id            uuid primary key default gen_random_uuid(),
  recipient_id  uuid not null references public.recipients(id) on delete cascade,
  event_date    date not null,
  channel       text not null,            -- whatsapp | email
  contact       text not null,
  sent_at       timestamptz
);

create index if not exists reminders_event_date_idx on public.reminders (event_date);

-- ---------------------------------------------------------------------
-- RLS : tout est fermé côté client. L'app n'écrit que via la clé
-- service_role depuis des routes serveur — le navigateur ne touche
-- jamais Postgres directement.
-- ---------------------------------------------------------------------
alter table public.recipients  enable row level security;
alter table public.requests    enable row level security;
alter table public.suggestions enable row level security;
alter table public.clicks      enable row level security;
alter table public.sessions    enable row level security;
alter table public.reminders   enable row level security;
