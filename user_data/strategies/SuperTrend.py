"""
SuperTrend Strategy (1h Futures)
ATR-based trend-following indicator with direction flips.
"""
import numpy as np
import talib.abstract as ta
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class SuperTrend(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 30

    stoploss = -0.04
    minimal_roi = {
        "0": 0.035,
        "90": 0.015,
        "180": 0.005,
    }

    process_only_new_candles = True
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        atr_period = 10
        multiplier = 3.0

        atr = ta.ATR(dataframe, timeperiod=atr_period)
        hl2 = (dataframe["high"] + dataframe["low"]) / 2

        upper_band = hl2 + multiplier * atr
        lower_band = hl2 - multiplier * atr

        # Calculate SuperTrend
        supertrend = np.zeros(len(dataframe))
        direction = np.ones(len(dataframe))  # 1 = bullish, -1 = bearish

        final_upper = upper_band.copy()
        final_lower = lower_band.copy()

        for i in range(1, len(dataframe)):
            # Adjust bands based on previous values
            if lower_band.iloc[i] > final_lower.iloc[i - 1]:
                final_lower.iloc[i] = lower_band.iloc[i]
            else:
                if dataframe["close"].iloc[i - 1] > final_lower.iloc[i - 1]:
                    final_lower.iloc[i] = lower_band.iloc[i]
                else:
                    final_lower.iloc[i] = final_lower.iloc[i - 1]

            if upper_band.iloc[i] < final_upper.iloc[i - 1]:
                final_upper.iloc[i] = upper_band.iloc[i]
            else:
                if dataframe["close"].iloc[i - 1] < final_upper.iloc[i - 1]:
                    final_upper.iloc[i] = upper_band.iloc[i]
                else:
                    final_upper.iloc[i] = final_upper.iloc[i - 1]

            # Determine direction
            if supertrend[i - 1] == final_upper.iloc[i - 1]:
                if dataframe["close"].iloc[i] > final_upper.iloc[i]:
                    supertrend[i] = final_lower.iloc[i]
                    direction[i] = 1
                else:
                    supertrend[i] = final_upper.iloc[i]
                    direction[i] = -1
            else:
                if dataframe["close"].iloc[i] < final_lower.iloc[i]:
                    supertrend[i] = final_upper.iloc[i]
                    direction[i] = -1
                else:
                    supertrend[i] = final_lower.iloc[i]
                    direction[i] = 1

        dataframe["supertrend"] = supertrend
        dataframe["st_direction"] = direction
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["st_direction"] == 1)
                & (dataframe["st_direction"].shift(1) == -1)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["st_direction"] == 1)
                & (dataframe["st_direction"].shift(1) == -1)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "supertrend_flip_bull"

        dataframe.loc[
            (
                (dataframe["st_direction"] == -1)
                & (dataframe["st_direction"].shift(1) == 1)
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["st_direction"] == -1)
                & (dataframe["st_direction"].shift(1) == 1)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "supertrend_flip_bear"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["st_direction"] == -1)
                & (dataframe["st_direction"].shift(1) == 1)
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["st_direction"] == -1)
                & (dataframe["st_direction"].shift(1) == 1)
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "supertrend_flip_bear"

        dataframe.loc[
            (
                (dataframe["st_direction"] == 1)
                & (dataframe["st_direction"].shift(1) == -1)
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["st_direction"] == 1)
                & (dataframe["st_direction"].shift(1) == -1)
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "supertrend_flip_bull"

        return dataframe
