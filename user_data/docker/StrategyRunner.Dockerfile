FROM freqtradeorg/freqtrade:stable

WORKDIR /freqtrade

COPY user_data/strategies /freqtrade/user_data/strategies
COPY user_data/configs /freqtrade/user_data/configs

RUN mkdir -p /freqtrade/user_data/dbs /freqtrade/user_data/logs /freqtrade/user_data/backtest_results

ENV PYTHONPATH=/freqtrade/user_data/strategies
