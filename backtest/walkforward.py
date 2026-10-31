"""Rolling walk-forward: every step, pick the best config on the previous `train` days,
trade it blind on the next `test` days, then roll forward. The stitched blind periods are
the honest estimate of what the selection process would have earned.

    python3 walkforward.py --symbols EURUSD --tf 5min --strategies bb_revert --train 60 --test 14
"""
import argparse
import os
from multiprocessing import Pool

import numpy as np
import pandas as pd

import engine
import strategies as st
from run import EXIT_KEYS, jobs_for

HERE = os.path.dirname(os.path.abspath(__file__))
_S = {}


def _init(bars, pip, costs):
    _S.update(bars=bars, pip=pip, costs=costs)


def _trades(job):
    """All trades of every exit variant of one signal configuration."""
    name, base, exits = job
    df, pip = _S["bars"], _S["pip"]
    sig, sl1, _ = st.GRID[name][0](df, dict(base, sl_atr=1.0, rr=1.0), pip)
    out = []
    for ex in exits:
        sl = sl1 * ex["sl_atr"]
        tr = engine.run(df, sig, sl, sl * ex["rr"], ex["max_bars"], pip, _S["costs"])
        out.append(({"strategy": name, **base, **ex}, tr[["entry_time", "exit_time", "pips"]]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="dukascopy")
    ap.add_argument("--symbols", nargs="+", default=["EURUSD"])
    ap.add_argument("--tf", default="5min")
    ap.add_argument("--strategies", nargs="+", default=list(st.GRID))
    ap.add_argument("--train", type=int, default=60, help="training window, days")
    ap.add_argument("--test", type=int, default=14, help="blind window, days")
    ap.add_argument("--min-trades", type=int, default=30)
    ap.add_argument("--commission-bp", type=float, default=0.7)
    a = ap.parse_args()

    for sym in a.symbols:
        raw = engine.load(os.path.join(HERE, "data", f"{a.source}_{sym}.csv.gz"))
        pip = engine.pip_size(sym)
        costs = engine.Costs(commission_pips=a.commission_bp * 1e-4 * raw.mid_c.median() / pip)
        bars = engine.resample(raw, a.tf)
        jobs = [j for n in a.strategies for j in jobs_for(n)]
        with Pool(os.cpu_count(), initializer=_init, initargs=(bars, pip, costs)) as pool:
            configs = [c for part in pool.imap_unordered(_trades, jobs, chunksize=4) for c in part]

        start = bars.index[0].normalize() + pd.Timedelta(days=a.train)
        steps, blind = [], []
        while start < bars.index[-1]:
            lo, hi = start - pd.Timedelta(days=a.train), start + pd.Timedelta(days=a.test)
            best, best_score = None, -np.inf
            for p, tr in configs:
                w = tr[(tr.entry_time >= lo) & (tr.entry_time < start)]
                if len(w) < a.min_trades:
                    continue
                s = engine.stats(w)
                score = s["net_pips"] / max(s["max_dd"], 10)
                if score > best_score:
                    best, best_score, best_tr = p, score, tr
            if best is not None and best_score > 0:
                out = best_tr[(best_tr.entry_time >= start) & (best_tr.entry_time < hi)]
                blind.append(out)
                steps.append(dict(start=start.date(), pick=best, train_score=round(best_score, 2),
                                  **engine.stats(out)))
            else:
                steps.append(dict(start=start.date(), pick=None, trades=0, net_pips=0.0))
            start = hi

        print(f"\n=== walk-forward {sym} {a.tf}: train {a.train}d, test {a.test}d, "
              f"commission {costs.commission_pips:.2f} pips")
        for s in steps:
            pick = s["pick"]
            desc = "flat (nothing profitable in training)" if pick is None else \
                ", ".join(f"{k}={v}" for k, v in pick.items() if k != "max_spread")
            print(f"{s['start']}  trades {s.get('trades', 0):4d}  net {s.get('net_pips', 0):8.1f}  | {desc}")
        allb = pd.concat(blind) if blind else pd.DataFrame(columns=["entry_time", "exit_time", "pips"])
        print("stitched blind result:", engine.stats(allb))


if __name__ == "__main__":
    main()
