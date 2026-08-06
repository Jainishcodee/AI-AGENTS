"""Command line interface.

    python -m stockseer.cli backtest --ticker RELIANCE.NS
    python -m stockseer.cli sweep    --tickers "RELIANCE.NS,TCS.NS,INFY.NS"
    python -m stockseer.cli train    --ticker ^NSEI
    python -m stockseer.cli predict  --ticker ^NSEI
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .pipeline import (
    ARTIFACTS,
    Config,
    build_dataset,
    predict_latest,
    run_backtest,
    save_results,
    shuffled_control,
    train_final,
)
from .report import plot_report, print_report

DISCLAIMER = (
    "\nStockSeer is a research tool, not investment advice. Out-of-sample results "
    "on past data are the ceiling of what to expect, never the floor: real "
    "execution adds slippage, and any edge you find by re-running with different "
    "settings until the numbers look good is an edge you invented.\n"
)


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--ticker", default="^NSEI",
                   help="yfinance symbol. NSE needs .NS (RELIANCE.NS), BSE .BO. "
                        "Indices: ^NSEI (Nifty 50), ^BSESN (Sensex), ^GSPC (S&P 500)")
    p.add_argument("--benchmark", default=None,
                   help="optional index for relative-strength features, e.g. ^NSEI")
    p.add_argument("--start", default="2012-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--horizon", type=int, default=1,
                   help="predict the return this many trading days ahead")
    p.add_argument("--task", choices=["classification", "regression"], default="classification")
    p.add_argument("--deadband", type=float, default=0.0,
                   help="drop training rows whose forward move is smaller than this "
                        "(e.g. 0.002 = 20bps of noise)")
    p.add_argument("--model", choices=["lgbm", "logistic", "ridge", "rf", "dummy"], default="lgbm")
    p.add_argument("--splits", type=int, default=5)
    p.add_argument("--min-train", type=int, default=750,
                   help="rows in the first training window (750 ~= 3 years)")
    p.add_argument("--rolling", action="store_true",
                   help="use a fixed-size rolling train window instead of expanding")
    p.add_argument("--threshold", type=float, default=0.5,
                   help="probability above which to go long")
    p.add_argument("--mode", choices=["long_flat", "long_short"], default="long_flat")
    p.add_argument("--cost-bps", type=float, default=5.0,
                   help="round-trip cost charged per unit of position change")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--refresh", action="store_true", help="bypass the price cache")


def _config(a: argparse.Namespace) -> Config:
    return Config(
        ticker=a.ticker, benchmark=a.benchmark, start=a.start, end=a.end,
        horizon=a.horizon, task=a.task, deadband=a.deadband, model=a.model,
        n_splits=a.splits, min_train=a.min_train, expanding=not a.rolling,
        threshold=a.threshold, mode=a.mode, cost_bps=a.cost_bps,
        seed=a.seed, refresh=a.refresh,
    )


def cmd_backtest(a: argparse.Namespace) -> int:
    cfg = _config(a)
    result = run_backtest(cfg)
    if a.control:
        result["shuffled_control"] = shuffled_control(cfg, result["dataset"])
    print_report(result)

    out = Path(a.out or ARTIFACTS)
    paths = save_results(result, out)
    tag = f"{cfg.ticker.replace('^', 'idx-')}__{cfg.model}__h{cfg.horizon}"
    chart = plot_report(result, out / f"{tag}__report.png", theme=a.theme)
    print(f" report  -> {chart}")
    print(f" summary -> {paths['summary']}")
    print(f" daily   -> {paths['sim']}")
    print(DISCLAIMER)
    return 0


def cmd_sweep(a: argparse.Namespace) -> int:
    """Run the same config across several tickers and rank the results.

    A sweep is the honest way to look for signal: if 1 ticker out of 20 shows a
    t-stat of 2, that is what 20 coin flips look like, not a discovery.
    """
    tickers = [t.strip() for t in a.tickers.split(",") if t.strip()]
    rows = []
    for ticker in tickers:
        a.ticker = ticker
        try:
            result = run_backtest(_config(a))
        except Exception as exc:
            print(f" {ticker:<16} FAILED: {exc}")
            continue
        m, s = result["metrics"], result["strategy"]
        rows.append({
            "ticker": ticker,
            "accuracy": m.get("accuracy", m.get("direction_accuracy", float("nan"))),
            "edge_t": m.get("edge_t_stat", float("nan")),
            "auc": m.get("auc", float("nan")),
            "sharpe": s["strategy"].get("sharpe", float("nan")),
            "bh_sharpe": s["buy_and_hold"].get("sharpe", float("nan")),
            "excess_cagr": s["excess_cagr"],
        })

    if not rows:
        print("No ticker completed successfully.")
        return 1

    rows.sort(key=lambda r: (r["edge_t"] if r["edge_t"] == r["edge_t"] else -99), reverse=True)
    print(f"\n{'ticker':<16}{'accuracy':>10}{'edge t':>9}{'AUC':>8}"
          f"{'sharpe':>9}{'B&H':>8}{'excess CAGR':>13}")
    print("-" * 73)
    for r in rows:
        print(f"{r['ticker']:<16}{r['accuracy'] * 100:>9.2f}%{r['edge_t']:>9.2f}"
              f"{r['auc']:>8.3f}{r['sharpe']:>9.2f}{r['bh_sharpe']:>8.2f}"
              f"{r['excess_cagr'] * 100:>12.2f}%")

    n = len(rows)
    hits = sum(1 for r in rows if r["edge_t"] > 2)
    print(f"\n {hits}/{n} tickers show t > 2. "
          f"At random you would expect about {n * 0.023:.1f}.")
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True)
        (Path(a.out) / "sweep.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(DISCLAIMER)
    return 0


def cmd_train(a: argparse.Namespace) -> int:
    path = train_final(_config(a), Path(a.out) if a.out else None)
    print(f" model -> {path}")
    return 0


def cmd_predict(a: argparse.Namespace) -> int:
    res = predict_latest(_config(a), a.model_path)
    arrow = {"LONG": "UP", "SHORT": "DOWN", "FLAT": "NO POSITION"}[res["signal"]]
    conf = res["score"] if a.task == "classification" else abs(res["score"])
    print(f"\n {res['ticker']}  as of {res['as_of']}  (close {res['last_close']:,.2f})")
    print(f" next {res['horizon_days']}d : {arrow}")
    print(f" score        : {conf:.4f}")
    print(f" signal       : {res['signal']}")
    print(f" model trained through {res['trained_through']}")
    if res["stale_bars"] > 5:
        print(f" WARNING: newest usable bar is {res['stale_bars']} days old.")
    print(DISCLAIMER)
    return 0


def cmd_inspect(a: argparse.Namespace) -> int:
    ds = build_dataset(_config(a))
    print(f"\n rows      : {len(ds.X)}")
    print(f" features  : {ds.X.shape[1]}")
    print(f" range     : {ds.X.index[0].date()} .. {ds.X.index[-1].date()}")
    print(f" up-day %  : {ds.y.mean() * 100:.2f}%")
    print(f" fwd ret   : mean {ds.fwd.mean() * 100:.4f}%  sd {ds.fwd.std() * 100:.4f}%")
    print("\n feature correlation with the forward return (top 15 by |rho|):")
    ic = ds.X.corrwith(ds.fwd, method="spearman").sort_values(key=abs, ascending=False)
    for name, val in ic.head(15).items():
        print(f"   {name:<24}{val:>8.4f}")
    print("\n For daily equity data almost everything lands under |0.05|. That is"
          "\n normal -- and it is why a single feature is never a strategy.\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stockseer",
        description="Walk-forward validated stock prediction on free data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("backtest", help="walk-forward evaluation + report")
    _add_common(p)
    p.add_argument("--out", default=None, help="output directory")
    p.add_argument("--theme", choices=["light", "dark"], default="light")
    p.add_argument("--control", action="store_true",
                   help="also run the shuffled-label leakage control (doubles runtime)")
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("sweep", help="same config across many tickers")
    _add_common(p)
    p.add_argument("--tickers", required=True, help="comma separated symbols")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser("train", help="fit on all history and save the model")
    _add_common(p)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("predict", help="signal for the most recent bar")
    _add_common(p)
    p.add_argument("--model-path", default=None, help="saved .joblib (else trains on the fly)")
    p.set_defaults(func=cmd_predict)

    p = sub.add_parser("inspect", help="dataset shape and raw feature/target correlations")
    _add_common(p)
    p.set_defaults(func=cmd_inspect)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
