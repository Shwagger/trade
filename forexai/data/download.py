"""Market data downloaders.

Fetching and parsing are deliberately separate: the parsers are pure functions
over bytes and are unit-tested against fixtures, while the transport is a thin
retrying wrapper. That way a provider changing its wire format fails loudly in
the tests instead of silently producing garbage bars.

Providers
---------
``yahoo``  hourly and daily bars, no API key, no extra dependency.
           Intraday history is capped at ~730 days by Yahoo.
``stooq``  daily bars going back decades, no API key. No volume for FX.

Neither is a professional feed. They are good enough to find out whether a
strategy is worth paying for real data. Before going live, re-run the
walk-forward on bars exported from the broker you will actually trade with.
"""

from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) forexai/2.0"

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
STOOQ_CSV = "https://stooq.com/q/d/l/?s={ticker}&i=d"

YAHOO_TICKERS = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X", "NZDUSD": "NZDUSD=X", "USDCHF": "USDCHF=X",
    "USDCAD": "USDCAD=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X",
    "XAUUSD": "GC=F", "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD",
}
STOOQ_TICKERS = {
    "EURUSD": "eurusd", "GBPUSD": "gbpusd", "USDJPY": "usdjpy",
    "AUDUSD": "audusd", "NZDUSD": "nzdusd", "USDCHF": "usdchf",
    "USDCAD": "usdcad", "EURGBP": "eurgbp", "EURJPY": "eurjpy",
    "XAUUSD": "xauusd",
}

# Yahoo's own limits: how far back each interval is served.
YAHOO_MAX_DAYS = {"1m": 7, "5m": 60, "15m": 60, "30m": 60, "1h": 730, "1d": 20_000}


class DownloadError(RuntimeError):
    """Raised when a provider cannot be reached or returns nothing usable."""


# ----------------------------------------------------------------------
# transport
# ----------------------------------------------------------------------
def http_get(url: str, timeout: float = 30.0, retries: int = 4) -> bytes:
    """GET with exponential backoff. Raises DownloadError, never urllib errors."""
    delay = 2.0
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
    raise DownloadError(
        f"could not reach {url.split('?')[0]} after {retries} attempts: {last}\n"
        "Check your internet connection, or use an export from your broker "
        "(see data/raw/README.md)."
    )


# ----------------------------------------------------------------------
# parsers (pure, tested)
# ----------------------------------------------------------------------
def parse_yahoo(payload: bytes) -> pd.DataFrame:
    """Turn a Yahoo chart API response into OHLCV bars."""
    try:
        body = json.loads(payload.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DownloadError(f"yahoo returned something that is not JSON: {exc}") from exc

    chart = body.get("chart") or {}
    if chart.get("error"):
        raise DownloadError(f"yahoo error: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise DownloadError("yahoo returned an empty result set")

    result = results[0]
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    if not stamps or not quote:
        raise DownloadError("yahoo returned no price series")

    frame = pd.DataFrame(
        {
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        },
        index=pd.to_datetime(stamps, unit="s", utc=True),
    )
    frame.index.name = "time"
    return frame


def parse_stooq(payload: bytes) -> pd.DataFrame:
    """Turn a Stooq daily CSV into OHLCV bars."""
    text = payload.decode("utf-8", errors="replace").strip()
    if not text or text.lower().startswith("no data"):
        raise DownloadError("stooq returned no data for that symbol")

    frame = pd.read_csv(io.StringIO(text))
    frame.columns = [c.strip().lower() for c in frame.columns]
    if "date" not in frame.columns or "close" not in frame.columns:
        raise DownloadError(f"unexpected stooq columns: {list(frame.columns)}")

    frame["time"] = pd.to_datetime(frame["date"], utc=True)
    frame = frame.set_index("time").drop(columns=["date"])
    if "volume" not in frame.columns:
        frame["volume"] = 1.0        # FX pairs on stooq carry no volume
    return frame[["open", "high", "low", "close", "volume"]]


def clean_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop unusable rows and enforce the OHLCV contract."""
    frame = frame.astype(float)
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame["volume"] = frame["volume"].fillna(0.0)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()

    sane = (
        (frame["high"] >= frame[["open", "close"]].max(axis=1) - 1e-12)
        & (frame["low"] <= frame[["open", "close"]].min(axis=1) + 1e-12)
        & (frame["low"] > 0)
    )
    frame = frame[sane]
    if frame.empty:
        raise DownloadError("every downloaded bar failed the sanity check")
    frame.index.name = "time"
    return frame


# ----------------------------------------------------------------------
# providers
# ----------------------------------------------------------------------
def fetch_yahoo(symbol: str, timeframe: str = "1h", years: float = 2.0) -> pd.DataFrame:
    ticker = YAHOO_TICKERS.get(symbol.upper(), symbol)
    max_days = YAHOO_MAX_DAYS.get(timeframe, 730)
    days = min(int(years * 365.25) + 5, max_days)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    url = (
        f"{YAHOO_CHART.format(ticker=ticker)}"
        f"?period1={int(start.timestamp())}&period2={int(end.timestamp())}"
        f"&interval={timeframe}&includePrePost=false"
    )
    return clean_bars(parse_yahoo(http_get(url)))


def fetch_stooq(symbol: str) -> pd.DataFrame:
    ticker = STOOQ_TICKERS.get(symbol.upper(), symbol.lower())
    return clean_bars(parse_stooq(http_get(STOOQ_CSV.format(ticker=ticker))))


def fetch(symbol: str, timeframe: str = "1h", years: float = 2.0,
          provider: str = "auto") -> tuple[pd.DataFrame, str]:
    """Download bars, returning ``(bars, provider_actually_used)``.

    ``auto`` uses Yahoo for intraday and falls back to Stooq for daily bars,
    so a single command works whether or not Yahoo is answering today.
    """
    provider = provider.lower()
    errors: list[str] = []

    order = (
        ["yahoo", "stooq"] if provider == "auto"
        else [provider]
    )
    for name in order:
        try:
            if name == "yahoo":
                return fetch_yahoo(symbol, timeframe, years), "yahoo"
            if name == "stooq":
                if timeframe != "1d":
                    errors.append("stooq only serves daily bars")
                    continue
                return fetch_stooq(symbol), "stooq"
            raise DownloadError(f"unknown provider: {name}")
        except DownloadError as exc:
            errors.append(f"{name}: {exc}")

    raise DownloadError(" | ".join(errors) if errors else "no provider available")


def save_csv(bars: pd.DataFrame, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    bars.to_csv(out, index_label="time")
    return out
