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

# Heavy imports (pandas, scikit-learn, matplotlib) are deliberately deferred
# into the commands that need them. `ipo calendar` and `notify` run on a bare
# Python with nothing but the standard library, which is what lets the GitHub
# Actions jobs install in seconds instead of minutes.

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


def _config(a: argparse.Namespace):
    from .pipeline import Config

    return Config(
        ticker=a.ticker, benchmark=a.benchmark, start=a.start, end=a.end,
        horizon=a.horizon, task=a.task, deadband=a.deadband, model=a.model,
        n_splits=a.splits, min_train=a.min_train, expanding=not a.rolling,
        threshold=a.threshold, mode=a.mode, cost_bps=a.cost_bps,
        seed=a.seed, refresh=a.refresh,
    )


def cmd_backtest(a: argparse.Namespace) -> int:
    from .pipeline import ARTIFACTS, run_backtest, save_results, shuffled_control
    from .report import plot_report, print_report

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
    from .pipeline import run_backtest

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
    from .pipeline import train_final

    path = train_final(_config(a), Path(a.out) if a.out else None)
    print(f" model -> {path}")
    return 0


def cmd_predict(a: argparse.Namespace) -> int:
    from .pipeline import predict_latest

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
    from .pipeline import build_dataset

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


def cmd_check(a: argparse.Namespace) -> int:
    """How risky is this stock, and how many shares should I buy?"""
    from .checkup import check, print_checkup

    for ticker in [t.strip() for t in a.ticker.split(",") if t.strip()]:
        try:
            k = check(ticker, capital=a.capital, risk_pct=a.risk_pct,
                      stop_atr=a.stop_atr, reward_multiple=a.reward,
                      max_position_pct=a.max_position)
            print_checkup(k, a.capital)
        except Exception as exc:
            print(f"\n {ticker}: {exc}\n")
    return 0


def cmd_etf(a: argparse.Namespace) -> int:
    """Gold and silver ETFs: are you paying a fair price today?"""
    from .etf import REGISTRY, print_study, scan_and_notify, study_premium, verdict

    tickers = ([t.strip() for t in a.ticker.split(",") if t.strip()]
               if a.ticker else list(REGISTRY))

    if a.action == "scan":
        print(f"\n{'symbol':<16}{'price':>10}{'fair value':>12}{'gap':>9}   verdict")
        print("-" * 72)
        for t in tickers:
            try:
                s = study_premium(t, start=a.start, refresh=a.refresh)
                v, _ = verdict(s)
                flags = "  (est.)" if s.approx else ""
                if s.nav_is_stale:
                    flags += f"  NAV {s.nav_date}"
                print(f"{t:<16}{s.price:>10,.2f}{s.nav:>12,.2f}"
                      f"{s.current * 100:>8.2f}%   {v}{flags}")
            except Exception as exc:
                print(f"{t:<16}FAILED: {exc}")
        print("\n Fair value is the fund's published NAV. A gap over ~1% is worth"
              "\n waiting out; it usually closes within a couple of days.\n")
        return 0

    if a.action == "notify":
        pushed = scan_and_notify(tickers, start=a.start, refresh=a.refresh)
        if pushed:
            for n in pushed:
                print(f"  [{n.urgency}] {n.title}")
        else:
            print("\n All tracked ETFs are near fair value. Nothing worth an alert.\n")
        return 0

    for t in tickers:
        try:
            print_study(study_premium(t, horizon=a.horizon, start=a.start,
                                      refresh=a.refresh))
        except Exception as exc:
            print(f"\n {t}: {exc}\n")
    return 0


