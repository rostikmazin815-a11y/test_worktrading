"""
Strategy Comparison Dashboard — FastAPI backend.
Optimized: cached Docker client, batch container lookup, persistent httpx client,
cached HTML, single DB reads.
"""

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import docker
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="Strategy Dashboard")

DB_DIR = Path("/app/user_data/dbs")
LOG_DIR = Path("/app/user_data/logs")
WALLET = 1000.0

BASE_STRATEGIES = [
    "RSI_MeanReversion",
    "MACD_Crossover",
    "BollingerBands_Bounce",
    "EMA_Cross",
    "Stochastic_RSI",
    "ADX_Trend",
    "Ichimoku_Cloud",
    "VWAP_Reversion",
    "SuperTrend",
    "TripleEMA_Momentum",
]
TIMEFRAMES = ["15m", "1h"]


def _service_name(strategy: str, timeframe: str) -> str:
    return f"{strategy.lower()}_{timeframe}".replace("__", "_")


def _instance_key(strategy: str, timeframe: str) -> str:
    return f"{strategy}_{timeframe}"


STRATEGY_INSTANCES = [
    {
        "key": _instance_key(strategy, timeframe),
        "strategy": strategy,
        "timeframe": timeframe,
        "service": _service_name(strategy, timeframe),
        "display_name": strategy.replace("_", " "),
    }
    for timeframe in TIMEFRAMES
    for strategy in BASE_STRATEGIES
]

PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
BINANCE_SYMBOLS = {
    "BTC/USDT:USDT": "BTCUSDT",
    "ETH/USDT:USDT": "ETHUSDT",
    "SOL/USDT:USDT": "SOLUSDT",
}

# ─── Cached singletons ─────────────────────────

_docker_client = None
_http_client = None
_html_cache = None

# Container status cache
_container_cache: dict = {}
_container_cache_ts: float = 0

# Price cache
_price_cache: dict = {}
_price_cache_ts: float = 0


def _get_docker():
    global _docker_client
    if _docker_client is None:
        try:
            _docker_client = docker.from_env()
        except Exception:
            pass
    return _docker_client


def _get_http():
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=3.0)
    return _http_client


def _get_html():
    global _html_cache
    if _html_cache is None:
        _html_cache = (Path(__file__).parent / "templates" / "index.html").read_text()
    return _html_cache


# ─── Batch container status ─────────────────────

def _refresh_container_statuses_sync():
    """Single Docker API call to get ALL container statuses (runs in bg thread)."""
    global _container_cache, _container_cache_ts
    client = _get_docker()
    if not client:
        return

    try:
        containers = client.containers.list(all=True, filters={
            "label": ["com.docker.compose.service"]
        })
        service_status = {}
        for c in containers:
            svc = c.labels.get("com.docker.compose.service", "")
            if svc:
                service_status[svc] = c.status
        _container_cache = service_status
        _container_cache_ts = time.monotonic()
    except Exception:
        pass


def _get_container_statuses() -> dict[str, str]:
    """Return cached statuses; refresh in background if stale."""
    now = time.monotonic()
    if now - _container_cache_ts > 3.0 or not _container_cache:
        # Fire and forget background refresh
        _executor.submit(_refresh_container_statuses_sync)
        if not _container_cache:
            # First call — wait for it
            try:
                _executor.submit(_refresh_container_statuses_sync).result(timeout=5)
            except Exception:
                pass
    return _container_cache or {item["service"]: "unknown" for item in STRATEGY_INSTANCES}


def _get_container_for_action(service_name: str):
    """Get container object for start/stop actions (not cached)."""
    client = _get_docker()
    if not client:
        return None
    try:
        containers = client.containers.list(all=True, filters={
            "label": [f"com.docker.compose.service={service_name}"]
        })
        return containers[0] if containers else None
    except Exception:
        return None


# ─── Price fetching ─────────────────────────────

async def _fetch_prices() -> dict[str, float]:
    """Fetch tracked futures prices, cached 2s."""
    global _price_cache, _price_cache_ts
    now = time.monotonic()
    if now - _price_cache_ts < 2.0 and _price_cache:
        return _price_cache

    try:
        client = _get_http()
        for pair, sym in BINANCE_SYMBOLS.items():
            resp = await client.get(
                f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={sym}"
            )
            if resp.status_code == 200:
                data = resp.json()
                _price_cache[pair] = float(data["price"])
        _price_cache_ts = now
    except Exception:
        pass
    return _price_cache


# ─── Database queries ───────────────────────────

