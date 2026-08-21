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

## Installation

```bash
git clone <ce-dépôt> && cd trade
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Aucun GPU, aucun torch, aucune API payante. Tourne sur un MacBook 2012 / 8 Go :
un fold complet (6 000 barres d'entraînement) prend quelques secondes.

## Démarrage en 30 secondes

```bash
python -m forexai walkforward --bars 40000        # validation complète + rapport
python -m forexai train                           # entraîne et sauvegarde le modèle
python -m forexai signal                          # décision sur la dernière bougie fermée
python -m forexai paper --window 500              # rejeu à blanc, aucun ordre envoyé
```

Par défaut les données sont **synthétiques**. Elles valident la mécanique, pas
un edge. Pour du sérieux, il faut de vraies barres (section suivante).

---

## Mettre de vraies données

1. Exporte de l'H1 EURUSD depuis MT5 (`Outils → Centre d'historique → Exporter`)
   ou Dukascopy (Historical Data Feed, CSV, **UTC**). Vise 3 ans minimum.
2. Pose le fichier dans `data/raw/EURUSD_H1.csv`.
3. Édite `config/eurusd_h1_real.yaml` — surtout le bloc `costs`, avec le spread
   et la commission **réels** de ton courtier.
4. Lance :

```bash
python -m forexai walkforward --config config/eurusd_h1_real.yaml
```

Alternative sans fichier, si tu as le réseau : `pip install yfinance` puis
`--source yahoo` (H1 limité à ~730 jours, suffisant pour un premier coup d'œil,
pas pour valider).

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
3. la probabilité du côté gagnant doit dépasser `min_confidence`.

Tout le reste devient **WAIT**. La majorité des bougies doivent être WAIT.

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
expectancy          +0.0933 R
mean +0.0933 R  95% CI [-0.0005, +0.1904]  P(edge > 0) = 97.5%
[INFO] mean in-sample minus out-of-sample expectancy: +0.417 R (the model is memorising)
```

* **Expectancy en R** — la seule métrique qui survit à un changement de taille
  de compte. 40 % de réussite à +2R vaut mieux que 70 % à -0,05R.
* **Intervalle de confiance bootstrap** — si l'IC contient 0, tu n'as pas
  d'edge, tu as un échantillon. C'est l'antidote au backtest chanceux.
* **Écart IS − OOS** — au-delà de ~0,25 R, le modèle apprend le passé par cœur.

Le verdict final n'est jamais « lance-toi » : au mieux c'est **GO TO DEMO**.

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

47 tests. Les plus importants :

* `test_no_lookahead.py` — tronquer ou corrompre le futur ne doit changer
  **aucune** valeur de feature passée. Si ce test tombe, tout le reste est un
  mensonge.
* `test_labeling.py` — barrières, égalités résolues contre nous, horizon.
* `test_risk.py` — chaque veto, le sizing, et le refus de trader quand le
  compte est trop petit pour respecter les 0,5 %.
* `test_backtest.py` — entrée au prochain open, P&L exact au pip près, effet
  des frais, une position à la fois.

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
