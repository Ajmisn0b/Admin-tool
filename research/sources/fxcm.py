"""FXCM public candle archive: weekly gzipped M1 files with bid and ask, published after each week closes."""
import datetime as dt
import gzip
import io
import os
import time
import urllib.error
import urllib.request

import pandas as pd

BASE = "https://candledata.fxcorporate.com/m1"


def _fetch(url, cache, tries=6):
    if os.path.exists(cache):
        return open(cache, "rb").read()
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                raw = r.read()
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            open(cache, "wb").write(raw)
            return raw
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None  # week not published yet
            time.sleep(2 * 2 ** a)
        except Exception:
            time.sleep(2 * 2 ** a)
    raise RuntimeError(f"download failed: {url}")


def load(sym, start, end, cache_dir, log=print):
    """Bid+ask M1 frame for every published week touching [start, end]."""
    frames, d = [], start - dt.timedelta(days=(start.weekday() + 1) % 7)  # back to Sunday
    while d <= end:
        week = int(d.strftime("%U"))  # FXCM numbers weeks Sunday-first, like %U
        raw = _fetch(f"{BASE}/{sym}/{d.year}/{week}.csv.gz", os.path.join(cache_dir, f"fxcm_{sym}_{d.year}_{week}.csv.gz"))
        if raw:
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass  # some files are served already decompressed
            df = pd.read_csv(io.BytesIO(raw))
            frames.append(df)
            log(f"fxcm {sym} week {week} {len(df)}")
        else:
            log(f"fxcm {sym} week {week} not published")
        d += dt.timedelta(days=7)
    df = pd.concat(frames)
    df["time"] = pd.to_datetime(df.pop("DateTime"), format="%m/%d/%Y %H:%M:%S.%f")
    df = df.set_index("time").sort_index()
    df.columns = ["bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c"]
    df["volume"] = float("nan")
    lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
    return df[(df.index >= lo) & (df.index < hi)]
