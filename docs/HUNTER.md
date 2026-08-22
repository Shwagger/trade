# AI Demand Hunter — le mode d'emploi

Un chasseur de demande. Il lit les endroits publics où des gens écrivent
eux-mêmes leur problème, jette 90 % de ce qu'il trouve, et te rend une liste
courte de demandes qui méritent dix minutes de ton temps — avec le prix et le
message déjà écrits.

Ce qu'il ne fait pas, et ne fera pas : envoyer. Aucun message n'est envoyé
automatiquement, aucun compte n'est créé, aucune plateforme n'est automatisée.
La machine chasse, l'humain parle. C'est à la fois la ligne éthique et la ligne
qui évite de faire bannir tes comptes.

---

## Trois commandes pour commencer

```bash
python -m hunter hunt --demo         # 1. hors ligne, sur des annonces synthétiques
python -m hunter hunt                # 2. la vraie chasse
python -m hunter draft <id>          # 3. le message prêt + le détail du score
```

Aucune dépendance : le chasseur n'utilise que la bibliothèque standard de
Python. Si `python -m hunter hunt --demo` affiche un rapport, l'installation
est terminée.

---

## Le cycle complet

```
   sources publiques           hunt
   (Reddit, HN, RSS…)     ────────────►  16 posts lus
           │                                  │
           │                             qualification      score 0-100, HOT / WARM / IGNORE
           │                                  │
           │                             extraction         budget, délai, catégorie, canal de réponse
           │                                  │
           │                             préparation        prix conseillé + message écrit
           ▼                                  ▼
     leads.jsonl  ◄──────────────────  4 HOT, 7 WARM
                                            │
                     TOI  ──────────────────┘   tu lis, tu adaptes une ligne, tu envoies
                      │
                      ▼
        python -m hunter mark <id> sent -n "envoyé en DM"
                      │
                      ▼
        python -m hunter pipeline      trouvés → envoyés → répondus → gagnés
```

---

## Le protocole des premiers jours

L'erreur classique est de construire un système avant d'avoir prouvé que
quelqu'un paie. Le chasseur est déjà construit : il ne reste qu'à s'en servir.

| Jour | Objectif | Commande |
|---|---|---|
| 1 | trouver de la demande réelle | `hunt` matin et soir, `list --tier HOT` |
| 1-2 | première conversation | `draft <id>`, tu relis, tu envoies toi-même, `mark <id> sent` |
| 2-5 | première vente, même 20 $ | répondre vite ; livrer la preuve gratuite avant de parler prix |
| 5 | comprendre **pourquoi** il a payé | `mark <id> won -n "il voulait juste le CSV, livré en 3h"` |
| 6-9 | répéter la même offre | `market` puis `niche` : ce qui revient devient ton produit |

Deux règles de discipline :

1. **Si trois jours de chasse ne donnent aucun HOT crédible, la piste est
   mauvaise.** Change de sources ou de catégories — n'attends pas neuf jours.
2. **N'automatise rien de plus avant la première vente.** Le chasseur suffit.

---

## Comment le score est calculé

Le score répond à une seule question : *quelle est la probabilité que cette
personne paie quelqu'un, bientôt, pour quelque chose que tu sais livrer ?*
Chaque point vient d'un mot précis du post, et `hunter draft <id>` te montre
lesquels :

```
POURQUOI CE SCORE
  score 100/100 -> HOT
    +   22 demande explicite    « Need someone »
    +   18 recrute              « [HIRING] »
    +   16 paiement annoncé     « budget »
    + 18.0 montant chiffré      « USD 300-500 »
    + 10.0 urgence              « ASAP »
    +    6 chemin de réponse    « DM »
    +   12 catalogue            « scrape+csv »
    + 12.0 fraîcheur            « moins de 2h »
```

Les trois idées qui font le gros du travail :

- **Un vendeur n'est pas un acheteur.** La moitié des boards freelance est
  faite de gens qui se vendent eux-mêmes. `[FOR HIRE] développeur senior
  disponible` marque zéro, volontairement.
- **De l'argent écrit vaut mieux que de l'enthousiasme.** « budget 400 $ »
  pèse plus que trois paragraphes sur une opportunité passionnante.
- **Ce qui est vieux est mort.** Une demande de quatre jours a déjà vingt
  réponses. La fraîcheur fait partie du score, pas de la décoration.

Sont éliminés d'office : le travail non payé (« equity only », « exposure »),
les arnaques, les concours spéculatifs, les posts de deux lignes.

Seuils : **HOT ≥ 70** (à traiter aujourd'hui), **WARM ≥ 45** (si le HOT est
vide), en dessous on ne regarde plus jamais.

---

## L'angle mort : la demande que personne ne sert

```bash
python -m hunter niche --days 14
```

