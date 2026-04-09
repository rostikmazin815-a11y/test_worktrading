"""
Bollinger Bands Bounce Strategy (1h Futures)
Enter when price touches outer bands with RSI confirmation.
"""
import talib.abstract as ta
from pandas import DataFrame

from _experiment_base import ExperimentStrategyBase


class BollingerBands_Bounce(ExperimentStrategyBase):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = True
    startup_candle_count = 40

    stoploss = -0.025
    minimal_roi = {
        "0": 0.02,
        "30": 0.01,
        "60": 0.005,
    }

    process_only_new_candles = True
    use_exit_signal = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bollinger["upperband"]
        dataframe["bb_middle"] = bollinger["middleband"]
        dataframe["bb_lower"] = bollinger["lowerband"]
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] <= dataframe["bb_lower"])
                & (dataframe["rsi"] < 40)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] <= dataframe["bb_lower"])
                & (dataframe["rsi"] < 40)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "bb_lower_rsi_revert"

        dataframe.loc[
            (
                (dataframe["close"] >= dataframe["bb_upper"])
                & (dataframe["rsi"] > 60)
                & (dataframe["volume"] > 0)
            ),
            "enter_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] >= dataframe["bb_upper"])
                & (dataframe["rsi"] > 60)
                & (dataframe["volume"] > 0)
            ),
            "enter_tag",
        ] = "bb_upper_rsi_revert"

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] >= dataframe["bb_middle"])
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] >= dataframe["bb_middle"])
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "bb_mid_revert"

        dataframe.loc[
            (
                (dataframe["close"] <= dataframe["bb_middle"])
                & (dataframe["volume"] > 0)
            ),
            "exit_short",
        ] = 1
        dataframe.loc[
            (
                (dataframe["close"] <= dataframe["bb_middle"])
                & (dataframe["volume"] > 0)
            ),
            "exit_tag",
        ] = "bb_mid_revert"

        return dataframe
