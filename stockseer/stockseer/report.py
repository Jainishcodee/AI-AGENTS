"""Console summary and the four-panel PNG report.

Colours come from a validated categorical palette (blue = strategy,
orange = buy-and-hold) held fixed across every panel, so an entity keeps its
hue wherever it appears. Both palettes pass CVD, lightness-band, chroma and
contrast checks against their own surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink_secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "strategy": "#2a78d6",
        "market": "#eb6834",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "ink_secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "strategy": "#3987e5",
        "market": "#d95926",
    },
}


# --------------------------------------------------------------------------- #
# Console
# --------------------------------------------------------------------------- #
def _pct(x: float | None) -> str:
    return "   n/a" if x is None or x != x else f"{x * 100:>6.2f}%"


def _num(x: float | None, nd: int = 2) -> str:
    return "  n/a" if x is None or x != x else f"{x:>6.{nd}f}"


def print_report(result: dict[str, Any]) -> None:
    cfg, period, m, s = (
        result["config"], result["period"], result["metrics"], result["strategy"]
    )
    task = cfg["task"]
    bar = "=" * 74

    print(f"\n{bar}")
    print(f" {cfg['ticker']}  |  {cfg['model']}  |  {task}  |  {cfg['horizon']}-day horizon")
    print(bar)
    print(
        f" out-of-sample window : {period['test_start']} .. {period['test_end']}"
        f"  ({period['n_test_days']} days)"
    )
    print(f" features             : {period['n_features']}")
    print(f" walk-forward folds   : {cfg['n_splits']} "
          f"({'expanding' if cfg['expanding'] else 'rolling'}, "
          f"min train {cfg['min_train']}, embargo {cfg['horizon']})")

    print(f"\n-- PREDICTIVE SKILL (out-of-sample) {'-' * 38}")
    if task == "classification":
        print(f" accuracy             : {_pct(m['accuracy'])}")
        print(f" always-majority base : {_pct(m['baseline_accuracy'])}   "
              f"(up-days {_pct(m['base_rate_up'])})")
        print(f" edge over baseline   : {_pct(m['edge_vs_baseline'])}   "
              f"t = {_num(m['edge_t_stat'])}")
        print(f" ROC AUC              : {_num(m['auc'], 4)}   (0.50 = coin flip)")
        print(f" Brier / log loss     : {_num(m['brier'], 4)} / {_num(m['log_loss'], 4)}")
    else:
        print(f" out-of-sample R²     : {_num(m['r2_oos'], 4)}   (<0 = worse than the mean)")
        print(f" information coef.    : {_num(m['ic_pearson'], 4)} pearson / "
              f"{_num(m['ic_spearman'], 4)} spearman")
        print(f" direction accuracy   : {_pct(m['direction_accuracy'])}")
        print(f" MAE                  : {_num(m['mae'], 4)}")

    if "shuffled_control" in result:
        c = result["shuffled_control"]
        print(f"\n-- LEAKAGE CONTROL (labels shuffled) {'-' * 37}")
        if task == "classification":
            # Shuffling preserves the class balance, so accuracy still lands near
            # the base rate and the edge goes slightly negative (a noisy model
            # loses to always-guess-majority). AUC is the load-bearing check: it
            # measures ordering, and ordering is exactly what shuffling destroys.
            print(f" ROC AUC              : {_num(c['auc'], 4)}   <- must land near 0.50")
            print(f" accuracy             : {_pct(c['accuracy'])}   "
                  f"(base rate {_pct(c['base_rate_up'])}; a small negative edge is normal)")
            leaked = abs(c["auc"] - 0.5) > 0.03
        else:
            print(f" information coef.    : {_num(c['ic_spearman'], 4)}   <- must land near 0")
            print(f" out-of-sample R²     : {_num(c['r2_oos'], 4)}   <- must be <= 0")
            leaked = abs(c["ic_spearman"]) > 0.05
        verdict = (
            "LEAK SUSPECTED - the numbers above are not trustworthy"
            if leaked
            else "clean - no detectable leakage"
        )
        print(f" control verdict      : {verdict}")

    st, bh = s["strategy"], s["buy_and_hold"]
    print(f"\n-- STRATEGY vs BUY & HOLD (net of {s['cost_bps']:.0f}bps per turn) {'-' * 17}")
    print(f" {'':<21}{'strategy':>12}{'buy & hold':>14}")
    print(f" {'total return':<21}{_pct(st.get('total_return')):>12}{_pct(bh.get('total_return')):>14}")
    print(f" {'CAGR':<21}{_pct(st.get('cagr')):>12}{_pct(bh.get('cagr')):>14}")
    print(f" {'ann. volatility':<21}{_pct(st.get('ann_vol')):>12}{_pct(bh.get('ann_vol')):>14}")
    print(f" {'Sharpe':<21}{_num(st.get('sharpe')):>12}{_num(bh.get('sharpe')):>14}")
    print(f" {'max drawdown':<21}{_pct(st.get('max_drawdown')):>12}{_pct(bh.get('max_drawdown')):>14}")
    print(f" {'daily hit rate':<21}{_pct(st.get('hit_rate')):>12}{_pct(bh.get('hit_rate')):>14}")
    print(f"\n avg exposure         : {_pct(s['avg_exposure'])}")
    print(f" annual turnover      : {_num(s['ann_turnover'], 1)}x")
    print(f" cumulative cost drag : {_pct(s['total_cost_drag'])}")

    imp = result.get("importance") or {}
    if imp:
        print(f"\n-- TOP FEATURES (mean gain across folds) {'-' * 33}")
        for name, val in list(imp.items())[:10]:
            print(f" {name:<24} {val * 100:>5.1f}%  {'#' * max(1, int(val * 180))}")

    print(f"\n{bar}")
    print(_verdict(result))
    print(f"{bar}\n")


def _verdict(result: dict[str, Any]) -> str:
    m, s = result["metrics"], result["strategy"]
    task = result["config"]["task"]
    excess = s["excess_cagr"]

    if task == "classification":
        t = m["edge_t_stat"]
        skill = (
            "no measurable edge (t < 2 -- indistinguishable from luck)"
            if t < 2
            else f"a small but statistically real edge (t = {t:.1f})"
        )
    else:
        ic = m["ic_spearman"]
        skill = (
            "no measurable edge (|IC| < 0.02)"
            if abs(ic) < 0.02
            else f"a usable rank signal (IC = {ic:.3f})"
        )

    beat = (
        f"beats buy & hold by {excess * 100:.1f}% CAGR"
        if excess > 0
        else f"trails buy & hold by {abs(excess) * 100:.1f}% CAGR"
    )
    return f" VERDICT: {skill}; net of costs it {beat}."


# --------------------------------------------------------------------------- #
# Chart
# --------------------------------------------------------------------------- #
def _style_axes(ax, th: dict[str, str]) -> None:
    ax.set_facecolor(th["surface"])
    ax.grid(True, color=th["grid"], linewidth=0.8, linestyle="-", zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(th["axis"])
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=th["muted"], labelsize=8, length=0)
    ax.title.set_color(th["ink"])


def plot_report(
    result: dict[str, Any], out_path: Path | str, theme: str = "light"
) -> Path:
    th = THEMES[theme]
    sim = result["sim"]
    cfg = result["config"]
    imp = result.get("importance") or {}

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), facecolor=th["surface"])
    (ax_eq, ax_dd), (ax_hit, ax_imp) = axes

    pct = FuncFormatter(lambda v, _: f"{v * 100:.0f}%")

    # -- 1. equity curves (2 series: legend + direct end labels) -------------
    strat_eq, mkt_eq = sim["strategy_equity"], sim["market_equity"]
    ax_eq.plot(strat_eq.index, strat_eq, color=th["strategy"], linewidth=2.0,
               label="Strategy", zorder=3)
    ax_eq.plot(mkt_eq.index, mkt_eq, color=th["market"], linewidth=2.0,
               label="Buy & hold", zorder=2)
    for series, color in ((strat_eq, th["strategy"]), (mkt_eq, th["market"])):
        ax_eq.annotate(
            f"{series.iloc[-1]:.2f}x",
            xy=(series.index[-1], series.iloc[-1]),
            xytext=(6, 0), textcoords="offset points",
            color=color, fontsize=9, fontweight="bold", va="center",
        )
    ax_eq.axhline(1.0, color=th["axis"], linewidth=0.8, zorder=1)
    ax_eq.set_title("Growth of 1 unit (out-of-sample, net of costs)",
                    fontsize=11, fontweight="bold", loc="left", pad=10)
    # Log scale so a 2x move looks the same wherever it happens -- but relabelled
    # as multiples, since "3 x 10^0" is not how anyone reads a return.
    ax_eq.set_yscale("log")
    ax_eq.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0, 1.5, 2.0, 3.0, 5.0, 7.0)))
    ax_eq.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}x"))
    ax_eq.yaxis.set_minor_formatter(NullFormatter())
    leg = ax_eq.legend(frameon=False, fontsize=9, loc="upper left")
    for text in leg.get_texts():
        text.set_color(th["ink_secondary"])
    _style_axes(ax_eq, th)

    # -- 2. drawdown --------------------------------------------------------
    for eq, color, label in (
        (strat_eq, th["strategy"], "Strategy"),
        (mkt_eq, th["market"], "Buy & hold"),
    ):
        dd = eq / eq.cummax() - 1.0
        ax_dd.fill_between(dd.index, dd, 0, color=color, alpha=0.16, linewidth=0)
        ax_dd.plot(dd.index, dd, color=color, linewidth=1.6, label=label)
    ax_dd.set_title("Drawdown from running peak", fontsize=11, fontweight="bold",
                    loc="left", pad=10)
    ax_dd.yaxis.set_major_formatter(pct)
    leg = ax_dd.legend(frameon=False, fontsize=9, loc="lower left")
    for text in leg.get_texts():
        text.set_color(th["ink_secondary"])
    _style_axes(ax_dd, th)

    # -- 3. rolling hit rate (single series -> no legend box) ---------------
    win = min(126, max(21, len(sim) // 8))
    correct = ((sim["score"] > cfg["threshold"]).astype(float)
               == (sim["market_ret"] > 0).astype(float)).astype(float)
    roll = correct.rolling(win).mean()
    ax_hit.plot(roll.index, roll, color=th["strategy"], linewidth=1.8, zorder=3)
    ax_hit.axhline(0.5, color=th["axis"], linewidth=1.0, zorder=2)
    ax_hit.annotate("coin flip", xy=(roll.index[0], 0.5),
                    xytext=(4, 5), textcoords="offset points",
                    color=th["muted"], fontsize=8, ha="left", zorder=4,
                    bbox=dict(facecolor=th["surface"], edgecolor="none", pad=1.5))
    ax_hit.set_title(f"Rolling {win}-day directional hit rate",
                     fontsize=11, fontweight="bold", loc="left", pad=10)
    ax_hit.yaxis.set_major_formatter(pct)
    _style_axes(ax_hit, th)

    # -- 4. feature importance (one series -> one colour, never a ramp) -----
    if imp:
        top = list(imp.items())[:12][::-1]
        names = [n for n, _ in top]
        vals = [v for _, v in top]
        ax_imp.barh(names, vals, color=th["strategy"], height=0.62, zorder=3)
        ax_imp.xaxis.set_major_formatter(pct)
        ax_imp.tick_params(axis="y", labelsize=8)
        for lbl in ax_imp.get_yticklabels():
            lbl.set_color(th["ink_secondary"])
    else:
        ax_imp.text(0.5, 0.5, "model exposes no feature importances",
                    ha="center", va="center", color=th["muted"], fontsize=10)
        ax_imp.set_xticks([])
        ax_imp.set_yticks([])
    ax_imp.set_title("Feature importance (mean share of gain across folds)",
                     fontsize=11, fontweight="bold", loc="left", pad=10)
    _style_axes(ax_imp, th)

    st = result["strategy"]["strategy"]
    metric_bit = (
        f"accuracy {result['metrics']['accuracy'] * 100:.2f}%  ·  "
        f"AUC {result['metrics']['auc']:.3f}"
        if cfg["task"] == "classification"
        else f"IC {result['metrics']['ic_spearman']:.3f}"
    )
    fig.suptitle(
        f"{cfg['ticker']}  ·  {cfg['model']}  ·  {cfg['horizon']}-day horizon",
        fontsize=15, fontweight="bold", color=th["ink"], x=0.012, ha="left", y=0.985,
    )
    fig.text(
        0.012, 0.945,
        f"{result['period']['test_start']} .. {result['period']['test_end']}  ·  "
        f"{metric_bit}  ·  Sharpe {st.get('sharpe', float('nan')):.2f}  ·  "
        f"costs {cfg['cost_bps']:.0f}bps  ·  walk-forward, no lookahead",
        fontsize=9.5, color=th["ink_secondary"], ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, facecolor=th["surface"])
    plt.close(fig)
    return out_path
