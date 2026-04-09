"""
Shared helpers for the 1h paper-trading strategy lab.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from freqtrade.persistence import Order, Trade
from freqtrade.strategy.interface import IStrategy


class ExperimentStrategyBase(IStrategy):
    """
    Common execution controls for the multi-strategy experiment.
    Adds light liquidity / funding filters and persists trade context for later analysis.
    """

    # Keep execution safeguards lightweight so strategies can actually produce entries
    # during paper-trading comparisons on liquid majors.
    max_entry_spread_ratio = 0.0040
    min_entry_side_notional = 5_000.0
    min_depth_imbalance_long = 0.65
    max_depth_imbalance_short = 1.35
    max_abs_funding_rate = 0.0030
    experiment_leverage = 1.0

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._pending_entry_context: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(number) or math.isinf(number):
            return None
        return number

    @staticmethod
    def _cache_key(pair: str, side: str, entry_tag: str | None) -> str:
        return f"{pair}|{side}|{entry_tag or 'untagged'}"

    def _build_market_snapshot(
        self,
        pair: str,
        side: str,
        rate: float,
        amount: float,
        current_time: datetime,
        entry_tag: str | None,
    ) -> dict[str, Any]:
        orderbook = self.dp.orderbook(pair, 5)
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])

        best_bid = self._safe_float(bids[0][0]) if bids else None
        best_ask = self._safe_float(asks[0][0]) if asks else None
        best_bid_qty = self._safe_float(bids[0][1]) if bids else None
        best_ask_qty = self._safe_float(asks[0][1]) if asks else None

        bid_notional_5 = sum((self._safe_float(p) or 0.0) * (self._safe_float(q) or 0.0) for p, q in bids)
        ask_notional_5 = sum((self._safe_float(p) or 0.0) * (self._safe_float(q) or 0.0) for p, q in asks)
        depth_imbalance = (
            bid_notional_5 / ask_notional_5
            if bid_notional_5 > 0.0 and ask_notional_5 > 0.0
            else None
        )
        spread_ratio = (
            ((best_ask - best_bid) / rate)
            if best_ask is not None and best_bid is not None and rate > 0
            else None
        )

        funding = self.dp.funding_rate(pair)
        funding_rate = self._safe_float(funding.get("fundingRate")) if funding else None

        market = self.dp.market(pair) or {}

        snapshot = {
            "strategy": self.get_strategy_name(),
            "pair": pair,
            "side": side,
            "entry_tag": entry_tag,
            "timeframe": self.timeframe,
            "signal_time": current_time.isoformat(),
            "proposed_rate": rate,
            "proposed_amount": amount,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "best_bid_qty": best_bid_qty,
            "best_ask_qty": best_ask_qty,
            "spread_ratio": spread_ratio,
            "bid_notional_top5": bid_notional_5,
            "ask_notional_top5": ask_notional_5,
            "depth_imbalance": depth_imbalance,
            "funding_rate": funding_rate,
            "funding_next": funding.get("fundingDatetime") if funding else None,
            "maker_fee": self._safe_float(self.exchange.get_fee(symbol=pair, taker_or_maker="maker")),
            "taker_fee": self._safe_float(self.exchange.get_fee(symbol=pair, taker_or_maker="taker")),
            "contract_size": self._safe_float(self.exchange.get_contract_size(pair)),
            "min_stake": self._safe_float(((market.get("limits") or {}).get("cost") or {}).get("min")),
            "min_amount": self._safe_float(((market.get("limits") or {}).get("amount") or {}).get("min")),
            "precision_price": self._safe_float((market.get("precision") or {}).get("price")),
            "precision_amount": self._safe_float((market.get("precision") or {}).get("amount")),
        }
        return snapshot

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        snapshot = self._build_market_snapshot(pair, side, rate, amount, current_time, entry_tag)
        accepted = True
        rejection_reason = None

        spread_ratio = snapshot.get("spread_ratio")
        depth_imbalance = snapshot.get("depth_imbalance")
        funding_rate = snapshot.get("funding_rate")
        side_notional = (
            snapshot.get("bid_notional_top5", 0.0)
            if side == "long"
            else snapshot.get("ask_notional_top5", 0.0)
        )

        if spread_ratio is not None and spread_ratio > self.max_entry_spread_ratio:
            accepted = False
            rejection_reason = "spread_too_wide"
        elif side_notional < self.min_entry_side_notional:
            accepted = False
            rejection_reason = "insufficient_top5_liquidity"
        elif (
            side == "long"
            and depth_imbalance is not None
            and depth_imbalance < self.min_depth_imbalance_long
        ):
            accepted = False
            rejection_reason = "weak_bid_support"
        elif (
            side == "short"
            and depth_imbalance is not None
            and depth_imbalance > self.max_depth_imbalance_short
        ):
            accepted = False
            rejection_reason = "weak_ask_support"
        elif (
            side == "long"
            and funding_rate is not None
            and funding_rate > self.max_abs_funding_rate
        ):
            accepted = False
            rejection_reason = "expensive_long_funding"
        elif (
            side == "short"
            and funding_rate is not None
            and funding_rate < -self.max_abs_funding_rate
        ):
            accepted = False
            rejection_reason = "expensive_short_funding"

        snapshot["accepted"] = accepted
        snapshot["rejection_reason"] = rejection_reason
        snapshot["order_type"] = order_type
        snapshot["time_in_force"] = time_in_force
        self._pending_entry_context[self._cache_key(pair, side, entry_tag)] = snapshot
        return accepted

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return min(self.experiment_leverage, max_leverage)

    def _entry_context_for_trade(self, trade: Trade) -> dict[str, Any] | None:
        return self._pending_entry_context.pop(
            self._cache_key(trade.pair, trade.trade_direction, trade.enter_tag),
            None,
        )

    def order_filled(
        self, pair: str, trade: Trade, order: Order, current_time: datetime, **kwargs
    ) -> None:
        if order.ft_order_side == trade.entry_side:
            entry_context = self._entry_context_for_trade(trade) or {}
            trade.set_custom_data(
                "entry_context",
                {
                    **entry_context,
                    "trade_id": trade.id,
                    "trade_direction": trade.trade_direction,
                    "open_rate": trade.open_rate,
                    "stake_amount": trade.stake_amount,
                    "leverage": trade.leverage,
                    "maker_fee_open_cost": trade.fee_open_cost,
                    "funding_fees_at_open": trade.funding_fees,
                    "open_date": trade.open_date.isoformat(),
                },
            )
            trade.set_custom_data(
                "experiment_labels",
                {
                    "strategy": trade.strategy,
                    "pair": trade.pair,
                    "timeframe": self.timeframe,
                    "direction": trade.trade_direction,
                    "trigger": trade.enter_tag or "untagged",
                },
            )
        elif order.ft_order_side == trade.exit_side:
            funding = self.dp.funding_rate(pair)
            trade.set_custom_data(
                "exit_context",
                {
                    "trade_id": trade.id,
                    "close_rate": trade.close_rate,
                    "close_profit": trade.close_profit,
                    "close_profit_abs": trade.close_profit_abs,
                    "exit_reason": trade.exit_reason,
                    "close_date": trade.close_date.isoformat() if trade.close_date else None,
                    "funding_rate": self._safe_float(funding.get("fundingRate")) if funding else None,
                    "funding_next": funding.get("fundingDatetime") if funding else None,
                    "funding_fees_total": trade.funding_fees,
                    "fee_close_cost": trade.fee_close_cost,
                },
            )
