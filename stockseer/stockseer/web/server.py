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
import os
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


def asdict_notif(n) -> dict:
    """Notification -> JSON, with the vibration pattern Jarvis should use."""
    from dataclasses import asdict

    return {**asdict(n), "vibration": n.vibration}


_FEED_RETRY_AFTER: dict[str, float] = {}
_UPGRADE_EVERY = 120.0          # seconds between attempts to get back to Angel


def _feed(kind: str = "auto"):
    """Cached feed, but keep trying to climb back to real-time.

    SmartAPI returns a spurious AG8004 often enough that a single bad probe at
    startup used to pin the whole session to 15-minute delayed Yahoo data. On an
    ordinary day that is a nuisance; on listing morning you would be acting on
    quarter-hour-old prices without noticing. So a degraded feed is retried
    rather than accepted.
    """
    import time as _t

    feed = _FEED_CACHE.get(kind)
    if feed is None:
        _FEED_CACHE[kind] = feed = get_feed(kind)
        return feed

    if kind == "auto" and getattr(feed, "delayed_seconds", 0) > 60:
        now = _t.time()
        if now >= _FEED_RETRY_AFTER.get(kind, 0.0):
            _FEED_RETRY_AFTER[kind] = now + _UPGRADE_EVERY
            try:
                from ..live.angel import AngelFeed

                upgraded = AngelFeed.from_env()
                log.info("recovered real-time feed: %s", upgraded.describe())
                _FEED_CACHE[kind] = upgraded
                return upgraded
            except Exception as exc:
                log.debug("still on delayed data (%s)", exc)
    return feed


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
def _auth_token() -> str:
    """Shared secret required on /api/* when the server is publicly reachable.

    Set STOCKSEER_TOKEN (in .env or the environment) to switch it on. Empty
    means no auth, which is correct on a private network -- Tailscale or your
    own LAN -- and dangerous over a public tunnel.
    """
    from ..live.angel import _load_dotenv

    _load_dotenv()
    return os.environ.get("STOCKSEER_TOKEN", "").strip()


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    token = _auth_token()

    @app.before_request
    def _check_token():
        if not token or not request.path.startswith("/api/"):
            return None
        # /api/ping stays open so discovery can still identify the server
        # without holding the secret.
        if request.path == "/api/ping":
            return None
        supplied = (request.headers.get("X-StockSeer-Token")
                    or request.args.get("token", ""))
        if supplied != token:
            return jsonify({"error": "unauthorized"}), 401
        return None

    # ---------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC, name)

    @app.get("/api/ping")
    def ping():
        """Identify this server, instantly.

        Deliberately does no work -- no broker login, no cache read. Phones
        discover the PC by sweeping a /24, so this gets hit ~250 times in a few
        seconds and must never block on a SmartAPI session.
        """
        from .. import __version__

        return jsonify({"app": "stockseer", "version": __version__})

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

    # ---------------------------------------------------- notifications (Jarvis)
    @app.get("/api/notify/pending")
    def notify_pending():
        """Undelivered alerts. Jarvis polls this and vibrates once per alert."""
        from ..notify import hub

        h = hub()
        # Record the poll so alerts are not also pushed via ntfy while Jarvis
        # is here to deliver them -- one event, one buzz.
        h.note_poll()
        items = h.pending(int(request.args.get("limit", 20)))
        return jsonify(_clean([{**asdict_notif(n)} for n in items]))

    @app.post("/api/notify/ack")
    def notify_ack():
        """Mark alerts delivered so the phone never buzzes twice for one event."""
        from ..notify import hub

        ids = (request.get_json(force=True) or {}).get("ids") or []
        return jsonify({"acknowledged": hub().mark_delivered(ids)})

    @app.post("/api/notify/test")
    def notify_test():
        """Queue a test alert so the phone can verify the buzz reaches it."""
        from ..notify import hub

        urgency = (request.args.get("urgency") or "act")
        n = hub().alert(
            "test", urgency, "StockSeer test alert",
            "If your phone buzzed, Jarvis is wired up correctly.\n"
            "This is the pattern real market alerts will use.",
        )
        return jsonify(_clean(asdict_notif(n)))

    @app.get("/api/notify/recent")
    def notify_recent():
        from ..notify import hub

        return jsonify(_clean([asdict_notif(n)
                               for n in hub().recent(int(request.args.get("limit", 50)))]))

    @app.get("/api/ipo/calendar")
    def ipo_calendar():
        from ..ipo.calendar import scan
        from ..ipo.registry import to_dict

        from ..ipo.apply import evaluate
        from ..ipo.study import load_base_rate

        rate = load_base_rate()
        events = scan(refresh=request.args.get("refresh") == "1")
        out = []
        for e in events:
            # `days_away` was dropped from CalendarEvent when the calendar was
            # narrowed to closing day only, and this endpoint kept reading it --
            # every call raised AttributeError. The event is always today now,
            # so the field had nothing left to say.
            app = evaluate(e.subs, e.terms, rate["median"])
            out.append({
                "kind": e.kind, "urgency": e.urgency, "ipo": to_dict(e.ipo),
                "retail_x": e.subs.retail_x if e.subs else None,
                "odds": e.subs.odds if e.subs else None,
                "lot_amount": getattr(e.terms, "lot_amount", None),
                "ev_per_application": app.ev_per_application if app else None,
                "ev_total": app.ev_total if app else None,
            })
        return jsonify(_clean(out))

    @app.post("/api/ipo/scan")
    def ipo_scan():
        """Run the calendar and queue notifications for anything due."""
        from ..ipo.calendar import notify_today

        pushed = notify_today(refresh=True)
        return jsonify(_clean({"queued": len(pushed),
                               "titles": [n.title for n in pushed]}))

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


