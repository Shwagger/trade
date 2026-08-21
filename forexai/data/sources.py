"""Market data loading.

Three sources, one interface:

* ``synthetic`` - offline generator, always available, used for pipeline tests.
* ``csv``       - any broker/MT5/Dukascopy export with OHLCV columns.
* ``yahoo``     - free hourly/daily FX bars (needs network + ``yfinance``).

Every loader returns a UTC-indexed DataFrame with columns
``open, high, low, close, volume`` sorted ascending and free of duplicates.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..config import DataConfig
from .synthetic import generate_ohlcv

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]

_YAHOO_SYMBOLS = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X", "USDCHF": "USDCHF=X", "USDCAD": "USDCAD=X",
    "XAUUSD": "GC=F", "BTCUSD": "BTC-USD",
}


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    rename = {
        "date": "time", "datetime": "time", "timestamp": "time", "<date>": "time",
        "o": "open", "h": "high", "l": "low", "c": "close",
        "tickvol": "volume", "tick_volume": "volume", "vol": "volume",
        "adj close": "adj_close",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time"]).set_index("time")
    else:
        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
        df = df[df.index.notna()]

    if "volume" not in df.columns:
        df["volume"] = 1.0

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"market data is missing required columns: {missing}")

    df = df[REQUIRED_COLUMNS].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna()
    # A bar whose high/low do not bracket open/close is corrupt data.
    sane = (df["high"] >= df[["open", "close"]].max(axis=1) - 1e-12) & (
        df["low"] <= df[["open", "close"]].min(axis=1) + 1e-12
    )
    df = df[sane]
    df.index.name = "time"
    return df


def load_csv(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"no such data file: {p}")
    sep = "\t" if p.suffix.lower() in {".tsv", ".txt"} else None
    df = pd.read_csv(p, sep=sep, engine="python")
    return _normalise(df)


def load_yahoo(symbol: str, timeframe: str = "1h", bars: int = 30_000) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - depends on user env
        raise RuntimeError(
            "yahoo source needs yfinance:  pip install yfinance"
        ) from exc

    ticker = _YAHOO_SYMBOLS.get(symbol.upper(), symbol)
    # Yahoo caps intraday history at ~730 days for 1h bars.
    period = {"1h": "730d", "30m": "60d", "15m": "60d", "5m": "60d", "1d": "max"}.get(
        timeframe, "730d"
    )
    raw = yf.download(
        ticker, period=period, interval=timeframe,
        auto_adjust=False, progress=False, threads=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"yahoo returned no data for {ticker} @ {timeframe}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return _normalise(raw).tail(bars)


def load_market_data(cfg: DataConfig, symbol: str = "EURUSD") -> pd.DataFrame:
    source = cfg.source.lower()
    if source == "synthetic":
        return generate_ohlcv(bars=cfg.bars, seed=cfg.seed)
    if source == "csv":
        if not cfg.path:
            raise ValueError("data.source = csv requires data.path")
        return load_csv(cfg.path).tail(cfg.bars)
    if source == "yahoo":
        return load_yahoo(symbol, cfg.timeframe, cfg.bars)
    raise ValueError(f"unknown data source: {cfg.source!r}")
