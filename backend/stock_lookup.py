from __future__ import annotations

from typing import Dict, List

import pandas as pd
import yfinance as yf

from .market_data import fetch_ohlcv

# Common Chinese -> US ticker aliases. You can extend this map.
CN_ALIAS: Dict[str, str] = {
    "苹果": "AAPL",
    "微软": "MSFT",
    "英伟达": "NVDA",
    "亚马逊": "AMZN",
    "谷歌": "GOOGL",
    "脸书": "META",
    "特斯拉": "TSLA",
    "奈飞": "NFLX",
    "超微": "AMD",
    "可口可乐": "KO",
    "沃尔玛": "WMT",
    "迪士尼": "DIS",
    "摩根大通": "JPM",
    "联合健康": "UNH",
    "伯克希尔": "BRK-B",
}


def resolve_symbol(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return ""
    if q in CN_ALIAS:
        return CN_ALIAS[q]

    # Direct ticker input fallback.
    t = q.upper().replace(" ", "")
    if all(ch.isalnum() or ch in {"-", "."} for ch in t):
        return t
    return q


def _safe_num(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _extract_financials(tk: yf.Ticker, info: dict) -> dict:

    income = tk.income_stmt
    balance = tk.balance_sheet
    cashflow = tk.cashflow

    def to_rows(df: pd.DataFrame, fields: List[str]) -> List[dict]:
        if df is None or df.empty:
            return []
        cols = list(df.columns)[:4]
        rows = []
        for f in fields:
            if f not in df.index:
                continue
            item = {"metric": f}
            for c in cols:
                label = c.strftime("%Y-%m-%d") if hasattr(c, "strftime") else str(c)
                val = df.loc[f, c]
                item[label] = _safe_num(val)
            rows.append(item)
        return rows

    income_rows = to_rows(income, ["Total Revenue", "Gross Profit", "Net Income", "Operating Income"])
    balance_rows = to_rows(balance, ["Total Assets", "Total Liabilities Net Minority Interest", "Stockholders Equity"])
    cash_rows = to_rows(cashflow, ["Operating Cash Flow", "Investing Cash Flow", "Financing Cash Flow", "Free Cash Flow"])

    summary = {
        "marketCap": _safe_num(info.get("marketCap")),
        "trailingPE": _safe_num(info.get("trailingPE")),
        "forwardPE": _safe_num(info.get("forwardPE")),
        "priceToBook": _safe_num(info.get("priceToBook")),
        "dividendYield": _safe_num(info.get("dividendYield")),
        "profitMargins": _safe_num(info.get("profitMargins")),
        "returnOnEquity": _safe_num(info.get("returnOnEquity")),
        "debtToEquity": _safe_num(info.get("debtToEquity")),
    }

    return {
        "summary": summary,
        "income_statement": income_rows,
        "balance_sheet": balance_rows,
        "cashflow": cash_rows,
    }


def search_stock_bundle(query: str, period: str = "6mo", interval: str = "1d") -> dict:
    symbol = resolve_symbol(query)
    if not symbol:
        return {"error": "Empty query"}

    warnings: List[str] = []

    # 1) Fetch K-line first. This is the most important output and should survive partial upstream failures.
    try:
        df = fetch_ohlcv(symbol, period=period, interval=interval)
    except Exception as e:
        return {
            "error": (
                f"数据源限流或网络抖动：{e}。"
                "建议配置 ALPHAVANTAGE_API_KEY（或 STOOQ_API_KEY）以提高稳定性。"
            ),
            "symbol": symbol,
        }
    if df.empty:
        return {
            "error": f"No market data for {symbol}. Try again later or switch period/interval.",
            "symbol": symbol,
        }
    if "cache" in str(df.attrs.get("source", "")):
        warnings.append("当前返回的是最近成功缓存数据（非最新实时请求）")

    # 2) Fetch profile/financials best-effort (can fail due to rate limits).
    tk = yf.Ticker(symbol)
    info = {}
    try:
        info = tk.info if tk.info else {}
    except Exception as e:
        warnings.append(f"profile/financials temporarily unavailable: {e}")

    kline = []
    for idx, row in df.tail(240).iterrows():
        kline.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(float(row.get("open", 0.0)), 4),
                "high": round(float(row.get("high", 0.0)), 4),
                "low": round(float(row.get("low", 0.0)), 4),
                "close": round(float(row.get("close", 0.0)), 4),
                "volume": int(row.get("volume", 0) or 0),
            }
        )

    profile = {
        "symbol": symbol,
        "shortName": info.get("shortName"),
        "longName": info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "website": info.get("website"),
        "longBusinessSummary": info.get("longBusinessSummary"),
        "currency": info.get("currency"),
        "exchange": info.get("exchange"),
    }

    financials = {"summary": {}, "income_statement": [], "balance_sheet": [], "cashflow": []}
    if info:
        try:
            financials = _extract_financials(tk, info)
        except Exception as e:
            warnings.append(f"financial statements unavailable: {e}")

    return {
        "query": query,
        "symbol": symbol,
        "data_source": df.attrs.get("source", "unknown"),
        "profile": profile,
        "kline": kline,
        "financials": financials,
        "warnings": warnings,
    }