def lan_addresses() -> list[tuple[str, str]]:
    """Every address this machine is reachable at, with its interface name.

    Needed because "which IP does my phone use" has no obvious answer: a laptop
    on USB tethering, wifi and a VM adapter has three or four, and only one of
    them routes to the phone.
    """
    import socket

    out: list[tuple[str, str]] = []
    try:
        import subprocess

        # PowerShell knows the interface names; socket alone only gives numbers.
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetIPAddress -AddressFamily IPv4 | "
             "Where-Object { $_.IPAddress -ne '127.0.0.1' } | "
             "ForEach-Object { $_.IPAddress + '|' + $_.InterfaceAlias }"],
            capture_output=True, text=True, timeout=10,
        )
        for line in res.stdout.splitlines():
            if "|" in line:
                ip, _, iface = line.strip().partition("|")
                if ip and not ip.startswith("169.254."):   # link-local: not routable
                    out.append((ip, iface))
    except Exception:
        pass

    if not out:
        try:
            out = [(socket.gethostbyname(socket.gethostname()), "primary")]
        except Exception:
            pass
    return out


def serve(host: str = "127.0.0.1", port: int = 8765, debug: bool = False) -> None:
    app = create_app()
    lan = host in ("0.0.0.0", "::")

    print(f"\n  StockSeer dashboard")
    print(f"  on this PC   http://127.0.0.1:{port}")
    if lan:
        print("\n  reachable from your phone at one of these"
              " (same network as the PC):")
        for ip, iface in lan_addresses():
            hint = ""
            if ip.startswith(("192.168.42.", "192.168.43.", "10.")):
                hint = "   <- likely the USB/wifi tether"
            elif ip.startswith("192.168.56."):
                hint = "   <- VirtualBox, not this one"
            print(f"    http://{ip}:{port}{hint}")
        print("\n  If the phone still cannot connect, Windows Firewall is"
              "\n  blocking it. In an ADMIN PowerShell, once:")
        print(f"    New-NetFirewallRule -DisplayName 'StockSeer' -Direction Inbound"
              f" -LocalPort {port} -Protocol TCP -Action Allow")
    else:
        print(f"\n  Bound to loopback only -- your phone CANNOT reach this.")
        print(f"  Restart with:  python -m stockseer.cli ui --lan")

    print(f"\n  feed: {_feed().describe()}")
    print("  Ctrl+C to stop\n")
    app.run(host=host, port=port, debug=debug, threaded=True)