`market` répond à « laquelle de mes catégories est la plus demandée ». `niche`
répond à une question plus intéressante : **qu'est-ce que les gens redemandent
sans arrêt, sans que personne ne le vende ?** C'est là que se cache un business
que personne n'a remarqué — pas dans une catégorie qui a déjà mille freelances.

```
  1. « instagram dms »   score 65/100
     3 demandes (0 chaudes) · budget médian $180 · 1 réponse par annonce · 100 % hors catalogue
       946538acb8  [HIRING] Auto-answer the same 5 questions in our Instagram DMs
       afade598b6  [HIRING] Someone to auto-answer our Instagram DMs about prices
       e7c6b5a222  Need help answering repetitive Instagram DMs for my bakery

  CE QUE ÇA VEUT DIRE
  « instagram dms » revient 3 fois et ton catalogue ne le couvre pas.
  C'est l'angle mort : écris l'offre standardisée, puis reprends ces 3 annonces une par une.
```

Le classement combine quatre mesures, toutes explicites dans le code
(`hunter/niche.py`) :

| poids | mesure | pourquoi |
|---|---|---|
| 0,35 | **répétition** | une niche, c'est ce qui revient |
| 0,20 | **spécificité** | « instagram dms » nomme un business, « questions » nomme un sujet |
| 0,15 | **argent** (plafonné à 400 $) | pour qu'un seul budget à 3 000 $ ne couronne pas un terme |
| 0,15 | **rareté** | moins il y a de réponses sous l'annonce, mieux c'est |
| 0,15 | **angle mort** | la part des demandes que le catalogue ne couvre pas |

### Le détail qui rend ça possible

Une demande hors catalogue est pénalisée dans le score d'intention (−10) : c'est
voulu, tu ne veux pas passer ta matinée sur un truc que tu ne sais pas livrer.
Mais du coup une niche non servie est **invisible par construction** — elle
tombe en IGNORE avant d'avoir été comptée.

Chaque lead porte donc deux notes :

- `score` — dois-je répondre à ça aujourd'hui ? (catalogue compris)
- `demand_score` — est-ce que quelqu'un veut vraiment payer ? (catalogue ignoré)

`niche` lit la seconde, avec un seuil plus bas (35) que le seuil de réponse :
un motif est fait de beaucoup de signaux faibles, pas d'un seul signal fort.

Et comme partout ailleurs, sous 25 demandes qualifiées il refuse de nommer quoi
que ce soit. Trois coïncidences ressemblent exactement à une tendance.

---

## Comment le prix est calculé

Chaque catégorie a un *playbook* (`hunter/playbook.py`) : un périmètre fixe,
un délai, un plancher sous lequel le job ne vaut pas le temps passé, et un prix
d'ancrage. Le prix conseillé suit trois règles :

1. jamais au-dessus du budget annoncé ;
2. 75 % du haut de leur fourchette quand ils ont annoncé une fourchette ;
3. un taux horaire est converti en forfait — le forfait se vend mieux et
   protège ton temps.

Quand le budget annoncé est sous le plancher, le chasseur le dit : à prendre
seulement comme première référence client, sinon passer.

Pour changer tes prix, édite `floor_usd` / `target_usd` dans
`hunter/playbook.py`. C'est fait pour être modifié.

---

## Le message

Il suit la seule structure qui obtient des réponses sur un board public :

1. la preuve que tu as lu le post (leurs mots, cités) ;
2. exactement ce que tu livres — trois lignes, sans brouillard ;
3. **quelque chose de gratuit, livré avant tout paiement** (les 20 premières
   lignes du CSV, les 15 premières secondes du montage, le diagnostic écrit) ;
4. un prix et une date ;
5. une question, pour que répondre soit plus facile qu'ignorer.

`--lang en|fr|pt` change la langue. **Le portugais est complet** : les 13
playbooks (puces métier, preuve gratuite, question de qualification) sont
traduits en pt-BR dans `hunter/i18n_pt.py`. Le français ne traduit que la
structure du message — les puces métier restent en anglais. Relis toujours
avant d'envoyer, ce que tu dois faire de toute façon.

**Le prix est cité dans la monnaie de l'acheteur.** Si l'annonce dit
« R$800 », le message dit « R$450 », pas « $85 » — et ton rapport, lui, garde
l'équivalent en dollars pour que tous les leads restent comparables. Sans
budget annoncé, la monnaie suit la langue : `pt` → BRL, `fr` → EUR, `en` → USD.
Les taux de change sont dans `hunter/extract.py`, statiques et approximatifs :
ils servent à comparer des leads, pas à facturer.

`--llm` fait repasser les messages HOT par un modèle local (Ollama, gratuit,
hors ligne). Si Ollama ne tourne pas, le message template est conservé, sans
erreur.