def cmd_alert(a: argparse.Namespace) -> int:
    """Price alerts: tell me when this gets to my level."""
    from .watchlist import Watchlist, notify

    wl = Watchlist()

    if a.action == "add":
        if not a.ticker:
            print(" --ticker is required")
            return 1
        kinds = [(k, v) for k, v in (("below", a.below), ("drop", a.drop),
                                     ("under_avg", a.under_avg)) if v is not None]
        if len(kinds) != 1:
            print(" give exactly one of --below, --drop or --under-avg")
            return 1
        kind, val = kinds[0]
        w = wl.add(a.ticker, kind, val, a.note or "")
        print(f"\n watching {w.ticker}: alert when {w.describe()}\n")
        return 0

    if a.action == "remove":
        print(" removed" if wl.remove(a.id) else f" no watch with id {a.id!r}")
        return 0

    if a.action == "rearm":
        print(" re-armed" if wl.rearm(a.id) else f" no watch with id {a.id!r}")
        return 0

    if a.action == "check":
        hits = wl.check()
        if not hits:
            print("\n Nothing has reached its level.\n")
            return 0
        for n in notify(hits):
            print(f"  [{n.urgency}] {n.title}")
        return 0

    if not wl.items:
        print("\n No watches yet. Add one:")
        print("   stockseer watch add --ticker SILVERBEES.NS --below 200")
        print("   stockseer watch add --ticker SILVERBEES.NS --drop 10\n")
        return 0

    print(f"\n {'id':<26}{'wants':<34}{'last price':>12}  state")
    print(" " + "-" * 76)
    for w in wl.items:
        state = "waiting" if w.armed else f"hit {w.triggered_on[:10]}"
        last = f"Rs.{w.last_price:,.2f}" if w.last_price else "-"
        print(f" {w.id:<26}{w.describe():<34}{last:>12}  {state}")
    print()
    return 0


def cmd_portfolio(a: argparse.Namespace) -> int:
    """Holdings, concentration, and which losses are worth realising."""
    from .portfolio import Portfolio, harvest, print_harvest, print_portfolio

    pf = Portfolio.load(a.file)

    if a.action == "import":
        n = pf.import_csv(a.csv)
        pf.save(a.file)
        print(f"\n imported {n} holdings\n")
        return 0

    if not pf.holdings:
        print("\n No holdings yet. Import a CSV with columns"
              " symbol,qty,avg_price[,days_held]:")
        print("   stockseer portfolio import --csv holdings.csv\n")
        return 1

    if a.gains is not None:
        pf.realised_gains = a.gains
        pf.save(a.file)

    positions = pf.price_all()

    if a.action in ("show", "concentration"):
        print_portfolio(positions)
        return 0

    if a.action == "harvest":
        plan = harvest(positions, pf.realised_gains, short_term=not a.long_term)
        print_harvest(plan, short_term=not a.long_term)
        return 0
    return 1


def cmd_pulse(a: argparse.Namespace) -> int:
    """Market check at the times that matter: open, 11:30, 13:30."""
    from .data import load_prices_live
    from .regime import snapshot

    names = [t.strip().upper() for t in a.tickers.split(",") if t.strip()]
    r = snapshot()

    print(f"\n{'=' * 70}")
    print(f" MARKET PULSE   {r.as_of[11:16]}   {r.summary}")
    print("=" * 70)

    rows = []
    for name in names:
        sym = name if "." in name else f"{name}.NS"
        try:
            c = load_prices_live(sym, start="2024-01-01", min_rows=60)["Close"]
            price = float(c.iloc[-1])
            rows.append({
                "sym": name, "price": price,
                "day": float(price / c.iloc[-2] - 1.0) if len(c) > 1 else 0.0,
                "vs50": float(price / c.rolling(50).mean().iloc[-1] - 1.0),
                "from_high": float(price / c.tail(252).max() - 1.0),
            })
        except Exception as exc:
            print(f"  {name}: {exc}")

    rows.sort(key=lambda x: x["from_high"])
    print(f"\n {'stock':<14}{'price':>10}{'today':>9}{'vs 50d':>9}{'from high':>11}")
    print(" " + "-" * 52)
    for x in rows:
        print(f" {x['sym']:<14}{x['price']:>10,.1f}{x['day'] * 100:>8.1f}%"
              f"{x['vs50'] * 100:>8.1f}%{x['from_high'] * 100:>10.1f}%")

    print("\n Sorted by distance from the 52-week high -- the cheapest relative")
    print(" to its own recent range is at the top. That is a price fact, not a")
    print(" forecast: nothing here says any of them will rise.")
    if r.vix is not None:
        print(f"\n India VIX {r.vix:.1f} ({r.vix_band}). VIX predicts the month")
        print(" ahead (t=9.5), not the next day or two (t=1.0).")
    print()
    return 0


def cmd_plan(a: argparse.Namespace) -> int:
    from .planner import compare_capital, plan_report

    plan_report(
        capital=a.capital, target_profit=a.target, win_rate=a.win_rate, rr=a.rr,
        risk_pct=a.risk_pct, stop_pct=a.stop_pct, max_trades=a.max_trades,
        delivery=a.delivery, leverage=a.leverage,
        win_rate_confidence=a.confidence, gap_prob=a.gap_prob,
    )
    if a.compare:
        compare_capital(
            a.target, [a.capital, 100_000, 300_000, 500_000, 1_000_000],
            win_rate=a.win_rate, rr_gross=a.rr, risk_pct=a.risk_pct,
            stop_pct=a.stop_pct, max_trades=a.max_trades,
            delivery=a.delivery, leverage=a.leverage,
            win_rate_confidence=a.confidence, gap_prob=a.gap_prob,
        )
    print(DISCLAIMER)
    return 0


