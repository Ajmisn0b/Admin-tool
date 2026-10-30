"""Download bid/ask M1 prices into research/data/<source>_<SYMBOL>.csv.gz

    python research/download.py --source dukascopy --symbols EURUSD GBPUSD XAUUSD --start 2026-09-01
"""
import argparse
import datetime as dt
import os

from sources import dukascopy, fxcm

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SOURCES = {"dukascopy": dukascopy, "fxcm": fxcm}


def path(source, sym):
    return os.path.join(DATA, f"{source}_{sym}.csv.gz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=SOURCES, required=True)
    ap.add_argument("--symbols", nargs="+", default=["EURUSD"])
    ap.add_argument("--start", type=dt.date.fromisoformat, required=True)
    ap.add_argument("--end", type=dt.date.fromisoformat, default=dt.datetime.now(dt.timezone.utc).date())
    a = ap.parse_args()
    for sym in a.symbols:
        df = SOURCES[a.source].load(sym, a.start, a.end, os.path.join(DATA, "cache"),
                                    log=lambda m: print(m, flush=True))
        df.to_csv(path(a.source, sym), float_format="%.8g")
        print(f"saved {path(a.source, sym)}: {len(df)} bars {df.index[0]} -> {df.index[-1]}", flush=True)


if __name__ == "__main__":
    main()
