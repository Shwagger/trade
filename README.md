# FOREX AI v2

Système de trading hybride : **analyse technique + machine learning + moteur de
risque**, avec validation walk-forward out-of-sample. Pas de boîte noire
téléchargée sur Internet — le cerveau est ici, dans le dépôt, lisible ligne par
ligne.

```
                    DONNÉES MARCHÉ
                         ↓
                 Feature Engineering          52 features, toutes causales
                         ↓
              ┌──────────┴──────────┐
              ↓                     ↓
        Analyse technique      Ensemble ML          règles auditables | GBM + forêt + logistique
              ↓                     ↓
              └──────────┬──────────┘
                         ↓
                   FUSION → SCORE               3 filtres : accord, edge, confiance
                         ↓
                   RISK MANAGER                 0,5 % max, SL obligatoire, R:R ≥ 2
                         ↓
                 BUY / SELL / WAIT
                         ↓
                     BACKTEST                   spread, slippage, commission, swap
                         ↓
                 WALK-FORWARD TEST              embargo, IS vs OOS, bootstrap
                         ↓
                   COMPTE DÉMO
                         ↓
                ──────── LIVE ────────
```

---

## Installation — les trois seules commandes à taper

```
git clone https://github.com/Shwagger/trade.git
cd trade
bash scripts/setup_mac.sh
```

C'est tout. Le script trouve ton Python, crée l'environnement, installe les
dépendances, lance les 158 tests, télécharge de vraies barres EURUSD, fait
tourner la validation, entraîne le modèle et te montre une alerte réelle.

Deux pièges macOS qu'il gère à ta place :

* **`command not found: python`** — sur macOS c'est `python3`. Le script le
  détecte seul, et une fois l'environnement activé, `python` fonctionne.
* **`zsh: parse error near ')'`** — tu as collé un bloc contenant des
  commentaires `#`. Le zsh interactif ne les reconnaît pas. D'où un script.

Si le script dit qu'il ne trouve aucun Python 3 :

```
xcode-select --install
```

Accepte la fenêtre, attends la fin, relance le script.

Aucun GPU, aucun torch, aucune API payante. Tourne sur un MacBook 2012 / 8 Go.

## Ensuite, à chaque nouvelle session de terminal

```
cd trade
source .venv/bin/activate
```

Sans cette ligne, `python -m forexai` ne trouvera rien.

## Les commandes

| commande | ce qu'elle fait |
|---|---|
| `fetch` | télécharge de vraies barres (Yahoo H1, Stooq D1), sans clé d'API |
| `walkforward` | validation out-of-sample glissante + rapport + verdict |
| `backtest` | un seul split train/test, plus rapide |
| `train` | entraîne sur tout l'historique et sauvegarde le modèle |
| `signal` | décision sur la dernière bougie fermée |
| `search` | teste des milliers de stratégies contre un holdout |
| `monitor` | surveille le marché en papier et se note en continu |
| `paper` | rejeu à blanc des dernières barres |

Par défaut les données sont **synthétiques**. Elles valident la mécanique, pas
un edge. Pour du sérieux, il faut de vraies barres (section suivante).

---

## Mettre de vraies données

**Le plus simple — rien à exporter à la main :**

```bash
python -m forexai fetch --symbol EURUSD --timeframe 1h --years 2
```

Yahoo, sans clé d'API, sans dépendance en plus. ~12 000 barres H1 (Yahoo plafonne
l'intraday à 730 jours). Pour des décennies d'historique :

```bash
python -m forexai fetch --symbol EURUSD --timeframe 1d --provider stooq
python -m forexai walkforward --config config/eurusd_d1_real.yaml
```

**Pour que je puisse lancer les tests moi-même :** je n'ai aucun accès aux
serveurs de données de marché depuis mon environnement (Yahoo, Stooq,
Alphavantage, Telegram : tous bloqués par la politique réseau). Ce qui passe,
c'est GitHub. Donc si tu veux que je fasse tourner la validation sur tes vraies
barres :

```bash
python -m forexai fetch --symbol EURUSD --timeframe 1h --years 2 --out data/shared/EURUSD_1H.csv
git add data/shared/EURUSD_1H.csv
git commit -m "Add real EURUSD H1 bars"
git push
```

