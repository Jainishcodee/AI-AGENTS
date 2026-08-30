# The Indian IPO grey market, and why StockSeer was giving bad advice

*Investigative briefing, August 2026.*

**What this is.** An assessment of three claims: that the Indian grey market —
reportedly run from Rajkot — determines how IPOs perform; that Indian equities
run on news in a way that defeats statistical strategies; and that StockSeer's
IPO alerts were not producing allotments.

**What this is not.** A guide to participating in the grey market. Those deals
are legally unenforceable, and SEBI attaches fraud liability to schemes built
on grey market pricing. Section 5 sets out the regulatory position precisely.

**How to read the evidence.** Claims are tiered. ★★★★★ means a primary
document or an outlet's own data collection; ★★☆☆☆ means one source that could
not be independently checked. The most interesting finding in this document is
tiered ★★☆☆☆, and the tier matters more than the finding.

---

## 0. The finding that changes what you do

StockSeer told you mainboard allotments returned **+14.4% mean, +9.1% median**
across 150 listings. That number is correct. It is also, on its own,
**misleading**, because it is conditional on receiving an allotment and was
never multiplied by the probability of doing so. On a 170×-subscribed issue
you receive shares 0.59% of the time.

The obvious correction — multiply the global median by 1/subscription — is
*also* wrong, and this document originally made that error. It assumes the
payoff is the same whatever the demand. It is not.

Backfilling final subscription for **382 mainboard listings** (NSE answers for
issues that closed years ago, back to 2003) gives the relationship directly:

| retail subscription | n | median gain | win rate | P(allot) | **EV per ₹1 lakh blocked** |
|---|---|---|---|---|---|
| under 1.3× | 77 | 0.00% | 43% | 100% | **₹0** |
| 1.3× – 3.5× | 76 | **−0.82%** | 43% | 44.9% | **−₹367** |
| 3.5× – 9.3× | 76 | +6.11% | 67% | 15.8% | ₹963 |
| 9.3× – 22.9× | 76 | +12.38% | 72% | 6.8% | ₹837 |
| over 22.9× | 77 | **+38.24%** | 87% | 2.3% | ₹876 |

**Spearman rho = +0.49, p < 0.0001.** Subscription strongly predicts the
listing gain, and two conclusions follow — both against intuition:

**Heavy subscription is not a penalty.** The payoff climbs almost exactly as
fast as the odds collapse, so expected value per rupee is roughly **flat above
3.5×**. Choosing between a 13× issue and a 170× issue barely matters. The
market prices this efficiently.

**The quiet issues are the dangerous ones.** Below ~3.5× the median gain is
*negative* and only 43% list up. `"Not yet full — everyone who applies should
get shares"` reads like an opportunity and is the one regime with genuinely
negative expected value. StockSeer's alert said exactly that, with no warning
attached.

So the real defect was never "you are applying to over-hyped IPOs." It was that
the alert quoted a single average payoff regardless of demand, which understated
hot issues roughly fourfold and inverted the sign on quiet ones.

The literature's allotment-adjusted argument (high-GMP issues returning ~1.27%
against a perceived 46.41%) survives as a caution about *headline* returns, but
the data here does not support the stronger reading that hot issues are worse
than cold ones. On this sample they are considerably better.

---

## 1. Mechanics — what the grey market actually is ★★★★★

Three distinct instruments trade, and conflating them causes most of the
confusion in popular coverage:

| Instrument | What trades | Pays out |
|---|---|---|
| **GMP** (Grey Market Premium) | the *shares* you expect to be allotted | only if allotted; deal cancels otherwise |
| **Kostak** | the *application*, at a fixed price | **regardless** of allotment |
| **Subject to Sauda** | the application, at a fixed price | **only if** allotted |

Subject-to-Sauda rates sit structurally above Kostak, because the buyer pays
only in the state of the world where the option is in the money.

**Who takes which side, and why it matters to you.** The seller is a retail
applicant swapping a lottery ticket for a certain, small, immediate profit. The
buyer is a financier wanting pre-listing exposure they cannot legally
accumulate. On a listing below GMP the seller still books their fixed gain and
**the buyer absorbs the entire loss**. Retail applicants selling into the grey
market are systematically the short-volatility, low-variance side — they have
sold the upside they were being told to get excited about.

