"""Forward (paper) test of the gold portfolio on live prices, no real orders.

Every run downloads the finished days of Dukascopy XAUUSD M1 prices since the warm-up date,
re-simulates the three frozen strategies from the backtest, and writes:
  forward/trades.csv   every signal with its entry, stop, target and result
  forward/README.md    the running summary (Arabic)
If TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set, it also sends what changed since the last run.

The strategy settings below are frozen: do not tune them while the test runs, or the test stops
being a forward test.
"""
import datetime as dt
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backtest"))
import engine  # noqa: E402
import strategies as st  # noqa: E402
from sources import dukascopy  # noqa: E402

SYMBOL = "XAUUSD"
START = dt.date(2026, 11, 2)              # first day that counts
WARMUP = START - dt.timedelta(days=10)    # history for the indicators
PIP = 0.1
SPREAD, COMMISSION = 0.10, 0.07           # Exness Raw-like, $ per ounce (as in the backtest)
DATA = os.path.join(HERE, "data")

# name, label, timeframe, signal function, params, stop ATR x, target R x, max bars, max cost/stop
STRATEGIES = [
    ("momentum", "زخم بعد حركة قوية", "5min", st.big_move,
     dict(session="ny", look=24, k=1.5, mode="follow"), 3.0, 1.5, 30, None),
    ("bollinger", "ارتداد بولنجر", "15min", st.bb_revert,
     dict(session="ny", n=50, k=3.0), 3.0, 3.0, 120, 0.02035),
    ("rsi5", "RSI مع الاتجاه", "5min", st.rsi_revert,
     dict(session="all", n=14, lo=30, trend=200), 2.0, 1.5, 120, 0.07992),
]


def day_frame(day, cache):
    sides = {}
    for side in ("BID", "ASK"):
        rows = dukascopy.day_candles(SYMBOL, day, side, cache)
        sides[side] = pd.DataFrame(rows, columns=["time", "o", "h", "l", "c", "v"]).set_index("time")
    b, a = sides["BID"], sides["ASK"]
    df = b[["o", "h", "l", "c"]].add_prefix("bid_").join(a[["o", "h", "l", "c"]].add_prefix("duka_ask_"), how="inner")
    df["volume"] = b["v"]
    return df


def load_prices():
    """Finished UTC days from WARMUP to yesterday, cached one file per day in forward/data/."""
    os.makedirs(DATA, exist_ok=True)
    yesterday = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    frames, cache = [], tempfile.mkdtemp()
    d = WARMUP
    while d <= yesterday:
        path = os.path.join(DATA, f"{SYMBOL}_{d}.csv.gz")
        if not os.path.exists(path):
            day_frame(d, cache).to_csv(path, float_format="%.8g")
            print("downloaded", d, flush=True)
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        if len(df):
            frames.append(df)
        d += dt.timedelta(days=1)
    df = pd.concat(frames).sort_index()
    for k in "ohlc":  # Exness-like costs: Dukascopy bid + a fixed spread, like the backtest
        df[f"ask_{k}"] = df[f"bid_{k}"] + SPREAD
        df[f"mid_{k}"] = (df[f"bid_{k}"] + df[f"ask_{k}"]) / 2
    return df


def simulate(prices):
    costs = engine.Costs(commission_pips=COMMISSION / PIP)
    out = []
    for key, label, tf, fn, p, stop_atr, rr, max_bars, max_cost in STRATEGIES:
        df = engine.resample(prices, tf)
        sig, sl1, _ = fn(df, dict(p, sl_atr=1.0, rr=1.0, max_spread=2.0), PIP)
        sl = sl1 * stop_atr
        if max_cost is not None:  # trade only when the market moves enough for the costs
            sig = sig.copy()
            sig[(SPREAD + COMMISSION) / np.where(sl > 0, sl, np.inf) > max_cost] = 0
        tr = engine.run(df, sig, sl, sl * rr, max_bars, PIP, costs)
        if tr.empty:
            continue
        i = df.index.get_indexer(pd.to_datetime(tr.entry_time)) - 1  # signal bar
        dist = sl[i]
        tr["strategy"], tr["label"] = key, label
        tr["stop"] = tr.entry - tr.side * dist
        tr["target"] = tr.entry + tr.side * dist * rr
        tr["R"] = tr.pips / (dist / PIP)
        held = df.index.get_indexer(pd.to_datetime(tr.exit_time)) - (i + 1)
        still_open = (pd.to_datetime(tr.exit_time) == df.index[-1]) & (tr.reason == "time") & (held < max_bars)
        tr["status"] = np.where(still_open, "open", "closed")
        out.append(tr[pd.to_datetime(tr.entry_time) >= pd.Timestamp(START)])
    cols = ["strategy", "label", "side", "entry_time", "entry", "stop", "target", "exit_time", "exit", "reason", "R", "status"]
    if not out:
        return pd.DataFrame(columns=cols)
    t = pd.concat(out)[cols].sort_values("entry_time").reset_index(drop=True)
    t.loc[t.status == "open", ["exit_time", "exit", "reason", "R"]] = [None, np.nan, "", np.nan]
    return t


