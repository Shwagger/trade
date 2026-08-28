# Givora

Site mobile-first en portugais brésilien, installable comme une app :
l'utilisateur décrit une personne en quatre écrans, un algorithme local rend
trois idées de cadeau avec une phrase de justification, et chaque lien sortant
est mesuré et monétisé. Aucun coût par recherche.

**La métrique du produit est le taux de clic sortant** (session → clic
marchand). C'est le chiffre en haut de `/admin`, et tout le reste sert à
l'expliquer.

## Mettre en ligne — aucune configuration requise

Le moteur étant déterministe, **l'état de la demande tient dans l'URL** : le
lien `/resultado/<jeton>` contient ce que l'utilisateur a répondu, et les trois
cartes sont recalculées à l'affichage. Aucune base de données n'est nécessaire
pour que le site fonctionne.

1. Sur Vercel, importe le dépôt.
2. **Root Directory : `givora`** (le dépôt contient aussi un autre projet à la
   racine, sinon le build échoue).
3. Déploie. C'est tout — pas une seule variable d'environnement.

Un lien partagé dans un groupe WhatsApp affiche les mêmes trois cartes pour tout
le monde, aujourd'hui et dans six mois.

### Ensuite, dans cet ordre

| Variable | Ce que ça débloque | Sans elle |
|---|---|---|
| `AMAZON_BR_TAG` & co. | **La commission.** C'est le revenu. | Le site marche, le trafic part gratuitement |
| `ADMIN_PASSWORD` | `/admin` : taux de clic, top suggestions | Panneau fermé |
| `NEXT_PUBLIC_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | La **mesure** (sessions, clics, votes partagés) | Le produit marche, on ne mesure rien |

Avec Supabase, applique les migrations de `supabase/migrations/` dans l'ordre.

## En local

```bash
npm install
npm run dev        # http://localhost:3000
```

Commandes : `npm run build`, `npm run lint`, `npm run typecheck`, `npm test`.

## Le moteur — un algorithme, pas un modèle payant

`src/lib/engine/` calcule les trois idées **en local, en quelques
millisecondes, sans appel réseau**. Conséquences directes :

- **coût par session : zéro.** La commission d'affiliation est une marge de
  100 %, et la facture ne bouge pas quand le trafic monte ;
- **réponse instantanée**, donc le parcours tient vraiment sous 30 secondes ;
- **reproductible à graine fixée** : quand une suggestion est mauvaise, on
  rejoue exactement le cas et on lit le détail du calcul (`explain()`) ;
- **rien ne peut inventer** un produit qui n'existe pas.

Quatre pièces :

| Fichier | Rôle |
|---|---|
| `catalog.ts` | ~85 **archétypes** de cadeau. C'est l'actif du produit. |
| `lexicon.ts` | Traduit le portugais réel (« corre no parque », « tá sempre com o cachorro ») en signaux. |
| `score.ts` | Somme pondérée lisible + sélection des 3. |
| `reasons.ts` | La phrase « por que combina ». |

**Des archétypes, pas des produits.** Chaque entrée porte une requête
marketplace qui ramène des dizaines de produits réels : jamais de lien mort,
jamais de rupture de stock, rien à re-synchroniser quand un vendeur disparaît.

**Le scoring** additionne intérêts (poids le plus fort), affinité de relation,
tranche d'âge, occasion, ajustement au budget et prazo, moins les pénalités
(déjà vu, descendu par le groupe, hors sujet). Un bruit déterministe dérivé de
la graine évite que deux profils identiques voient exactement la même chose.
Trois filtres sont **durs** : hors budget, âge inadapté, occasion inadaptée —
ces articles ne s'affichent jamais.

**Les règles produit sont garanties par construction**, pas par une consigne
polie : trois catégories différentes, une seule phrase, et la justification ne
peut citer qu'un signal réellement extrait du texte de l'utilisateur. Sans
signal, elle le dit (« Sem muita pista, essa é a aposta de baixo risco »)
au lieu d'inventer un détail.

`npm test` : 25 tests, dont **800 combinaisons** relation × âge × occasion ×
budget qui doivent toutes rendre 3 idées de 3 catégories, dans le budget.

### L'IA reste possible, éteinte, et payante

`src/lib/recommend/anthropic.ts` existe et fonctionne (sortie structurée,
validation Zod, une relance, rate limit). Il faut **`USE_AI_ENGINE=1` ET une
clé** pour l'allumer — une clé seule ne déclenche jamais de facture. Si l'IA
échoue ou dépasse le délai, l'algorithme reprend la main immédiatement et
l'utilisateur ne voit rien. À rallumer le jour où le volume justifie de payer
pour des justifications rédigées sur mesure ; d'ici là, c'est de l'argent
dépensé pour un gain que le catalogue peut donner gratuitement.

## L'affiliation (phase 3)

**`src/lib/affiliates.ts` est le seul fichier à toucher.** Une entrée par
marketplace, chaque ligne commentée, avec le degré de confiance du format
indiqué honnêtement — Amazon et Magalu sont sûrs, Mercado Livre et Shopee sont
à vérifier dans ton panneau affilié avant de compter sur la commission.

Deux choses que ce fichier fait et qui comptent :

1. **Le filtre de prix est injecté dans l'URL** (`low-price`/`high-price` chez
   Amazon, `_PriceRange_` chez Mercado Livre, `minPrice` chez Shopee). Sans lui
   l'utilisateur atterrit sur une page de résultats où la moitié des produits
   est hors budget, et il repart.
2. **L'URL marchande ne sort jamais dans le HTML.** Tous les liens pointent sur
   `/go/[suggestionId]`, qui enregistre le clic puis redirige en 302. Le tag
   n'est pas lisible dans le code source, et changer de programme
   d'affiliation ne demande pas de re-rendre une seule carte.

### Photos et fiches produit

Les cartes montrent une **illustration de la catégorie** du cadeau, pas une
photo de produit : auto-hébergée, zéro requête, zéro licence, jamais d'image
cassée. C'est honnête — nos entrées sont des catégories, pas des références.

Afficher la vraie photo d'un produit précis suppose le flux produit d'un
marchand. `src/lib/products.ts` est la couche prête à recevoir ça ; elle renvoie
`null` tant qu'aucun identifiant n'est configuré, et les cartes retombent sur
l'illustration. Le plus accessible est **Mercado Livre** (compte développeur
gratuit) ; Amazon PA-API exige trois ventes qualifiantes avant de donner
l'accès, ce n'est donc pas une option au démarrage.

### Aller jusqu'au produit exact

Les liens visent aujourd'hui une **page de résultats filtrée**, pas une fiche
produit : atteindre la fiche demande les API produit des marchands (Amazon
PA-API, API Mercado Livre), qui ont chacune leur inscription et leurs
credentials. C'est un choix conscient, pas un raccourci — un lien produit deviné
tombe en 404 ou sur une rupture de stock, ce qui coûte plus de commissions qu'il
n'en rapporte. Quand les credentials seront là, la résolution s'insère dans
`buildAffiliateUrl` sans toucher au reste.

## Ce qui nous démarque

Quatre choses que les « AI gift finder » concurrents ne font pas :

1. **On lui rend ses propres mots.** La phrase qu'il a tapée est affichée en
   citation au-dessus des cartes, et chaque justification doit citer un détail
   qu'il a réellement donné — c'est une règle vérifiée côté serveur, pas une
   consigne polie dans un prompt.
2. **Le prazo.** « Precisa chegar até quando ? » : sous deux jours le moteur
   privilégie le numérique. Le retard est la vraie angoisse du cadeau.
3. **Le vote du groupe.** Le lien partagé dans le WhatsApp de la famille devient
   un sondage : 👍/👎 par carte, un avis par personne, décompte visible. Les
   cartes descendues nourrissent le refinar. C'est la boucle de croissance, et
   `requests.shared_at` mesure si elle existe vraiment.
4. **Installable.** Manifeste PWA, `display: standalone`, icônes, safe areas, et
   les trois détails qui trahissent un site web au toucher (flash gris au tap,
   rubber-band, sélection de texte involontaire) sont neutralisés.

## Architecture

```
src/
  app/
    page.tsx                        formulaire 4 étapes (client)
    resultado/[requestId]/page.tsx  composant serveur : demande + votes
    go/[suggestionId]/route.ts      clic -> 302 affilié
    admin/                          panneau, mot de passe par env
    api/request | recommend | vote | share | session | admin-login
    manifest.ts                     PWA
  components/                       StepShell, ResultView, SuggestionCard…
  lib/
    affiliates.ts                   ⚠️ LE fichier de config affiliation
    recommend/{anthropic,prompt,schema,stub}.ts
    store.ts                        Supabase, sinon mémoire
    rate-limit.ts  session.ts  admin-stats.ts  constants.ts
  middleware.ts                     cookie session_id + source utm
supabase/migrations/                0001 schéma, 0002 votes+prazo, 0003 RPC
tests/schema.test.mjs               règles produit du moteur
```

## Limites connues

- **Le rate limit est par instance**, pas global : sur Vercel chaque instance a
  sa mémoire. Ça arrête un script naïf, pas un attaquant. Un compteur partagé
  (Postgres ou Upstash) quand le trafic le justifiera — seule l'implémentation
  de `hit()` change.
- **Le catalogue est un actif éditorial, jamais « fini ».** Sur les profils
  très spécifiques dans la tranche « R$ 300 ou mais », il arrive qu'un seul
  archétype porte le bon signal : les deux autres cartes retombent alors sur
  des valeurs sûres et le disent honnêtement. La correction est d'ajouter des
  archétypes, pas de toucher au scoring.
- **Les formats d'affiliation Mercado Livre et Shopee sont à confirmer** dans
  les panneaux respectifs (voir les commentaires du fichier).
