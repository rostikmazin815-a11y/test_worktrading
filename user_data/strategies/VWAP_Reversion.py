"""
VWAP Reversion Strategy (1h Futures)
Price mean-reverts to rolling VWAP with standard deviation bands.
"""
import numpy as np
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class VWAP_Reversion(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 200

    stoploss = -0.03
    minimal_roi = {
        "0": 0.015,
        "30": 0.008,
        "60": 0.004,
    }

    process_only_new_candles = True
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        window = 100
        typical_price = (dataframe["high"] + dataframe["low"] + dataframe["close"]) / 3
        vol_tp = typical_price * dataframe["volume"]
        # Rolling VWAP
        dataframe["vwap"] = (
            vol_tp.rolling(window=window).sum()
            / dataframe["volume"].rolling(window=window).sum()
        )
        # Deviation from VWAP
        deviation = dataframe["close"] - dataframe["vwap"]
        dataframe["vwap_std"] = deviation.rolling(window=window).std()
        dataframe["vwap_upper"] = dataframe["vwap"] + 1.5 * dataframe["vwap_std"]
        dataframe["vwap_lower"] = dataframe["vwap"] - 1.5 * dataframe["vwap_std"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["vwap_lower"])
                & (dataframe["close"].shift(1) >= dataframe["vwap_lower"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["vwap_lower"])
                & (dataframe["close"].shift(1) >= dataframe["vwap_lower"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "vwap_lower_reclaim"

        dataframe.loc[
            (
                (dataframe["close"] > dataframe["vwap_upper"])
                & (dataframe["close"].shift(1) <= dataframe["vwap_upper"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["vwap_upper"])
                & (dataframe["close"].shift(1) <= dataframe["vwap_upper"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "vwap_upper_reject"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] >= dataframe["vwap"])
                & (dataframe["close"].shift(1) < dataframe["vwap"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] >= dataframe["vwap"])
                & (dataframe["close"].shift(1) < dataframe["vwap"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "vwap_mean_revert_complete"

        dataframe.loc[
            (
                (dataframe["close"] <= dataframe["vwap"])
                & (dataframe["close"].shift(1) > dataframe["vwap"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] <= dataframe["vwap"])
                & (dataframe["close"].shift(1) > dataframe["vwap"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "vwap_mean_revert_complete"

        return dataframe