**Settlement without enforceability.** Deals are struck over phone calls, with
no written contract. Books are kept in Excel or Tally. There is no clearing
house, no margin, no novation. Settlement is cash on listing day at roughly
09:45, after dealers net off and punch orders. Cash moves physically by
**angadia** — the Gujarat–Mumbai trusted-courier system — going door to door.
Deals expire if the IPO has not happened within 90 days. On default, in the
industry reference's own words, *"there is nothing anyone can do."*

**So what enforces it?** Reputational exclusion, not law. Entry is by referral
only. That is the classic structure of a closed-membership informal market:
membership is rationed by vouching and the sanction for default is permanent
expulsion. This matters for the geography question — that enforcement
technology *requires* dense repeat interaction, which is a structural reason to
expect regional concentration rather than a coincidence.

---

## 2. Geography — Gujarat yes, Rajkot unproven

### Gujarat as the centre of gravity ★★★☆☆

Business Standard, reporting on a March 2010 SEBI circular that directed
exchanges to take *"remedial, penal and disciplinary"* action over broker
involvement in the grey market, placed the market in "small towns of
**Gujarat, Rajasthan, Maharashtra, West Bengal** and some north Indian states."
Industry reference material consistently names Mumbai, Ahmedabad, Surat and
Rajkot as hubs. The angadia settlement layer is itself a Gujarati/Marwari
institution — the grey market piggybacks on pre-existing communal cash-transfer
infrastructure.

Note the regulator-derived framing is **broader than Gujarat**. Anyone
describing this as a Gujarat monopoly is overstating it.

### "Rajkot runs the biggest operation" ★★☆☆☆ — hold as hypothesis

The entire evidentiary basis is **one paywalled article** (The Ken, October
2024), claiming Rajkot is India's 3rd-largest source of retail IPO
applications on a population of ~2 million, that it "houses the country's
greatest grey market," and that roadshows almost always cover Mumbai,
Ahmedabad and Rajkot.

Why this is not established fact:

1. **The load-bearing statistic cannot be verified.** NSE and BSE do not
   publish city-wise retail application counts. The figure presumably came from
   registrar data; no third party can check it and no other outlet reproduces it.
2. **Apparent corroboration is circular.** Every downstream repetition traces
   back to the same article.
3. **No regulator document, no academic paper** identifies Rajkot as dominant.
   The scholarly literature discusses mechanism and pricing, not geography.
4. **A causal claim is smuggled in.** "Rajkot derailed Hyundai" is narrative.
   The verifiable fact is that Hyundai's GMP collapsed from ~₹570–1,000 to
   ₹38–60 and the stock listed ~1.5% down. That is GMP *tracking* deteriorating
   sentiment about a richly-priced issue — an interpretation, not a measurement.

A trap worth naming: Business Standard's 2011 piece *"Rajkot-based companies
make beeline for IPOs"* is about Rajkot **issuers** going public. It says
nothing about grey market dealing and should not be cited as support.

---

## 3. Players — genuinely undocumented ★★★★☆

**No reputable outlet has ever named an IPO grey-market dealer.** This is a
confident negative after targeted searching, and it is the section where false
information is most likely to reach you.

The market is anonymous by design: no registry, no licence, no trade body, and
access only via personal referral. Three categories of name get wrongly
conflated into "grey market players":

- **Market commentators.** An unlisted-shares platform founder quoted in the
  press about GMP runs a platform for unlisted shares — being quoted is not
  evidence of dealing.
- **SEBI-penalised IPO promoters.** The names in the Veerkrupa order (§4) are
  promoters, a merchant banker and a PR outfit penalised for a promotion
  scheme that *used* a GMP figure. They are not dealers.
- **Cyber-fraud arrests.** Searches for "grey market IPO arrest" return
  fake-IPO investment scams that use "IPO" as bait. Unrelated, and routinely
  miscited as if connected.

One structural oddity worth flagging: the largest GMP-publishing property both
reports the price and hosts the forum where counterparties find each other,
while its disclaimer states it does not "trade, deal, or support" such
transactions.

---

## 4. Does GMP predict listing gains? — **No** ★★★★★

### The base rate

**Business Standard, own data collection, calendar year 2025: of 101 mainboard
IPOs, 56 — nearly 55% — listed *below* their grey market price.**

That is a coin flip, slightly worse. Named cases of GMP overshooting include
NSDL (grey market ₹925, listed ₹880), Orkla India, Aegis Vopak, Vikram Solar
and Canara HSBC Life. Failures ran both directions: Afcons had positive GMP and
listed at a discount; NTPC Green had flat GMP and closed +12%.

