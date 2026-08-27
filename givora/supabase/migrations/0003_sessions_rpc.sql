-- =====================================================================
-- Givora — migration 0003
-- Enregistrement des sessions : le dénominateur du taux de clic.
--
-- Une fonction plutôt qu'un upsert côté application, pour une raison
-- précise : on veut incrémenter pages_viewed SANS écraser first_seen ni
-- la source d'origine. Un upsert classique réécrirait les deux à chaque
-- page vue, et l'attribution de campagne serait perdue dès le deuxième
-- écran.
-- =====================================================================

create or replace function public.givora_touch_session(
  p_session_id text,
  p_source     jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.sessions (session_id, source, pages_viewed)
  values (p_session_id, coalesce(p_source, '{}'::jsonb), 1)
  on conflict (session_id) do update
    set pages_viewed = public.sessions.pages_viewed + 1,
        -- La source n'est écrite qu'une fois : la PREMIÈRE origine gagne.
        -- Un lien WhatsApp partagé ne doit pas voler l'attribution de la
        -- campagne qui a réellement amené la personne.
        source = case
                   when public.sessions.source = '{}'::jsonb
                     then coalesce(p_source, '{}'::jsonb)
                   else public.sessions.source
                 end;
end;
$$;

comment on function public.givora_touch_session is
  'Crée ou touche une session. Préserve first_seen et la source d''origine.';

-- Index de lecture pour /admin : « les clics du jour » et le regroupement
-- par marketplace passent tous les deux par ces jointures.
create index if not exists clicks_suggestion_clicked_idx
  on public.clicks (suggestion_id, clicked_at desc);