---

## Ce que le marché demande

C'est la sortie stratégique, et elle vaut autant que les leads :

```bash
python -m hunter market --days 14
```

```
  catégorie                      part  posts  HOT  budget médian
  Automatisation / intégration  31.0%      9    4  $900     #######
  Scraping / listes de données  17.2%      5    2  $350     ####
  ...
  -> le marché te dit de vendre : Automatisation / intégration (9 demandes, 4 chaudes)
     standardise cette offre avant d'en ajouter une deuxième.
```

Sous 15 demandes qualifiées, il refuse de conclure et te le dit. Lire un
échantillon de 4 posts, c'est deviner avec des étapes en plus.

---

## Les sources

Tout est gratuit, public, en lecture seule, sans clé d'API. Configuration dans
`config/hunter.json` :

| source | ce qu'on y trouve | remarque |
|---|---|---|
| `reddit` | r/forhire, r/hiring, r/slavelabour… | la plus dense en « je paie pour X » |
| `hn` | le fil mensuel *Freelancer? Seeking freelancer?* | budgets plus élevés, moins de volume |
| `remoteok` | missions contract / freelance | surtout des postes salariés, filtre activé |
| `rss` | n'importe quel flux | désactivé par défaut |

Le marché brésilien est activé : `brdev` et `empreendedorismo` sont dans la
liste des subreddits, et le scoring lit le portugais (« preciso de alguém »,
« orçamento », « pago no Pix » comptent comme des signaux ; « CLT », « permuta »,
« divisão de lucros » éliminent l'annonce). Si un de ces subreddits renvoie
`FAIL` à chaque chasse, il n'existe pas ou il est fermé — supprime-le de
`config/hunter.json`. Pour ajouter d'autres sources lusophones, une alerte
Google sur `"preciso de alguém para"` ou `"procuro freelancer"` en flux RSS
marche exactement pareil.

**Ajouter un radar gratuit en deux minutes** : crée une alerte Google sur
`"need someone to build"` ou `"looking for a freelancer"`, choisis « flux RSS »
comme mode de livraison, colle l'URL dans `config/hunter.json` → `rss.feeds`,
mets `enabled: true`.

Limites connues, dites franchement :

- **Reddit bloque souvent les IP de datacenter** (403). Depuis ta machine ça
  passe ; depuis GitHub Actions, souvent pas. HN et les flux RSS passent des
  deux côtés. Le rapport te dit toujours quelle source a échoué et pourquoi.
- `--rate` est le délai entre deux requêtes (2 s par défaut dans le workflow).
  Ne descends pas en dessous de 1 s : tu te ferais limiter, et ce serait mérité.
- Les plateformes freelance (Contra, Upwork, Fiverr…) changent régulièrement
  leurs conditions et leurs frais. Vérifie toi-même les conditions du moment
  avant de bâtir ta stratégie dessus — ce dépôt ne les lit pas.

---

## Chasser pendant que tu dors

`.github/workflows/hunter.yml` lance une chasse toutes les deux heures sur les
serveurs de GitHub, et t'envoie les leads HOT sur Telegram.

```
Settings -> Secrets and variables -> Actions -> New repository secret
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
```

(La procédure pour obtenir ces deux valeurs est en tête de `forexai/notify.py`.)

**Le dépôt est public**, donc `state/hunter/` est dans `.gitignore` : tes leads
et tes notes ne sont jamais committés. Le workflow garde sa mémoire dans le
cache Actions, et publie le tableau de bord + les leads en artefact
téléchargeable à la fin de chaque run.

---

## Toutes les commandes

```bash
python -m hunter hunt [--demo] [--sources reddit,hn] [--lang en|fr|pt]
                      [--html state/hunter/dashboard.html] [--telegram] [--llm]
python -m hunter list [--tier HOT] [--status new] [--category automation] [--json]
python -m hunter draft <id> [--lang fr] [--llm]
python -m hunter mark <id> new|drafted|sent|replied|won|dead [-n "note"]
python -m hunter pipeline
python -m hunter market [--days 14]
python -m hunter niche [--days 14] [--min-count 3]
python -m hunter html [--out chemin.html]
python -m hunter sources
```

L'état vit dans `state/hunter/leads.jsonl` : un lead par ligne, en clair. Tu
peux l'ouvrir, corriger un statut à la main, en supprimer un. Le chasseur ne
réécrit jamais ton statut, tes notes, ni un message que tu as déjà retouché.

---

## Le tableau de bord

```bash
python -m hunter hunt --html state/hunter/dashboard.html
```

Une page HTML autonome : filtres HOT / WARM, le message copiable en un clic,
le lien vers l'annonce, et la table de la demande. Ouvre-la dans un navigateur,
ou envoie-la sur ton téléphone.