### Reconciling this with the academic literature

Peer-reviewed work is more favourable — the *Journal of Financial Markets*
(2014) finds when-issued trading plays a real role in price discovery, and
working papers find GMPs are "generally unbiased predictors of listing prices"
and anticipate subscription before book-building.

Both are true, and the reconciliation is the analytically important part:

- **GMP is informative about direction and rank.** It aggregates real money
  from informed participants.
- **GMP is systematically biased upward in level.** It says roughly *which*
  IPOs pop, not *how much*.
- **The structure predicts exactly this.** Every participant except the
  marginal buyer benefits from a high printed number — sellers get better
  Kostak, dealers get volume, issuers get subscription, GMP sites get traffic.
  **There is no short-side constituency to police an inflated quote.** A market
  with an asymmetric incentive to print high numbers prints high numbers.

### Why GMP is nonetheless not worth chasing

The usual argument is that a retail investor cannot harvest the correlation,
because a high GMP is the signal that causes oversubscription, which collapses
allotment probability. Expected return = P(allotment) × conditional return, and
GMP raises the second term by crushing the first.

**Our own measurement (§0) says that argument is too strong.** Across 382
listings the two effects roughly cancel: EV per rupee is flat above 3.5×
subscription rather than falling. Hot issues are not a trap; they are
approximately fairly priced.

The real reason GMP earns you nothing is duller. **Subscription is published,
official, free, and measurably predictive (rho = +0.49).** GMP is an
unverifiable second-hand quote about a market with no records, biased upward,
demonstrably fabricable, and — per the academic work — it mostly *anticipates
subscription*. Once you have the subscription figure, GMP has already told you
whatever it knew, less reliably. StockSeer reads the official number for free
before the 5 PM cut-off, which is the whole of GMP's informational content
without any of its epistemics.

### GMP can be manufactured ★★★★★

In the **Veerkrupa Jewellers** matter (SEBI order, 29 May 2026), a GMP of ₹7 on
a ₹27 SME IPO was placed into a **paid Zee News article** and paid YouTube
videos, with UPI payments traced to channel operators. WhatsApp evidence showed
a noticee negotiating the price of publication and instructing that *"nowhere
should it say paid."*

SEBI's finding on the number itself: the GMP *"was not based on primary factor
of demand and supply."* The company's profit after tax was ₹1.07 lakh.
Seventeen noticees were restrained for 3–5 years with disgorgement.

Read that precisely: **the GMP was not a market observation that got distorted.
It was an input to a paid promotion, negotiated before publication.** In thin
issues, "GMP" can be a marketing number wearing the costume of a price.

### Numbers circulating that you should not trust

Figures like "GMP is 60–70% accurate" trace to SEO content sites with no
methodology, no sample definition and no named author. They are not evidence.

---

## 5. Regulatory position ★★★★★

SEBI's own words, from the Veerkrupa order:

> **"GMP though is not illegal per se, it is an over the counter market which
> lacks regulatory protection."**

And on the defence that an unregulated activity cannot be sanctioned:

> **"Any vacuum in Regulations cannot be allowed to be used for perpetrating
> fraud upon investors by unfair means. Absence of Regulation does not give
> exemption to commit wrong."**

The precise position: grey market dealing is **not prohibited, not regulated,
and not enforceable** — but fraud liability under s.12A and the PFUTP
regulations reaches any scheme that uses GMP as a device to induce dealing.

**SEBI has not banned GMP-publishing websites.** No evidence of any action
against one was found; they operate openly with disclaimers.

**The direction of travel is substitution, not prohibition.** SEBI has
discussed a regulated **"when-listed"** platform to allow trading in the three
days between allotment and listing, which would leave the grey market nothing
to arbitrage. Announced January 2025, still "in-principle" as of the most
recent reporting — two chairpersons and 18+ months with no launch. Treat
"SEBI is about to kill the grey market" as premature.

---

## 6. Allotment mechanics — the actionable section ★★★★★

### Category reservations (SEBI ICDR 2018)

| Route | QIB | NII | **Retail** |
|---|---|---|---|
| Reg 6(1) — profitability route | ≤ 50% | ≥ 15% | **≥ 35%** |
| Reg 6(2) — QIB route (loss-making) | ≥ 75% | ≤ 15% | **10%** |

