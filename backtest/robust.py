"""Configs that make money in-sample AND out-of-sample on every symbol given.

    python3 robust.py --source dukascopy --symbols EURUSD GBPUSD --tf 5min
"""
import argparse
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STAT = ("trades", "net_pips", "pf", "win_rate", "max_dd", "avg", "sharpe_d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="dukascopy")
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--tf", nargs="+", default=["1min", "5min", "15min"])
    ap.add_argument("--min-trades", type=int, default=20, help="per symbol, per period")
    a = ap.parse_args()
    for tf in a.tf:
        merged = None
        for sym in a.symbols:
            r = pd.read_csv(os.path.join(HERE, "reports", f"grid_{a.source}_{sym}_{tf}.csv"))
            r = r[r.strategy != "random"]
            keys = [c for c in r.columns if not c.startswith(("is_", "oos_"))]
            r = r.set_index(keys)[[f"{p}_{s}" for p in ("is", "oos") for s in STAT]].add_prefix(f"{sym}:")
            merged = r if merged is None else merged.join(r, how="inner")
        ok = pd.Series(True, index=merged.index)
        for sym in a.symbols:
            for p in ("is", "oos"):
                ok &= (merged[f"{sym}:{p}_net_pips"] > 0) & (merged[f"{sym}:{p}_trades"] >= a.min_trades)
        win = merged[ok]
        total = sum(win[f"{s}:{p}_net_pips"] for s in a.symbols for p in ("is", "oos")) if len(win) else []
        print(f"\n--- {tf}: {ok.sum()} of {len(merged)} configs profitable in IS and OOS on {', '.join(a.symbols)}")
        if len(win):
            win = win.assign(total=total).sort_values("total", ascending=False)
            show = win[[c for c in win.columns if c.endswith(("net_pips", "trades", "pf")) or c == "total"]]
            with pd.option_context("display.width", 250, "display.max_columns", 50):
                print(show.head(10).reset_index().dropna(axis=1, how="all").to_string(index=False))


if __name__ == "__main__":
    main()
