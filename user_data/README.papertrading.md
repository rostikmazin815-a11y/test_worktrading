# Paper Trading Lab

This setup runs 10 independent futures paper-trading strategies on `BTC/USDT:USDT`, `ETH/USDT:USDT`, `SOL/USDT:USDT`, `XRP/USDT:USDT`, `BNB/USDT:USDT`, `HYPE/USDT:USDT`, `LINK/USDT:USDT`, and `LTC/USDT:USDT` on `5m`, `15m`, `1h`, and `4h`.

It is configured to run through Docker Compose without mounting your `Desktop` folder into Docker.

What is tracked:

- every trade is stored in its strategy SQLite database in `user_data/dbs/*.sqlite`
- funding fees and exchange fees come from Freqtrade futures accounting
- entry liquidity context, spread snapshot, trigger tag, and exit context are stored in `trade_custom_data`
- a unified analytics database is exported to `user_data/backtest_results/paper_trading_analysis.sqlite`
- a markdown summary report is exported to `user_data/backtest_results/paper_trading_report.md`

Runtime baseline:

- deposit: `1000 USDT`
- pairs: `BTC`, `ETH`, `SOL`, `XRP`, `BNB`, `HYPE`, `LINK`, `LTC`
- timeframes: `5m`, `15m`, `1h`, `4h`
- strategy instances: `40` total
- paper mode only: all trades are dry-run and written to SQLite

Run the lab with Docker Compose:

```bash
bash user_data/scripts/launch_all.sh
```

Equivalent direct command:

```bash
docker compose -f docker-compose.strategies.yml up -d --build
```

Stop the lab:

```bash
bash user_data/scripts/stop_all.sh
```

Export DBs and logs from Docker to local files:

```bash
bash user_data/scripts/export_docker_results.sh
```

Generate comparison + unified analytics DB:

```bash
python3 user_data/scripts/compare_results.py
```

One-shot morning flow:

```bash
bash user_data/scripts/finalize_run.sh
```

Useful SQLite entry points after the run:

- `strategy_summary`
- `pair_summary`
- `trigger_summary`
- `trade_analysis`
- `timeframe_summary`
- `trades_by_pair`
- `trades_by_trigger`
- `formula_candidates`

Example queries:

```sql
SELECT * FROM strategy_summary ORDER BY net_after_costs_usdt DESC;
SELECT * FROM pair_summary WHERE pair = 'BTC/USDT:USDT' ORDER BY net_after_costs_usdt DESC;
SELECT * FROM trigger_summary WHERE total_trades >= 2 ORDER BY net_after_costs_usdt DESC;
SELECT * FROM formula_candidates LIMIT 20;
```
