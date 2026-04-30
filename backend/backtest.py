from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

import numpy as np
import pandas as pd

from .indicators import rsi, sma


@dataclass
class StrategyDef:
    code: str
    name: str
    description: str


STRATEGIES = [
    StrategyDef("ma_cross", "均线金叉", "MA10 上穿 MA30 买入，下穿卖出"),
    StrategyDef("rsi_revert", "RSI 均值回归", "RSI<30 买入，RSI>60 卖出"),
]


def signal_ma_cross(df: pd.DataFrame) -> pd.Series:
    c = df["close"]
    fast = sma(c, 10)
    slow = sma(c, 30)
    sig = (fast > slow).astype(int)
    return sig


def signal_rsi_revert(df: pd.DataFrame) -> pd.Series:
    rv = rsi(df["close"], 14)
    sig = pd.Series(index=df.index, data=np.nan)
    holding = 0
    for i in range(len(df)):
        if pd.isna(rv.iloc[i]):
            sig.iloc[i] = holding
            continue
        if holding == 0 and rv.iloc[i] < 30:
            holding = 1
        elif holding == 1 and rv.iloc[i] > 60:
            holding = 0
        sig.iloc[i] = holding
    return sig.fillna(method="ffill").fillna(0).astype(int)


SIGNAL_MAP: Dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "ma_cross": signal_ma_cross,
    "rsi_revert": signal_rsi_revert,
}


def run_backtest(df: pd.DataFrame, strategy_code: str, init_cash: float = 10000.0) -> dict:
    if df.empty:
        return {"error": "No data"}
    sig_fn = SIGNAL_MAP.get(strategy_code)
    if not sig_fn:
        return {"error": "Unknown strategy"}

    px = df["close"].copy()
    signal = sig_fn(df).reindex(px.index).fillna(0)
    ret = px.pct_change().fillna(0)
    strategy_ret = ret * signal.shift(1).fillna(0)

    equity = (1 + strategy_ret).cumprod() * init_cash
    bh_equity = (1 + ret).cumprod() * init_cash

    total_return = equity.iloc[-1] / init_cash - 1
    bh_return = bh_equity.iloc[-1] / init_cash - 1
    max_drawdown = ((equity / equity.cummax()) - 1).min()
    sharpe = 0.0
    if strategy_ret.std() > 1e-9:
        sharpe = (strategy_ret.mean() / strategy_ret.std()) * (252 ** 0.5)

    trades = int((signal.diff().abs() == 1).sum())

    curve = [
        {"date": idx.strftime("%Y-%m-%d"), "equity": round(float(val), 2)}
        for idx, val in equity.items()
    ]

    return {
        "strategy": strategy_code,
        "init_cash": init_cash,
        "final_equity": round(float(equity.iloc[-1]), 2),
        "total_return": round(float(total_return), 4),
        "buy_hold_return": round(float(bh_return), 4),
        "max_drawdown": round(float(max_drawdown), 4),
        "sharpe": round(float(sharpe), 4),
        "trades": trades,
        "curve": curve,
    }
