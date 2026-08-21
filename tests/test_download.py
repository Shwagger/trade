"""Downloader parsers, tested offline against fixtures.

The network transport cannot be unit-tested, so the wire formats are pinned
here instead: if Yahoo or Stooq change their layout, these tests fail loudly
rather than the pipeline quietly training on garbage.
"""

import json

import pandas as pd
import pytest

from forexai.data.download import (
    DownloadError,
    clean_bars,
    parse_stooq,
    parse_yahoo,
)


def yahoo_payload(**overrides):
    body = {
        "chart": {
            "error": None,
            "result": [
                {
                    "timestamp": [1704186000, 1704189600, 1704193200],
                    "indicators": {
                        "quote": [
                            {
                                "open": [1.1040, 1.1046, 1.1051],
                                "high": [1.1049, 1.1055, 1.1058],
                                "low": [1.1038, 1.1042, 1.1047],
                                "close": [1.1046, 1.1051, 1.1049],
                                "volume": [1520, 1610, 1480],
                            }
                        ]
                    },
                }
            ],
        }
    }
    body["chart"].update(overrides)
    return json.dumps(body).encode()


def test_parse_yahoo_builds_utc_ohlcv():
    bars = parse_yahoo(yahoo_payload())
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
    assert str(bars.index.tz) == "UTC"
    assert len(bars) == 3
    assert bars["close"].iloc[0] == pytest.approx(1.1046)


def test_parse_yahoo_reports_provider_errors():
    with pytest.raises(DownloadError, match="yahoo error"):
        parse_yahoo(yahoo_payload(error={"code": "Not Found"}))


def test_parse_yahoo_rejects_an_empty_series():
    with pytest.raises(DownloadError):
        parse_yahoo(json.dumps({"chart": {"result": [{}], "error": None}}).encode())


def test_parse_yahoo_rejects_html_error_pages():
    with pytest.raises(DownloadError, match="not JSON"):
        parse_yahoo(b"<html>rate limited</html>")


def test_parse_stooq_daily_csv():
    csv = (
        b"Date,Open,High,Low,Close\n"
        b"2024-01-02,1.10400,1.10490,1.10380,1.10460\n"
        b"2024-01-03,1.10460,1.10520,1.09900,1.09950\n"
    )
    bars = parse_stooq(csv)
    assert len(bars) == 2
    assert bars["volume"].eq(1.0).all()          # FX on stooq has no volume
    assert bars.index[0] == pd.Timestamp("2024-01-02", tz="UTC")


def test_parse_stooq_rejects_an_empty_response():
    with pytest.raises(DownloadError):
        parse_stooq(b"No data")


def test_clean_bars_drops_impossible_candles():
    idx = pd.date_range("2024-01-02", periods=3, freq="1h", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [1.10, 1.10, 1.10],
            "high": [1.11, 1.09, 1.11],      # bar 1: high below the open
            "low": [1.09, 1.08, 1.09],
            "close": [1.105, 1.105, 1.105],  # bar 1: close above its own high
            "volume": [1.0, 1.0, 1.0],
        },
        index=idx,
    )
    cleaned = clean_bars(frame)
    assert len(cleaned) == 2
    assert idx[1] not in cleaned.index


def test_clean_bars_drops_rows_with_missing_prices():
    idx = pd.date_range("2024-01-02", periods=2, freq="1h", tz="UTC")
    frame = pd.DataFrame(
        {"open": [1.10, None], "high": [1.11, 1.11], "low": [1.09, 1.09],
         "close": [1.105, 1.105], "volume": [1.0, None]},
        index=idx,
    )
    assert len(clean_bars(frame)) == 1


def test_clean_bars_refuses_to_return_nothing():
    idx = pd.date_range("2024-01-02", periods=1, freq="1h", tz="UTC")
    frame = pd.DataFrame(
        {"open": [1.10], "high": [1.05], "low": [1.09], "close": [1.10], "volume": [1.0]},
        index=idx,
    )
    with pytest.raises(DownloadError):
        clean_bars(frame)