def cmd_rules(a: argparse.Namespace) -> int:
    """Measure every alert rule on real intraday history before trusting it."""
    from .live.feed import get_feed
    from .live.rules import evaluate_all

    feed = get_feed(a.feed)
    print(f"\n feed: {feed.describe()}   interval: {a.interval}   history: {a.days}d")
    print(f" barriers: stop {a.stop_atr}xATR, target {a.target_atr}xATR,"
          f" costs {a.cost_r}R\n")

    header = (f"{'symbol':<14}{'rule':<16}{'n':>5}{'hit%':>7}{'stop%':>7}"
              f"{'exp R':>8}{'B/E%':>7}  verdict")
    print(header)
    print("-" * len(header))

    for symbol in [s.strip() for s in a.tickers.split(",") if s.strip()]:
        try:
            bars = feed.history(symbol, a.interval, a.days)
        except Exception as exc:
            print(f"{symbol:<14}FAILED: {exc}")
            continue
        for st in evaluate_all(bars, stop_atr=a.stop_atr,
                               target_atr=a.target_atr, cost_r=a.cost_r):
            if st.n_signals == 0:
                print(f"{symbol:<14}{st.rule:<16}{0:>5}   never fired")
                continue
            verdict = ("TRADE" if st.worth_trading else
                       "too few signals" if st.n_signals < 30 else "MUTE (no edge)")
            print(f"{symbol:<14}{st.rule:<16}{st.n_signals:>5.0f}"
                  f"{st.hit_rate * 100:>7.1f}{st.stop_rate * 100:>7.1f}"
                  f"{st.expectancy_r:>+8.3f}{st.breakeven_win_rate * 100:>7.1f}"
                  f"  {verdict}")
    print("\n 'exp R' is expected profit per signal in units of risk, net of costs."
          "\n Anything at or below zero should never fire an alert.\n")
    return 0


def cmd_watch(a: argparse.Namespace) -> int:
    from .live.feed import get_feed
    from .live.ledger import Ledger
    from .live.monitor import Monitor

    symbols = [s.strip() for s in a.tickers.split(",") if s.strip()]
    mon = Monitor(
        symbols=symbols,
        feed=get_feed(a.feed),
        ledger=Ledger(capital=a.capital),
        interval=a.interval,
        capital=a.capital,
        risk_pct=a.risk_pct,
        stop_atr=a.stop_atr,
        target_atr=a.target_atr,
        paper=not a.live,
    )
    try:
        mon.run(poll_seconds=a.poll, once=a.once)
    except KeyboardInterrupt:
        print("\n stopped.")
    return 0