If an issue comes via Reg 6(2), your pool is 10%, not 35%. Frequently
overlooked, and StockSeer does not currently distinguish the two.

### The rule, in SEBI's language

> **"there is no discretion in the allotment process."**

> "the allotment to each retail individual investor … **shall not be less than
> the minimum bid lot**, subject to availability … and the **remaining
> available shares, if any, shall be allotted on a proportionate basis.**"

### The regime change most explainers miss

- **Undersubscribed:** everyone gets what they applied for.
- **Mildly oversubscribed** — enough shares for one lot each: everyone gets
  1 lot, surplus distributed proportionately. **Bidding more lots genuinely
  helps here.**
- **Heavily oversubscribed** — not enough for one lot each: computerised
  lottery for a single lot. **One application is one entry whether you bid one
  lot or thirteen.** Extra lots are dead capital.

P(allotment) ≈ 1 / (retail subscription multiple). At 10× → ~10%; at 50× → ~2%;
at 170× → ~0.6%.

**The strategic consequence is counterintuitive:** bidding the maximum is
correct only in the mild regime, and strictly wrong in the heavy one — which is
the regime every exciting IPO is in.

### Multiple PANs — legal, and the largest available lever

- **One PAN = one application.** Multiple demat accounts under the same PAN do
  not multiply entries; all such applications are rejected, and the penalty is
  symmetric — you typically lose all of them, not all but one.
- **Different family members, each with their own PAN, demat and bank account,
  may each apply once.** Four members = four independent entries. This
  multiplies entries rather than nudging odds within one, which is why it
  dominates every other consideration.

Two cautions, flagged as analysis rather than sourced findings: under ASBA/UPI
funds are blocked in the *applicant's own* account, so routing one person's
money through family accounts raises benami and tax-attribution questions; and
the applicants must be real, consenting adults with their own KYC and funds.

### sHNI is a trap

The small-HNI category (>₹2 lakh to ₹10 lakh) commits ~13× a retail lot to
compete for a **~5%** pool instead of a **~35%** pool. The "fewer people have
₹2 lakh" intuition fails — in hot issues sHNI is often subscribed harder than
retail. The same ₹2 lakh split across 13 retail applications on 13 different
PANs gives 13 independent entries, which is structurally superior.

---

## 7. The news claim — ~20% supported

The claim was: *Indian markets run on news, so statistical strategies cannot
work here; they only work in US markets.*

### What holds ★★★★☆

India is genuinely sentiment-sensitive. Aggregate news sentiment significantly
influences Nifty returns on extreme-move days and the day preceding. Investor
sentiment measurably *slows* price adjustment. India exhibits excess volatility
the US does not. Indian markets are less than fully efficient — though the
literature consistently finds them **converging** toward efficiency.

### What does not ★★★★★

**The market is not dominated by human news-reactors.**

| Segment | Algorithmic share |
|---|---|
| NSE equity cash | **57%** |
| F&O | **~70%** |
| Stock futures | **74%** |

Direct retail is at a **10-year low** (33.6% of cash turnover); proprietary
trading at a **21-year high** (29.7%).

**Statistics demonstrably work in India — better than in the US, on the factor
at issue.** India's momentum premium is **11.0%/yr since 1994** on the IIM
Ahmedabad factor library (19.3% on the legacy series), *larger* than the US
equivalent. NSE's own indices: Nifty200 Momentum 30 at **18.65%** TR CAGR since
2005, Nifty Alpha 50 at **20.39%** since 2003, against Nifty 50 TRI ~12.4%.

**Money flows from news-followers to systematic players.** SEBI's own studies:
93% of individual F&O traders lost money FY22–24; individual net losses reached
**₹1.06 lakh crore in FY25**, with algo and proprietary firms on the winning
side. And **73% of Indian large-cap active funds trail over 10 years** — if
news-reading were the edge, the full-time news-readers would be winning.

### Why our own backtest failed, and what it does not prove

Our merged five-signal agent scored AUC 0.52 and lost to buy-and-hold. **US ML
studies on the identical task cluster at ~52% mean accuracy.** The number does
not distinguish India from the US, so it cannot support an India-specific claim.

The real diagnosis is five design choices, of which the fourth is decisive:

1. **Daily horizon** — the most competed, lowest signal-to-noise horizon.
   India's documented anomalies live at 1–12 months.
