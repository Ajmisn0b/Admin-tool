"""HistData.com free M1 ASCII files (bid only).

Timestamps are New York local time WITH daylight saving (checked against Dukascopy:
UTC-5 in January, UTC-4 in October), not fixed EST as the site states.

HistData has no ask side, so ask = bid + a fixed spread passed in by the caller.
"""
import glob
import os

import pandas as pd


def load(folder, sym, spread):
    files = sorted(glob.glob(os.path.join(folder, f"DAT_ASCII_{sym}_M1_*.csv")))
    df = pd.concat(pd.read_csv(f, sep=";", header=None, names=["t", "o", "h", "l", "c", "v"]) for f in files)
    t = pd.to_datetime(df.pop("t"), format="%Y%m%d %H%M%S")
    df.index = (t.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
                 .dt.tz_convert("UTC").dt.tz_localize(None))
    df = df[df.index.notna()]
    df = df[~df.index.duplicated()].sort_index()
    out = pd.DataFrame(index=df.index)
    for k in "ohlc":
        out[f"bid_{k}"] = df[k]
        out[f"ask_{k}"] = df[k] + spread
    out["volume"] = float("nan")
    out.index.name = "time"
    return out
