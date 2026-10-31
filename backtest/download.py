"""Build bid/ask M1 price files in backtest/data/<source>_<SYMBOL>.csv.gz

    python3 download.py --source dukascopy --symbols XAUUSD --start 2026-09-01
    ./fetch_histdata.sh XAUUSD 2025 2026/1 2026/2 ...      # first, for HistData
    python3 download.py --source histdata --symbols XAUUSD --start 2025-09-01 --spread 0.30

HistData has no ask side, so --spread (in price units, e.g. 0.30 = 30 cents on gold) sets ask = bid + spread.
"""
import argparse
import datetime as dt
import os

import pandas as pd

from sources import dukascopy, fxcm, histdata

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def path(name, sym):
    return os.path.join(DATA, f"{name}_{sym}.csv.gz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["dukascopy", "fxcm", "histdata"], required=True)
    ap.add_argument("--symbols", nargs="+", default=["XAUUSD"])
    ap.add_argument("--start", type=dt.date.fromisoformat, required=True)
    ap.add_argument("--end", type=dt.date.fromisoformat, default=dt.datetime.now(dt.timezone.utc).date())
    ap.add_argument("--spread", type=float, default=0.30, help="histdata only: fixed spread in price units")
    ap.add_argument("--name", help="output name instead of the source name, e.g. hd_real")
    a = ap.parse_args()
    for sym in a.symbols:
        if a.source == "histdata":
            df = histdata.load(os.path.join(DATA, "histdata"), sym, a.spread)
            df = df[(df.index >= pd.Timestamp(a.start)) & (df.index < pd.Timestamp(a.end) + pd.Timedelta(days=1))]
        else:
            mod = dukascopy if a.source == "dukascopy" else fxcm
            df = mod.load(sym, a.start, a.end, os.path.join(DATA, "cache"), log=lambda m: print(m, flush=True))
        out = path(a.name or a.source, sym)
        df.to_csv(out, float_format="%.8g")
        print(f"saved {out}: {len(df)} bars {df.index[0]} -> {df.index[-1]}", flush=True)


if __name__ == "__main__":
    main()
