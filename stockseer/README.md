# StockSeer

A stock prediction tool that tells you the truth about whether it works.

Free stack end to end: Yahoo Finance data via `yfinance`, LightGBM/scikit-learn
models, no paid API keys, no accounts. Runs on Indian (NSE/BSE) and US symbols.

The hard part of stock ML is not the model — it is building an evaluation you can
believe. Most tutorials report 90%+ accuracy because they shuffle a time series,
scale features on the full sample, or predict a price level (where "predict today's
close" scores brilliantly and means nothing). StockSeer is built so those mistakes
are impossible, and it prints the honest number even when the honest number is
"no edge".

---

## Install

```powershell
pip install -r requirements.txt
```

## Use

```powershell
# Walk-forward backtest with the leakage control
python -m stockseer.cli backtest --ticker RELIANCE.NS --benchmark ^NSEI --horizon 5 --control

# Same config across many symbols -- the only honest way to read a good result
python -m stockseer.cli sweep --tickers "RELIANCE.NS,TCS.NS,INFY.NS,HDFCBANK.NS" --horizon 5

# Signal for the latest bar
python -m stockseer.cli predict --ticker ^NSEI --horizon 5 --threshold 0.55

# Fit on all history and save; then predict from the saved model
python -m stockseer.cli train --ticker ^NSEI --horizon 5
python -m stockseer.cli predict --ticker ^NSEI --model-path artifacts/idx-NSEI__lgbm__h5.joblib

# Raw feature/target correlations, no model involved
python -m stockseer.cli inspect --ticker ^NSEI

# What a capital + profit target actually requires (costs, ruin risk, edge uncertainty)
python -m stockseer.cli plan --capital 40000 --target 50000 --confidence 5 --compare
```

### `plan` — the arithmetic before the trading

`plan` answers "what does this goal actually demand of me" with a 20,000-path
Monte Carlo over the real NSE cost schedule. Two things make it worth running,
and both are usually left out:

- **Your win rate is an estimate, not a fact.** `--confidence` says how many real
  trades it rests on. Claim 55% after 5 trades and the truth is plausibly 17-83%
  — a range that straddles the break-even line. Simulations that assume the
  estimate is exact report ~100% success, which is how confident bad plans get
  built.
- **Stops don't always hold.** `--gap-prob` sends a fraction of losses straight
  through the stop at `--gap-multiple` the intended size. Rare, and responsible
  for a large share of real blow-ups.

It also refuses to silently swallow an unfundable plan: risking 25% across a 2%
stop needs 12.5x leverage, and at 1x your real risk is 2%, not 25%. It says so.

**Symbols:** NSE needs `.NS` (`RELIANCE.NS`), BSE needs `.BO`. Indices: `^NSEI`
(Nifty 50), `^NSEBANK` (Bank Nifty), `^BSESN` (Sensex), `^GSPC` (S&P 500).

Each `backtest` writes three files to `artifacts/`: a four-panel PNG, a JSON
summary, and the full daily series as CSV. Prices are cached in `cache/`, so
re-runs are offline and instant.

---

## What it does

```
prices ──► features ──► forward label ──► purged walk-forward ──► metrics + strategy
(yfinance)  (42-53)      (t → t+h)         (5 expanding folds)     (skill vs. profit)
```

**Features** (`features.py`) — 42 scale-free technical features: multi-horizon
returns, 12-1 momentum, distance from four SMAs, MACD, RSI(5/14), Bollinger %B
and width, realised vol at four windows, ATR, rolling skew/kurtosis, drawdown and
252-day percentile rank, intraday range and close location, gap, volume z-scores,
OBV slope, and calendar effects. Pass `--benchmark` for 11 more: relative strength
at four horizons, rolling beta, and index state.

Everything is a ratio, a z-score, or a percentile — never a raw price. A model fed
raw prices learns the level of the stock in the training window and falls apart
the moment the level changes.

**Label** (`labels.py`) — the forward return from close `t` to close `t+h`.
Direction for classification, volatility-scaled return for regression. `--deadband`
drops near-flat moves from training: forcing an "up" label on a +0.01% day teaches
the model to fit noise.

**Models** (`models.py`) — LightGBM (default), logistic, ridge, random forest, and
`dummy` (always-majority). Hyperparameters are deliberately shallow and heavily
regularised. Daily equity returns have a signal-to-noise ratio near 1:50; a deep
ensemble will memorise the noise and produce a gorgeous in-sample curve that dies
on contact with new data.

---

## The four guardrails

**1. No lookahead, enforced by test.** Every feature at row `t` uses only data
through the close of `t`. This is not a code-review promise — `tests/` recomputes
the whole feature matrix on truncated data and asserts row `t` is bit-identical:

```python
full = build_features(prices)
truncated = build_features(prices.iloc[:cut])
assert_series_equal(full.iloc[cut - 1], truncated.iloc[-1])
```

A stray `.shift(-1)`, a `center=True` window, or a scaler fitted on the full sample
all fail this test immediately.

**2. Purged, embargoed walk-forward** (`splits.py`). Train on the past, test on the
next block, roll forward — never a shuffled split. And the last `h` training rows
are *dropped*: with a 5-day horizon their labels span 5 days into the test period,
so keeping them hands the model the answer. This boundary leak is subtle enough
that it survives in a lot of published work.

**3. A shuffled-label control** (`--control`). Re-runs the entire pipeline with the
target randomly permuted. AUC must collapse to ~0.50. If it does not, information
is leaking somewhere and the real number is worthless. Reported alongside the real
result, so you never have to take the pipeline on faith.

**4. Costs and the right baseline.** Every backtest reports the model against
buy-and-hold, net of `--cost-bps` charged on position *changes*. Skill and profit
are printed separately because they come apart constantly: a 52% accurate model
that trades daily loses to costs; a 50.5% model that is right on the big days wins.

The tool also prints a **t-statistic on the accuracy edge**. Below t = 2, an edge
is not distinguishable from luck — and `sweep` reminds you how many t > 2 hits
pure chance would have handed you across the symbols you tried.

---

## What you should expect to find

Running the default config on Nifty 50, Reliance, TCS, Infosys, HDFC Bank, ITC and
the S&P 500: **AUC lands between 0.51 and 0.54, and no symbol clears t = 2.** After
costs, every configuration trailed buy-and-hold.

That is the correct result, and it is worth stating plainly: daily direction on
liquid large-caps is close to unpredictable from price and volume alone. The 0.52
AUC is real but too small to survive transaction costs. Anyone showing you 70%
accuracy on daily direction has a leak, and this repo is largely a machine for
proving that to yourself.

Where the honest version of this work goes next:

- **Volatility, not direction.** Forecasting realised vol is genuinely tractable
  (AUC 0.65+) and is what options desks actually trade. Swap the label; the rest
  of the pipeline is unchanged.
- **Cross-sectional ranking.** "Which 10 of the Nifty 50 outperform next month" is
  a far easier question than "does this one go up tomorrow", and it is how real
  quant equity works. Needs a panel loop over `build_dataset`.
- **Data nobody else has.** Price and volume are the most-mined dataset on earth.
  Edge lives in earnings-call text, supply-chain data, insider filings, options
  flow — things not already in the last 40 years of OHLCV.
- **Longer horizons.** Monthly and quarterly returns carry more signal per unit of
  noise, and cost drag falls by an order of magnitude.

---

## Layout

| File | Role |
|---|---|
| `stockseer/data.py` | yfinance loading, adjustment, CSV cache |
| `stockseer/features.py` | 42+ technical features, all backward-looking |
| `stockseer/labels.py` | forward returns, direction/regression targets, deadband |
| `stockseer/splits.py` | purged embargoed walk-forward folds |
| `stockseer/models.py` | LightGBM / logistic / ridge / RF / dummy |
| `stockseer/backtest.py` | OOS prediction, metrics, position sizing, cost model |
| `stockseer/pipeline.py` | end-to-end wiring, shuffled control, save/load |
| `stockseer/report.py` | console summary + four-panel PNG |
| `stockseer/cli.py` | `backtest` / `sweep` / `train` / `predict` / `inspect` |
| `tests/` | the integrity suite — run it before trusting any number |

```powershell
python -m pytest
```

---

## Disclaimer

Research tooling, not investment advice. Backtested out-of-sample results are the
*ceiling* of live performance, never the floor — real execution adds slippage,
impact, and gaps you cannot trade through. And note the meta-risk this tool cannot
protect you from: if you re-run with different settings until the numbers look
good, the edge you find is one you invented. Pick your configuration first, run it
once, and believe the result.
