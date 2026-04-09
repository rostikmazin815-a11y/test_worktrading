"""
RSI Mean Reversion Strategy (1h Futures)
Buy when RSI is oversold, sell when overbought. Classic mean-reversion approach.
"""
import talib.abstract as ta
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class RSI_MeanReversion(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 30

    stoploss = -0.03
    minimal_roi = {
        "0": 0.02,
        "30": 0.01,
        "60": 0.005,
    }

    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["rsi_sma"] = dataframe["rsi"].rolling(window=10).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] < 30)
                & (dataframe["rsi"].shift(1) >= 30)  # RSI crosses below 30
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["rsi"] < 30)
                & (dataframe["rsi"].shift(1) >= 30)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "rsi_oversold_cross"

        dataframe.loc[
            (
                (dataframe["rsi"] > 70)
                & (dataframe["rsi"].shift(1) <= 70)  # RSI crosses above 70
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["rsi"] > 70)
                & (dataframe["rsi"].shift(1) <= 70)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "rsi_overbought_cross"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] > 50)
                & (dataframe["rsi"].shift(1) <= 50)
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["rsi"] > 50)
                & (dataframe["rsi"].shift(1) <= 50)
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "rsi_mean_reversion_complete"

        dataframe.loc[
            (
                (dataframe["rsi"] < 50)
                & (dataframe["rsi"].shift(1) >= 50)
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["rsi"] < 50)
                & (dataframe["rsi"].shift(1) >= 50)
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "rsi_mean_reversion_complete"

        return dataframe
