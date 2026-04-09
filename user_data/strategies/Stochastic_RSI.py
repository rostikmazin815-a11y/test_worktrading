"""
Stochastic RSI Strategy (1h Futures)
StochRSI oversold/overbought with volume confirmation.
"""
import talib.abstract as ta
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class Stochastic_RSI(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 30

    stoploss = -0.03
    minimal_roi = {
        "0": 0.02,
        "45": 0.01,
        "90": 0.005,
    }

    process_only_new_candles = True
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        stoch_rsi = ta.STOCHRSI(dataframe, timeperiod=14, fastk_period=3, fastd_period=3)
        dataframe["stochrsi_k"] = stoch_rsi["fastk"]
        dataframe["stochrsi_d"] = stoch_rsi["fastd"]
        dataframe["volume_sma"] = dataframe["volume"].rolling(window=20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["stochrsi_k"] > dataframe["stochrsi_d"])
                & (dataframe["stochrsi_k"].shift(1) <= dataframe["stochrsi_d"].shift(1))
                & (dataframe["stochrsi_k"] < 30)
                & (dataframe["volume"] > dataframe["volume_sma"])
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["stochrsi_k"] > dataframe["stochrsi_d"])
                & (dataframe["stochrsi_k"].shift(1) <= dataframe["stochrsi_d"].shift(1))
                & (dataframe["stochrsi_k"] < 30)
                & (dataframe["volume"] > dataframe["volume_sma"])
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "stochrsi_oversold_reclaim"

        dataframe.loc[
            (
                (dataframe["stochrsi_k"] < dataframe["stochrsi_d"])
                & (dataframe["stochrsi_k"].shift(1) >= dataframe["stochrsi_d"].shift(1))
                & (dataframe["stochrsi_k"] > 70)
                & (dataframe["volume"] > dataframe["volume_sma"])
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["stochrsi_k"] < dataframe["stochrsi_d"])
                & (dataframe["stochrsi_k"].shift(1) >= dataframe["stochrsi_d"].shift(1))
                & (dataframe["stochrsi_k"] > 70)
                & (dataframe["volume"] > dataframe["volume_sma"])
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "stochrsi_overbought_rollover"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["stochrsi_k"] > 70)
                & (dataframe["stochrsi_k"] < dataframe["stochrsi_d"])
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["stochrsi_k"] > 70)
                & (dataframe["stochrsi_k"] < dataframe["stochrsi_d"])
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "stochrsi_exhaustion"

        dataframe.loc[
            (
                (dataframe["stochrsi_k"] < 30)
                & (dataframe["stochrsi_k"] > dataframe["stochrsi_d"])
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["stochrsi_k"] < 30)
                & (dataframe["stochrsi_k"] > dataframe["stochrsi_d"])
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "stochrsi_exhaustion"

        return dataframe
