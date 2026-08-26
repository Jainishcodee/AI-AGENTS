# Portfolio Analysis Report — 26 Aug 2026

Account: SRBEA2077 (Viral Mahendrakumar Shah) · Data: 4 broker Excel files + app screenshots of 25 Aug 2026
Scripts: `portfolio_analysis.py` → `reconcile_fy.py` → `visualize_portfolio.py` (run in that order) · `fetch_market.py` for live prices
Outputs: `output/*.csv` (tidy data) · `visuals/fig1..fig7.png` (charts)

---

## 1. The bottom line — 3 years, all charges and taxes included

| Financial year | Gross realized P&L | All charges | **Net after everything** |
|---|---:|---:|---:|
| FY2024-25 | +₹58,344 | ₹25,333 | **+₹33,011** |
| FY2025-26 | −₹24,779 | ₹43,466 | **−₹68,245** |
| FY2026-27 (to 25 Aug) | +₹28,916 (app: ₹26,003) | ₹26,320 | **≈ +₹2,596** (app official: +₹1,559 before DP charges) |
| **Total** | | **₹95,120** | **≈ −₹32,600 to −₹36,800** |

- Broker's own lifetime statement (Jun 2022 → 25 Aug 2026): gross **+₹58,505**, trade charges **−₹83,995** → net **−₹25,491**; add non-trade charges (DP/AMC/interest/pledge) **−₹11,326** → **−₹36,817 realized**.
- Add unrealized loss on current holdings **−₹3,191** → **total wealth impact ≈ −₹40,000**.
- **Charges consumed 163% of all gross trading profit.** Brokerage alone: ₹44,463. STT: ₹25,665.
- Split by style (lifetime, net of charges): **intraday +₹50,819** (on ~₹3.8 crore turnover) vs **delivery −₹76,309**. The delivery losses are concentrated in hot IPOs bought post-listing: WAAREEENER −₹24.9k, OLAELEC −₹17.6k, STALLION −₹16.0k, BLUESTONE −₹15.5k.
- Method note: intraday P&L was recomputed from the tradebooks and matches the broker's lifetime figure to within ₹100 (0.1%). Delivery P&L per FY required reconciliation because IPO-allotment cost basis is absent from tradebooks (88 sells worth ₹8.76L had no matching buys); per-scrip gaps were allocated to FYs by unmatched-sell dates. Where both legs exist, my FIFO matches the broker to the rupee.

### Tax notes (CA hat)
- Intraday = **speculative business income** (ITR-3). Delivery held <12m = STCG @20% (post Jul-2024 rate).
- FY2025-26's large loss is valuable only if the ITR was filed by the due date with the loss schedules: speculative loss carries forward 4 years (offsets only speculative income); short-term capital loss carries 8 years (offsets any capital gains). If FY26's return captured the losses, FY27 gains can be sheltered. Verify this with your ITR filings.
- STT on intraday is deductible as business expense against speculative income; keep the broker files as evidence.

## 2. Current portfolio vs the market (25 Aug 2026)

Invested ₹75,881 → value ₹72,691 = **−4.2%**, while **NIFTY 50 is +6.7–8.4% this FY** (22,331 on 30 Mar → ~24,208), and mid/small-cap indices are at record highs. This is underperformance of ~11 percentage points in 5 months — driven by buying IPOs *after* their listing pops.

