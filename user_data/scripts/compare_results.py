#!/usr/bin/env python3
"""
Compare paper-trading strategy results and export a unified analytics SQLite database.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WALLET = 1000.0
ROOT_DIR = Path(__file__).resolve().parent.parent
DB_DIR = ROOT_DIR / "dbs"
RESULTS_DIR = ROOT_DIR / "backtest_results"
DEFAULT_EXPORT_DB = RESULTS_DIR / "paper_trading_analysis.sqlite"
DEFAULT_REPORT = RESULTS_DIR / "paper_trading_report.md"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def parse_strategy_key(strategy_key: str) -> tuple[str, str]:
    for timeframe in ("15m", "1h"):
        suffix = f"_{timeframe}"
        if strategy_key.endswith(suffix):
            return strategy_key[: -len(suffix)], timeframe
    return strategy_key, "unknown"


def query_trades(db_path: Path) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                pair,
                is_short,
                open_rate,
                close_rate,
                close_profit,
                close_profit_abs,
                stake_amount,
                amount,
                leverage,
                fee_open_cost,
                fee_close_cost,
                funding_fees,
                open_date,
                close_date,
                exit_reason,
                strategy,
                enter_tag
            FROM trades
            WHERE is_open = 0
            ORDER BY close_date ASC, id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_open_trades(db_path: Path) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                id,
                pair,
                is_short,
                open_rate,
                stake_amount,
                amount,
                leverage,
                funding_fees,
                open_date,
                strategy,
                enter_tag
            FROM trades
            WHERE is_open = 1
            ORDER BY open_date ASC, id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_custom_data(db_path: Path) -> dict[int, dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT ft_trade_id, cd_key, cd_type, cd_value
            FROM trade_custom_data
            ORDER BY ft_trade_id ASC, cd_key ASC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return {}
    finally:
        conn.close()

    grouped: dict[int, dict[str, Any]] = defaultdict(dict)
    for row in rows:
        trade_id = row["ft_trade_id"]
        value: Any = row["cd_value"]
        if row["cd_type"] == "bool":
            value = row["cd_value"].lower() == "true"
        elif row["cd_type"] == "int":
            value = int(row["cd_value"])
        elif row["cd_type"] == "float":
            value = float(row["cd_value"])
        elif row["cd_type"] not in {"str"}:
            value = json.loads(row["cd_value"])
        grouped[trade_id][row["cd_key"]] = value
    return grouped


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def safe_round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def outcome_label(profit_abs: float, epsilon: float = 1e-9) -> str:
    if profit_abs > epsilon:
        return "win"
    if profit_abs < -epsilon:
        return "loss"
    return "flat"


def compute_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "profit_usdt": 0.0,
            "profit_pct": 0.0,
            "win_rate": 0.0,
            "avg_duration_min": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "total_funding": 0.0,
            "total_fees": 0.0,
            "longs": 0,
            "shorts": 0,
            "best_trade_pct": 0.0,
            "worst_trade_pct": 0.0,
            "wins": 0,
            "losses": 0,
            "flats": 0,
            "avg_profit_pct": 0.0,
            "expectancy_usdt": 0.0,
            "avg_win_usdt": 0.0,
            "avg_loss_usdt": 0.0,
            "profit_factor": 0.0,
            "net_after_costs_usdt": 0.0,
        }

    profits_abs = [float(t.get("close_profit_abs") or 0.0) for t in trades]
    profits_pct = [float(t.get("close_profit") or 0.0) for t in trades]
    win_values = [p for p in profits_abs if p > 0]
    loss_values = [p for p in profits_abs if p < 0]
    wins = len(win_values)
    losses = len(loss_values)
    flats = len(trades) - wins - losses

    durations = []
    for trade in trades:
        opened = parse_dt(trade.get("open_date"))
        closed = parse_dt(trade.get("close_date"))
        if opened and closed:
            durations.append((closed - opened).total_seconds() / 60.0)

    running_profit = 0.0
    running_max = 0.0
    max_drawdown = 0.0
    for profit in profits_abs:
        running_profit += profit
        running_max = max(running_max, running_profit)
        max_drawdown = max(max_drawdown, running_max - running_profit)

    sharpe = 0.0
    if len(profits_pct) > 1:
        mean_return = sum(profits_pct) / len(profits_pct)
        variance = sum((value - mean_return) ** 2 for value in profits_pct) / len(profits_pct)
        stddev = math.sqrt(variance)
        if stddev > 0:
            sharpe = mean_return / stddev * math.sqrt(len(profits_pct))

    total_profit = float(sum(profits_abs))
    total_funding_signed = float(sum(t.get("funding_fees") or 0.0 for t in trades))
    total_funding = float(sum(abs(t.get("funding_fees") or 0.0) for t in trades))
    total_fees = float(
        sum((t.get("fee_open_cost") or 0.0) + (t.get("fee_close_cost") or 0.0) for t in trades)
    )
    gross_wins = float(sum(win_values))
    gross_losses_abs = float(abs(sum(loss_values)))
    profit_factor = gross_wins / gross_losses_abs if gross_losses_abs > 0 else (999.0 if gross_wins > 0 else 0.0)

    return {
        "total_trades": len(trades),
        "profit_usdt": safe_round(total_profit),
        "profit_pct": safe_round(total_profit / WALLET * 100),
        "win_rate": safe_round(wins / len(trades) * 100, 1),
        "avg_duration_min": safe_round(sum(durations) / len(durations), 1) if durations else 0.0,
        "max_drawdown_pct": safe_round(max_drawdown / WALLET * 100),
        "sharpe": safe_round(sharpe, 2),
        "total_funding": safe_round(total_funding),
        "total_fees": safe_round(total_fees),
        "longs": sum(1 for t in trades if not t.get("is_short")),
        "shorts": sum(1 for t in trades if t.get("is_short")),
        "best_trade_pct": safe_round(max(profits_pct) * 100),
        "worst_trade_pct": safe_round(min(profits_pct) * 100),
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "avg_profit_pct": safe_round((sum(profits_pct) / len(profits_pct)) * 100, 3),
        "expectancy_usdt": safe_round(total_profit / len(trades)),
        "avg_win_usdt": safe_round(gross_wins / wins) if wins else 0.0,
        "avg_loss_usdt": safe_round(sum(loss_values) / losses) if losses else 0.0,
        "profit_factor": safe_round(profit_factor, 2),
        "net_after_costs_usdt": safe_round(total_profit - total_fees - total_funding_signed),
    }


def print_table(results: list[tuple[str, dict[str, Any], int]]) -> None:
    header = (
        f"{'#':>2}  {'Strategy':<24} {'Trades':>6} {'Profit $':>9} {'Profit %':>9} "
        f"{'WinRate':>7} {'AvgDur':>8} {'MaxDD%':>7} {'PF':>6} "
        f"{'Funding':>8} {'Fees':>7} {'L/S':>7} {'Open':>4}"
    )
    separator = "-" * len(header)

    print("\n" + separator)
    print("  STRATEGY COMPARISON — Paper Trading Results")
    print(f"  Wallet: {WALLET} USDT | Mode: Futures (Binance) | TF: 15m + 1h")
    print(separator)
    print(header)
    print(separator)

    for rank, (name, metrics, open_count) in enumerate(results, 1):
        ls = f"{metrics['longs']}/{metrics['shorts']}"
        duration = f"{metrics['avg_duration_min']:.0f}m" if metrics["avg_duration_min"] else "-"
        print(
            f"{rank:>2}  {name:<24} {metrics['total_trades']:>6} {metrics['profit_usdt']:>+9.2f} "
            f"{metrics['profit_pct']:>+8.2f}% {metrics['win_rate']:>6.1f}% {duration:>8} "
            f"{metrics['max_drawdown_pct']:>6.2f}% {metrics['profit_factor']:>6.2f} "
            f"{metrics['total_funding']:>8.2f} {metrics['total_fees']:>7.2f} {ls:>7} {open_count:>4}"
        )

    print(separator)


def plot_equity_curves(all_results: list[tuple[str, list[dict[str, Any]]]]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Skipping chart.")
        print("Install: pip install matplotlib")
        return

    fig, ax = plt.subplots(figsize=(14, 7))
    for name, trades in all_results:
        if not trades:
            continue
        profits = [float(t.get("close_profit_abs") or 0.0) for t in trades]
        cumulative = []
        running_profit = 0.0
        for profit in profits:
            running_profit += profit
            cumulative.append(running_profit)
        dates = [parse_dt(t.get("close_date")) for t in trades]
        valid = [(date, value) for date, value in zip(dates, cumulative) if date is not None]
        if valid:
            ax.plot([v[0] for v in valid], [v[1] for v in valid], label=name, linewidth=1.5)

    ax.set_title("Strategy Equity Curves (Paper Trading)")
    ax.set_xlabel("Time")
    ax.set_ylabel("Cumulative Profit (USDT)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)

    chart_path = ROOT_DIR / "strategy_comparison.png"
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150)
    print(f"Chart saved: {chart_path}")
    plt.close()


def export_analysis_db(
    export_path: Path,
    strategy_rows: list[dict[str, Any]],
    pair_rows: list[dict[str, Any]],
    trigger_rows: list[dict[str, Any]],
    trade_rows: list[dict[str, Any]],
) -> None:
    export_path.parent.mkdir(parents=True, exist_ok=True)
    if export_path.exists():
        export_path.unlink()

    conn = sqlite3.connect(str(export_path))
    try:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE strategy_summary (
                strategy_key TEXT PRIMARY KEY,
                strategy TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                total_trades INTEGER NOT NULL,
                open_trades INTEGER NOT NULL,
                profit_usdt REAL NOT NULL,
                profit_pct REAL NOT NULL,
                win_rate REAL NOT NULL,
                avg_duration_min REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL,
                sharpe REAL NOT NULL,
                total_funding REAL NOT NULL,
                total_fees REAL NOT NULL,
                longs INTEGER NOT NULL,
                shorts INTEGER NOT NULL,
                best_trade_pct REAL NOT NULL,
                worst_trade_pct REAL NOT NULL,
                wins INTEGER NOT NULL,
                losses INTEGER NOT NULL,
                flats INTEGER NOT NULL,
                expectancy_usdt REAL NOT NULL,
                avg_win_usdt REAL NOT NULL,
                avg_loss_usdt REAL NOT NULL,
                profit_factor REAL NOT NULL,
                net_after_costs_usdt REAL NOT NULL,
                generated_at TEXT NOT NULL
            );

            CREATE TABLE pair_summary (
                strategy_key TEXT NOT NULL,
                strategy TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                pair TEXT NOT NULL,
                total_trades INTEGER NOT NULL,
                profit_usdt REAL NOT NULL,
                profit_pct REAL NOT NULL,
                win_rate REAL NOT NULL,
                avg_duration_min REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL,
                total_funding REAL NOT NULL,
                total_fees REAL NOT NULL,
                longs INTEGER NOT NULL,
                shorts INTEGER NOT NULL,
                wins INTEGER NOT NULL,
                losses INTEGER NOT NULL,
                flats INTEGER NOT NULL,
                expectancy_usdt REAL NOT NULL,
                avg_win_usdt REAL NOT NULL,
                avg_loss_usdt REAL NOT NULL,
                profit_factor REAL NOT NULL,
                net_after_costs_usdt REAL NOT NULL,
                PRIMARY KEY (strategy_key, pair)
            );

            CREATE TABLE trigger_summary (
                strategy_key TEXT NOT NULL,
                strategy TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                pair TEXT NOT NULL,
                enter_tag TEXT NOT NULL,
                total_trades INTEGER NOT NULL,
                profit_usdt REAL NOT NULL,
                profit_pct REAL NOT NULL,
                win_rate REAL NOT NULL,
                wins INTEGER NOT NULL,
                losses INTEGER NOT NULL,
                flats INTEGER NOT NULL,
                expectancy_usdt REAL NOT NULL,
                avg_win_usdt REAL NOT NULL,
                avg_loss_usdt REAL NOT NULL,
                profit_factor REAL NOT NULL,
                total_funding REAL NOT NULL,
                total_fees REAL NOT NULL,
                net_after_costs_usdt REAL NOT NULL,
                PRIMARY KEY (strategy_key, pair, enter_tag)
            );

            CREATE TABLE trade_analysis (
                source_db TEXT NOT NULL,
                strategy_key TEXT NOT NULL,
                strategy TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                trade_id INTEGER NOT NULL,
                pair TEXT NOT NULL,
                side TEXT NOT NULL,
                enter_tag TEXT,
                exit_reason TEXT,
                outcome TEXT NOT NULL,
                open_date TEXT,
                close_date TEXT,
                duration_min REAL,
                open_rate REAL,
                close_rate REAL,
                stake_amount REAL,
                amount REAL,
                leverage REAL,
                profit_ratio REAL,
                profit_abs REAL,
                funding_fees REAL,
                fee_open_cost REAL,
                fee_close_cost REAL,
                entry_context_json TEXT,
                exit_context_json TEXT,
                experiment_labels_json TEXT,
                custom_data_json TEXT,
                PRIMARY KEY (source_db, trade_id)
            );

            CREATE VIEW timeframe_summary AS
            SELECT timeframe,
                   COUNT(*) AS strategy_instances,
                   SUM(total_trades) AS total_trades,
                   SUM(open_trades) AS open_trades,
                   ROUND(SUM(profit_usdt), 2) AS profit_usdt,
                   ROUND(AVG(win_rate), 2) AS avg_win_rate,
                   ROUND(AVG(expectancy_usdt), 2) AS avg_expectancy_usdt,
                   ROUND(MAX(profit_usdt), 2) AS best_instance_profit_usdt
            FROM strategy_summary
            GROUP BY timeframe;

            CREATE VIEW trades_by_pair AS
            SELECT pair,
                   timeframe,
                   strategy,
                   COUNT(*) AS total_trades,
                   ROUND(SUM(profit_abs), 2) AS profit_usdt,
                   ROUND(AVG(profit_ratio) * 100, 3) AS avg_profit_pct,
                   ROUND(AVG(CASE WHEN outcome = 'win' THEN 1.0 ELSE 0.0 END) * 100, 2) AS win_rate
            FROM trade_analysis
            GROUP BY pair, timeframe, strategy;

            CREATE VIEW trades_by_trigger AS
            SELECT strategy,
                   timeframe,
                   pair,
                   COALESCE(enter_tag, 'untagged') AS enter_tag,
                   COUNT(*) AS total_trades,
                   ROUND(SUM(profit_abs), 2) AS profit_usdt,
                   ROUND(AVG(profit_ratio) * 100, 3) AS avg_profit_pct,
                   ROUND(AVG(CASE WHEN outcome = 'win' THEN 1.0 ELSE 0.0 END) * 100, 2) AS win_rate
            FROM trade_analysis
            GROUP BY strategy, timeframe, pair, COALESCE(enter_tag, 'untagged');

            CREATE VIEW formula_candidates AS
            SELECT timeframe,
                   pair,
                   strategy,
                   enter_tag,
                   total_trades,
                   profit_usdt,
                   win_rate,
                   expectancy_usdt,
                   profit_factor,
                   net_after_costs_usdt
            FROM trigger_summary
            WHERE total_trades >= 2
            ORDER BY net_after_costs_usdt DESC, profit_factor DESC, win_rate DESC;
            """
        )

        conn.executemany(
            """
            INSERT INTO strategy_summary (
                strategy_key, strategy, timeframe, total_trades, open_trades, profit_usdt, profit_pct,
                win_rate, avg_duration_min, max_drawdown_pct, sharpe, total_funding, total_fees, longs,
                shorts, best_trade_pct, worst_trade_pct, wins, losses, flats, expectancy_usdt,
                avg_win_usdt, avg_loss_usdt, profit_factor, net_after_costs_usdt, generated_at
            )
            VALUES (
                :strategy_key, :strategy, :timeframe, :total_trades, :open_trades, :profit_usdt, :profit_pct,
                :win_rate, :avg_duration_min, :max_drawdown_pct, :sharpe, :total_funding, :total_fees, :longs,
                :shorts, :best_trade_pct, :worst_trade_pct, :wins, :losses, :flats, :expectancy_usdt,
                :avg_win_usdt, :avg_loss_usdt, :profit_factor, :net_after_costs_usdt, :generated_at
            )
            """,
            strategy_rows,
        )

        conn.executemany(
            """
            INSERT INTO pair_summary (
                strategy_key, strategy, timeframe, pair, total_trades, profit_usdt, profit_pct, win_rate,
                avg_duration_min, max_drawdown_pct, total_funding, total_fees, longs, shorts, wins, losses,
                flats, expectancy_usdt, avg_win_usdt, avg_loss_usdt, profit_factor, net_after_costs_usdt
            )
            VALUES (
                :strategy_key, :strategy, :timeframe, :pair, :total_trades, :profit_usdt, :profit_pct, :win_rate,
                :avg_duration_min, :max_drawdown_pct, :total_funding, :total_fees, :longs, :shorts, :wins, :losses,
                :flats, :expectancy_usdt, :avg_win_usdt, :avg_loss_usdt, :profit_factor, :net_after_costs_usdt
            )
            """,
            pair_rows,
        )

        conn.executemany(
            """
            INSERT INTO trigger_summary (
                strategy_key, strategy, timeframe, pair, enter_tag, total_trades, profit_usdt, profit_pct,
                win_rate, wins, losses, flats, expectancy_usdt, avg_win_usdt, avg_loss_usdt, profit_factor,
                total_funding, total_fees, net_after_costs_usdt
            )
            VALUES (
                :strategy_key, :strategy, :timeframe, :pair, :enter_tag, :total_trades, :profit_usdt, :profit_pct,
                :win_rate, :wins, :losses, :flats, :expectancy_usdt, :avg_win_usdt, :avg_loss_usdt, :profit_factor,
                :total_funding, :total_fees, :net_after_costs_usdt
            )
            """,
            trigger_rows,
        )

        conn.executemany(
            """
            INSERT INTO trade_analysis (
                source_db, strategy_key, strategy, timeframe, trade_id, pair, side, enter_tag, exit_reason,
                outcome, open_date, close_date, duration_min, open_rate, close_rate, stake_amount, amount,
                leverage, profit_ratio, profit_abs, funding_fees, fee_open_cost, fee_close_cost,
                entry_context_json, exit_context_json, experiment_labels_json, custom_data_json
            )
            VALUES (
                :source_db, :strategy_key, :strategy, :timeframe, :trade_id, :pair, :side, :enter_tag, :exit_reason,
                :outcome, :open_date, :close_date, :duration_min, :open_rate, :close_rate, :stake_amount, :amount,
                :leverage, :profit_ratio, :profit_abs, :funding_fees, :fee_open_cost, :fee_close_cost,
                :entry_context_json, :exit_context_json, :experiment_labels_json, :custom_data_json
            )
            """,
            trade_rows,
        )

        conn.commit()
    finally:
        conn.close()


