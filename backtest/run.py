"""Grid-search every scalping hypothesis, choose on in-sample, judge on out-of-sample.

    python3 run.py --source dukascopy --symbols EURUSD --tf 1min 5min --split 2026-10-12

Writes reports/grid_<source>_<sym>_<tf>.csv (every combo, IS and OOS stats) and prints the
in-sample winners next to their out-of-sample results and the random-entry control.
"""
import argparse
import os
from multiprocessing import Pool

import numpy as np
import pandas as pd

import engine
import strategies as st

HERE = os.path.dirname(os.path.abspath(__file__))
EXIT_KEYS = ("sl_atr", "rr", "max_bars")
_BARS = {}


def _init(bars, pip, split, costs):
    _BARS.update(bars=bars, pip=pip, split=split, costs=costs)


def _evaluate(job):
    """One signal configuration, swept across every exit setting."""
    name, base, exits = job
    df, pip, split, costs = _BARS["bars"], _BARS["pip"], _BARS["split"], _BARS["costs"]
    fn = st.GRID[name][0] if name != "random" else st.random_entry
    sig, sl1, _ = fn(df, dict(base, sl_atr=1.0, rr=1.0), pip)
    rows = []
    for ex in exits:
        sl = sl1 * ex["sl_atr"]
        tr = engine.run(df, sig, sl, sl * ex["rr"], ex["max_bars"], pip, costs)
        is_ = tr[tr.entry_time < split]
        oos = tr[tr.entry_time >= split]
        r = {"strategy": name, **base, **ex}
        r.update({f"is_{k}": v for k, v in engine.stats(is_).items()})
        r.update({f"oos_{k}": v for k, v in engine.stats(oos).items()})
        rows.append(r)
    return rows


def jobs_for(name):
    groups = {}
    for p in st.combos(name):
        base = {k: v for k, v in p.items() if k not in EXIT_KEYS}
        groups.setdefault(tuple(sorted(base.items(), key=str)), (base, []))[1].append(
            {k: p[k] for k in EXIT_KEYS})
    return [(name, b, ex) for b, ex in groups.values()]


def random_jobs(n_seeds):
    exits = [dict(zip(EXIT_KEYS, v)) for v in
             __import__("itertools").product(*(st.EXITS[k] for k in EXIT_KEYS))]
    return [("random", dict(seed=s, rate=0.01, session=sess, max_spread=2.0), exits)
            for s in range(n_seeds) for sess in ("london_ny",)]


def score(df, prefix):
    return df[f"{prefix}_net_pips"] / np.maximum(df[f"{prefix}_max_dd"], 10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="dukascopy")
    ap.add_argument("--symbols", nargs="+", default=["EURUSD"])
    ap.add_argument("--tf", nargs="+", default=["1min", "5min"])
    ap.add_argument("--split", default="2026-10-12", help="first out-of-sample day")
    ap.add_argument("--strategies", nargs="+", default=list(st.GRID))
    ap.add_argument("--commission-bp", type=float, default=0.7,
                    help="round-trip commission in basis points of notional (0.7 = $35 per million per side)")
    ap.add_argument("--min-trades", type=int, default=40)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    a = ap.parse_args()
    os.makedirs(os.path.join(HERE, "reports"), exist_ok=True)
    split = np.datetime64(a.split)

    for sym in a.symbols:
        raw = engine.load(os.path.join(HERE, "data", f"{a.source}_{sym}.csv.gz"))
        pip = engine.pip_size(sym)
        costs = engine.Costs(commission_pips=a.commission_bp * 1e-4 * raw.mid_c.median() / pip)
        spread = (raw.ask_c - raw.bid_c) / pip
        print(f"\n=== {a.source} {sym}: {len(raw)} M1 bars, median spread {spread.median():.2f} pips, "
              f"commission {costs.commission_pips:.2f} pips RT, IS < {a.split} <= OOS")
        for tf in a.tf:
            bars = engine.resample(raw, tf)
            jobs = [j for n in a.strategies for j in jobs_for(n)] + random_jobs(30)
            with Pool(a.workers, initializer=_init, initargs=(bars, pip, split, costs)) as pool:
                rows = [r for part in pool.imap_unordered(_evaluate, jobs, chunksize=4) for r in part]
            res = pd.DataFrame(rows)
            res["is_score"], res["oos_score"] = score(res, "is"), score(res, "oos")
            out = os.path.join(HERE, "reports", f"grid_{a.source}_{sym}_{tf}.csv")
            res.to_csv(out, index=False)
            report(res, a.min_trades, f"{sym} {tf}")


def report(res, min_trades, label):
    rnd = res[res.strategy == "random"]
    real = res[(res.strategy != "random") & (res.is_trades >= min_trades)]
    print(f"\n--- {label}: {len(res) - len(rnd)} configs tested, {len(real)} with >= {min_trades} IS trades")
    print(f"random control (IS net pips): median {rnd.is_net_pips.median():.0f}, "
          f"95th pct {rnd.is_net_pips.quantile(.95):.0f}; OOS median {rnd.oos_net_pips.median():.0f}")
    prof_is = real[real.is_net_pips > 0]
    print(f"IS-profitable configs: {len(prof_is)}; of those also OOS-profitable: "
          f"{(prof_is.oos_net_pips > 0).sum()}")
    cols = ["strategy", "session", "is_trades", "is_net_pips", "is_pf", "is_win_rate", "is_max_dd",
            "oos_trades", "oos_net_pips", "oos_pf", "oos_win_rate", "oos_max_dd"]
    params = [c for c in res.columns if c not in cols and not c.startswith(("is_", "oos_"))
              and c not in ("max_spread",)]
    best = real.sort_values("is_score", ascending=False).groupby("strategy").head(2)
    with pd.option_context("display.width", 250, "display.max_columns", 50):
        print(best[cols + [c for c in params if c != "session"]].dropna(axis=1, how="all").to_string(index=False))


if __name__ == "__main__":
    main()