def _query_db(db_path: Path, query: str) -> list[dict]:
    if not db_path.exists():
        return []
    connection_attempts = [
        {
            "database": str(db_path),
            "kwargs": {"timeout": 1, "isolation_level": None},
        },
        {
            "database": f"file:{db_path}?mode=ro",
            "kwargs": {"uri": True, "timeout": 1, "isolation_level": None},
        },
    ]

    for attempt in connection_attempts:
        conn = None
        try:
            conn = sqlite3.connect(attempt["database"], **attempt["kwargs"])
            conn.execute("PRAGMA busy_timeout=500")
            conn.execute("PRAGMA read_uncommitted=1")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            continue
        finally:
            if conn is not None:
                conn.close()

    return []


def _get_closed_trades(strategy_key: str) -> list[dict]:
    return _query_db(
        DB_DIR / f"{strategy_key}.sqlite",
        """SELECT pair, is_short, open_rate, close_rate,
                  close_profit, close_profit_abs, stake_amount, amount,
                  fee_open_cost, fee_close_cost, funding_fees, timeframe,
                  open_date, close_date, exit_reason, strategy, enter_tag
           FROM trades WHERE is_open = 0 ORDER BY close_date ASC""",
    )


def _get_open_trades(strategy_key: str) -> list[dict]:
    return _query_db(
        DB_DIR / f"{strategy_key}.sqlite",
        """SELECT id, pair, is_short, open_rate, stake_amount, amount,
                  leverage, funding_fees, funding_fee_running,
                  fee_open, fee_open_cost, fee_close,
                  open_date, strategy, enter_tag, timeframe,
                  stop_loss, initial_stop_loss, max_rate, min_rate
           FROM trades WHERE is_open = 1""",
    )


_executor = ThreadPoolExecutor(max_workers=10)

# Strategies data cache
_strategies_cache: list = []
_strategies_cache_ts: float = 0

# Trade data cache per strategy
_trades_cache: dict = {}  # strategy -> {"open": [...], "closed": [...]}
_trades_cache_ts: float = 0


def _refresh_all_trades():
    """Load all trades from all DBs in parallel threads."""
    global _trades_cache, _trades_cache_ts
    now = time.monotonic()
    if now - _trades_cache_ts < 2.0 and _trades_cache:
        return _trades_cache

    def load_one(instance):
        key = instance["key"]
        return key, _get_open_trades(key), _get_closed_trades(key)

    futures = [_executor.submit(load_one, instance) for instance in STRATEGY_INSTANCES]
    result = {}
    for f in futures:
        try:
            strategy, open_t, closed_t = f.result(timeout=3)
            result[strategy] = {"open": open_t, "closed": closed_t}
        except Exception:
            pass

    _trades_cache = result
    _trades_cache_ts = now
    return result


def _load_strategy_data(instance: dict, statuses: dict, trades_data: dict) -> dict:
    """Build strategy response from cached trade data."""
    data = trades_data.get(instance["key"], {"open": [], "closed": []})
    metrics = _compute_metrics(data["closed"])
    return {
        "key": instance["key"],
        "name": instance["strategy"],
        "display_name": instance["display_name"],
        "timeframe": instance["timeframe"],
        "service": instance["service"],
        "status": statuses.get(instance["service"], "not_found"),
        "open_trades": len(data["open"]),
        "closed_trades": len(data["closed"]),
        "metrics": metrics,
    }


# ─── Metrics (pure python, no numpy) ───────────

def _compute_metrics(trades: list[dict]) -> dict:
    empty = {
        "total_trades": 0, "profit_usdt": 0.0, "profit_pct": 0.0,
        "win_rate": 0.0, "avg_duration_min": 0.0, "max_drawdown_pct": 0.0,
        "sharpe": 0.0, "total_funding": 0.0, "total_fees": 0.0,
        "longs": 0, "shorts": 0, "best_pct": 0.0, "worst_pct": 0.0,
    }
    if not trades:
        return empty

    profits_abs = [t["close_profit_abs"] or 0.0 for t in trades]
    profits_pct = [t["close_profit"] or 0.0 for t in trades]
    total_profit = sum(profits_abs)
    wins = sum(1 for p in profits_abs if p > 0)
    n = len(trades)

    # Duration
    total_dur = 0.0
    dur_count = 0
    for t in trades:
        try:
            od = datetime.fromisoformat(t["open_date"])
            cd = datetime.fromisoformat(t["close_date"])
            total_dur += (cd - od).total_seconds() / 60
            dur_count += 1
        except (TypeError, ValueError):
            pass

    # Max drawdown (pure python)
    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for p in profits_abs:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    # Sharpe (pure python)
    sharpe = 0.0
    if n > 1:
        mean_r = sum(profits_pct) / n
        var_r = sum((r - mean_r) ** 2 for r in profits_pct) / n
        if var_r > 0:
            sharpe = mean_r / (var_r ** 0.5) * (n ** 0.5)

    return {
        "total_trades": n,
        "profit_usdt": round(total_profit, 2),
        "profit_pct": round(total_profit / WALLET * 100, 2),
        "win_rate": round(wins / n * 100, 1),
        "avg_duration_min": round(total_dur / dur_count, 1) if dur_count else 0.0,
        "max_drawdown_pct": round(max_dd / WALLET * 100, 2),
        "sharpe": round(sharpe, 2),
        "total_funding": round(sum(abs(t["funding_fees"] or 0.0) for t in trades), 4),
        "total_fees": round(sum((t["fee_open_cost"] or 0.0) + (t["fee_close_cost"] or 0.0) for t in trades), 4),
        "longs": sum(1 for t in trades if not t["is_short"]),
        "shorts": sum(1 for t in trades if t["is_short"]),
        "best_pct": round(max(profits_pct) * 100, 2),
        "worst_pct": round(min(profits_pct) * 100, 2),
    }


