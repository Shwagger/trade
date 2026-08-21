# Bars committed on purpose

`data/raw/` is git-ignored: it is your scratch space, and nobody wants a 40 MB
tick dump in a diff.

**This** directory is not ignored. Put a CSV here and push it when you want the
data to travel with the repository - so it can be reviewed, re-run by someone
else, or picked up by an assistant working on the repo who has no market-data
access of its own.

```bash
python -m forexai fetch --symbol EURUSD --timeframe 1h --years 2 --out data/shared/EURUSD_1H.csv
git add data/shared/EURUSD_1H.csv
git commit -m "Add real EURUSD H1 bars"
git push
```

Then anyone, anywhere, can reproduce the run:

```bash
python -m forexai walkforward --source csv --path data/shared/EURUSD_1H.csv
```

Keep it reasonable: H1 for a few years is about 1 MB and is fine to commit.
Tick data is not - export candles, not ticks.