5 of 6 holdings listed within the last 3 weeks (ARDEE 12 Aug, DHOOTTRANS 17 Aug, SHIPROCKET 19 Aug, HORIZONIND 24 Aug, LALITHAA 24 Aug). All were bought in the secondary market at/near listing prices, not IPO allotment. Market context (verified): FY26 was the worst market year since COVID (Nifty −5%+, US-Iran war, crude ~$140 peak, record FII selling); FY27 has recovered sharply; the SME/recent-IPO segment burned investors through 2025 (132 of 254 SME IPOs closed 2025 in losses; RBI flagged the listing-pop-then-fade pattern — the exact pattern in this account's losers).

## 3. Hold / sell — verdicts with evidence

**Honesty first:** no computational tool reliably predicts short-term prices (validated repeatedly: daily-direction ML on liquid stocks ≈ coin-flip, AUC ~0.52). What IS computable and cross-checked: valuations vs peers, margin trends, cash flows, and **dated supply events**. That's what these verdicts use. All five new IPOs face **anchor lock-in expiry 9–18 Sep 2026** — a known supply overhang 2–3 weeks away.

| Stock | P&L | Verdict | Core evidence (cross-checked, 2+ sources) |
|---|---|---|---|
| **DHOOTTRANS** | +6.7% | **SELL — book the profit** | ~81× FY26 P/E vs peers 43–63×; already at Ambit's ₹1,598 target (only published TP); EBIT margin fell 15.6%→12.6% over 2 yrs; ~43% of equity encumbered under Bain's loan; anchor unlock 11 Sep with anchors up ~80% — maximum incentive to sell |
| **ARDEE** | −16.8% | **EXIT** | Q1 FY27: revenue +36% but EBITDA flat, margin −354bps; 40.6% revenue from one customer (Amara Raja); the one brokerage stop-loss (₹65) already breached; 52-wk low made this week; anchor unlock ~9 Sep. Valuation (20× vs peers 29–34×) is the only support |
| **HORIZONIND** | −5.4% | **EXIT** | Loss-making (FY26 −₹204 cr, widening), ₹6,887 cr debt, interest = 69% of income; even planned IPO-funded deleveraging doesn't reach breakeven; IPO subscribed only 1.52× (retail <1×), broke issue price in 2 sessions; anchor unlock 18 Sep is huge vs free float; Blackstone (75.4%) sell-down overhang |
| **SHIPROCKET** | −9.3% | **EXIT / reduce** | Core business genuinely profitable + OCF turned positive — but consolidated loss re-widened FY26; at ₹132 the P/S discount to Unicommerce is gone (~4.6× vs 4.7× for a profitable peer); bought near the ₹157 spike; anchor unlock 16 Sep; giant pre-IPO unlock (Bertelsmann/Temasek/Eternal, >50% of company) ~Feb 2027; first-ever quarterly result ~mid-Sep. Supports: ₹131 (listing), ₹97 (issue) |
| **LALITHAA** | −4.0% | **HOLD (small), tight leash** | The only one with real valuation support: P/E 13.5 vs peer avg ~30×, best-in-class RoNW ~40%, ₹1,200 cr fresh capital funding expansion. Risks: FY26 profit gold-price-inflated (unhedged), negative OCF −₹400 cr, promoter SEBI summons + ~₹1,066 cr GST notice (unreconciled), anchor unlock ~13 Sep. Exit if it closes below issue price ₹201 territory or Q1 results disappoint (due ~Sep) |
| **COALINDIA** | −3.2% | **HOLD** | 1 share is immaterial. ~6.5% dividend yield covers the price dip; consensus Buy, avg TP ₹464 (+15%) |
| **IDEA** | 0 shares | **Don't re-enter as investment** | +31% CY26 rally is news-driven (SBI loan reports, AGR cut to ₹64,046 cr, tariff-hike hopes); consensus target ₹11.86 is ~20% BELOW price; still losing ₹3,754 cr/quarter. Your FY27 intraday on it netted +₹3,884 — trading it is a different (already-working) activity |

**The bigger, computable finding:** stock selection isn't the main leak — **structure is**. Lifetime: intraday +₹50.8k net vs delivery-IPO-chasing −₹76.3k net, and ₹95k of charges on ~₹4.6 crore total turnover. Two structural fixes are worth more than any prediction tool: (1) stop buying hot IPOs post-listing (this account's 4 biggest losers = exactly that pattern, and the RBI study of 2025 documented it market-wide); (2) the brokerage schedule here (~₹44.5k lifetime) belongs to a full-service broker — a discount broker charges ₹0 delivery / ~₹20 per intraday order, which would have saved an estimated ₹30k+.

## 4. Charges over time (see fig3 + fig4)

- 29 months of data, average **₹2,889/month** in trade charges; peaks: **Jul 2026 ₹8,850**, **Aug 2026 ₹7,615**, Dec 2025 ₹6,794 — charges are accelerating in FY27 because intraday churn is at its highest.
- Worst month: **May 2025, −₹50,796** net (Waaree/Mobikwik-era delivery losses). Best: **May 2026, +₹15,483**.
- Composition (lifetime): Brokerage ₹44.4k (47%) > STT ₹25.7k (27%) > GST ₹8.5k > DP charges ₹11.0k+ > exchange/stamp/SEBI remainder.

## Files

| File | What it is |
|---|---|
| `portfolio_analysis.py` | Parses 4 Excel files; FIFO + intraday matching; writes `output/*.csv` |
| `reconcile_fy.py` | Corrects per-FY delivery P&L to broker lifetime per-scrip numbers |
| `visualize_portfolio.py` | Renders the 7 charts into `visuals/` |
| `fetch_market.py` | Pulls holding + NIFTY prices from Yahoo Finance (free) |
| `visuals/fig1_waterfall.png` | Lifetime money story: gross → charges → net → unrealized |
| `visuals/fig2_fy_pnl.png` | Per-FY gross/charges/net |
| `visuals/fig3_monthly.png` | Monthly net P&L bars vs charges line |
| `visuals/fig4_charges.png` | Charges composition per FY |
| `visuals/fig5_scrips.png` | Lifetime top 8 winners/losers by stock |
| `visuals/fig6_style.png` | Intraday vs delivery net result |
| `visuals/fig7_holdings.png` | Current holdings vs NIFTY |

*Not investment advice; verdicts are evidence summaries as of 26 Aug 2026. Anchor-unlock dates for ARDEE and LALITHAA are computed from SEBI's 30/90-day rule (not independently published). The ₹1,066 cr LALITHAA GST figure could not be reconciled against its ₹56 cr disclosed contingent liabilities — verify in the RHP before relying on it.*
