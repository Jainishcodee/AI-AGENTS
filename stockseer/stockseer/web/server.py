"""Flask backend for the dashboard.

Every CLI command is exposed as a job. Long commands (backtest, sweep, rules) run
on a background thread and stream their console output to the browser, so the UI
shows exactly what the terminal would -- there is no second, prettier set of
numbers that might disagree with the real ones.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

from ..data import load_prices
from ..pipeline import ARTIFACTS, Config, build_dataset, predict_latest, run_backtest, shuffled_control
from ..planner import plan_report
from ..report import print_report
from ..sizing import simulate_survival
from ..live.advisors import Call, CallLog, print_scorecard, score_calls
from ..live.feed import get_feed
from ..live.intraday import enrich
from ..live.ledger import Ledger
from ..live.monitor import ALERT_FILE, Monitor
from ..live.rules import REGISTRY, evaluate_all, live_signals

log = logging.getLogger(__name__)
STATIC = Path(__file__).resolve().parent / "static"
STATE = Path(__file__).resolve().parent.parent.parent / "artifacts" / "ui_state.json"

JOBS: dict[str, dict[str, Any]] = {}
_FEED_CACHE: dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# Job plumbing
# --------------------------------------------------------------------------- #
def _start_job(name: str, fn: Callable[[], Any]) -> str:
    jid = uuid.uuid4().hex[:12]
    buf = io.StringIO()
    JOBS[jid] = {"id": jid, "name": name, "status": "running",
                 "result": None, "error": None, "_buf": buf}

    def runner():
        try:
            with contextlib.redirect_stdout(buf):
                JOBS[jid]["result"] = fn()
            JOBS[jid]["status"] = "done"
        except Exception as exc:
            JOBS[jid]["status"] = "error"
            JOBS[jid]["error"] = f"{type(exc).__name__}: {exc}"
            JOBS[jid]["trace"] = traceback.format_exc()
            log.exception("job %s (%s) failed", jid, name)

    threading.Thread(target=runner, daemon=True).start()
    return jid


def _clean(obj: Any) -> Any:
    """Make numpy/pandas values JSON-safe, turning NaN into None."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (f != f or f in (float("inf"), float("-inf"))) else f
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if obj is None or isinstance(obj, (str, int)):
        return obj
    return str(obj)


def _feed(kind: str = "auto"):
    if kind not in _FEED_CACHE:
        _FEED_CACHE[kind] = get_feed(kind)
    return _FEED_CACHE[kind]


def _load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"watchlist": ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "^NSEI"],
            "capital": 40000.0}


