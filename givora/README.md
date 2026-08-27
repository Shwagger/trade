# Givora — phase 1

Site mobile-first en portugais brésilien : l'utilisateur décrit une personne en
quatre écrans, on lui rend trois idées de cadeau avec une phrase de
justification et un lien vers le marketplace.

**Ce dépôt contient la phase 1 uniquement** : le parcours complet, la
persistance et le schéma de base. Le moteur IA (phase 2) et l'affiliation +
tracking (phase 3) ne sont pas encore là — voir « Ce qui n'est PAS fait » plus
bas.

## Démarrer

```bash
npm install
npm run dev        # http://localhost:3000
```

Sans variables d'environnement, l'app tourne quand même : le store bascule sur
une version **en mémoire** (voir `src/lib/store.ts`), pratique pour regarder le
parcours tout de suite. Tout est perdu au redémarrage du serveur.

Pour brancher Supabase :

```bash
cp .env.example .env.local   # puis remplir les deux variables
```

et appliquer `supabase/migrations/0001_init.sql` (SQL editor Supabase, ou
`supabase db push`).

Autres commandes : `npm run build`, `npm run lint`, `npm run typecheck`.

## Le parcours

| Écran | Route | Contenu |
|---|---|---|
| 1 | `/` | Quem vai ganhar o presente ? — 12 relations, un tap = écran suivant |
| 2 | `/` | Idade + o que curte — chips d'âge, champ libre, 20 chips d'intérêt |
| 3 | `/` | Qual é a ocasião ? — 7 occasions, un tap = écran suivant |
| 4 | `/` | Quanto quer gastar ? — 4 tranches, le tap déclenche l'envoi |
| → | `/resultado/[requestId]` | Les 3 cartes, « refinar », partage WhatsApp |

Sept taps et une phrase tapée du début à la fin. Les quatre écrans vivent dans
un seul composant client (`src/app/page.tsx`) : quatre `useState` et un index
d'étape, aucun state manager.

## Architecture

```
src/
  app/
    page.tsx                      formulaire 4 étapes (client)
    resultado/[requestId]/page.tsx  composant serveur : lit la demande en base
    api/request/route.ts          crée recipient + request, renvoie l'id
    api/recommend/route.ts        génère les 3 suggestions et les persiste
  components/
    StepShell.tsx / Progress.tsx  gabarit commun aux 4 écrans
    ResultView.tsx                cartes, skeleton, refinar, WhatsApp (client)
    SuggestionCard.tsx            une carte
    SuggestionSkeleton.tsx        même gabarit que la carte, en gris
  lib/
    constants.ts                  TOUTES les options du formulaire
    store.ts                      accès données (Supabase, sinon mémoire)
    supabase.ts                   client service_role, serveur uniquement
    marketplace.ts                PROVISOIRE — remplacé par affiliates.ts en phase 3
    recommend/stub.ts             PROVISOIRE — remplacé par l'appel Anthropic en phase 2
supabase/migrations/0001_init.sql  les 6 tables, RLS activée partout
```

Deux routes séparées et pas une seule, volontairement : `/api/request` écrit la
demande en base **avant** que le moteur tourne. Si le moteur tombe, la demande
est quand même enregistrée — c'est la seule façon de mesurer les abandons plus
tard.

La migration crée les six tables du modèle (`recipients`, `requests`,
`suggestions`, `clicks`, `sessions`, `reminders`), y compris celles que les
phases 2 et 3 utiliseront, pour ne pas re-migrer deux fois.

## Ce qui n'est PAS fait (par design)

- **Phase 2 — moteur IA.** `src/lib/recommend/stub.ts` est un catalogue de 12
  produits en dur, avec un score par mots-clés. Il respecte déjà les contraintes
  produit (3 catégories différentes, une phrase de justification qui cite un
  détail donné par l'utilisateur, filtrage par budget) pour que le rendu final
  soit réaliste, mais **ce n'est pas de l'IA**. En phase 2, `/api/recommend`
  appellera Anthropic, validera avec Zod, retentera une fois, et posera un rate
  limit par IP. Le contrat de sortie ne bouge pas : rien d'autre à modifier.
- **Phase 3 — affiliation et tracking.** Les boutons pointent aujourd'hui
  directement vers l'URL de recherche publique du marketplace, sans tag
  (`src/lib/marketplace.ts`). `rel="sponsored nofollow noopener"` et
  `target="_blank"` sont déjà posés. En phase 3 : `lib/affiliates.ts`,
  redirection via `/go/[suggestionId]`, middleware `session_id`, page `/admin`.
  Les tables `clicks` et `sessions` existent déjà et sont vides.

Limite connue du stub : sur « R$ 300 ou plus », les fourchettes de prix affichées
sont hautes alors que le catalogue est du milieu de gamme. Le vrai moteur choisit
des produits adaptés au budget — ça se règle en phase 2.