def cmd_paper(a: argparse.Namespace) -> int:
    from .live.ledger import Ledger, trades_needed_for_confidence

    led = Ledger(capital=a.capital)

    if a.action == "open":
        t = led.open_trade(a.symbol, a.rule, a.side, a.entry, a.stop,
                           a.target, a.qty, note=a.note or "")
        print(f"\n opened {t.id}: {a.qty} {a.symbol} @ {a.entry:.2f}")
        print(f" stop {a.stop:.2f}  target {a.target:.2f}"
              f"  risking Rs {t.risk_amount:,.0f}\n")
        return 0

    if a.action == "close":
        t = led.close_trade(a.id, a.exit, a.reason or "manual")
        print(f"\n closed {t.id} at {a.exit:.2f} ({t.exit_reason})")
        print(f" P&L Rs {t.pnl():,.2f}  =  {t.r_multiple():+.2f}R"
              f"  (costs Rs {t.costs:.2f})\n")
        return 0

    if a.action == "export":
        path = led.export_csv(a.out or "artifacts/journal/trades.csv")
        print(f" exported -> {path}")
        return 0

    if a.action == "compare":
        rows = led.compare_sources()
        if not rows:
            print("\n No closed trades yet. Log signals with --rule <source-name> to"
                  "\n audit any provider: --rule my_rules, --rule tipsProviderX, etc.\n")
            return 0
        print(f"\n{'source':<22}{'n':>5}{'win%':>7}{'95% interval':>16}"
              f"{'exp R':>9}{'P&L':>11}  verdict")
        print("-" * 88)
        for src, st, verdict in rows:
            print(f"{src:<22}{st.n_closed:>5}{st.win_rate * 100:>7.1f}"
                  f"{st.win_rate_lo * 100:>8.0f}-{st.win_rate_hi * 100:<7.0f}"
                  f"{st.expectancy_r:>+9.3f}{st.total_pnl:>11,.0f}  {verdict}")
        print("\n Same barriers, same costs, same scoring for every source --"
              "\n including whatever anyone else recommends to you.\n")
        return 0

    st = led.stats(a.rule)
    print(f"\n{'=' * 70}")
    print(f" PAPER JOURNAL  |  {st.n_closed} closed, {st.n_open} open"
          + (f"  |  rule: {a.rule}" if a.rule else ""))
    print("=" * 70)
    if st.n_closed == 0:
        print("\n No closed trades yet. Log some with:"
              "\n   stockseer paper open --symbol RELIANCE.NS --rule vwap_reclaim \\"
              "\n                        --entry 1400 --stop 1385 --target 1425 --qty 28\n")
        return 0

    print(f"\n win rate        : {st.win_rate * 100:.1f}%"
          f"   ({st.wins}W / {st.losses}L)")
    print(f" 95% interval    : {st.win_rate_lo * 100:.1f}% - {st.win_rate_hi * 100:.1f}%")
    print(f" expectancy      : {st.expectancy_r:+.3f}R per trade")
    print(f" avg win / loss  : {st.avg_win_r:+.2f}R / {st.avg_loss_r:+.2f}R")
    print(f" best / worst    : {st.best_r:+.2f}R / {st.worst_r:+.2f}R")
    print(f" worst streak    : {st.max_consecutive_losses} losses in a row")
    print(f" total P&L       : Rs {st.total_pnl:,.2f}"
          f"   (costs Rs {st.total_costs:,.2f})")

    breakeven = 0.42
    print(f"\n break-even win rate is ~{breakeven * 100:.0f}% at 1.5R.")
    if st.win_rate_lo > breakeven:
        print(" Your interval clears it. This is evidence of a real edge.")
    elif st.win_rate_hi < breakeven:
        print(" Your interval sits entirely BELOW it. This is evidence of no edge --"
              "\n stop and change something rather than trading more.")
    else:
        # Project off a realistic win rate, not the observed one. After 3 trades
        # the observed rate is often 100% or 0%, and projecting from that would
        # promise certainty in a week.
        need = trades_needed_for_confidence(min(max(st.win_rate, 0.45), 0.60), breakeven)
        print(f" Your interval straddles it -- {st.n_closed} trades is not yet an answer."
              f"\n At this win rate you would need ~{need} trades to know.")
    print()
    return 0


def cmd_advisor(a: argparse.Namespace) -> int:
    """Score anyone's recommendations against random entry in the same names."""
    from .data import load_prices
    from .live.advisors import Call, CallLog, print_scorecard, score_calls

    log_ = CallLog(a.file)

    if a.action == "add":
        c = log_.add(Call(
            source=a.source, symbol=a.symbol, side=a.side,
            published_at=a.at, entry=a.entry, stop=a.stop, target=a.target,
            horizon_days=a.horizon, note=a.note or "",
        ))
        print(f"\n logged {c.id}: {c.source} says {c.side} {c.symbol}"
              f" on {c.published_at}\n")
        return 0

    if a.action == "import":
        n = log_.import_csv(a.csv, a.source)
        print(f"\n imported {n} calls from {a.csv}")
        print(f" sources now: {', '.join(log_.sources())}\n")
        return 0

    if a.action == "list":
        print(f"\n {len(log_.calls)} calls from {len(log_.sources())} sources")
        for c in log_.calls[-40:]:
            print(f"  {c.id:<22}{c.published_at[:10]}  {c.side:<6}{c.symbol:<16}{c.source}")
        print()
        return 0

    if not log_.calls:
        print("\n No calls logged yet. Add them one at a time:"
              "\n   stockseer advisor add --source someservice --symbol RELIANCE.NS \\"
              "\n                         --at 2026-06-02 --target 1500 --stop 1350"
              "\n\n or bulk-import a CSV with columns"
              " symbol,side,published_at[,entry,stop,target,horizon_days,source]:"
              "\n   stockseer advisor import --csv calls.csv --source someservice\n")
        return 1

    def loader(symbol: str):
        return load_prices(symbol, start=a.start, end=a.end)

    outcomes, stats = score_calls(
        log_.calls, loader, cost_pct=a.cost_pct,
        default_stop_pct=a.default_stop, default_target_pct=a.default_target,
    )
    print_scorecard(stats)

    if a.out:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {s: vars(v) for s, v in stats.items()}, indent=2, default=str
        ), encoding="utf-8")
        print(f" scorecard -> {out}\n")
    print(DISCLAIMER)
    return 0