Le dossier `data/shared/` est exclu du `.gitignore` exactement pour ça. Un H1 sur
deux ans pèse environ 1 Mo.

**Le plus sérieux — l'export de ton propre courtier**, parce que c'est chez lui
que tu vas trader et que ses prix et ses frais sont les seuls qui comptent :

1. MT5 → `Outils → Centre d'historique → Exporter`, ou Dukascopy (CSV, **UTC**).
2. Fichier dans `data/raw/EURUSD_H1.csv`.
3. Dans `config/eurusd_h1_real.yaml`, mets le **vrai** spread et la **vraie**
   commission de ton compte.
4. `python -m forexai walkforward --config config/eurusd_h1_real.yaml`

---

## Ce que fait chaque brique

### `features.py` — 52 features, toutes causales
Momentum multi-horizon, distances aux EMA normalisées par l'ATR, ADX/DI, RSI,
MACD, Bollinger, ratio de volatilité, position dans le canal de Donchian,
anatomie des bougies, volume en z-score, heure/session encodées en sinus.

Tout est normalisé par la volatilité ou exprimé en ratio : un modèle entraîné
sur l'EURUSD à 1,05 reste valable à 1,20.

### `labeling.py` — triple barrière
L'étiquette répond exactement à la question posée à l'exécution : *« si j'ouvre
au prochain open, stop à 1,5 ATR, cible à 3 ATR, 48 barres max — est-ce que ça
gagne ? »* Trois classes : long gagnant, short gagnant, rien. Quand une bougie
touche la cible **et** le stop, on suppose le stop d'abord.

### `models/ensemble.py` — la tête ML
Trois apprenants aux biais différents votent : gradient boosting, forêt
aléatoire, régression logistique. Probabilités calibrées sur la **fin** de la
fenêtre d'entraînement (jamais sur le test). La logistique sert de garde-fou :
quand les arbres l'écrasent en train et perdent en test, on apprenait du bruit.

### `models/technical.py` — la tête règles
Score lisible dans [-1, 1], conscient du régime : on suit le momentum quand
l'ADX est haut, on fade les extrêmes quand il est bas, transition douce entre
les deux, et une porte de volatilité qui coupe le score dans les marchés morts
ou en panique.

### `signal.py` — la fusion
Trois filtres avant d'engager un centime :
1. les deux têtes ne doivent pas se contredire,
2. l'edge fusionné doit dépasser `min_score`,
3. la probabilité du côté gagnant doit battre **sa propre fréquence de base**
   d'au moins `min_confidence_lift`.

Le point 3 mérite une explication, parce qu'un seuil absolu était un bug réel
dans la v1 de ce dépôt : en H1 les trois classes pèsent ~33 % chacune, en daily
la classe « aucun trade » monte à 73 %. Une probabilité de 20 % vaut donc « deux
fois mieux que le hasard » en daily et « nettement sous le hasard » en H1. Un
seuil fixe à 0,40 gelait tout le système en daily **sans un seul message
d'erreur**. Le seuil est maintenant relatif à ce que le modèle a réellement vu
à l'entraînement.

Tout le reste devient **WAIT**. La majorité des bougies doivent être WAIT, et le
rapport te dit exactement quel filtre a bloqué quoi.

### `risk.py` — le patron
La couche signal ne fait que *proposer*. C'est ici qu'on décide, et c'est ici
qu'on calcule la taille. Vetos, dans l'ordre :

| Veto | Défaut |
|---|---|
| kill switch drawdown total | 20 % |
| perte journalière | 2 % |
| cooldown après série perdante | 4 pertes → 12 barres |
| positions simultanées | 1 |
| session | Londres / overlap / New York |
| spread trop large | > 2,5 pips |
| volatilité hors bande | < 5 ou > 60 pips d'ATR |
| R:R planifié | < 2,0 |
| R:R net de frais | < 1,5 |
| lot sous le minimum courtier | refus plutôt que dépassement du risque |

Le sizing est du fixed-fractional : `0,5 % de l'équité / (distance de stop en
pips × valeur du pip + commission)`, arrondi **vers le bas**. Le risque réel ne
peut donc que passer *sous* le mandat, jamais au-dessus — c'est testé.