def format_report_row(
    row: dict[str, Any], columns: list[str], aliases: dict[str, str] | None = None
) -> str:
    aliases = aliases or {}
    return "| " + " | ".join(str(row.get(column, aliases.get(column, "-"))) for column in columns) + " |"


def top_rows(rows: list[dict[str, Any]], count: int = 5) -> list[dict[str, Any]]:
    return rows[:count]


def build_report(
    report_path: Path,
    generated_at: str,
    strategy_rows: list[dict[str, Any]],
    pair_rows: list[dict[str, Any]],
    trigger_rows: list[dict[str, Any]],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)

    overall = sorted(strategy_rows, key=lambda row: (row["net_after_costs_usdt"], row["profit_factor"]), reverse=True)
    by_pair = sorted(pair_rows, key=lambda row: (row["net_after_costs_usdt"], row["profit_factor"]), reverse=True)
    by_trigger = sorted(
        [row for row in trigger_rows if row["total_trades"] >= 2],
        key=lambda row: (row["net_after_costs_usdt"], row["profit_factor"], row["win_rate"]),
        reverse=True,
    )

    timeframe_aggregate: dict[str, dict[str, float]] = defaultdict(lambda: {"profit": 0.0, "trades": 0.0})
    for row in strategy_rows:
        timeframe_aggregate[row["timeframe"]]["profit"] += float(row["net_after_costs_usdt"])
        timeframe_aggregate[row["timeframe"]]["trades"] += float(row["total_trades"])

    lines = [
        "# Paper Trading Report",
        "",
        f"Generated at: `{generated_at}`",
        "",
        f"Wallet: `{WALLET:.0f} USDT`",
        "",
        "Universe: `BTC/USDT:USDT`, `ETH/USDT:USDT`, `SOL/USDT:USDT` on `15m` and `1h`",
        "",
        "## Summary",
        "",
        f"- Strategy instances: `{len(strategy_rows)}`",
        f"- Closed trades: `{sum(int(row['total_trades']) for row in strategy_rows)}`",
        f"- Open positions at export: `{sum(int(row['open_trades']) for row in strategy_rows)}`",
        f"- Net after costs: `{sum(float(row['net_after_costs_usdt']) for row in strategy_rows):+.2f} USDT`",
        "",
        "## Best Strategy Instances",
        "",
        "| Strategy Key | TF | Trades | Net After Costs | Win Rate | Expectancy | PF |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in top_rows(overall, 8):
        lines.append(
            f"| {row['strategy_key']} | {row['timeframe']} | {row['total_trades']} | "
            f"{row['net_after_costs_usdt']:+.2f} | {row['win_rate']:.1f}% | "
            f"{row['expectancy_usdt']:+.2f} | {row['profit_factor']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Best Coin x Timeframe x Strategy",
            "",
            "| Pair | TF | Strategy | Trades | Net After Costs | Win Rate | Expectancy | PF |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in top_rows(by_pair, 12):
        lines.append(
            f"| {row['pair']} | {row['timeframe']} | {row['strategy']} | {row['total_trades']} | "
            f"{row['net_after_costs_usdt']:+.2f} | {row['win_rate']:.1f}% | "
            f"{row['expectancy_usdt']:+.2f} | {row['profit_factor']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Best Trigger Formulas",
            "",
            "| Pair | TF | Strategy | Trigger | Trades | Net After Costs | Win Rate | Expectancy | PF |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    if by_trigger:
        for row in top_rows(by_trigger, 15):
            lines.append(
                f"| {row['pair']} | {row['timeframe']} | {row['strategy']} | {row['enter_tag']} | "
                f"{row['total_trades']} | {row['net_after_costs_usdt']:+.2f} | {row['win_rate']:.1f}% | "
                f"{row['expectancy_usdt']:+.2f} | {row['profit_factor']:.2f} |"
            )
    else:
        lines.append("| - | - | - | - | 0 | +0.00 | 0.0% | +0.00 | 0.00 |")

    lines.extend(["", "## Timeframe Split", ""])
    for timeframe in ("15m", "1h"):
        split = timeframe_aggregate.get(timeframe, {"profit": 0.0, "trades": 0.0})
        lines.append(
            f"- `{timeframe}`: `{int(split['trades'])}` closed trades, "
            f"`{split['profit']:+.2f} USDT` net after costs"
        )

    lines.extend(
        [
            "",
            "## SQL Entry Points",
            "",
            "- `strategy_summary`",
            "- `pair_summary`",
            "- `trigger_summary`",
            "- `trade_analysis`",
            "- `timeframe_summary`",
            "- `formula_candidates`",
            "",
        ]
    )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare paper trading strategy results")
    parser.add_argument("--chart", action="store_true", help="Generate equity curve chart")
    parser.add_argument(
        "--export-db",
        default=str(DEFAULT_EXPORT_DB),
        help="Path to the unified analysis SQLite export",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT),
        help="Path to the markdown report export",
    )
    args = parser.parse_args()

    if not DB_DIR.exists():
        print(f"Database directory not found: {DB_DIR}")
        sys.exit(1)

    export_path = Path(args.export_db).resolve()
    report_path = Path(args.report).resolve()
    db_files = sorted(
        path for path in DB_DIR.glob("*.sqlite") if path.resolve() != export_path and path.stem != "dashboard"
    )
    if not db_files:
        print(f"No strategy .sqlite files found in {DB_DIR}")
        print("Have you started the strategies? Run: bash user_data/scripts/launch_all.sh")
        sys.exit(1)

    results = []
    all_trades_for_chart = []
    strategy_rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    trigger_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    generated_at = datetime.now(timezone.utc).isoformat()

    for db_path in db_files:
        strategy_key = db_path.stem
        strategy_name, timeframe = parse_strategy_key(strategy_key)
        trades = query_trades(db_path)
        open_trades = query_open_trades(db_path)
        custom_data = query_custom_data(db_path)
        metrics = compute_metrics(trades)

        results.append((strategy_key, metrics, len(open_trades)))
        all_trades_for_chart.append((strategy_key, trades))

        strategy_rows.append(
            {
                "strategy_key": strategy_key,
                "strategy": strategy_name,
                "timeframe": timeframe,
                "open_trades": len(open_trades),
                "generated_at": generated_at,
                **metrics,
            }
        )

        pairs = sorted({trade["pair"] for trade in trades})
        for pair in pairs:
            pair_trades = [trade for trade in trades if trade["pair"] == pair]
            pair_metrics = compute_metrics(pair_trades)
            pair_rows.append(
                {
                    "strategy_key": strategy_key,
                    "strategy": strategy_name,
                    "timeframe": timeframe,
                    "pair": pair,
                    **pair_metrics,
                }
            )

            trigger_tags = sorted({trade.get("enter_tag") or "untagged" for trade in pair_trades})
            for enter_tag in trigger_tags:
                tagged_trades = [
                    trade for trade in pair_trades if (trade.get("enter_tag") or "untagged") == enter_tag
                ]
                trigger_metrics = compute_metrics(tagged_trades)
                trigger_rows.append(
                    {
                        "strategy_key": strategy_key,
                        "strategy": strategy_name,
                        "timeframe": timeframe,
                        "pair": pair,
                        "enter_tag": enter_tag,
                        **trigger_metrics,
                    }
                )

        for trade in trades:
            trade_custom = custom_data.get(trade["id"], {})
            opened = parse_dt(trade.get("open_date"))
            closed = parse_dt(trade.get("close_date"))
            duration_min = (closed - opened).total_seconds() / 60.0 if opened and closed else None
            profit_abs = float(trade.get("close_profit_abs") or 0.0)
            trade_rows.append(
                {
                    "source_db": str(db_path),
                    "strategy_key": strategy_key,
                    "strategy": strategy_name,
                    "timeframe": timeframe,
                    "trade_id": trade["id"],
                    "pair": trade["pair"],
                    "side": "short" if trade["is_short"] else "long",
                    "enter_tag": trade.get("enter_tag") or "untagged",
                    "exit_reason": trade.get("exit_reason"),
                    "outcome": outcome_label(profit_abs),
                    "open_date": trade.get("open_date"),
                    "close_date": trade.get("close_date"),
                    "duration_min": safe_round(duration_min, 1) if duration_min is not None else None,
                    "open_rate": trade.get("open_rate"),
                    "close_rate": trade.get("close_rate"),
                    "stake_amount": trade.get("stake_amount"),
                    "amount": trade.get("amount"),
                    "leverage": trade.get("leverage"),
                    "profit_ratio": trade.get("close_profit"),
                    "profit_abs": trade.get("close_profit_abs"),
                    "funding_fees": trade.get("funding_fees"),
                    "fee_open_cost": trade.get("fee_open_cost"),
                    "fee_close_cost": trade.get("fee_close_cost"),
                    "entry_context_json": json.dumps(trade_custom.get("entry_context"), ensure_ascii=True),
                    "exit_context_json": json.dumps(trade_custom.get("exit_context"), ensure_ascii=True),
                    "experiment_labels_json": json.dumps(
                        trade_custom.get("experiment_labels"), ensure_ascii=True
                    ),
                    "custom_data_json": json.dumps(trade_custom, ensure_ascii=True),
                }
            )

    results.sort(key=lambda item: item[1]["net_after_costs_usdt"], reverse=True)
    print_table(results)

    total_strategies = len(results)
    profitable = sum(1 for _, metrics, _ in results if metrics["net_after_costs_usdt"] > 0)
    total_trades = sum(metrics["total_trades"] for _, metrics, _ in results)
    print(f"  Strategy instances: {total_strategies} | Profitable: {profitable} | Closed trades: {total_trades}")

    if results and results[0][1]["total_trades"] > 0:
        best = results[0]
        print(
            f"  Best instance: {best[0]} ({best[1]['net_after_costs_usdt']:+.2f} USDT net, "
            f"win rate {best[1]['win_rate']:.1f}%, PF {best[1]['profit_factor']:.2f})"
        )

    export_analysis_db(export_path, strategy_rows, pair_rows, trigger_rows, trade_rows)
    build_report(report_path, generated_at, strategy_rows, pair_rows, trigger_rows)
    print(f"  Unified analysis DB: {export_path}")
    print(f"  Markdown report: {report_path}")

    if args.chart:
        plot_equity_curves(all_trades_for_chart)


if __name__ == "__main__":
    main()