def _report_push(queued: list) -> None:
    """Say plainly whether each alert reached the phone.

    A scan that finds an IPO, prints it, and pushes nothing produces a log
    indistinguishable from success. This makes the difference visible in the
    one place anyone actually looks.
    """
    from .push import describe

    sent = [n for n in queued if getattr(n, "pushed", False)]
    print(f"\n {describe()}")
    print(f" queued {len(queued)}, reached phone {len(sent)}")
    for n in queued:
        mark = ("sent" if getattr(n, "pushed", False)
                else n.data.get("push_skipped", "NOT SENT"))
        print(f"   [{mark}] {n.title}")
    print()


def _push_failed(queued: list) -> bool:
    """True when something was worth sending and none of it went out."""
    from .push import configured

    if not queued:
        return False
    if not configured():
        print(" ERROR: alerts were queued but NTFY_TOPIC is not set, so none")
        print(" of them reached your phone. If this ran in GitHub Actions,")
        print(" check the repository secret.\n")
        return True
    if not any(getattr(n, "pushed", False) for n in queued):
        from .push import LAST_ERROR

        why = LAST_ERROR.get("reason", "no detail from the relay")
        print(f" ERROR: every push to ntfy failed -- {why}")
        if "429" in why:
            print(" A 429 is a rate limit on the source IP. GitHub runners")
            print(" share IPs across the platform, so this is not about your")
            print(" topic. An ntfy account token raises the limit.\n")
        else:
            print()
        return True
    return False


def cmd_ipo(a: argparse.Namespace) -> int:
    from .ipo.calendar import notify_today, print_calendar
    from .ipo.registry import refresh_registry, upcoming_listings

    if a.action == "calendar":
        print_calendar(refresh=a.refresh, include_sme=a.include_sme)
        if a.notify:
            pushed = notify_today(refresh=False, include_sme=a.include_sme)
            if a.heartbeat:
                from .ipo.calendar import heartbeat
                hb = heartbeat(force=a.force_heartbeat,
                               include_sme=a.include_sme)
                if hb:
                    pushed.append(hb)
            _report_push(pushed)
            if a.require_push and _push_failed(pushed):
                return 2
        return 0

    if a.action == "refresh":
        print(f"\n registry: {refresh_registry()}\n")
        return 0

    if a.action == "upcoming":
        rows = upcoming_listings(a.days)
        print(f"\n Listing in the next {a.days} days:")
        for i in rows:
            print(f"   {i.symbol:<14}{i.listing_date}  issue Rs.{i.issue_price}"
                  f"  {'SME' if i.is_sme else 'MAIN'}")
        print()
        return 0

    if a.action == "study":
        from .ipo.study import run_study

        run_study(limit=a.limit, refresh=a.refresh)
        return 0

    if a.action == "morning":
        from datetime import date, timedelta

        from .ipo.intraday import run_intraday_study
        from .ipo.registry import past_issues
        from .live.feed import get_feed

        feed = get_feed(a.feed)
        cutoff = date.today() - timedelta(days=a.days - 3)
        ipos = [i for i in past_issues() if i.listed and i.listing_day()
                and i.listing_day() >= cutoff
                and (a.include_sme or not i.is_sme)]
        print(f"\n {len(ipos)} listings since {cutoff} · feed {feed.describe()}\n")
        run_intraday_study(feed, ipos, interval=a.interval, days_back=a.days)
        return 0

    if a.action == "autorun":
        # Entry point for Task Scheduler. Cheap and silent on the ~350 days a
        # year when nothing lists, so it can be armed daily and forgotten.
        from datetime import datetime

        from .ipo.calendar import notify_today
        from .ipo.registry import listing_today

        pushed = notify_today(refresh=True)
        print(f" calendar: queued {len(pushed)} alert(s)")

        today = listing_today()
        if not today:
            print(" nothing lists today; exiting.")
            return 0

        print(f" listing today: {', '.join(i.symbol for i in today)}")
        if datetime.now().hour >= 16:
            print(" market closed; not starting the watcher.")
            return 0

        from .ipo.watcher import WatchConfig, run
        from .live.feed import get_feed

        cfg = WatchConfig(capital=a.capital, stop_pct=a.stop_pct,
                          target_pct=a.target_pct, near_pct=a.near_pct,
                          poll_seconds=a.poll, confirm_minutes=a.confirm)
        try:
            run(feed=get_feed(a.feed), config=cfg)
        except KeyboardInterrupt:
            print("\n stopped.")
        return 0

    if a.action == "watch":
        from .ipo.watcher import WatchConfig, run
        from .live.feed import get_feed

        cfg = WatchConfig(capital=a.capital, stop_pct=a.stop_pct,
                          target_pct=a.target_pct, trail_pct=a.trail_pct,
                          near_pct=a.near_pct, poll_seconds=a.poll,
                          confirm_minutes=a.confirm)
        syms = [s.strip() for s in a.symbols.split(",")] if a.symbols else None
        try:
            run(symbols=syms, feed=get_feed(a.feed), config=cfg, once=a.once)
        except KeyboardInterrupt:
            print("\n stopped.")
        return 0
    return 1