def _save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    # ---------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC, name)

    # ---------------------------------------------------------------- state
    @app.get("/api/state")
    def get_state():
        st = _load_state()
        st["feed"] = _feed().describe()
        st["rules"] = [{"name": r.name, "side": r.side, "description": r.description}
                       for r in REGISTRY]
        return jsonify(st)

    @app.post("/api/state")
    def set_state():
        st = _load_state()
        st.update(request.get_json(force=True) or {})
        _save_state(st)
        return jsonify(st)

    # --------------------------------------------------------------- search
    @app.get("/api/search")
    def search_symbols():
        from ..live.symbols import search

        q = request.args.get("q", "")
        limit = min(int(request.args.get("limit", 20)), 50)
        return jsonify(_clean(search(q, limit)))

    # ---------------------------------------------------------------- chart
    @app.get("/api/candles")
    def candles():
        symbol = request.args.get("symbol", "RELIANCE.NS")
        interval = request.args.get("interval", "5m")
        days = int(request.args.get("days", 10))

        if interval == "1d":
            raw = load_prices(symbol, start=request.args.get("start", "2022-01-01"))
            bars = raw.copy()
            bars["vwap"] = bars["Close"].rolling(20).mean()   # SMA20 stands in daily
            bars["ema9"] = bars["Close"].ewm(span=9, adjust=False).mean()
            bars["ema21"] = bars["Close"].ewm(span=50, adjust=False).mean()
            markers = []
        else:
            raw = _feed(request.args.get("feed", "auto")).history(symbol, interval, days)
            bars = enrich(raw)
            sigs = live_signals(raw, symbol, REGISTRY)
            markers = [{
                "time": int(s.at.timestamp()),
                "position": "belowBar" if s.side == "long" else "aboveBar",
                "color": "#0ca30c" if s.side == "long" else "#d03b3b",
                "shape": "arrowUp" if s.side == "long" else "arrowDown",
                "text": s.rule,
            } for s in sigs]

        def series(col):
            s = bars[col]
            return [{"time": int(t.timestamp()), "value": None if v != v else float(v)}
                    for t, v in s.items() if v == v]

        ohlc = [{
            "time": int(t.timestamp()),
            "open": float(r["Open"]), "high": float(r["High"]),
            "low": float(r["Low"]), "close": float(r["Close"]),
        } for t, r in bars.iterrows()]

        vol = [{
            "time": int(t.timestamp()), "value": float(r["Volume"]),
            "color": "rgba(12,163,12,0.45)" if r["Close"] >= r["Open"]
                     else "rgba(208,59,59,0.45)",
        } for t, r in bars.iterrows()]

        last = bars.iloc[-1]
        prev = bars["Close"].iloc[-2] if len(bars) > 1 else last["Close"]
        return jsonify(_clean({
            "symbol": symbol, "interval": interval,
            "candles": ohlc, "volume": vol,
            "vwap": series("vwap"), "ema9": series("ema9"), "ema21": series("ema21"),
            "markers": markers,
            "last": float(last["Close"]),
            "change_pct": float(last["Close"] / prev - 1.0) if prev else 0.0,
            "feed": _feed().describe(),
        }))

    # ---------------------------------------------------------------- jobs
    @app.post("/api/jobs")
    def create_job():
        body = request.get_json(force=True) or {}
        cmd = body.get("command")
        p = body.get("params") or {}
        handler = HANDLERS.get(cmd)
        if handler is None:
            return jsonify({"error": f"unknown command {cmd!r}"}), 400
        return jsonify({"job_id": _start_job(cmd, lambda: handler(p))})

    @app.get("/api/jobs/<jid>")
    def poll_job(jid):
        job = JOBS.get(jid)
        if job is None:
            return jsonify({"error": "no such job"}), 404
        return jsonify(_clean({
            "id": job["id"], "name": job["name"], "status": job["status"],
            "output": job["_buf"].getvalue(),
            "result": job["result"], "error": job["error"],
        }))

    # ---------------------------------------------------------------- journal
    @app.get("/api/journal")
    def journal():
        led = Ledger(capital=_load_state().get("capital", 40000.0))
        st = led.stats()
        return jsonify(_clean({
            "trades": [{
                **t.__dict__, "pnl": t.pnl(),
                "r_multiple": None if t.is_open else t.r_multiple(),
                "is_open": t.is_open,
            } for t in reversed(led.trades)],
            "stats": st.__dict__,
            "sources": [
                {"source": s, "stats": stats.__dict__, "verdict": v}
                for s, stats, v in (led.compare_sources()
                                    if hasattr(led, "compare_sources") else [])
            ],
        }))

    @app.post("/api/journal/open")
    def journal_open():
        b = request.get_json(force=True)
        led = Ledger(capital=_load_state().get("capital", 40000.0))
        t = led.open_trade(b["symbol"], b.get("rule", "manual"), b.get("side", "long"),
                           float(b["entry"]), float(b["stop"]), float(b["target"]),
                           int(b["qty"]), note=b.get("note", ""))
        return jsonify(_clean(t.__dict__))

    @app.post("/api/journal/close")
    def journal_close():
        b = request.get_json(force=True)
        led = Ledger(capital=_load_state().get("capital", 40000.0))
        t = led.close_trade(b["id"], float(b["exit"]), b.get("reason", "manual"))
        return jsonify(_clean({**t.__dict__, "pnl": t.pnl(), "r_multiple": t.r_multiple()}))

    # ---------------------------------------------------------------- alerts
    @app.get("/api/alerts")
    def alerts():
        if not ALERT_FILE.exists():
            return jsonify([])
        try:
            return jsonify(json.loads(ALERT_FILE.read_text(encoding="utf-8"))[-100:][::-1])
        except json.JSONDecodeError:
            return jsonify([])

    # ---------------------------------------------------------------- advisor
    @app.get("/api/advisor/calls")
    def advisor_calls():
        clog = CallLog()
        return jsonify(_clean({
            "sources": clog.sources(),
            "calls": [c.__dict__ for c in clog.calls[-200:]][::-1],
            "n": len(clog.calls),
        }))

    @app.post("/api/advisor/add")
    def advisor_add():
        b = request.get_json(force=True)
        clog = CallLog()
        c = clog.add(Call(
            source=b.get("source", "unknown"), symbol=b["symbol"],
            side=b.get("side", "long"), published_at=b["published_at"],
            entry=b.get("entry"), stop=b.get("stop"), target=b.get("target"),
            horizon_days=int(b.get("horizon_days", 10)), note=b.get("note", ""),
        ))
        return jsonify(_clean(c.__dict__))

    return app