# ─── API Routes ─────────────────────────────────


@app.on_event("startup")
async def startup_warmup():
    """Pre-warm caches on startup so first request is fast."""
    _executor.submit(_refresh_container_statuses_sync)
    _executor.submit(_refresh_all_trades)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(_get_html())


@app.get("/api/strategies")
async def api_strategies():
    global _strategies_cache, _strategies_cache_ts
    now = time.monotonic()
    if now - _strategies_cache_ts < 2.0 and _strategies_cache:
        return _strategies_cache

    statuses = _get_container_statuses()
    trades_data = _refresh_all_trades()

    result = [_load_strategy_data(instance, statuses, trades_data) for instance in STRATEGY_INSTANCES]
    result.sort(key=lambda x: x["metrics"]["profit_usdt"], reverse=True)
    _strategies_cache = result
    _strategies_cache_ts = now
    return result


@app.get("/api/trades/{strategy}")
async def api_trades(strategy: str):
    instance = next((item for item in STRATEGY_INSTANCES if item["key"] == strategy), None)
    if not instance:
        raise HTTPException(404, f"Unknown strategy: {strategy}")
    trades_data = _refresh_all_trades()
    data = trades_data.get(instance["key"], {"open": [], "closed": []})
    return {"closed": data["closed"], "open": data["open"]}


@app.get("/api/equity")
async def api_equity():
    trades_data = _refresh_all_trades()
    curves = {}
    for instance in STRATEGY_INSTANCES:
        strategy = instance["key"]
        trades = trades_data.get(strategy, {}).get("closed", [])
        if not trades:
            curves[strategy] = []
            continue
        cum = 0.0
        points = []
        for t in trades:
            cum += t["close_profit_abs"] or 0.0
            points.append({"date": t["close_date"], "profit": round(cum, 2)})
        curves[strategy] = points
    return curves


@app.get("/api/positions")
async def api_positions():
    prices = await _fetch_prices()
    trades_data = _refresh_all_trades()
    result = []
    total_unrealized = 0.0

    for instance in STRATEGY_INSTANCES:
        strategy = instance["key"]
        for t in trades_data.get(strategy, {}).get("open", []):
            current_price = prices.get(t["pair"], 0.0)
            open_rate = t["open_rate"] or 0.0
            amount = t["amount"] or 0.0
            is_short = bool(t["is_short"])
            funding = (t["funding_fees"] or 0.0) + (t["funding_fee_running"] or 0.0)
            fee_open_cost = t["fee_open_cost"] or 0.0

            if current_price > 0 and open_rate > 0 and amount > 0:
                pnl = (open_rate - current_price if is_short else current_price - open_rate) * amount
                fee_close_rate = t["fee_close"] or 0.0004
                close_fee_est = current_price * amount * fee_close_rate
                pnl_net = pnl - fee_open_cost - close_fee_est - abs(funding)
                pnl_pct = (pnl_net / (t["stake_amount"] or 1)) * 100
            else:
                pnl_net = 0.0
                pnl_pct = 0.0

            total_unrealized += pnl_net

            try:
                dur_min = (datetime.utcnow() - datetime.fromisoformat(t["open_date"])).total_seconds() / 60
            except (TypeError, ValueError):
                dur_min = 0.0

            result.append({
                "strategy": instance["strategy"],
                "strategy_key": strategy,
                "timeframe": instance["timeframe"],
                "id": t["id"], "pair": t["pair"],
                "is_short": is_short,
                "open_rate": round(open_rate, 2),
                "current_price": round(current_price, 2),
                "amount": round(amount, 6),
                "stake_amount": round(t["stake_amount"] or 0, 2),
                "leverage": t["leverage"] or 1.0,
                "pnl": round(pnl_net, 4), "pnl_pct": round(pnl_pct, 2),
                "funding_fees": round(funding, 4),
                "duration_min": round(dur_min, 1),
                "open_date": t["open_date"],
                "stop_loss": t["stop_loss"], "enter_tag": t["enter_tag"],
            })

    result.sort(key=lambda x: (x["strategy"], x["pair"]))
    return {
        "positions": result,
        "total_unrealized": round(total_unrealized, 4),
        "prices": {k: round(v, 2) for k, v in prices.items()},
    }


