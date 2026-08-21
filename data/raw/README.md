# Where to put real bars

Drop a CSV here and point `data.path` at it. Any of these layouts is read
without editing:

```
time,open,high,low,close,volume
2024-01-02 08:00:00,1.10412,1.10488,1.10390,1.10461,1523
```

MetaTrader 5 export (`Tools -> History Center -> Export`) and Dukascopy
(`Historical Data Feed`, CSV, UTC) both work as-is: the loader lower-cases the
headers and understands `date`/`datetime`/`timestamp`, `tickvol`/`vol`.

Rules that matter more than the format:

* **UTC**. Mixed timezones silently destroy the session features.
* **One timeframe per file.** H1 is the default the config is tuned for.
* **At least 3 years.** Walk-forward needs a training window plus several
  forward test windows; under ~15 000 bars you get one or two folds and no
  statistical power.
* **Bid or mid, consistently.** The backtester adds the spread itself; if your
  file is already ask-side you would pay the spread twice.
