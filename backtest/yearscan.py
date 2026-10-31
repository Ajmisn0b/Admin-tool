"""Every config over the whole period: total, both halves, share of profitable months.

    python3 yearscan.py --source hd_ecn --tf 1min --strategies rsi_deep --split 2026-04-01 --commission-bp 0.35
"""
import argparse, os
from multiprocessing import Pool
import numpy as np, pandas as pd
import engine, strategies as st
HERE = os.path.dirname(os.path.abspath(__file__))
from run import jobs_for
import walkforward as wf

def summarize(args):
    p, tr, split = args
    if len(tr) == 0:
        return None
    m = tr.groupby(pd.to_datetime(tr.entry_time).dt.to_period("M")).pips.sum()
    h1, h2 = tr[tr.entry_time < split], tr[tr.entry_time >= split]
    s = engine.stats(tr)
    return {**p, **s, "h1": round(h1.pips.sum(), 1), "h2": round(h2.pips.sum(), 1),
            "months_pos": round((m > 0).mean(), 2), "worst_month": round(m.min(), 1)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="histdata"); ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="5min"); ap.add_argument("--split", default="2026-04-01")
    ap.add_argument("--strategies", nargs="+", default=list(st.GRID))
    ap.add_argument("--commission-bp", type=float, default=0.7)
    a = ap.parse_args()
    raw = engine.load(os.path.join(HERE, "data", f"{a.source}_{a.symbol}.csv.gz")); pip = engine.pip_size(a.symbol)
    costs = engine.Costs(commission_pips=a.commission_bp * 1e-4 * raw.mid_c.median() / pip)
    bars = engine.resample(raw, a.tf)
    jobs = [j for n in a.strategies for j in jobs_for(n)]
    with Pool(os.cpu_count(), initializer=wf._init, initargs=(bars, pip, costs)) as pool:
        cfgs = [c for part in pool.imap_unordered(wf._trades, jobs, chunksize=4) for c in part]
    split = np.datetime64(a.split)
    rows = [r for r in map(summarize, [(p, t, split) for p, t in cfgs]) if r]
    res = pd.DataFrame(rows)
    os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
    res.to_csv(os.path.join(HERE, "reports", f"year_{a.source}_{a.symbol}_{a.tf}.csv"), index=False)
    ok = res[(res.trades >= 100)]
    print(f"{a.source} {a.symbol} {a.tf}: {len(res)} configs, {len(ok)} with >=100 trades; "
          f"profitable overall {(ok.net_pips>0).mean():.0%}; both halves {((ok.h1>0)&(ok.h2>0)).mean():.0%}")
    best = ok[(ok.h1 > 0) & (ok.h2 > 0)].sort_values("months_pos", ascending=False)
    cols = [c for c in ["strategy","session","n","k","fast","slow","lo","trend","mode","look","open_hour","mins","window",
            "sl_atr","rr","max_bars","trades","net_pips","pf","win_rate","max_dd","h1","h2","months_pos","worst_month"] if c in best]
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        print(best[cols].head(15).to_string(index=False))

if __name__ == "__main__":
    main()
