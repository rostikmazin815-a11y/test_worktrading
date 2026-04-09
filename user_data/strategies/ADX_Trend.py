"""
ADX Trend Strategy (1h Futures)
ADX for trend strength + DI crossover for direction.
"""
import talib.abstract as ta
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class ADX_Trend(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 30

    stoploss = -0.04
    minimal_roi = {
        "0": 0.03,
        "90": 0.01,
        "180": 0.005,
    }

    process_only_new_candles = True
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["plus_di"] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe["minus_di"] = ta.MINUS_DI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["adx"] > 25)
                & (dataframe["plus_di"] > dataframe["minus_di"])
                & (dataframe["plus_di"].shift(1) <= dataframe["minus_di"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["adx"] > 25)
                & (dataframe["plus_di"] > dataframe["minus_di"])
                & (dataframe["plus_di"].shift(1) <= dataframe["minus_di"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "adx_di_bull_cross"

        dataframe.loc[
            (
                (dataframe["adx"] > 25)
                & (dataframe["minus_di"] > dataframe["plus_di"])
                & (dataframe["minus_di"].shift(1) <= dataframe["plus_di"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["adx"] > 25)
                & (dataframe["minus_di"] > dataframe["plus_di"])
                & (dataframe["minus_di"].shift(1) <= dataframe["plus_di"].shift(1))
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "adx_di_bear_cross"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["adx"] < 20)
                | (dataframe["minus_di"] > dataframe["plus_di"])
            )
            & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["adx"] < 20)
                | (dataframe["minus_di"] > dataframe["plus_di"])
            )
            & (dataframe["volume"] > 0),
            "exit_tag",
        ] = "adx_trend_weakened"

        dataframe.loc[
            (
                (dataframe["adx"] < 20)
                | (dataframe["plus_di"] > dataframe["minus_di"])
            )
            & (dataframe["volume"] > 0),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["adx"] < 20)
                | (dataframe["plus_di"] > dataframe["minus_di"])
            )
            & (dataframe["volume"] > 0),
            "exit_tag",
        ] = "adx_trend_weakened"

        return dataframe
