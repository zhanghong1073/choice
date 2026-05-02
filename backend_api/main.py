from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
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


class TradeStrategyRunRequest(BaseModel):
    tickers: List[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA"])
    period: str = "6mo"
    strategy: str = "ma_cross"
    init_cash: float = 10000.0


app = FastAPI(title="US Stock Quant API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_DIR = ROOT_DIR / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "quant.db"


def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _db_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


_init_db()


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


@app.post("/api/strategy/run")
def run_us_trade_strategy(req: TradeStrategyRunRequest):
    run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tickers = [t.strip().upper() for t in req.tickers if t.strip()]
    if not tickers:
        return {"run_at": run_at, "status": "failed", "message": "tickers is empty", "rows": []}

    rows = []
    success = 0
    for t in tickers:
        try:
            df = fetch_ohlcv(t, period=req.period, interval="1d")
            if df.empty:
                rows.append({"ticker": t, "signal": "N/A", "result": "无行情数据"})
                continue
            bt = run_backtest(df, req.strategy, init_cash=req.init_cash)
            total_return = bt.get("total_return")
            if total_return is None:
                rows.append({"ticker": t, "signal": "N/A", "result": "回测失败"})
                continue

            signal = "BUY" if total_return > 0.05 else "SELL" if total_return < -0.05 else "HOLD"
            result_text = f"收益 {round(float(total_return) * 100, 2)}%, Sharpe {bt.get('sharpe', '-')}"
            rows.append({"ticker": t, "signal": signal, "result": result_text})
            success += 1
        except Exception as e:
            rows.append({"ticker": t, "signal": "N/A", "result": f"执行异常: {str(e)[:60]}"})

    status = "success" if success > 0 else "failed"
    message = f"完成 {len(tickers)} 只，成功 {success} 只"
    details_text = " | ".join([f"{r['ticker']}:{r['signal']}/{r['result']}" for r in rows])
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = _db_conn()
    try:
        conn.execute(
            """
            INSERT INTO strategy_runs (run_at, status, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_at, status, message, json.dumps(rows, ensure_ascii=False), created_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {"run_at": run_at, "status": status, "message": message, "rows": rows, "details_text": details_text}


@app.get("/api/strategy/runs")
def list_strategy_runs(limit: int = 50):
    lim = max(1, min(limit, 200))
    conn = _db_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, run_at, status, message, details_json, created_at
            FROM strategy_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    finally:
        conn.close()

    out = []
    for r in rows:
        details = []
        try:
            details = json.loads(r["details_json"] or "[]")
        except Exception:
            details = []
        details_text = " | ".join([f"{x.get('ticker')}:{x.get('signal')}/{x.get('result')}" for x in details])
        out.append(
            {
                "id": r["id"],
                "run_at": r["run_at"],
                "status": r["status"],
                "result": f"{r['message']}{(' | ' + details_text) if details_text else ''}",
                "created_at": r["created_at"],
            }
        )
    return {"rows": out}
