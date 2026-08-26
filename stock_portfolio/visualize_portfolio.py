"""
Portfolio visualizations (run portfolio_analysis.py + reconcile_fy.py first).

Produces 7 PNGs in ./visuals/ answering:
  1. Lifetime money story (waterfall)          -> fig1_waterfall.png
  2. Per-FY gross / charges / net              -> fig2_fy_pnl.png
  3. Monthly net P&L vs charges timeline       -> fig3_monthly.png
  4. Charges breakdown by component per FY     -> fig4_charges.png
  5. Lifetime winners & losers by stock        -> fig5_scrips.png
  6. Intraday vs delivery split                -> fig6_style.png
  7. Current holdings vs market                -> fig7_holdings.png
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")
VIS = os.path.join(BASE, "visuals")
os.makedirs(VIS, exist_ok=True)

# ---- palette (validated reference instance, light mode) ----
SURFACE, PAGE = "#fcfcfb", "#f9f9f7"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
MAGENTA, GREEN, VIOLET, RED = "#e87ba4", "#008300", "#4a3aa7", "#e34948"
POS, NEG, NEUT = BLUE, RED, MUTED          # diverging: blue <-> red, gray neutral

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "figure.facecolor": PAGE, "axes.facecolor": SURFACE,
    "savefig.facecolor": PAGE, "savefig.dpi": 150,
    "text.color": INK, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": BASELINE, "axes.linewidth": 1.0,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "font.size": 10,
})


def style_ax(ax, ygrid=True):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y" if ygrid else "x", visible=True)
    ax.grid(axis="x" if ygrid else "y", visible=False)
    ax.tick_params(length=0)


def inr(x, compact=False):
    """Indian-style formatting; compact -> lakh/crore."""
    sign = "-" if x < 0 else ""
    a = abs(x)
    if compact and a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f}Cr"
    if compact and a >= 1e5:
        return f"{sign}₹{a / 1e5:.1f}L"
    s = f"{a:,.0f}"
    parts = s.split(",")
    if len(parts) > 2:  # re-group to Indian style: 1,23,456
        digits = "".join(parts)
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{sign}₹{s}"


def title(ax_or_fig, text, sub=None):
    if isinstance(ax_or_fig, plt.Figure):
        ax_or_fig.suptitle(text, x=0.02, ha="left", fontsize=14,
                           fontweight="semibold", color=INK)
        if sub:
            ax_or_fig.text(0.02, 0.945, sub, ha="left", fontsize=10, color=INK2)
    else:
        ax_or_fig.set_title(text, loc="left", fontsize=13,
                            fontweight="semibold", color=INK, pad=30)
        if sub:
            ax_or_fig.text(0, 1.035, sub, transform=ax_or_fig.transAxes,
                           fontsize=9.5, color=INK2)


rec = pd.read_csv(os.path.join(OUT, "fy_summary_reconciled.csv"), index_col=0)
monthly = pd.read_csv(os.path.join(OUT, "monthly.csv"), index_col=0, parse_dates=True)
charges_bd = pd.read_csv(os.path.join(OUT, "charges_breakdown.csv"))
scrips = pd.read_csv(os.path.join(OUT, "scrip_lifetime_pnl.csv"), index_col=0)

FY_LBL = {"FY2024-25": "FY2024-25", "FY2025-26": "FY2025-26",
          "FY2026-27*": "FY2026-27\n(to 25 Aug)"}

# ================================================== 1. lifetime waterfall
steps = [
    ("Gross trading\nprofit", 58504.69, "flow"),
    ("Brokerage &\ntaxes on trades", -83995.20, "flow"),
    ("DP / AMC /\nother charges", -11326.10, "flow"),
    ("Realized net\n(all-in)", None, "total"),
    ("Unrealized loss,\ncurrent holdings", -3190.79, "flow"),
    ("Total wealth\nimpact", None, "total"),
]
fig, ax = plt.subplots(figsize=(9.2, 5.2))
running, x = 0.0, 0
for label, val, kind in steps:
    if kind == "total":
        color = NEUT
        ax.bar(x, running, 0.56, color=color)
        ax.text(x, min(running, 0) - 2600, inr(running), ha="center", va="top",
                fontsize=10, fontweight="semibold", color=INK)
    else:
        color = POS if val >= 0 else NEG
        ax.bar(x, val, 0.56, bottom=running, color=color)
        ytxt = running + val
        va = "bottom" if val >= 0 else "top"
        off = 1400 if val >= 0 else -1400
        base = max(running, ytxt) if val >= 0 else min(running, ytxt)
        ax.text(x, base + off, inr(val), ha="center", va=va, fontsize=10,
                color=INK2)
        running += val
    x += 1
ax.axhline(0, color=BASELINE, lw=1)
ax.set_ylim(-50000, 74000)
ax.set_xticks(range(len(steps)))
ax.set_xticklabels([s[0] for s in steps], fontsize=9, color=INK2)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: inr(v, True)))
style_ax(ax)
title(ax, "Where the money went — full account history (Jun 2022 → 25 Aug 2026)",
      "Trading made ₹58.5k gross, but charges took ₹95.3k — 163% of the profit earned")
fig.tight_layout()
fig.savefig(os.path.join(VIS, "fig1_waterfall.png"))
plt.close(fig)

# ================================================== 2. per-FY gross/charges/net
fig, ax = plt.subplots(figsize=(9.2, 5.2))
fys = list(rec.index)
xs = range(len(fys))
w = 0.26
gross = rec["GrossRealizedAdj"]
charges = -rec["TotalCharges"]
net = rec["NetAfterAllChargesAdj"]
ax.bar([i - w for i in xs], gross, w, color=BLUE, label="Gross realized P&L")
ax.bar(xs, charges, w, color=ORANGE, label="All charges (as outflow)")
ax.bar([i + w for i in xs], net, w, color=AQUA, label="Net after all charges")
for i, v in zip(xs, net):
    ax.text(i + w, v + (2000 if v >= 0 else -2000), inr(v),
            ha="center", va="bottom" if v >= 0 else "top",
            fontsize=9.5, fontweight="semibold", color=INK)
ax.axhline(0, color=BASELINE, lw=1)
ax.set_xticks(list(xs))
ax.set_xticklabels([FY_LBL[f] for f in fys], color=INK2)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: inr(v, True)))
ax.legend(frameon=False, loc="lower left", fontsize=9)
style_ax(ax)
title(ax, "Profit & loss by financial year — after every charge and tax",
      "One good year (FY25), one very bad year (FY26), breakeven so far in FY27. "
      "Delivery P&L for FY25/26 reconciled to broker lifetime figures")
fig.tight_layout()
fig.savefig(os.path.join(VIS, "fig2_fy_pnl.png"))
plt.close(fig)

# ================================================== 3. monthly timeline
fig, ax = plt.subplots(figsize=(10.5, 5.0))
m = monthly.copy()
colors = [POS if v >= 0 else NEG for v in m["NetPnL"]]
ax.bar(range(len(m)), m["NetPnL"], 0.62, color=colors,
       label="Net realized P&L (month)")
ax.plot(range(len(m)), m["TradeCharges"], color=ORANGE, lw=2,
        solid_capstyle="round", label="Charges paid (month)")
ax.axhline(0, color=BASELINE, lw=1)
ticks = [i for i, d in enumerate(m.index) if d.month in (4, 8, 12)]
ax.set_xticks(ticks)
ax.set_xticklabels([m.index[i].strftime("%b %y") for i in ticks], color=INK2)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: inr(v, True)))
worst = m["NetPnL"].idxmin()
best = m["NetPnL"].idxmax()
for d, lab_va in ((worst, "top"), (best, "bottom")):
    i = list(m.index).index(d)
    v = m.loc[d, "NetPnL"]
    ax.text(i, v + (-1500 if lab_va == "top" else 1500),
            f"{d.strftime('%b %y')}: {inr(v)}", ha="center", va=lab_va,
            fontsize=9, color=INK2)
ax.legend(frameon=False, loc="lower left", fontsize=9)
style_ax(ax)
title(ax, "Month by month — net realized P&L vs charges paid",
      "Bars: monthly result net of trade charges (IPO-allotment months understated). "
      "Line: broker & govt collections that month")
fig.tight_layout()
fig.savefig(os.path.join(VIS, "fig3_monthly.png"))
plt.close(fig)

# ================================================== 4. charges breakdown
order = ["Brokerage", "GST", "STT", "Exchange Turnover", "Stamp Duty", "DP Charges"]
piv = charges_bd.pivot_table(index="FY", columns="Component", values="Amount",
                             aggfunc="sum").fillna(0.0)
other = piv[[c for c in piv.columns if c not in order]].sum(axis=1)
piv = piv.reindex(columns=order).fillna(0.0)
piv["Other"] = other
piv = piv.loc[list(rec.index)]
comp_colors = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET]
fig, ax = plt.subplots(figsize=(9.6, 4.6))
left = pd.Series(0.0, index=piv.index)
for comp, c in zip(piv.columns, comp_colors):
    vals = piv[comp]
    ax.barh(range(len(piv)), vals, 0.52, left=left, color=c, label=comp,
            edgecolor=SURFACE, linewidth=2)
    for i, (v, l) in enumerate(zip(vals, left)):
        if v > 4200:  # label only segments wide enough to fit
            ax.text(l + v / 2, i, inr(v), ha="center", va="center",
                    fontsize=8.5, color="#ffffff" if c in (BLUE, GREEN, VIOLET, ORANGE) else INK)
    left = left + vals
for i, tot in enumerate(left):
    ax.text(tot + 600, i, inr(tot), va="center", fontsize=10,
            fontweight="semibold", color=INK)
ax.set_yticks(range(len(piv)))
ax.set_yticklabels([FY_LBL[f].replace("\n", " ") for f in piv.index], color=INK2)
ax.invert_yaxis()
ax.set_xlim(0, left.max() * 1.14)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: inr(v, True)))
ax.legend(frameon=False, loc="upper right", fontsize=8.5, ncols=2)
style_ax(ax, ygrid=False)
title(ax, "What the charges were made of, year by year",
      "Brokerage + STT alone are ~69% of all charges. 'Other' = SEBI fees, IPFT, AMC, pledge, interest, penalties")
fig.tight_layout()
fig.savefig(os.path.join(VIS, "fig4_charges.png"))
plt.close(fig)

# ================================================== 5. winners & losers
st = scrips.sort_values("TotalNet")
show = pd.concat([st.head(8), st.tail(8)])
fig, ax = plt.subplots(figsize=(9.2, 6.4))
vals = show["TotalNet"]
ax.barh(range(len(show)), vals, 0.56,
        color=[NEG if v < 0 else POS for v in vals])
for i, v in enumerate(vals):
    ax.text(v + (500 if v >= 0 else -500), i, inr(v),
            ha="left" if v >= 0 else "right", va="center", fontsize=8.5, color=INK2)
ax.axvline(0, color=BASELINE, lw=1)
ax.set_yticks(range(len(show)))
ax.set_yticklabels(show.index, fontsize=9, color=INK2)
ax.set_xlim(vals.min() * 1.25, vals.max() * 1.3)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: inr(v, True)))
style_ax(ax, ygrid=False)
title(ax, "Lifetime net P&L by stock — 8 biggest losers and winners",
      "Intraday + delivery combined, net of trade charges (broker-computed). "
      "Losers are dominated by hot-IPO names bought post-listing")
fig.tight_layout()
fig.savefig(os.path.join(VIS, "fig5_scrips.png"))
plt.close(fig)

# ================================================== 6. intraday vs delivery
fig, ax = plt.subplots(figsize=(7.6, 4.4))
cats = ["Intraday trading", "Delivery investing"]
vals = [50818.84, -76309.36]
turn = [37993611 + 38094505, 8346329 + 8303940]
ax.bar(range(2), vals, 0.44, color=[POS, NEG])
for i, (v, t) in enumerate(zip(vals, turn)):
    ax.text(i, v + (2500 if v >= 0 else -2500), inr(v), ha="center",
            va="bottom" if v >= 0 else "top", fontsize=11,
            fontweight="semibold", color=INK)
    ax.text(i, 3000 if v < 0 else -6500, f"turnover {inr(t / 2, True)}",
            ha="center", fontsize=9, color=MUTED)
ax.axhline(0, color=BASELINE, lw=1)
ax.set_xticks(range(2))
ax.set_xticklabels(cats, fontsize=11, color=INK2)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: inr(v, True)))
style_ax(ax)
title(ax, "Two very different games — net result after charges (lifetime)",
      "Intraday made money even after ₹50k of charges; buying IPOs/stocks for delivery lost ₹76k")
fig.tight_layout()
fig.savefig(os.path.join(VIS, "fig6_style.png"))
plt.close(fig)

# ================================================== 7. current holdings vs market
hold = pd.DataFrame([
    # symbol, unrealized %, unrealized INR (app screenshots, 25 Aug 2026)
    ("DHOOTTRANS", 6.72, 1289.73),
    ("COALINDIA", -3.18, -13.24),
    ("LALITHAA", -3.98, -505.50),
    ("HORIZONIND", -5.37, -801.78),
    ("SHIPROCKET", -9.28, -2034.00),
    ("ARDEE", -16.76, -1126.00),
], columns=["Symbol", "Pct", "INR"])
fig, ax = plt.subplots(figsize=(9.2, 4.8))
ax.barh(range(len(hold)), hold["Pct"], 0.56,
        color=[POS if v >= 0 else NEG for v in hold["Pct"]])
for i, (p, v) in enumerate(zip(hold["Pct"], hold["INR"])):
    ax.text(p + (0.4 if p >= 0 else -0.4), i, f"{p:+.1f}%  ({inr(v)})",
            ha="left" if p >= 0 else "right", va="center", fontsize=9, color=INK2)
ax.axvline(0, color=BASELINE, lw=1)
ax.axvline(6.7, color=MUTED, lw=1.4, ls=(0, (1, 0)))  # solid reference line
ax.text(6.7, len(hold) - 0.25, " NIFTY 50 this FY: +6.7%", fontsize=9,
        color=INK2, va="top")
ax.set_yticks(range(len(hold)))
ax.set_yticklabels(hold["Symbol"], fontsize=10, color=INK2)
ax.set_xlim(-24, 15)
ax.xaxis.set_major_formatter(mticker.PercentFormatter())
style_ax(ax, ygrid=False)
title(ax, "Current holdings — unrealized P&L vs the market (25 Aug 2026)",
      "Portfolio −4.2% overall while NIFTY 50 is +6.7% since April. "
      "5 of 6 positions are IPOs listed within the last 2 weeks")
fig.tight_layout()
fig.savefig(os.path.join(VIS, "fig7_holdings.png"))
plt.close(fig)

print("Wrote 7 figures to", VIS)
