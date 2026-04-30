from __future__ import annotations

import sys
from pathlib import Path
from typing import List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.backtest import STRATEGIES, run_backtest
from backend.market_data import choose_universe, fetch_multi_tickers, fetch_ohlcv
from backend.screener import PRESETS, run_screener
from backend.stock_lookup import search_stock_bundle


class ScreenRequest(BaseModel):
    tickers: List[str] | None = None
    period: str = "6mo"
    conditions: List[str] = Field(default_factory=lambda: ["bull_trend"])


class BacktestRequest(BaseModel):
    ticker: str
    strategy: str = "ma_cross"
    period: str = "1y"
    init_cash: float = 10000.0


class StockSearchRequest(BaseModel):
    query: str
    period: str = "6mo"
    interval: str = "1d"


app = FastAPI(title="US Stock Quant API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/presets")
def get_presets():
    return {"presets": [p.__dict__ for p in PRESETS], "strategies": [s.__dict__ for s in STRATEGIES]}


@app.post("/api/screen")
def screen(req: ScreenRequest):
    universe = choose_universe(req.tickers)
    data = fetch_multi_tickers(universe, period=req.period)
    rows = run_screener(data, req.conditions)
    return {"universe_size": len(universe), "match_count": len(rows), "results": rows}


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    df = fetch_ohlcv(req.ticker.upper(), period=req.period)
    result = run_backtest(df, req.strategy, init_cash=req.init_cash)
    result["ticker"] = req.ticker.upper()
    return result


@app.post("/api/stock/search")
def stock_search(req: StockSearchRequest):
    return search_stock_bundle(req.query, period=req.period, interval=req.interval)
