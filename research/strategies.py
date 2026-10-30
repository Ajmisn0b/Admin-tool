"""Scalping hypotheses. Each strategy maps (bars, params) -> (signal, sl, tp) where
signal is +1/-1/0 decided at bar close and sl/tp are price distances.

Signals fire on events (crossing into a condition), not on every bar the condition holds,
so a strategy does not instantly re-enter the same setup after a stop.
"""
import itertools

import numpy as np
import pandas as pd

SESSIONS = {  # London local hours [start, end)
    "all": (0, 24),
    "london": (8, 12),
    "ny": (13, 17),
    "overlap": (13, 16),
    "london_ny": (8, 17),
}


def ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    c = df.mid_c.shift()
    tr = pd.concat([df.mid_h - df.mid_l, (df.mid_h - c).abs(), (df.mid_l - c).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def rsi(x, n):
    d = x.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def london_hour(df):
    return df.index.tz_localize("UTC").tz_convert("Europe/London").hour


def edge(cond):
    """True only on the bar where cond turns on."""
    cond = pd.Series(cond).fillna(False).astype(bool)
    return (cond & ~cond.shift(fill_value=False)).values


def finish(df, long_, short_, a, p, pip):
    """Apply the shared filters (session, spread) and build ATR-based exits."""
    sig = np.where(long_, 1, np.where(short_, -1, 0))
    h0, h1 = SESSIONS[p["session"]]
    hr = london_hour(df)
    sig[(hr < h0) | (hr >= h1)] = 0
    spread = (df.ask_c - df.bid_c).values
    sig[spread > p.get("max_spread", 1e9) * np.nanmedian(spread)] = 0  # x times the usual spread
    a = a.values
    sl = np.maximum(a * p["sl_atr"], p.get("min_stop_pips", 0) * pip)
    tp = sl * p["rr"]
    return sig, sl, tp


def ema_cross(df, p, pip):
    f, s, a = ema(df.mid_c, p["fast"]), ema(df.mid_c, p["slow"]), atr(df)
    return finish(df, edge(f > s), edge(f < s), a, p, pip)


def bb_revert(df, p, pip):
    m = df.mid_c.rolling(p["n"]).mean()
    sd = df.mid_c.rolling(p["n"]).std()
    a = atr(df)
    return finish(df, edge(df.mid_c < m - p["k"] * sd), edge(df.mid_c > m + p["k"] * sd), a, p, pip)


def rsi_revert(df, p, pip):
    r, a = rsi(df.mid_c, p["n"]), atr(df)
    long_, short_ = edge(r < p["lo"]), edge(r > 100 - p["lo"])
    if p["trend"]:  # only fade pullbacks inside the larger trend
        up = (df.mid_c > ema(df.mid_c, p["trend"])).values
        long_, short_ = long_ & up, short_ & ~up
    return finish(df, long_, short_, a, p, pip)


def donchian_break(df, p, pip):
    hh = df.mid_h.rolling(p["n"]).max().shift()
    ll = df.mid_l.rolling(p["n"]).min().shift()
    a = atr(df)
    return finish(df, edge(df.mid_c > hh), edge(df.mid_c < ll), a, p, pip)


def zscore_fade_after_burst(df, p, pip):
    """Big single-bar move (range > k*ATR) -> trade with it (follow) or against it (fade)."""
    a = atr(df)
    body = df.mid_c - df.mid_o
    burst = (df.mid_h - df.mid_l) > p["k"] * a.shift()
    up, dn = (burst & (body > 0)).values, (burst & (body < 0)).values
    if p["mode"] == "fade":
        up, dn = dn, up
    return finish(df, up, dn, a, p, pip)


def opening_range(df, p, pip):
    """Range of the first `mins` minutes after the session opens (London local time), then breakout."""
    loc = df.index.tz_localize("UTC").tz_convert("Europe/London")
    day = loc.date
    mins = loc.hour * 60 + loc.minute
    start = p["open_hour"] * 60
    in_rng = (mins >= start) & (mins < start + p["mins"])
    after = (mins >= start + p["mins"]) & (mins < start + p["mins"] + p["window"])
    g = pd.DataFrame({"h": df.mid_h.where(in_rng), "l": df.mid_l.where(in_rng), "d": day}, index=df.index)
    rh = g.groupby("d").h.transform("max").values
    rl = g.groupby("d").l.transform("min").values
    c = df.mid_c.values
    long_ = edge(after & (c > rh))
    short_ = edge(after & (c < rl))
    # one trade per direction per day
    seen, out_l, out_s = set(), np.zeros(len(c), bool), np.zeros(len(c), bool)
    for i in np.flatnonzero(long_ | short_):
        k = (day[i], long_[i])
        if k not in seen:
            seen.add(k)
            (out_l if long_[i] else out_s)[i] = True
    pp = dict(p, session="all")
    return finish(df, out_l, out_s, atr(df), pp, pip)


def fix_fade(df, p, pip):
    """Fade the run-up into the 16:00 London fix: enter at the fix against the last `look` minutes."""
    loc = df.index.tz_localize("UTC").tz_convert("Europe/London")
    step = int((df.index[1] - df.index[0]).total_seconds() // 60) or 1
    at_fix = (loc.hour == 15) & (loc.minute == 60 - step)  # bar closing at 16:00
    move = (df.mid_c - df.mid_c.shift(p["look"] // step)).values
    big = np.abs(move) > p["k"] * atr(df).values * np.sqrt(p["look"] / step)
    return finish(df, at_fix & big & (move < 0), at_fix & big & (move > 0), atr(df), dict(p, session="all"), pip)


def random_entry(df, p, pip):
    """Control group: same exits and filters, coin-flip direction at random times."""
    rng = np.random.default_rng(p["seed"])
    x = rng.random(len(df)) < p["rate"]
    d = rng.random(len(df)) < 0.5
    return finish(df, x & d, x & ~d, atr(df), p, pip)


EXITS = dict(sl_atr=[1.0, 2.0, 3.0], rr=[0.5, 1.0, 1.5, 2.0], max_bars=[30, 120])
COMMON = dict(session=["london", "ny", "london_ny", "all"], max_spread=[2.0])  # max_spread: multiple of median spread

GRID = {
    "ema_cross": (ema_cross, dict(fast=[5, 9, 20], slow=[21, 50, 100])),
    "bb_revert": (bb_revert, dict(n=[20, 50], k=[2.0, 2.5, 3.0])),
    "rsi_revert": (rsi_revert, dict(n=[2, 7, 14], lo=[10, 20, 30], trend=[0, 200, 600])),
    "donchian_break": (donchian_break, dict(n=[15, 30, 60, 120])),
    "burst": (zscore_fade_after_burst, dict(k=[2.0, 3.0, 4.0], mode=["follow", "fade"])),
    "fix_fade": (fix_fade, dict(look=[30, 60], k=[0.0, 0.5, 1.0], session=["all"])),
    "opening_range": (opening_range, dict(open_hour=[8, 13], mins=[15, 30, 60], window=[120, 240], session=["all"])),
}


def combos(name):
    fn, g = GRID[name]
    grid = {**COMMON, **EXITS, **g}
    keys = list(grid)
    for vals in itertools.product(*(grid[k] for k in keys)):
        p = dict(zip(keys, vals))
        if name == "ema_cross" and p["fast"] >= p["slow"]:
            continue
        yield p
