import numpy as np
import pandas as pd

import engine

PIP = 0.0001


def bars(rows, spread=0.0001):
    """rows of bid (o, h, l, c); ask = bid + spread."""
    df = pd.DataFrame(rows, columns=["bid_o", "bid_h", "bid_l", "bid_c"],
                      index=pd.date_range("2026-09-01", periods=len(rows), freq="1min"))
    for k in "ohlc":
        df[f"ask_{k}"] = df[f"bid_{k}"] + spread
    return df


def trade(df, side, sl_pips, tp_pips, max_bars=10, comm=0.0):
    sig = np.zeros(len(df))
    sig[0] = side
    return engine.run(df, sig, sl_pips * PIP, tp_pips * PIP, max_bars, PIP, engine.Costs(comm)).iloc[0]


def test_long_pays_spread_and_hits_tp():
    df = bars([(1.1, 1.1, 1.1, 1.1), (1.1, 1.1, 1.1, 1.1), (1.1, 1.1012, 1.1, 1.101)])
    t = trade(df, 1, 10, 10)  # buy ask 1.1001, tp 1.1011 hit by bid high 1.1012
    assert t.reason == "tp" and round(t.pips, 6) == 10


def test_same_bar_sl_and_tp_counts_as_loss():
    df = bars([(1.1, 1.1, 1.1, 1.1), (1.1, 1.1, 1.1, 1.1), (1.1, 1.103, 1.097, 1.1)])
    t = trade(df, 1, 10, 10)
    assert t.reason == "sl" and round(t.pips, 6) == -10


def test_short_exits_on_ask_and_gap_fills_at_open():
    df = bars([(1.1, 1.1, 1.1, 1.1), (1.1, 1.1, 1.1, 1.1), (1.103, 1.104, 1.102, 1.103)])
    t = trade(df, -1, 10, 10, comm=0.7)  # sell bid 1.1, stop 1.101; gaps to ask open 1.1031
    assert t.reason == "sl" and round(t.pips, 6) == -31.7


def test_time_stop():
    df = bars([(1.1, 1.1, 1.1, 1.1)] * 5)
    t = trade(df, 1, 10, 10, max_bars=2)  # flat market: lose exactly the spread
    assert t.reason == "time" and round(t.pips, 6) == -1