def cmd_notify(a: argparse.Namespace) -> int:
    from .notify import hub

    h = hub()
    if a.action == "pending":
        items = h.pending()
        print(f"\n {len(items)} undelivered alert(s)")
        for n in items:
            print(f"   [{n.urgency:<8}] {n.title}")
        print()
        return 0
    if a.action == "recent":
        for n in h.recent(a.limit):
            flag = "sent" if n.delivered else "queued"
            print(f" {n.created_at[:16]}  [{flag:<6}] {n.urgency:<8} {n.title}")
        return 0
    if a.action == "test":
        from .push import configured, describe, self_test

        n = h.alert("test", a.urgency, "StockSeer test alert",
                    "If your phone buzzed, Jarvis is wired up correctly.",
                    dedupe_key=None)
        print(f"\n queued for Jarvis: {n.title}  (vibration {n.vibration})")
        print(f" {describe()}")
        if configured():
            res = self_test()
            for urgency, ok in res.items():
                print(f"   ntfy {urgency:<9} {'sent' if ok else 'FAILED'}")
            print("\n Three notifications should have arrived on your phone,"
                  "\n each buzzing more insistently than the last.\n")
        else:
            print("\n No push topic set. Alerts only reach Jarvis while your PC"
                  "\n is on and reachable. Set NTFY_TOPIC in .env for 24x7"
                  "\n delivery with the PC off.\n")
        return 0

    if a.action == "push":
        from .push import configured, describe, self_test

        print(f"\n {describe()}")
        if not configured():
            print(" Set NTFY_TOPIC in .env first.\n")
            return 1
        for urgency, ok in self_test().items():
            print(f"   {urgency:<9} {'sent' if ok else 'FAILED'}")
        print()
        return 0
    if a.action == "clear":
        h.clear()
        print(" cleared.")
        return 0
    return 1