### `backtest.py` — l'exécution
Contrat de timing, garanti par l'ordre de la boucle :

```
clôture barre i     → signal calculé sur les features de la barre i
open barre i+1      → ordre exécuté, taille calculée par le risk manager
barres suivantes    → stop / cible / timeout surveillés
```

Rien dans la décision de la barre `i` ne peut voir la barre `i+1`. Le prix de
fill est inconnu au moment de décider — comme en réel. Bid/ask modélisés à
±½ spread, slippage sur les entrées et les stops, commission par lot,
swap par rollover.

### `walkforward.py` — le seul backtest qui compte
Fenêtre d'entraînement glissante, **embargo** d'au moins la durée de vie d'un
label entre train et test (sinon une étiquette d'entraînement chevauche une
barre de test et fuite l'information), puis trading en avant sur des données
jamais vues. L'équité se compose d'un fold au suivant.

Chaque fold rapporte l'**in-sample** et l'**out-of-sample** côte à côte. Un gros
écart = le modèle mémorise. C'est écrit noir sur blanc dans le rapport.

---

## Lire le rapport

```
expectancy          +0.0427 R
mean +0.0427 R  95% CI [-0.0313, +0.1203]  P(edge > 0) = 86.1%
[INFO] mean in-sample minus out-of-sample expectancy: +0.368 R (the model is memorising)
verdict: NO-GO
```

C'est le résultat réel du dépôt sur 40 000 barres synthétiques, 22 folds,
1 084 trades. **NO-GO**, et c'est la bonne réponse : sur des données quasi
efficientes, il n'y a pas d'edge à trouver, et le système le dit au lieu de
l'inventer.

* **Expectancy en R** — la seule métrique qui survit à un changement de taille
  de compte. 40 % de réussite à +2R vaut mieux que 70 % à -0,05R.
* **Intervalle de confiance bootstrap** — si l'IC contient 0, tu n'as pas
  d'edge, tu as un échantillon. C'est l'antidote au backtest chanceux.
* **Écart IS − OOS** — au-delà de ~0,25 R, le modèle apprend le passé par cœur.

Le verdict final n'est jamais « lance-toi » : au mieux c'est **GO TO DEMO**.

---

## Chercher des millions de stratégies — sans se mentir

```bash
python -m forexai search --n 4000 --jobs 4
```

L'espace de recherche fait **700 710 912 combinaisons**. Sept cents millions.

| dimension | valeurs |
|---|---|
| familles de règles | tendance, retour à la moyenne, cassure, momentum, croisement MACD, croisement stochastique, fade de canal, cassure de session, pullback, squeeze de volatilité, engulfing |
| filtres d'entrée | aucun, alignement multi-timeframe, bande de volatilité, les deux |
| gestion de sortie | fixe, break-even à 1R, stop suiveur ATR, break-even + suiveur |
| paramètres | périodes rapides/lentes, RSI, Donchian, seuil ADX, Bollinger, stop, cible, durée max, session |

### Pourquoi générer plutôt que télécharger des PDF

Tu m'as dit : « il y a des millions de stratégies en PDF sur Google, il doit
toutes les connaître ». Je te dois la vérité là-dessus, parce que c'est ton
argent : **collectionner des PDF ne marcherait pas, et générer marche mieux.**

* Ces millions de documents décrivent en réalité **une petite douzaine d'idées**
  reformulées : croisement de moyennes, RSI en survente, cassure de range,
  divergence, retour à la moyenne, pattern de bougie. Le vocabulaire du trading
  technique est petit ; c'est le marketing qui est grand.
* Un PDF ne se backteste pas. « Achetez quand la tendance est forte » n'est pas
  exécutable : il manque la définition de « forte », le stop, la taille, la
  sortie. Il faudrait de toute façon le traduire en règles — c'est exactement ce
  que fait `StrategySpec`.
* Les 11 familles ci-dessus **couvrent** ce que ces documents décrivent, et le
  générateur en produit 700 millions de variantes, dont des milliers que
  personne n'a jamais publiées.
* La contrainte n'a jamais été le nombre de stratégies. Elle est de savoir
  **laquelle tient hors échantillon** — et c'est un problème statistique, pas un
  problème de collecte.

Chaque candidat est backtesté avec le même moteur de risque et les mêmes frais
que le reste du système. 4 000 candidats prennent environ 3 minutes sur 4 cœurs.

Et surtout, elle te protège du piège qui a ruiné plus de comptes que n'importe
quel krach : **si tu testes 3 000 stratégies sur un marché de pile ou face, la
meilleure aura l'air excellente.** C'est de l'arithmétique, pas du talent.

Deux défenses, non désactivables :

1. **Un holdout que la recherche ne voit jamais.** Les données sont coupées en
   deux *avant* la première stratégie générée. Tout est classé sur le segment de
   recherche ; seuls les finalistes touchent le holdout, une seule fois.
2. **Le Sharpe déflaté** (Bailey & López de Prado). Connaissant le nombre
   d'essais et la dispersion de leurs résultats, on calcule ce que le
   *meilleur sur N* obtiendrait **sans aucun edge**. Un gagnant qui ne passe pas
   cette barre est du bruit bien coiffé.

```
  best-of-N by luck   0.3194 Sharpe per trade
  deflated Sharpe     32.9%  -> INDISTINGUISHABLE FROM LUCK
  No winner. Either the deflated Sharpe says luck, or the finalists
  died on the holdout. This is the normal outcome and it saved you money.
```

Pas de gagnant est le résultat **normal**. Le jour où il y en a un, c'est là que
ça devient intéressant.

---

## Alertes Telegram — savoir quoi faire, et comment

```bash
export TELEGRAM_BOT_TOKEN="123456789:AAF..."
export TELEGRAM_CHAT_ID="987654321"
python -m forexai monitor --interval 300 --telegram
```

Une alerte qui dit « ACHETER EURUSD » ne vaut rien : elle te laisse les deux
seules décisions qui comptent — où mettre le stop et quelle taille prendre.
Celles d'ici contiennent l'ordre complet :

```
LONG EURUSD 1h
bar 2024-05-02 13:00:00+00:00

  entry     ~1.08000  (market, now)
  stop      1.07850   (16.4 pips)
  target    1.08300   (28.6 pips)
  size      0.29 lots
  risk      49.59  (0.50% of 10,000)
  R:R       2.00  (1.63 after costs)

  confidence 31% (1.35x base rate)
  ml +0.50 | rules +0.30

Place the stop with the order, not after.
```

Tu reçois aussi la clôture de chaque trade papier (`+1,8R`), l'alerte de dérive,
et l'arrêt d'urgence si le kill switch se déclenche.

### Créer le bot (2 minutes, chez toi)

1. Dans Telegram, écris à **@BotFather**, envoie `/newbot`, suis les questions.
   Il te donne un token du genre `123456789:AAF...`.
2. **Écris un message à ton bot** — sans ça il n'a pas le droit de t'écrire.
3. Ouvre `https://api.telegram.org/bot<TON_TOKEN>/getUpdates` dans le navigateur
   et copie le `chat.id`.
4. Exporte les deux variables ci-dessus et lance le monitor.

Sans les variables, les alertes tombent dans la console au lieu de se perdre.
Et si Telegram est en panne, le monitor continue de surveiller : une alerte
ratée est journalisée, elle n'arrête jamais le processus.

---

## Surveiller le marché en continu

```bash
python -m forexai monitor --interval 300
```

Le monitor regarde chaque bougie se fermer, prend la décision, la journalise, et
**se note lui-même** contre ce que le backtest avait promis.

C'est volontairement un pont **papier** : il n'envoie jamais d'ordre. Parce que
le chiffre qui dit si un système est réel, c'est l'écart entre l'espérance
backtestée et l'espérance *en avant*, sur des barres que le modèle n'a jamais
vues. Le monitor mesure cet écart en continu, gratuitement, sans capital exposé.
Brancher un courtier avant de connaître cet écart, c'est comme ça que les
comptes meurent.

Sur chaque bougie fermée :

1. il exécute l'ordre décidé à la bougie précédente, à l'open — jamais au close
2. il gère la position ouverte avec **exactement** les règles de sortie du
   backtester (fonction partagée, pas réécrite — un test vérifie que les deux
   produisent les mêmes trades, au pip près)
3. il décide sur la bougie qui vient de fermer
4. il écrit tout dans `runs/monitor/<SYMBOL>/journal.jsonl`
5. il **réentraîne** le modèle tous les `--retrain-every` barres
6. il lève une **alerte de dérive** quand les résultats en avant sortent de
   l'intervalle de confiance du backtest

L'état (équité, position, cooldown, limite journalière, kill switch) est
persisté sur disque : tuer le process et le relancer ne remet aucun garde-fou à
zéro.

Pour le faire tourner tout seul, une passe par heure via `cron` :

```bash
0 * * * * cd /chemin/vers/trade && .venv/bin/python -m forexai monitor --interval 0
```

---

## IA locale (optionnelle)

`llm.py` peut interroger un modèle local via [Ollama](https://ollama.com) :

```bash
ollama pull llama3.2:3b     # ~2 Go, tourne sur 8 Go de RAM
python -m forexai signal --llm
```

Ce que le LLM **ne fait pas** : prédire le prix, choisir une direction,
dimensionner. Un modèle de langage n'a aucun edge sur des ticks.

Ce qu'il fait : expliquer en français la décision du stack numérique, et servir
de **soupape à sens unique** — il peut rétrograder un trade en WAIT s'il repère
un danger structurel, il ne peut jamais en créer un ni l'agrandir. Ollama
éteint ? On retombe sur une explication template, jamais sur une erreur.

---

## Tests

```bash
python -m pytest tests/ -q
```

158 tests. Les plus importants :

* `test_no_lookahead.py` — tronquer ou corrompre le futur ne doit changer
  **aucune** valeur de feature passée. Si ce test tombe, tout le reste est un
  mensonge.
* `test_labeling.py` — barrières, égalités résolues contre nous, horizon.
* `test_risk.py` — chaque veto, le sizing, et le refus de trader quand le
  compte est trop petit pour respecter les 0,5 %.
* `test_backtest.py` — entrée au prochain open, P&L exact au pip près, effet
  des frais, une position à la fois.
* `test_monitor.py` — **le monitor live doit reproduire le backtest trade pour
  trade.** S'ils divergent, tous les chiffres de recherche deviennent une
  fiction. C'est ce test qui a attrapé un décalage d'une barre dans le comptage
  de la durée de détention.
* `test_search.py` — les 11 familles × 4 filtres sont toutes causales, le
  holdout ne chevauche jamais la recherche, et le seuil de chance monte bien
  avec le nombre d'essais. C'est ce test qui a montré que le pattern engulfing
  classique ne se déclenche **jamais** en forex intraday (les bougies n'ont pas
  de gap), ce qui a imposé la version adaptée au FX.
* `test_notify.py` — l'alerte contient bien le stop et la taille, et un Telegram
  injoignable ne fait jamais tomber le monitor.

---

## Le chemin honnête vers le réel

| Étape | Critère de passage |
|---|---|
| 1. Walk-forward sur données réelles | ≥ 200 trades OOS, expectancy > 0, P(edge>0) ≥ 95 %, écart IS−OOS < 0,25 R |
| 2. Robustesse | Le résultat survit à +50 % de spread et à un décalage des seuils de ±20 % |
| 3. Autres marchés / périodes | Même paramètres sur GBPUSD, USDJPY, et sur une période jamais touchée |
| 4. Démo | 3 mois minimum. La courbe live doit ressembler au rapport |
| 5. Réel | Capital que tu peux perdre entièrement, à 0,25 % de risque les 3 premiers mois |

Chaque étape peut dire non. C'est le but.

### Ce que ce dépôt ne promet pas

Il ne promet pas de gagner de l'argent. Il ne promet pas de revenus aujourd'hui,
ni cette semaine. Un système qui passe l'étape 1 ce soir n'a encore rien prouvé
en conditions réelles — le premier vrai signal de qualité, c'est la démo qui le
donne, et ça prend des mois.

Ce qu'il fournit : une infrastructure honnête, qui **mesure** au lieu de
promettre, et qui refuse de trader quand les conditions ne sont pas réunies.
La différence entre un compte qui dure et un compte qui explose, elle est là.