2. **Price-only features.**
3. **Sign target**, discarding magnitude.
4. **A liquid large-cap universe.** A 19-year NSE backtest decomposes the same
   momentum signal by liquidity:

   | Bucket | Net CAGR |
   |---|---|
   | Illiquid momentum, 15 stocks | **19.43%** |
   | Nifty 50 | 10.41% |
   | **Liquid momentum, 15 stocks** | **8.51%** — underperforms |

5. **STT-heavy turnover costs**, which punish daily rebalancing more than in
   the US.

We tested precisely the bucket where India's momentum premium has already been
arbitraged away. The null result was correct and correctly scoped to *liquid
large caps*. It does not generalise to "India."

**And the logical hole in the original claim:** if Indian prices genuinely
lagged news, that would make quantitative work *easier*, not impossible. Slow
information incorporation is the definition of exploitable inefficiency — and
it is measurable: post-earnings-announcement drift in India produces roughly
**6% over the 64 trading days** following an announcement from a pure earnings-
surprise sort. That is a purely statistical signal, and the NSE corporate-
announcements API that would feed it is free and requires no key.

---

## Scorecard

| Claim | Verdict | Strength |
|---|---|---|
| Grey market exists; GMP/Kostak/Sauda are real | **True** | ★★★★★ |
| Cash settlement via angadia, unenforceable | **True** | ★★★★☆ |
| Gujarat/Mumbai is the centre of gravity | **True** | ★★★☆☆ |
| **Rajkot is *the* biggest operation** | **Plausible, unconfirmed** | ★★☆☆☆ |
| Named dealer networks are publicly documented | **False** | ★★★★☆ |
| GMP correlates with listing direction | **True** | ★★★★☆ |
| GMP reliably predicts listing *gains* | **False** — 55% listed below GMP in 2025 | ★★★★★ |
| GMP can be fabricated | **True** — SEBI order, WhatsApp evidence | ★★★★★ |
| GMP is illegal | **False** — SEBI: "not illegal per se" | ★★★★★ |
| SEBI has banned GMP websites | **False** | ★★★★☆ |
| Family-member applications are legal | **True** | ★★★★☆ |
| sHNI improves your odds | **Mostly false** | ★★★☆☆ |
| Subscription predicts the listing gain | **True** — rho +0.49, n=382 | ★★★★★ |
| Heavily-subscribed IPOs are a poor bet | **False** — EV flat above 3.5× | ★★★★☆ |
| Barely-subscribed IPOs are a good bet | **False** — negative EV, 43% win | ★★★★☆ |
| Indian markets are news-sensitive | **True** | ★★★★☆ |
| Statistics cannot work in India | **False** — momentum 11–19%/yr since 1994 | ★★★★★ |
| Quant only works in US markets | **False, and inverted** | ★★★★★ |

## Where the evidence is thinnest

1. **The Rajkot claim.** One paywalled article, one unverifiable statistic.
   Registrar-level city data would settle it.
2. **NII/sNII allotment mechanics.** Credible sources contradict each other;
   check the specific issue's RHP rather than any explainer, including this one.
3. **Tax and benami exposure on family applications.** Structurally obvious,
   legally untested in anything located.
4. **Working-paper point estimates** on GMP accuracy. Directionally credible,
   numerically unverified.
5. Several major Indian outlets (Economic Times, Mint, Moneycontrol, Reuters)
   could not be read during this research. Original reporting there — including
   on Rajkot — would not have been seen.

## What changed in StockSeer as a result

- Expected value now appears in every alert, with return on blocked capital,
  and the payoff is **looked up by subscription level** rather than assumed
  — see [apply.py](../stockseer/ipo/apply.py). A barely-subscribed issue now
  correctly shows a negative expected value
- The one-lot-per-PAN rule is stated whenever retail is oversubscribed
- Mainboard is now an `EQ`-only allow-list; **130 of 569 supposed "mainboard"
  issues were bonds, NCDs and InvITs**, and removing them moved the headline
  from +13.5%/+7.3% to **+14.35%/+9.14%**
- SME issues no longer leak into alerts — the upcoming-issues feed names the
  field `series`, not `securityType`, so every upcoming issue had defaulted to
  mainboard
- The base rate is measured and cached rather than hardcoded
- Historical subscription is backfilled from NSE, which answers for closed
  issues back to 2003 — see [backfill.py](../stockseer/ipo/backfill.py)