# --------------------------------------------------------------------------- #
# Command handlers -- one per CLI command
# --------------------------------------------------------------------------- #
def _cfg(p: dict) -> Config:
    return Config(
        ticker=p.get("ticker", "^NSEI"), benchmark=p.get("benchmark") or None,
        start=p.get("start", "2012-01-01"), end=p.get("end") or None,
        horizon=int(p.get("horizon", 5)), task=p.get("task", "classification"),
        deadband=float(p.get("deadband", 0.0)), model=p.get("model", "lgbm"),
        n_splits=int(p.get("splits", 5)), min_train=int(p.get("min_train", 750)),
        expanding=not p.get("rolling", False),
        threshold=float(p.get("threshold", 0.5)), mode=p.get("mode", "long_flat"),
        cost_bps=float(p.get("cost_bps", 5.0)),
    )


def h_backtest(p: dict) -> dict:
    cfg = _cfg(p)
    res = run_backtest(cfg)
    if p.get("control"):
        res["shuffled_control"] = shuffled_control(cfg, res["dataset"])
    print_report(res)

    sim = res["sim"]
    equity = [{"time": int(t.timestamp()),
               "strategy": float(r["strategy_equity"]),
               "market": float(r["market_equity"])}
              for t, r in sim.iterrows()]
    return _clean({
        "metrics": res["metrics"], "strategy": res["strategy"],
        "period": res["period"], "importance": dict(list(res["importance"].items())[:15]),
        "equity": equity,
        "control": res.get("shuffled_control"),
        "chart": f"{cfg.ticker.replace('^', 'idx-')}__{cfg.model}__h{cfg.horizon}__report.png",
    })


def h_sweep(p: dict) -> dict:
    rows = []
    for ticker in [t.strip() for t in p.get("tickers", "").split(",") if t.strip()]:
        cfg = _cfg({**p, "ticker": ticker})
        try:
            res = run_backtest(cfg)
        except Exception as exc:
            print(f" {ticker}: FAILED {exc}")
            continue
        m, s = res["metrics"], res["strategy"]
        rows.append({"ticker": ticker,
                     "accuracy": m.get("accuracy", m.get("direction_accuracy")),
                     "edge_t": m.get("edge_t_stat"), "auc": m.get("auc"),
                     "sharpe": s["strategy"].get("sharpe"),
                     "bh_sharpe": s["buy_and_hold"].get("sharpe"),
                     "excess_cagr": s["excess_cagr"]})
        print(f" {ticker}: done")
    hits = sum(1 for r in rows if (r["edge_t"] or -99) > 2)
    print(f"\n {hits}/{len(rows)} show t > 2; chance alone gives ~{len(rows) * 0.023:.1f}")
    return _clean({"rows": rows, "hits": hits, "expected_by_chance": len(rows) * 0.023})


def h_predict(p: dict) -> dict:
    return _clean(predict_latest(_cfg(p)))


def h_inspect(p: dict) -> dict:
    ds = build_dataset(_cfg(p))
    ic = ds.X.corrwith(ds.fwd, method="spearman").sort_values(key=abs, ascending=False)
    return _clean({
        "rows": len(ds.X), "features": int(ds.X.shape[1]),
        "start": str(ds.X.index[0].date()), "end": str(ds.X.index[-1].date()),
        "up_pct": float(ds.y.mean()),
        "fwd_mean": float(ds.fwd.mean()), "fwd_sd": float(ds.fwd.std()),
        "ic": [{"feature": k, "rho": float(v)} for k, v in ic.head(20).items()],
    })


