"""Fig 8: round-trip cost %% vs order value per broker (the 'safety net' chart)."""
import os
import runpy

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
ns = runpy.run_path(os.path.join(BASE, "order_size_optimizer.py"))
round_trip, BROKERS = ns["round_trip"], ns["BROKERS"]

SURFACE, PAGE = "#fcfcfb", "#f9f9f7"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]

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

vs = np.geomspace(1000, 500000, 300)
short = {"Your broker (full-service ~0.05%)": "Your broker",
         "Zerodha": "Zerodha", "Groww": "Groww",
         "Upstox": "Upstox", "Angel One": "Angel One",
         "Marwadi-type full service": "Marwadi-type"}

fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), sharex=True)
for ax, kind, ttl in zip(axes, ("intraday", "delivery"),
                         ("Intraday round trip", "Delivery round trip")):
    for (b, lbl), c in zip(short.items(), SERIES):
        pct = [round_trip(v, b, kind) / v * 100 for v in vs]
        ax.plot(vs, pct, color=c, lw=2, solid_capstyle="round", label=lbl)
    ax.set_xscale("log")
    ax.set_xticks([1000, 5000, 20000, 66667, 200000, 500000])
    ax.set_xticklabels(["₹1k", "₹5k", "₹20k", "₹67k", "₹2L", "₹5L"])
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}%"))
    ax.set_title(ttl, loc="left", fontsize=11.5, fontweight="semibold",
                 color=INK, pad=8)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="y", visible=True)
    ax.grid(axis="x", visible=False)
axes[0].set_ylim(0, 0.7)
axes[1].set_ylim(0, 3.0)
axes[1].annotate("DP charge + 0.2% STT make small\ndelivery trades brutally expensive",
                 xy=(1500, 2.4), fontsize=8.5, color=INK2)
axes[0].annotate("₹20 cap kicks in →\ncost keeps falling", xy=(80000, 0.14),
                 fontsize=8.5, color=INK2)
axes[0].annotate("Groww = Angel One = Upstox above ₹5k (all 0.1%)",
                 xy=(5500, 0.30), fontsize=8.5, color=INK2)
axes[0].annotate("Zerodha = Marwadi-type until ₹67k (both 0.03%)",
                 xy=(1100, 0.062), fontsize=8.5, color=INK2)
axes[0].legend(frameon=False, fontsize=9, loc="upper right")
axes[0].set_ylabel("Round-trip charges as % of order value\n(= price move needed to break even)",
                   fontsize=9)
fig.suptitle("The order-size 'safety net' — charges vs order value, by broker",
             x=0.055, ha="left", fontsize=13.5, fontweight="semibold", color=INK)
fig.text(0.055, 0.925,
         "Charges depend on order VALUE, never share quantity. Flat fees (₹20 caps, "
         "₹5 floors, DP charges) are what small orders fail to amortize",
         fontsize=9.5, color=INK2)
fig.tight_layout(rect=(0, 0, 1, 0.90))
fig.savefig(os.path.join(BASE, "visuals", "fig8_order_size.png"))
print("wrote fig8_order_size.png")
