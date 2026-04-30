from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

import pandas as pd

from .indicators import rsi, sma


@dataclass
class PresetCondition:
    code: str
    name: str
    description: str


PRESETS: List[PresetCondition] = [
    PresetCondition("bull_trend", "多头趋势", "收盘价 > MA20 > MA60 且 RSI(14) 在 45~70"),
    PresetCondition("oversold_rebound", "超跌反弹", "RSI(14) < 35 且 最新收盘价重新站上 MA20"),
    PresetCondition("volume_breakout", "放量突破", "最新成交量 > 20日均量*1.5 且 收盘价创新20日新高"),
]


def _bull_trend(df: pd.DataFrame) -> bool:
    if len(df) < 80:
        return False
    c = df["close"]
    ma20 = sma(c, 20)
    ma60 = sma(c, 60)
    rv = rsi(c, 14)
    row = pd.DataFrame({"c": c, "ma20": ma20, "ma60": ma60, "rsi": rv}).dropna().iloc[-1]
    return bool(row["c"] > row["ma20"] > row["ma60"] and 45 <= row["rsi"] <= 70)


def _oversold_rebound(df: pd.DataFrame) -> bool:
    if len(df) < 40:
        return False
    c = df["close"]
    ma20 = sma(c, 20)
    rv = rsi(c, 14)
    stat = pd.DataFrame({"c": c, "ma20": ma20, "rsi": rv}).dropna()
    if len(stat) < 2:
        return False
    last = stat.iloc[-1]
    prev = stat.iloc[-2]
    return bool(prev["c"] < prev["ma20"] and last["c"] > last["ma20"] and last["rsi"] < 35)


def _volume_breakout(df: pd.DataFrame) -> bool:
    if len(df) < 30 or "volume" not in df.columns:
        return False
    c = df["close"]
    v = df["volume"]
    vol20 = v.rolling(20).mean()
    high20 = c.rolling(20).max()
    row = pd.DataFrame({"c": c, "v": v, "vol20": vol20, "h20": high20}).dropna().iloc[-1]
    return bool(row["v"] > row["vol20"] * 1.5 and row["c"] >= row["h20"])


CONDITION_MAP: Dict[str, Callable[[pd.DataFrame], bool]] = {
    "bull_trend": _bull_trend,
    "oversold_rebound": _oversold_rebound,
    "volume_breakout": _volume_breakout,
}


def run_screener(data: dict[str, pd.DataFrame], condition_codes: List[str]) -> list[dict]:
    chosen = [CONDITION_MAP[c] for c in condition_codes if c in CONDITION_MAP]
    if not chosen:
        return []

    rows: list[dict] = []
    for ticker, df in data.items():
        if df.empty:
            continue
        hits = []
        for code in condition_codes:
            fn = CONDITION_MAP.get(code)
            if fn and fn(df):
                hits.append(code)
        if hits:
            rows.append(
                {
                    "ticker": ticker,
                    "last_close": round(float(df["close"].iloc[-1]), 2),
                    "matched": hits,
                }
            )
    return rows