def pf(r):
    loss = -r[r < 0].sum()
    return r[r > 0].sum() / loss if loss > 0 else float("inf")


def write_summary(t, prices):
    closed = t[t.status == "closed"]
    days = max((prices.index[-1].normalize() - pd.Timestamp(START)).days + 1, 0)
    lines = [
        "# اختبار المراقبة (بدون صفقات حقيقية)",
        "",
        f"آخر تحديث: {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC، والأسعار لين {prices.index[-1]:%Y-%m-%d %H:%M} UTC.",
        f"بدأ الاختبار {START} ({days} يوم). التكاليف مثل حساب Raw في إكسنس. R = وحدة مخاطرة (خسارة صفقة ضربت الستوب).",
        "",
        "| الاستراتيجية | صفقات مقفلة | الرابحة | المجموع | معامل الربح | مفتوحة |",
        "|---|---|---|---|---|---|",
    ]
    for key, label, *_ in STRATEGIES + [("all", "**المحفظة كاملة**")]:
        s = closed if key == "all" else closed[closed.strategy == key]
        o = t[(t.status == "open") & ((key == "all") | (t.strategy == key))]
        win = f"{(s.R > 0).mean():.0%}" if len(s) else "-"
        tot = f"{s.R.sum():+.1f}R" if len(s) else "-"
        lines.append(f"| {label} | {len(s)} | {win} | {tot} | {pf(s.R):.2f} | {len(o)} |" if len(s)
                     else f"| {label} | 0 | - | - | - | {len(o)} |")
    lines += [
        "",
        "**المتوقع من الاختبار التاريخي:** حوالي +0.1R لكل صفقة، وحوالي 19 صفقة بالشهر في سوق مثل 2026. "
        "أقل من شهر نتائجه عشوائية، فلا تحكم قبل 3 أشهر تقريباً.",
        "",
        "## آخر الصفقات",
        "",
        "| الدخول (UTC) | الاستراتيجية | الاتجاه | الدخول | الستوب | الهدف | النتيجة |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in t.tail(20).iloc[::-1].iterrows():
        res = "مفتوحة" if r.status == "open" else f"{r.R:+.2f}R"
        side = "شراء" if r.side > 0 else "بيع"
        lines.append(f"| {pd.Timestamp(r.entry_time):%Y-%m-%d %H:%M} | {r.label} | {side} | {r.entry:.2f} | "
                     f"{r.stop:.2f} | {r.target:.2f} | {res} |")
    if t.empty:
        lines.append("| - | ما فيه صفقات للحين | | | | | |")
    open(os.path.join(HERE, "README.md"), "w").write("\n".join(lines) + "\n")


def telegram(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat or not text:
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=30)


def changes(old, new):
    """Telegram text for trades that are new or closed since the previous run."""
    key = lambda r: (r.strategy, str(r.entry_time))  # noqa: E731
    before = {key(r): r.status for r in old.itertuples()} if len(old) else {}
    msg = []
    for r in new.itertuples():
        side = "شراء" if r.side > 0 else "بيع"
        if key(r) not in before:
            msg.append(f"🔔 {r.label}: {side} {r.entry:.2f} | ستوب {r.stop:.2f} | هدف {r.target:.2f}")
        if r.status == "closed" and before.get(key(r)) != "closed":
            msg.append(f"✅ {r.label}: {side} من {r.entry:.2f} انقفلت {r.R:+.2f}R")
    if msg:
        closed = new[new.status == "closed"]
        msg.append(f"المجموع من {START}: {closed.R.sum():+.1f}R في {len(closed)} صفقة")
    return "\n".join(msg)


def main():
    prices = load_prices()
    trades = simulate(prices)
    path = os.path.join(HERE, "trades.csv")
    old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
    trades.to_csv(path, index=False, float_format="%.4f")
    write_summary(trades, prices)
    text = changes(old, pd.read_csv(path))
    if os.environ.get("TELEGRAM_TEST") == "true":  # manual run with the test box ticked
        closed = trades[trades.status == "closed"]
        text = (f"✅ بوت تنبيهات الذهب متصل.\nالأسعار لين {prices.index[-1]:%Y-%m-%d %H:%M} UTC، "
                f"سعر الذهب {prices.bid_c.iloc[-1]:.2f}.\nاختبار المراقبة من {START}: "
                f"{len(closed)} صفقة مقفلة، {closed.R.sum():+.1f}R.\n" + text).strip()
    print(text or "no changes")
    telegram(text)


if __name__ == "__main__":
    main()
