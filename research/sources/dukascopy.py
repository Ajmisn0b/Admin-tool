"""Dukascopy datafeed: daily M1 candle files (BID/ASK) plus hourly tick files for the current day."""
import datetime as dt
import lzma
import os
import struct
import time
import urllib.error
import urllib.request

import pandas as pd

BASE = "https://datafeed.dukascopy.com/datafeed"


def point(sym):
    return 1e3 if "JPY" in sym or sym.startswith(("XAU", "XAG")) else 1e5


def _fetch(url, cache, tries=8):
    """Return file bytes (b'' for 404), cached on disk; None if every attempt failed."""
    if cache and os.path.exists(cache):
        return open(cache, "rb").read()
    for a in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raw = b""
                break
            time.sleep(60 if e.code == 429 else 2 * 2 ** min(a, 4))  # 429: the server asks us to slow down
        except Exception:
            time.sleep(2 * 2 ** min(a, 4))
    else:
        return None
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        open(cache, "wb").write(raw)
    time.sleep(1)  # stay polite to the free datafeed
    return raw


def day_candles(sym, day, side, cache_dir):
    """M1 candles for one finished UTC day. side is 'BID' or 'ASK'."""
    url = f"{BASE}/{sym}/{day.year}/{day.month - 1:02d}/{day.day:02d}/{side}_candles_min_1.bi5"
    raw = _fetch(url, os.path.join(cache_dir, f"{sym}_{side}_{day}.bi5"))
    if raw is None:
        raise RuntimeError(f"download failed: {url}")
    if not raw:
        return []
    buf, p, base = lzma.decompress(raw), point(sym), dt.datetime(day.year, day.month, day.day)
    out = []
    for i in range(0, len(buf), 24):
        t, o, c, lo, h, v = struct.unpack(">5If", buf[i:i + 24])
        if v > 0:  # zero-volume rows are flat fillers while the market is closed
            out.append((base + dt.timedelta(seconds=t), o / p, h / p, lo / p, c / p, v))
    return out


def today_from_ticks(sym, now, cache_dir):
    """Bid/ask M1 candles for today's finished hours, built from tick files."""
    day, p, rows = now.date(), point(sym), []
    for h in range(now.hour):
        url = f"{BASE}/{sym}/{day.year}/{day.month - 1:02d}/{day.day:02d}/{h:02d}h_ticks.bi5"
        raw = _fetch(url, os.path.join(cache_dir, f"{sym}_ticks_{day}_{h:02d}.bi5"))
        if not raw:
            continue
        buf, base = lzma.decompress(raw), dt.datetime(day.year, day.month, day.day, h)
        for i in range(0, len(buf), 20):
            ms, ask, bid, av, bv = struct.unpack(">3I2f", buf[i:i + 20])
            rows.append((base + dt.timedelta(milliseconds=ms), bid / p, ask / p, bv))
    if not rows:
        return pd.DataFrame()
    t = pd.DataFrame(rows, columns=["time", "bid", "ask", "vol"]).set_index("time")
    g = t.resample("1min")
    df = pd.concat({
        "bid_o": g.bid.first(), "bid_h": g.bid.max(), "bid_l": g.bid.min(), "bid_c": g.bid.last(),
        "ask_o": g.ask.first(), "ask_h": g.ask.max(), "ask_l": g.ask.min(), "ask_c": g.ask.last(),
        "volume": g.vol.sum(),
    }, axis=1)
    return df.dropna()


def load(sym, start, end, cache_dir, log=print):
    """Bid+ask M1 frame from start to end (dates, inclusive); today is filled from ticks."""
    today = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    frames, d = [], start
    while d <= end and d < today.date():
        sides = {}
        for side in ("BID", "ASK"):
            sides[side] = pd.DataFrame(day_candles(sym, d, side, cache_dir),
                                       columns=["time", "o", "h", "l", "c", "v"]).set_index("time")
        b, a = sides["BID"], sides["ASK"]
        if len(b) and len(a):
            df = b[["o", "h", "l", "c"]].add_prefix("bid_").join(a[["o", "h", "l", "c"]].add_prefix("ask_"), how="inner")
            df["volume"] = b["v"]
            frames.append(df)
        log(f"dukascopy {sym} {d} {len(b)}")
        d += dt.timedelta(days=1)
    if end >= today.date():
        frames.append(today_from_ticks(sym, today, cache_dir))
    return pd.concat(frames).sort_index()