@app.get("/api/history")
async def api_history(limit: int = 100):
    trades_data = _refresh_all_trades()
    all_trades = []
    for instance in STRATEGY_INSTANCES:
        strategy = instance["key"]
        for t in trades_data.get(strategy, {}).get("closed", []):
            all_trades.append({
                "strategy": instance["strategy"],
                "strategy_key": strategy,
                "timeframe": instance["timeframe"],
                "pair": t["pair"],
                "is_short": bool(t["is_short"]),
                "open_rate": round(t["open_rate"] or 0, 2),
                "close_rate": round(t["close_rate"] or 0, 2),
                "profit": round(t["close_profit_abs"] or 0, 4),
                "profit_pct": round((t["close_profit"] or 0) * 100, 2),
                "stake_amount": round(t["stake_amount"] or 0, 2),
                "fee_open": round(t["fee_open_cost"] or 0, 4),
                "fee_close": round(t["fee_close_cost"] or 0, 4),
                "funding_fees": round(t["funding_fees"] or 0, 4),
                "exit_reason": t["exit_reason"], "enter_tag": t["enter_tag"],
                "open_date": t["open_date"], "close_date": t["close_date"],
            })
    all_trades.sort(key=lambda t: t.get("close_date") or "", reverse=True)
    return all_trades[:limit]


@app.post("/api/start/{strategy}")
async def api_start(strategy: str):
    instance = next((item for item in STRATEGY_INSTANCES if item["key"] == strategy), None)
    if not instance:
        raise HTTPException(404)
    c = _get_container_for_action(instance["service"])
    if not c:
        raise HTTPException(404, "Container not found")
    c.start()
    global _container_cache_ts
    _container_cache_ts = 0
    return {"status": "started", "strategy": strategy}


@app.post("/api/stop/{strategy}")
async def api_stop(strategy: str):
    instance = next((item for item in STRATEGY_INSTANCES if item["key"] == strategy), None)
    if not instance:
        raise HTTPException(404)
    c = _get_container_for_action(instance["service"])
    if not c:
        raise HTTPException(404, "Container not found")
    c.stop(timeout=15)
    global _container_cache_ts
    _container_cache_ts = 0
    return {"status": "stopped", "strategy": strategy}


@app.post("/api/start-all")
async def api_start_all():
    global _container_cache_ts
    results = {}
    for instance in STRATEGY_INSTANCES:
        c = _get_container_for_action(instance["service"])
        if c:
            try:
                c.start()
                results[instance["key"]] = "started"
            except Exception as e:
                results[instance["key"]] = f"error: {e}"
        else:
            results[instance["key"]] = "not_found"
    _container_cache_ts = 0
    return results


@app.post("/api/stop-all")
async def api_stop_all():
    global _container_cache_ts
    results = {}
    for instance in STRATEGY_INSTANCES:
        c = _get_container_for_action(instance["service"])
        if c:
            try:
                c.stop(timeout=15)
                results[instance["key"]] = "stopped"
            except Exception as e:
                results[instance["key"]] = f"error: {e}"
        else:
            results[instance["key"]] = "not_found"
    _container_cache_ts = 0
    return results


@app.get("/api/logs/{strategy}")
async def api_logs(strategy: str, lines: int = 100):
    instance = next((item for item in STRATEGY_INSTANCES if item["key"] == strategy), None)
    if not instance:
        raise HTTPException(404)
    log_path = LOG_DIR / f"{instance['key']}.log"
    if not log_path.exists():
        return {"lines": [], "strategy": strategy}
    try:
        with open(log_path, "rb") as f:
            # Read only tail of file efficiently
            try:
                f.seek(0, 2)
                size = f.tell()
                # Read last 50KB max
                read_size = min(size, 50_000)
                f.seek(size - read_size)
                tail = f.read().decode("utf-8", errors="replace")
            except Exception:
                f.seek(0)
                tail = f.read().decode("utf-8", errors="replace")
        return {"lines": tail.split("\n")[-lines:], "strategy": strategy}
    except Exception as e:
        raise HTTPException(500, str(e))