def h_plan(p: dict) -> dict:
    capital = float(p.get("capital", 40000))
    target = float(p.get("target", 50000))
    kw = dict(
        win_rate=float(p.get("win_rate", 0.55)), rr=float(p.get("rr", 1.5)),
        risk_pct=float(p.get("risk_pct", 0.02)), stop_pct=float(p.get("stop_pct", 0.02)),
        max_trades=int(p.get("max_trades", 500)), delivery=bool(p.get("delivery")),
        leverage=float(p.get("leverage", 1.0)),
        win_rate_confidence=int(p.get("confidence", 30)),
        gap_prob=float(p.get("gap_prob", 0.03)),
    )
    plan_report(capital=capital, target_profit=target, **kw)
    res = simulate_survival(
        capital=capital, target_profit=target, win_rate=kw["win_rate"],
        rr_gross=kw["rr"], risk_pct=kw["risk_pct"], stop_pct=kw["stop_pct"],
        max_trades=kw["max_trades"], delivery=kw["delivery"], leverage=kw["leverage"],
        win_rate_confidence=kw["win_rate_confidence"], gap_prob=kw["gap_prob"],
    )
    return _clean({**res.__dict__, "capital": capital, "target": target})


def h_rules(p: dict) -> dict:
    feed = _feed(p.get("feed", "auto"))
    out = []
    for symbol in [s.strip() for s in p.get("tickers", "").split(",") if s.strip()]:
        try:
            bars = feed.history(symbol, p.get("interval", "5m"), int(p.get("days", 55)))
        except Exception as exc:
            print(f" {symbol}: FAILED {exc}")
            continue
        for st in evaluate_all(bars, stop_atr=float(p.get("stop_atr", 1.0)),
                               target_atr=float(p.get("target_atr", 1.5)),
                               cost_r=float(p.get("cost_r", 0.05))):
            out.append({"symbol": symbol, **st.__dict__,
                        "worth_trading": st.worth_trading})
        print(f" {symbol}: scored {len(REGISTRY)} rules")
    return _clean({"rows": out})


def h_watch(p: dict) -> dict:
    symbols = [s.strip() for s in p.get("tickers", "").split(",") if s.strip()]
    mon = Monitor(symbols=symbols, feed=_feed(p.get("feed", "auto")),
                  interval=p.get("interval", "5m"),
                  capital=float(p.get("capital", 40000)),
                  risk_pct=float(p.get("risk_pct", 0.01)))
    print(" calibrating rules...")
    mon.calibrate()
    alerts = mon.scan()
    for a in alerts:
        print(f" [{a.urgency}] {a.message}")
    if not alerts:
        print(" no signals on the latest completed bar.")
    return _clean({"alerts": [a.__dict__ for a in alerts],
                   "calibration": {sym: {r: s.__dict__ for r, s in d.items()}
                                   for sym, d in mon.rule_stats.items()}})


def h_advisor_score(p: dict) -> dict:
    clog = CallLog()
    if not clog.calls:
        print(" no calls logged yet -- add some in the Advisor panel first.")
        return {"stats": {}}
    outcomes, stats = score_calls(
        clog.calls, lambda s: load_prices(s, start=p.get("start", "2012-01-01")),
        cost_pct=float(p.get("cost_pct", 0.0011)),
        default_stop_pct=float(p.get("default_stop", 0.05)),
        default_target_pct=float(p.get("default_target", 0.10)),
    )
    print_scorecard(stats)
    return _clean({
        "stats": {k: {**v.__dict__, "verdict": v.verdict} for k, v in stats.items()},
        "outcomes": [{**o.call.__dict__, "result": o.result,
                      "r_multiple": o.r_multiple, "pct_return": o.pct_return,
                      "filled_at": o.filled_at, "exit_at": o.exit_at}
                     for o in outcomes[-200:]],
    })


HANDLERS: dict[str, Callable[[dict], Any]] = {
    "backtest": h_backtest, "sweep": h_sweep, "predict": h_predict,
    "inspect": h_inspect, "plan": h_plan, "rules": h_rules,
    "watch": h_watch, "advisor": h_advisor_score,
}


def serve(host: str = "127.0.0.1", port: int = 8765, debug: bool = False) -> None:
    app = create_app()
    print(f"\n  StockSeer dashboard  ->  http://{host}:{port}\n")
    print(f"  feed: {_feed().describe()}")
    print("  Ctrl+C to stop\n")
    app.run(host=host, port=port, debug=debug, threaded=True)