def cmd_ui(a: argparse.Namespace) -> int:
    from .web.server import serve

    if a.lan:
        a.host = "0.0.0.0"
    if not a.no_open:
        import threading
        import webbrowser

        threading.Timer(1.2, lambda: webbrowser.open(f"http://{a.host}:{a.port}")).start()
    serve(host=a.host, port=a.port)
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

    p = sub.add_parser("check",
                       help="how risky is this stock, and how many shares to buy")
    p.add_argument("--ticker", required=True,
                   help="one symbol, or several separated by commas")
    p.add_argument("--capital", type=float, default=40_000.0)
    p.add_argument("--risk-pct", type=float, default=0.02,
                   help="fraction of capital you accept losing on this trade")
    p.add_argument("--stop-atr", type=float, default=2.0,
                   help="stop distance in multiples of the stock's daily range")
    p.add_argument("--reward", type=float, default=2.0,
                   help="target as a multiple of the risk")
    p.add_argument("--max-position", type=float, default=0.35,
                   help="never put more than this share of capital in one stock")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("etf", help="gold/silver ETFs: are you paying a fair price?")
    p.add_argument("action", nargs="?", default="scan",
                   choices=["scan", "study", "notify"])
    p.add_argument("--ticker", default=None,
                   help="default: all tracked ETFs (GOLDBEES, SILVERBEES, "
                        "TATAGOLD, TATSILV)")
    p.add_argument("--start", default="2022-01-01")
    p.add_argument("--horizon", type=int, default=21,
                   help="days ahead to measure in 'study'")
    p.add_argument("--refresh", action="store_true", help="re-fetch NAVs")
    p.set_defaults(func=cmd_etf)

    p = sub.add_parser("alert", help="tell me when a stock reaches my price")
    p.add_argument("action", nargs="?", default="list",
                   choices=["list", "add", "remove", "rearm", "check"])
    p.add_argument("--ticker")
    p.add_argument("--below", type=float, help="alert below this price")
    p.add_argument("--drop", type=float, help="alert this %% below the 52-week high")
    p.add_argument("--under-avg", type=float,
                   help="alert this %% below the 50-day average")
    p.add_argument("--note", help="why you want it, shown in the alert")
    p.add_argument("--id", help="which watch, for remove/rearm")
    p.set_defaults(func=cmd_alert)

    p = sub.add_parser("portfolio",
                       help="holdings, concentration, and tax-loss harvesting")
    p.add_argument("action", nargs="?", default="show",
                   choices=["show", "concentration", "harvest", "import"])
    p.add_argument("--file", default=None)
    p.add_argument("--csv", help="for import: symbol,qty,avg_price[,days_held]")
    p.add_argument("--gains", type=float, default=None,
                   help="realised gains booked this financial year")
    p.add_argument("--long-term", action="store_true",
                   help="treat the gains as long-term (12.5%% above Rs.1.25L)")
    p.set_defaults(func=cmd_portfolio)

    p = sub.add_parser("pulse",
                       help="market check on the quality watchlist")
    p.add_argument("--tickers", default="TORNTPHARM,PIDILITIND,BRITANNIA,TITAN,BAJFINANCE,MARICO,TVSMOTOR,TRENT,EICHERMOT,NESTLEIND",
                   help="default: the screened quality list")
    p.set_defaults(func=cmd_pulse)

    p = sub.add_parser("plan", help="what a capital + profit target actually requires")
    p.add_argument("--capital", type=float, required=True)
    p.add_argument("--target", type=float, required=True, help="profit goal in rupees")
    p.add_argument("--win-rate", type=float, default=0.55)
    p.add_argument("--rr", type=float, default=1.5, help="reward:risk before costs")
    p.add_argument("--risk-pct", type=float, default=0.02, help="fraction of capital per trade")
    p.add_argument("--stop-pct", type=float, default=0.02, help="stop distance as a fraction")
    p.add_argument("--max-trades", type=int, default=500)
    p.add_argument("--delivery", action="store_true", help="delivery instead of intraday")
    p.add_argument("--leverage", type=float, default=1.0)
    p.add_argument("--confidence", type=int, default=30,
                   help="how many real trades your win-rate estimate rests on. "
                        "Use 0-10 if you have no track record yet.")
    p.add_argument("--gap-prob", type=float, default=0.03,
                   help="fraction of losses that gap past the stop")
    p.add_argument("--compare", action="store_true",
                   help="also show the same target across capital levels")
    p.set_defaults(func=cmd_plan)

    def _live_args(sp):
        sp.add_argument("--tickers", default="RELIANCE.NS",
                        help="comma separated NSE symbols")
        sp.add_argument("--interval", default="5m",
                        choices=["1m", "3m", "5m", "15m", "30m", "60m"])
        sp.add_argument("--feed", default="auto", choices=["auto", "angel", "yahoo"])
        sp.add_argument("--stop-atr", type=float, default=1.0)
        sp.add_argument("--target-atr", type=float, default=1.5)

    p = sub.add_parser("rules", help="measure each alert rule on real intraday history")
    _live_args(p)
    p.add_argument("--days", type=int, default=55)
    p.add_argument("--cost-r", type=float, default=0.05,
                   help="transaction cost per trade in units of risk")
    p.set_defaults(func=cmd_rules)

    p = sub.add_parser("watch", help="live session monitor with entry and exit alerts")
    _live_args(p)
    p.add_argument("--capital", type=float, default=40_000.0)
    p.add_argument("--risk-pct", type=float, default=0.01)
    p.add_argument("--poll", type=int, default=60, help="seconds between scans")
    p.add_argument("--once", action="store_true", help="scan once and exit")
    p.add_argument("--live", action="store_true",
                   help="mark alerts as real-money rather than paper")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("paper", help="paper-trading journal: measure your real win rate")
    p.add_argument("action", nargs="?", default="stats",
                   choices=["stats", "open", "close", "export", "compare"])
    p.add_argument("--capital", type=float, default=40_000.0)
    p.add_argument("--rule", default=None)
    p.add_argument("--symbol"); p.add_argument("--side", default="long")
    p.add_argument("--entry", type=float); p.add_argument("--stop", type=float)
    p.add_argument("--target", type=float); p.add_argument("--qty", type=int)
    p.add_argument("--id"); p.add_argument("--exit", type=float)
    p.add_argument("--reason"); p.add_argument("--note"); p.add_argument("--out")
    p.set_defaults(func=cmd_paper)

    p = sub.add_parser("advisor",
                       help="score a tip service / analyst / channel against random entry")
    p.add_argument("action", nargs="?", default="score",
                   choices=["score", "add", "import", "list"])
    p.add_argument("--file", default=None, help="call log path")
    p.add_argument("--source", default="unknown", help="who made the call")
    p.add_argument("--symbol"); p.add_argument("--side", default="long")
    p.add_argument("--at", help="publication date/time, e.g. 2026-06-02 or 2026-06-02T10:05")
    p.add_argument("--entry", type=float, default=None,
                   help="omit to fill at the close of the published bar")
    p.add_argument("--stop", type=float, default=None)
    p.add_argument("--target", type=float, default=None)
    p.add_argument("--horizon", type=int, default=10, help="max trading days to hold")
    p.add_argument("--note"); p.add_argument("--csv"); p.add_argument("--out")
    p.add_argument("--start", default="2012-01-01"); p.add_argument("--end", default=None)
    p.add_argument("--cost-pct", type=float, default=0.0011,
                   help="round-trip cost as a fraction (0.0011 = 11bps delivery)")
    p.add_argument("--default-stop", type=float, default=0.05,
                   help="stop to assume when the call gives none")
    p.add_argument("--default-target", type=float, default=0.10)
    p.set_defaults(func=cmd_advisor)

    p = sub.add_parser("ipo", help="IPO calendar, listing studies, and the live watcher")
    p.add_argument("action", nargs="?", default="calendar",
                   choices=["calendar", "upcoming", "refresh", "study", "morning",
                            "watch", "autorun"])
    p.add_argument("--refresh", action="store_true", help="re-fetch from NSE")
    p.add_argument("--notify", action="store_true", help="queue alerts for Jarvis")
    p.add_argument("--require-push", action="store_true",
                   help="exit non-zero if a queued alert never reached the "
                        "phone, so CI shows silence as a red job")
    p.add_argument("--heartbeat", action="store_true",
                   help="on Mondays, also send a 'still watching' digest so a "
                        "silent week is distinguishable from a broken job")
    p.add_argument("--force-heartbeat", action="store_true",
                   help="send the digest regardless of weekday")
    p.add_argument("--include-sme", action="store_true",
                   help="include SME issues. Off by default: their minimum "
                        "application is about a lakh, so a small account "
                        "cannot act on the alert")
    p.add_argument("--days", type=int, default=95)
    p.add_argument("--limit", type=int, default=450, help="IPOs to measure in 'study'")
    p.add_argument("--interval", default="5m")
    p.add_argument("--feed", default="auto", choices=["auto", "angel", "yahoo"])
    p.add_argument("--symbols", default=None, help="override which IPOs to watch")
    p.add_argument("--capital", type=float, default=40_000.0,
                   help="sizes the quantity and rupee amounts in alerts")
    p.add_argument("--target-pct", type=float, default=0.035,
                   help="measured average best exit before 11:00 was +3.35%%")
    p.add_argument("--stop-pct", type=float, default=0.030,
                   help="measured average dip before 11:00 was -2.80%%")
    p.add_argument("--trail-pct", type=float, default=0.025)
    p.add_argument("--near-pct", type=float, default=0.008,
                   help="how early to warn before a level is reached")
    p.add_argument("--confirm", type=int, default=5,
                   help="minutes it must hold above the open before a buy alert")
    p.add_argument("--poll", type=int, default=10,
                   help="seconds between price checks while a position is open")
    p.add_argument("--once", action="store_true")
    p.set_defaults(func=cmd_ipo)

    p = sub.add_parser("notify", help="alert queue that Jarvis polls")
    p.add_argument("action", nargs="?", default="pending",
                   choices=["pending", "recent", "test", "push", "clear"])
    p.add_argument("--urgency", default="act", choices=["info", "act", "critical"])
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_notify)

    p = sub.add_parser("ui", help="launch the web dashboard (every command, clickable)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--lan", action="store_true",
                   help="bind all interfaces so your phone can reach it "
                        "(required for Jarvis alerts)")
    p.add_argument("--no-open", action="store_true", help="do not open a browser")
    p.set_defaults(func=cmd_ui)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
