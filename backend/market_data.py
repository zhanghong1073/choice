from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path
from datetime import date, timedelta
from typing import List

import pandas as pd
import requests
import yfinance as yf


DEFAULT_US_TICKERS: List[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "JPM",
    "V", "MA", "UNH", "XOM", "JNJ", "WMT", "PG", "KO", "PEP", "DIS",
]

_OHLCV_CACHE: dict[tuple[str, str, str], tuple[float, pd.DataFrame]] = {}
_CACHE_TTL_SECONDS = 180
_DISK_CACHE_MAX_AGE_SECONDS = 7 * 24 * 3600
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def _cache_file(ticker: str, period: str, interval: str) -> Path:
    return _CACHE_DIR / f"{ticker.upper()}_{period}_{interval}.json"


def _to_json_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for idx, row in df.iterrows():
        rows.append(
            {
                "date": pd.to_datetime(idx).strftime("%Y-%m-%d"),
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0) or 0),
            }
        )
    return rows


def _from_json_rows(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def _write_disk_cache(ticker: str, period: str, interval: str, df: pd.DataFrame, source: str) -> None:
    payload = {
        "saved_at": int(time.time()),
        "source": source,
        "rows": _to_json_rows(df),
    }
    _cache_file(ticker, period, interval).write_text(json.dumps(payload), encoding="utf-8")


def _read_disk_cache(ticker: str, period: str, interval: str) -> pd.DataFrame:
    fp = _cache_file(ticker, period, interval)
    if not fp.exists():
        return pd.DataFrame()
    try:
        payload = json.loads(fp.read_text(encoding="utf-8"))
        saved_at = int(payload.get("saved_at", 0))
        if time.time() - saved_at > _DISK_CACHE_MAX_AGE_SECONDS:
            return pd.DataFrame()
        df = _from_json_rows(payload.get("rows", []))
        if not df.empty:
            df.attrs["source"] = f"{payload.get('source', 'unknown')}-cache"
        return df
    except Exception:
        return pd.DataFrame()


def fetch_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    key = (ticker.upper(), period, interval)
    now = time.time()
    cached = _OHLCV_CACHE.get(key)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1].copy()

    df = pd.DataFrame()
    last_err: Exception | None = None
    is_intraday = interval in {"30m", "60m", "90m", "1h", "2h", "4h"}

    # Path 1: Alpha Vantage (primary non-Yahoo source when API key is provided).
    av_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
    if av_key and interval in {"1d", "1wk"}:
        try:
            fn = "TIME_SERIES_DAILY_ADJUSTED" if interval == "1d" else "TIME_SERIES_WEEKLY_ADJUSTED"
            url = "https://www.alphavantage.co/query"
            resp = requests.get(
                url,
                params={"function": fn, "symbol": ticker.upper(), "outputsize": "full", "apikey": av_key},
                headers=_HTTP_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            js = resp.json()
            key_name = "Time Series (Daily)" if interval == "1d" else "Weekly Adjusted Time Series"
            ts = js.get(key_name, {})
            if ts:
                rows = []
                for d, vals in ts.items():
                    rows.append(
                        {
                            "date": pd.to_datetime(d),
                            "open": float(vals.get("1. open", 0)),
                            "high": float(vals.get("2. high", 0)),
                            "low": float(vals.get("3. low", 0)),
                            "close": float(vals.get("4. close", 0)),
                            "volume": float(vals.get("6. volume", vals.get("5. volume", 0))),
                        }
                    )
                adf = pd.DataFrame(rows).sort_values("date").set_index("date")
                period_days = {"3mo": 95, "6mo": 190, "1y": 380, "2y": 760}
                days = period_days.get(period, 190)
                start = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=days)
                df = adf[adf.index >= start]
                if not df.empty:
                    df.attrs["source"] = "alphavantage"
        except Exception as e:
            last_err = e

    # Path 2: Stooq fallback (non-Yahoo, no key).
    if df.empty and interval in {"1d", "1wk"}:
        try:
            stooq_key = os.getenv("STOOQ_API_KEY", "").strip()
            stooq_symbol = f"{ticker.lower()}.us"
            stooq_url = "https://stooq.com/q/d/l/"
            params = {"s": stooq_symbol, "i": "d"}
            if stooq_key:
                params["apikey"] = stooq_key
            resp = requests.get(stooq_url, params=params, headers=_HTTP_HEADERS, timeout=8)
            resp.raise_for_status()
            text = resp.text.strip()
            if text and "No data" not in text and "404" not in text:
                sdf = pd.read_csv(io.StringIO(text))
                if not sdf.empty and {"Date", "Open", "High", "Low", "Close"}.issubset(sdf.columns):
                    sdf["Date"] = pd.to_datetime(sdf["Date"])
                    sdf = sdf.sort_values("Date")
                    sdf = sdf.rename(
                        columns={
                            "Date": "date",
                            "Open": "open",
                            "High": "high",
                            "Low": "low",
                            "Close": "close",
                            "Volume": "volume",
                        }
                    )
                    sdf = sdf.set_index("date")
                    if "volume" not in sdf.columns:
                        sdf["volume"] = 0

                    period_days = {"3mo": 95, "6mo": 190, "1y": 380, "2y": 760}
                    days = period_days.get(period, 190)
                    start = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=days)
                    sdf = sdf[sdf.index >= start]

                    if interval == "1wk" and not sdf.empty:
                        agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
                        sdf = sdf.resample("W-FRI").agg(agg).dropna(subset=["open", "high", "low", "close"])
                    df = sdf
                    df.attrs["source"] = "stooq"
        except Exception as e:
            last_err = e

    # Path 3: yfinance download with retry/backoff.
    for i in range(3):
        if not df.empty:
            break
        try:
            yf_interval = "1h" if interval == "2h" else "1h" if interval == "4h" else interval
            df = yf.download(
                ticker,
                period="60d" if is_intraday and period in {"6mo", "1y", "2y"} else period,
                interval=yf_interval,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if interval in {"2h", "4h"} and not df.empty:
                rule = "2H" if interval == "2h" else "4H"
                agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
                if not isinstance(df.columns, pd.MultiIndex):
                    df = df.resample(rule).agg(agg).dropna(subset=["Open", "High", "Low", "Close"])
            if not df.empty:
                df.attrs["source"] = "yfinance-download"
                break
        except Exception as e:
            last_err = e
        time.sleep(0.6 * (i + 1))

    # Path 4: yfinance Ticker.history fallback.
    if df.empty:
        try:
            tk = yf.Ticker(ticker)
            yf_interval = "1h" if interval == "2h" else "1h" if interval == "4h" else interval
            df = tk.history(
                period="60d" if is_intraday and period in {"6mo", "1y", "2y"} else period,
                interval=yf_interval,
                auto_adjust=True,
            )
            if interval in {"2h", "4h"} and not df.empty:
                rule = "2H" if interval == "2h" else "4H"
                agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
                if not isinstance(df.columns, pd.MultiIndex):
                    df = df.resample(rule).agg(agg).dropna(subset=["Open", "High", "Low", "Close"])
            if not df.empty:
                df.attrs["source"] = "yfinance-history"
        except Exception as e:
            last_err = e

    # Path 5: Yahoo chart endpoint fallback.
    if df.empty and interval in {"1d", "1wk"}:
        try:
            range_map = {"3mo": "3mo", "6mo": "6mo", "1y": "1y", "2y": "2y"}
            interval_map = {"1d": "1d", "1wk": "1wk"}
            r = range_map.get(period, "6mo")
            iv = interval_map.get(interval, "1d")
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            resp = requests.get(url, params={"range": r, "interval": iv}, headers=_HTTP_HEADERS, timeout=8)
            resp.raise_for_status()
            js = resp.json()
            result = (((js or {}).get("chart") or {}).get("result") or [None])[0]
            if result:
                ts = result.get("timestamp") or []
                quote = (((result.get("indicators") or {}).get("quote")) or [None])[0] or {}
                frame = pd.DataFrame(
                    {
                        "open": quote.get("open"),
                        "high": quote.get("high"),
                        "low": quote.get("low"),
                        "close": quote.get("close"),
                        "volume": quote.get("volume"),
                    },
                    index=pd.to_datetime(ts, unit="s"),
                )
                df = frame.dropna(subset=["open", "high", "low", "close"], how="any")
                if not df.empty:
                    df.attrs["source"] = "yahoo-chart"
        except Exception as e:
            last_err = e

    if df.empty:
        # Last resort: return latest successful cached data from local disk.
        disk_df = _read_disk_cache(ticker, period, interval)
        if not disk_df.empty:
            _OHLCV_CACHE[key] = (time.time(), disk_df.copy())
            return disk_df
        if last_err:
            raise last_err
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    df = df[[c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]].copy()
    df.index = pd.to_datetime(df.index)
    _OHLCV_CACHE[key] = (time.time(), df.copy())
    _write_disk_cache(ticker, period, interval, df, df.attrs.get("source", "unknown"))
    return df


def fetch_multi_tickers(tickers: List[str], period: str = "6mo") -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            out[t] = fetch_ohlcv(t, period=period)
        except Exception:
            out[t] = pd.DataFrame()
    return out


def choose_universe(custom: List[str] | None) -> List[str]:
    if custom:
        return [x.strip().upper() for x in custom if x.strip()]
    return DEFAULT_US_TICKERS
