"""Bar-by-bar scalping backtester on bid/ask M1 data.

Rules, chosen to be pessimistic rather than flattering:
- A signal is computed on a closed bar and filled at the NEXT bar's open:
  longs buy the ask, shorts sell the bid, so the real spread is paid on entry.
- Longs exit on the bid, shorts exit on the ask.
- If stop-loss and take-profit are both touched inside the same bar, the stop wins.
- A gap through a level fills at the bar open, not at the level.
- Commission is charged per round trip in pips.
- One position at a time; no new entry on the bar a trade closed.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


def pip_size(sym):
    if sym.startswith(("XAU",)):
        return 0.1
    return 0.01 if "JPY" in sym else 0.0001


@dataclass
class Costs:
    commission_pips: float = 0.7  # ~$7 per lot round trip on an ECN account
    extra_slippage_pips: float = 0.0  # added against us on every fill


def load(path):
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df["mid_o"] = (df.bid_o + df.ask_o) / 2
    df["mid_h"] = (df.bid_h + df.ask_h) / 2
    df["mid_l"] = (df.bid_l + df.ask_l) / 2
    df["mid_c"] = (df.bid_c + df.ask_c) / 2
    return df


def resample(df, rule):
    if rule in (None, "1min"):
        return df
    agg = {}
    for p in ("bid", "ask", "mid"):
        agg.update({f"{p}_o": "first", f"{p}_h": "max", f"{p}_l": "min", f"{p}_c": "last"})
    agg["volume"] = "sum"
    return df.resample(rule, label="left", closed="left").agg(agg).dropna(subset=["bid_o"])


def run(df, signal, sl, tp, max_bars, pip, costs=Costs()):
    """Simulate trades.

    signal: array of +1/-1/0 decided at the close of each bar.
    sl, tp: arrays (or scalars) of distances in PRICE units from the entry fill.
    Returns a DataFrame with one row per trade, pnl in pips net of costs.
    """
    n = len(df)
    sig = np.asarray(signal, dtype=np.int8)
    sl = np.broadcast_to(np.asarray(sl, dtype=float), (n,))
    tp = np.broadcast_to(np.asarray(tp, dtype=float), (n,))
    bo, bh, bl = df.bid_o.values, df.bid_h.values, df.bid_l.values
    ao, ah, al = df.ask_o.values, df.ask_h.values, df.ask_l.values
    t = df.index.values
    slip = costs.extra_slippage_pips * pip
    trades = []
    free_from = 0  # first bar where a new signal may be taken
    for i in np.flatnonzero(sig):
        if i < free_from or i >= n - 1:
            continue
        s = sig[i]
        if not (sl[i] > 0 and tp[i] > 0):
            continue
        e = i + 1
        if s > 0:
            entry = ao[e] + slip
            stop, take = entry - sl[i], entry + tp[i]
        else:
            entry = bo[e] - slip
            stop, take = entry + sl[i], entry - tp[i]
        exit_price, reason, j = None, "time", e
        last = min(e + max_bars, n - 1)
        for j in range(e, last + 1):
            if s > 0:
                o, hi, lo = bo[j], bh[j], bl[j]
                if j > e and o <= stop:
                    exit_price, reason = o, "sl"
                elif lo <= stop:
                    exit_price, reason = stop, "sl"
                elif j > e and o >= take:
                    exit_price, reason = o, "tp"
                elif hi >= take:
                    exit_price, reason = take, "tp"
            else:
                o, hi, lo = ao[j], ah[j], al[j]
                if j > e and o >= stop:
                    exit_price, reason = o, "sl"
                elif hi >= stop:
                    exit_price, reason = stop, "sl"
                elif j > e and o <= take:
                    exit_price, reason = o, "tp"
                elif lo <= take:
                    exit_price, reason = take, "tp"
            if exit_price is not None:
                break
        if exit_price is None:  # time stop: close at the last bar's close on the exit side
            j = last
            exit_price = (df.bid_c.values[j] - slip) if s > 0 else (df.ask_c.values[j] + slip)
        elif reason == "sl":
            exit_price = exit_price - slip if s > 0 else exit_price + slip
        pnl = (exit_price - entry) * s / pip - costs.commission_pips
        trades.append((t[e], t[j], s, entry, exit_price, reason, pnl))
        free_from = j + 1
    return pd.DataFrame(trades, columns=["entry_time", "exit_time", "side", "entry", "exit", "reason", "pips"])


def stats(tr):
    if len(tr) == 0:
        return dict(trades=0, net_pips=0.0, win_rate=0.0, pf=0.0, avg=0.0, max_dd=0.0, sharpe_d=0.0)
    p = tr.pips.values
    eq = p.cumsum()
    dd = (np.maximum.accumulate(np.maximum(eq, 0)) - eq).max()
    gw, gl = p[p > 0].sum(), -p[p < 0].sum()
    daily = tr.groupby(pd.to_datetime(tr.exit_time).dt.date).pips.sum()
    sh = daily.mean() / daily.std() * np.sqrt(252) if len(daily) > 2 and daily.std() > 0 else 0.0
    return dict(trades=len(p), net_pips=round(p.sum(), 1), win_rate=round((p > 0).mean() * 100, 1),
                pf=round(gw / gl, 2) if gl > 0 else float("inf"), avg=round(p.mean(), 2),
                max_dd=round(dd, 1), sharpe_d=round(sh, 2))
