# PEASE CAPITAL

## Fund Scope and Operating Blueprint

## 1. Fund identity

**Working name:** Pease Capital
**Fund type:** Technology-driven, multi-strategy hedge fund
**Initial capital:** $1,000
**Investment style:** Systematic-first, research-led, multi-asset and regime-aware
**Primary objective:** Generate attractive risk-adjusted returns while protecting the fund from catastrophic loss
**Secondary objective:** Build a documented and reproducible investment process that can eventually manage substantially more capital

Pease Capital will operate internally as though it were already an institutional hedge fund.

The small initial capital will limit position sizes and available instruments, but it will not limit the quality of the fund’s:

* research;
* modelling;
* risk management;
* portfolio construction;
* performance reporting;
* operating discipline.

The fund will not be designed as a personal investment dashboard. It will be designed as a scalable investment-management system.

---

# 2. Fund mission

Pease Capital exists to identify, test and combine independent investment opportunities across public markets.

The fund will seek returns from:

1. quantitative signals;
2. macroeconomic regimes;
3. market trends;
4. individual security analysis;
5. relative-value relationships;
6. behavioural and sentiment changes;
7. volatility and risk mispricing.

Every investment must be supported by an explicit thesis, measurable evidence and predefined risk controls.

---

# 3. Core principles

## 3.1 Research before capital

No strategy receives capital merely because it sounds reasonable.

Every strategy must move through:

```text
Idea
→ hypothesis
→ data collection
→ model development
→ backtesting
→ robustness testing
→ paper trading
→ risk approval
→ limited deployment
→ performance review
```

## 3.2 Risk is managed centrally

Individual strategies may generate trade ideas, but they will not determine their own final position sizes without restriction.

A central risk engine will control:

* maximum exposure;
* maximum position size;
* drawdown limits;
* portfolio correlations;
* liquidity requirements;
* concentration;
* leverage;
* strategy shutdowns.

## 3.3 Models advise; the portfolio process decides

No single model will have unrestricted authority to place trades.

A trade recommendation must pass through:

```text
Model signal
+ confidence
+ market regime
+ portfolio fit
+ transaction costs
+ risk limits
= approved allocation
```

## 3.4 Simplicity must defeat complexity

A sophisticated model must demonstrate an improvement over simpler alternatives.

Every model will be compared against appropriate baselines such as:

* buy and hold;
* equal weighting;
* moving-average strategies;
* linear regression;
* logistic regression;
* sector-relative momentum;
* simple volatility targeting.

## 3.5 Every decision must be auditable

The fund must be able to reconstruct:

* what information was available;
* which model generated the signal;
* what the model predicted;
* what risks were identified;
* why the position was opened;
* why its size was selected;
* why it was closed;
* whether the result came from skill, luck or unintended exposure.

---

# 4. Investment universe

## Phase One instruments

The initial live portfolio will focus on instruments that are liquid, fractional-share compatible and economical for a small account.

These may include:

* US-listed equities;
* broad-market ETFs;
* sector ETFs;
* Treasury ETFs;
* gold and commodity ETFs;
* short-duration Treasury or cash-equivalent instruments.

Examples of research-universe instruments include:

```text
Equities:       AAPL, MSFT, NVDA, JPM and similar securities
Equity ETFs:    SPY, QQQ, IWM
Sector ETFs:    XLK, XLF, XLE, XLV
Bonds:          TLT, IEF, SHY
Alternatives:   GLD, DBC
Defensive:      Cash or Treasury-bill exposure
```

## Future instruments

After the fund develops sufficient infrastructure and evidence, it may research:

* international equities;
* emerging markets;
* currencies;
* commodities;
* futures;
* options;
* volatility strategies;
* pairs trading;
* market-neutral portfolios;
* long-short equity;
* event-driven strategies.

These instruments will not automatically be approved for live trading merely because they are researched.

## 4.1 Live book versus monitored universe

The live portfolio and the research radar are not the same set.

```text
Live book
  Positions the fund actually holds.
  Marked continuously. Subject to risk limits.

Monitored universe
  Structured catalog the fund watches even if it has never traded a name.
  Includes equities, ETFs, indices and proxies for sectors, rates, FX and
  relevant commodities. Grouped by sector, industry and sub-industry.
  Used to discover unusual price, volume, volatility, event and
  cross-asset behaviour.

Working set (about 100 names per day)
  The subset of the monitored universe that is actively screened that day.
  Includes current holdings, watchlist names, Opportunity Queue names,
  sector and market benchmarks, and names the radar has flagged as unusual.
```

The fund must be able to surface a security the portfolio manager has never typed, provided it is in the monitored universe and an anomaly or event is detected.

A name appearing on the radar is not an approved trade. It is a discovery event that enters the Opportunity Queue at **Discovered**, with an evidence package for Ticker Analyst.

## 4.2 Phase One monitored universe

The first radar will cover liquid names and the proxies needed for relative and macro context:

* S&P 500 and other highly liquid US large-cap equities as capacity allows;
* major US equity, sector, Treasury, gold and commodity ETFs used as regime and industry proxies;
* rates and FX proxies needed for Nigeria and US context (for example USD/NGN);
* commodities that matter to monitored sectors (for example crude oil for energy);
* current holdings, watchlist names and Opportunity Queue names, always included;
* vendor movers and unusual-activity lists as discovery supplements;
* a focused NGX set of liquid Nigerian equities and ETFs that NGN Market can serve.

The daily working set should be approximately **100 tickers**. That number is a human attention budget, not a vendor limit. The stored catalog may be larger. The screen ranks the catalog and presents the working set.

Penny stocks, OTC names, and illiquid microcaps are excluded from Phase One monitoring. Additional markets may be added later without changing the radar architecture.

## 4.3 Instrument metadata and industry grouping

Every monitored instrument must carry structured metadata, including where available:

* ticker, exchange, country, currency;
* sector, industry, sub-industry;
* market capitalisation and liquidity class;
* asset type;
* benchmark and sector benchmark;
* primary macro exposures;
* known peers, substitutes, suppliers and customers.

The radar is organised by industry first, ticker second. The operator should be able to see:

* which industries are quiet;
* which industries are heating (breadth, volume, volatility, news intensity);
* whether a move is isolated, industry-wide, national or macro;
* which individual names inside an industry are unusual relative to their own history and to their peers.

Sector ETFs (XLK, XLF, XLE, XLV and similar) and relevant commodity or FX proxies are first-class monitored instruments. They are the industry- and macro-level pulse when individual-name coverage is incomplete.

---

# 5. Initial exclusions

During the first phase, the fund will not use:

* borrowed leverage;
* uncovered options;
* highly illiquid securities;
* penny stocks;
* excessive intraday trading;
* untested cryptocurrency strategies;
* strategies whose expected profit is smaller than estimated trading costs;
* strategies dependent on unavailable institutional data;
* outside investor capital.

These may be revisited only after the required data, operational controls and risk infrastructure exist.

---

# 6. Fund structure

Pease Capital will use a virtual multi-manager structure.

Although one person may operate several functions initially, each function will remain logically separate.

```text
Pease Capital
│
├── Investment Committee
│
├── Office of the CIO
│   ├── Strategy approval
│   ├── Capital allocation
│   ├── Portfolio construction
│   └── Performance evaluation
│
├── Central Risk Office
│   ├── Market risk
│   ├── Position limits
│   ├── Drawdown control
│   ├── Stress testing
│   └── Model risk
│
├── Research and Technology
│   ├── Data infrastructure
│   ├── Feature engineering
│   ├── Model development
│   ├── Backtesting
│   └── Production systems
│
├── Investment Pods
│   ├── Macro Regime Pod
│   ├── Cross-Asset Trend Pod
│   ├── Quantitative Equity Pod
│   ├── Fundamental Equity Pod
│   ├── Relative-Value Pod
│   └── Experimental Research Pod
│
├── Execution and Operations
│
└── Reporting and Performance Attribution
```

---

# 7. Investment pods

## 7.1 Macro Regime Pod

### Purpose

Determine the prevailing economic and market environment and position the portfolio accordingly.

### Inputs

* inflation;
* economic growth;
* interest rates;
* yield curve;
* credit conditions;
* volatility;
* US-dollar strength;
* commodity prices;
* market breadth.

### Models

* Hidden Markov Models;
* Gaussian mixture models;
* rule-based macro classification;
* change-point detection;
* regime probability models.

### Outputs

```text
Current regime
Probability of each regime
Expected asset behaviour
Regime transition risk
Recommended strategic allocation
```

This pod draws primarily from the systematic macro philosophy associated with Bridgewater.

---

## 7.2 Cross-Asset Trend Pod

### Purpose

Identify persistent directional trends across asset classes.

### Markets

* equities;
* bonds;
* gold;
* commodities;
* currencies when available.

### Models and signals

* moving-average crossovers;
* breakout models;
* time-series momentum;
* volatility-adjusted momentum;
* trend-strength measures;
* multi-horizon signal combinations.

### Output

Each asset receives:

```text
Direction
Trend strength
Signal confidence
Expected holding period
Volatility-adjusted position recommendation
```

---

## 7.3 Quantitative Equity Pod

### Purpose

Rank equities using systematic factors and predictive models.

### Factor groups

* value;
* quality;
* momentum;
* growth;
* profitability;
* earnings revisions;
* sentiment;
* low volatility;
* liquidity;
* sector-relative strength.

### Models

* weighted factor scoring;
* linear and logistic regression;
* random forests;
* XGBoost or LightGBM;
* ranking models;
* quantile regression.

### Primary question

> Which securities are most likely to outperform comparable securities over a defined future period?

The pod should emphasize cross-sectional ranking rather than relying exclusively on exact price forecasts.

---

## 7.4 Fundamental Equity Pod

### Purpose

Conduct deep research on specific companies and maintain a concentrated watchlist of high-conviction opportunities.

### Research areas

* business model;
* competitive advantage;
* management;
* financial quality;
* capital allocation;
* valuation;
* industry structure;
* catalysts;
* downside risks.

### Valuation methods

* discounted cash flow;
* comparable-company analysis;
* historical multiple analysis;
* scenario valuation;
* sum-of-the-parts valuation where appropriate.

### Output

Every researched company receives:

* investment thesis;
* bull case;
* base case;
* bear case;
* valuation range;
* expected catalysts;
* thesis breakers;
* confidence rating;
* maximum permissible allocation.

This pod borrows from the concentrated fundamental approach associated with TCI.

---

## 7.5 Relative-Value Pod

### Purpose

Identify mispricing between economically related instruments rather than relying solely on market direction.

### Possible strategies

* pairs trading;
* sector-relative trades;
* ETF versus constituent relationships;
* statistical arbitrage;
* spread mean reversion;
* factor-neutral equity portfolios.

### Models

* correlation analysis;
* cointegration testing;
* z-score models;
* Kalman filters;
* principal component analysis;
* clustering;
* residual-return modelling.

This pod will initially remain in research and paper-trading mode because many relative-value strategies require short selling, leverage or larger capital.

---

## 7.6 Experimental Research Pod

### Purpose

Test ideas that have not yet earned a place in the core portfolio.

Examples include:

* alternative data;
* deep-learning forecasts;
* event-driven models;
* earnings-surprise models;
* options signals;
* news-based trading;
* reinforcement learning;
* unconventional portfolio-allocation methods.

The experimental pod will receive no live capital until a strategy meets the fund’s validation standards.

---

# 8. Ticker Intelligence System

The Ticker Intelligence System will be one of the fund’s central products.

When a ticker is submitted, the system will produce an institutional-style research memo using the same analytical framework every time.

## 8.1 Ticker-analysis pipeline

```text
Ticker
│
├── Company profile
├── Financial statements
├── Valuation
├── Price behaviour
├── Earnings and filings
├── News and sentiment
├── Macro and sector regime
├── Risk analysis
├── Peer comparison
└── Portfolio compatibility
        ↓
Structured investment memo
```

## 8.2 Three-layer analyst model

Every ticker analysis must be organized into three layers.

### Layer 1: Descriptive analysis

The first layer answers:

```text
What is true now?
```

It measures the ticker’s current:

* valuation;
* growth;
* margins;
* leverage;
* volatility;
* momentum.

This layer must distinguish observed facts from inferred judgments. Missing data lowers confidence rather than being silently ignored.

### Layer 2: Comparative analysis

The second layer answers:

```text
How does this ticker compare?
```

The ticker must be compared against:

* its own history;
* its sector;
* its direct peers;
* the complete stock universe.

Comparative outputs may include percentile ranks, spread from historical median, sector-relative momentum, peer-relative valuation, and universe-relative quality or risk.

### Layer 3: Predictive analysis

The third layer answers:

```text
What should we expect from here, using only information available today?
```

The model must estimate:

* expected relative return;
* downside distribution;
* model confidence;
* portfolio improvement or deterioration.

Predictive analysis is advisory only. It cannot override portfolio risk limits or human approval.

## 8.3 Automation sequence

The ticker workflow will evolve in stages:

```text
Ticker entered
-> data prefill
-> AI-suggested research questions
-> descriptive scorecard
-> comparative ranking
-> predictive model output
-> portfolio-fit check
-> human review
-> saved memo
```

AI-generated questions and draft memo language must be treated as suggestions. Model outputs must be versioned, timestamped and linked to the exact data available at the time.

## 8.4 Required analysis modules

### Business-quality engine

Evaluates:

* growth;
* profitability;
* free cash flow;
* return on capital;
* earnings quality;
* leverage;
* balance-sheet strength;
* share dilution.

### Valuation engine

Calculates:

* relative valuation;
* historical valuation;
* peer valuation;
* discounted cash-flow scenarios;
* bull, base and bear values.

### Technical and market-behaviour engine

Evaluates:

* momentum;
* trend;
* relative strength;
* volatility;
* drawdown;
* volume;
* market sensitivity.

### Document intelligence engine

Processes:

* annual reports;
* quarterly reports;
* material-event filings;
* earnings releases;
* earnings transcripts;
* management guidance;
* risk-factor changes.

### Sentiment and event engine

Classifies:

* news sentiment;
* forward-looking sentiment;
* management confidence;
* guidance direction;
* event significance;
* narrative changes.

### Regime engine

Determines whether the ticker is supported or threatened by the current:

* market regime;
* sector regime;
* rate environment;
* inflation environment;
* volatility environment.

### Risk engine

Calculates:

* beta;
* downside beta;
* volatility;
* maximum drawdown;
* value at risk;
* expected shortfall;
* liquidity;
* factor exposure;
* earnings-event risk;
* portfolio correlation.

## 8.5 Standard ticker memo

Every ticker analysis must contain:

1. Executive view
2. Business description
3. Financial quality
4. Valuation
5. Price behaviour
6. Earnings and filing developments
7. News and sentiment
8. Macro and sector regime
9. Bull case
10. Base case
11. Bear case
12. Thesis breakers
13. Risk assessment
14. Model scores
15. Portfolio suitability
16. Recommended maximum position
17. Confidence level
18. Data timestamp and model version

## 8.6 Example output

```text
Ticker:                  XYZ
Classification:          Buy candidate
Time horizon:            6-12 months
Fundamental score:       82/100
Valuation score:         68/100
Momentum score:          74/100
Sentiment score:         61/100
Regime compatibility:    78/100
Risk score:              46/100
Overall conviction:      72/100
Maximum allocation:      4%
```

The system must explain the evidence behind every score.

## 8.7 Reviewed Ticker Analyst Scope

### Pease Capital — Ticker Analyst Scope

#### 1. Purpose

Ticker Analyst is Pease Capital’s **security research and investment-underwriting system**.

Its job is not simply to produce a stock score or write an investment memo.

It must answer, in sequence:

1. **Why are we looking at this security?**
2. **Is it worth spending research time on?**
3. **What is actually happening with the business and security?**
4. **What do independent analytical models conclude?**
5. **What is the investment thesis and what would invalidate it?**
6. **How attractive is the security relative to its peers and alternatives?**
7. **Does it fit the current portfolio and market regime?**
8. **What risks would the fund assume by owning it?**
9. **Should it progress toward a capital decision?**
10. **After a decision, has anything changed that invalidates the original analysis?**

Ticker Analyst therefore sits between **Market Radar** and the fund’s **Risk / Portfolio / Execution systems**.

```text
Market Radar
    ↓
Ticker Analyst
    ↓
Opportunity Queue
    ↓
Risk Centre
    ↓
Portfolio Engine
    ↓
Pre-Trade Check
    ↓
PM Decision
    ↓
Position Monitoring
```

Ticker Analyst may recommend that a security advance toward investment, but it does **not independently authorize a trade or determine final position size**.

---

### 2. Core Design Principle

Ticker Analyst will operate as a staged underwriting process rather than a linear memo wizard.

The new architecture is:

```text
Ticker / Discovery
       ↓
1. Discovery Context
       ↓
2. Quick Triage
       ↓
3. Deep Research
       ↓
4. Independent Model Analysis
       ↓
5. Model Consensus
       ↓
6. Investment Thesis
       ↓
7. Comparative / Alternative Analysis
       ↓
8. Portfolio Fit
       ↓
9. Risk Review
       ↓
10. Research Decision
       ↓
Opportunity Queue / Watch / Reject
       ↓
11. Continuous Monitoring
```

Each stage answers a different question.

---

### 3. Entry Points

Ticker Analyst can be entered from several parts of Pease Capital.

#### 3.1 Manual research

The PM manually enters a security.

```text
Ticker Analyst
→ Select market
→ Select ticker
```

Discovery source:

```text
manual
```

---

#### 3.2 Market Radar

A Radar anomaly is opened for deeper analysis.

Ticker Analyst receives the complete discovery package:

* anomaly score;
* Radar priority;
* price anomaly;
* volume anomaly;
* relative move;
* industry event;
* sector event;
* associated news;
* relationship signals;
* alternatives;
* AI Radar summary;
* discovery timestamp.

Discovery source:

```text
market_radar
```

---

#### 3.3 Watchlist

A watched security experiences a material change.

Examples:

* unusual price movement;
* new filing;
* earnings;
* significant news;
* model score change;
* sector regime change.

Discovery source:

```text
watchlist
```

---

#### 3.4 Existing position

Ticker Analyst may be opened because an existing holding requires review.

Discovery source:

```text
position_monitoring
```

This activates position-specific analysis such as:

* thesis status;
* current P&L;
* portfolio contribution;
* changed risks;
* add/maintain/reduce/exit review.

---

#### 3.5 Opportunity Queue

An existing research candidate can be reopened.

Discovery source:

```text
opportunity_queue
```

---

#### 3.6 News/Event

A material story can launch security research directly.

Discovery source:

```text
news_event
```

---

### 4. Permanent Ticker Desk

Ticker Analyst should not behave primarily like a one-time wizard.

Every instrument receives a persistent research desk.

Recommended routing:

```text
/ticker-analyst/AAPL
/ticker-analyst/NGX:GTCO
```

The desk becomes the permanent institutional record for that security.

It contains:

* current research view;
* current scores;
* latest model predictions;
* latest memo;
* previous analyses;
* Radar discoveries;
* news;
* watchlist status;
* Opportunity Queue status;
* position information;
* Risk Centre information;
* trade history;
* thesis history;
* model changes;
* event timeline.

---

### 5. Stage One — Discovery Context

The first question is:

> **Why are we looking at this ticker?**

Ticker Analyst should never lose the context that generated the research request.

Example:

```text
AAPL

DISCOVERY SOURCE
Market Radar

Detected:
24 Aug 2026 — 14:30 UTC

Radar priority:
P1

Why it surfaced:
• +3.2σ abnormal return
• 2.4× normal volume
• +4.1% residual move vs technology sector
• material company news detected

Industry state:
Technology — Positive / High activity

Related securities:
MSFT
GOOG
NVDA

Potential alternatives:
QQQ
MSFT

Radar AI Summary:
...
```

For manually entered tickers:

```text
Discovery source:
Manual PM research
```

---

### 6. Stage Two — Quick Triage

#### Purpose

Quick Triage answers:

> **Is this security worth deeper research?**

It should be extremely fast.

It should **not** require:

* a written thesis;
* bull/base/bear cases;
* full valuation;
* an AI memo;
* portfolio sizing.

---

#### 6.1 Quick Triage inputs

Use readily available information:

##### Identity

* ticker;
* company;
* exchange;
* country;
* sector;
* industry;
* asset class.

##### Market

* current price;
* daily move;
* weekly/monthly returns;
* price vs 200-day average;
* relative strength;
* volume;
* volatility.

##### Basic fundamentals

* market cap;
* revenue growth;
* earnings growth;
* profitability;
* basic valuation;
* leverage.

##### Context

* Radar evidence;
* latest important news;
* watchlist status;
* existing position;
* current regime.

---

#### 6.2 Quick Triage output

Example:

```text
AAPL

RESEARCH PRIORITY
HIGH

INITIAL VIEW
ATTRACTIVE / EXPENSIVE

Confidence
74%

Top Drivers
+ Exceptional profitability
+ Earnings growth accelerating
+ Strong relative momentum

Top Blockers
- Premium valuation
- Elevated expectations
- High technology exposure in current portfolio

Why Now
Radar detected abnormal sector-relative movement.

Recommended Research Action
PROCEED TO DEEP RESEARCH
```

---

#### 6.3 Triage actions

The allowed outputs are:

```text
REJECT
WATCH
RESEARCH
```

Not:

```text
BUY
SELL
```

Because the security has not yet passed full underwriting.

---

### 7. Stage Three — Deep Research

Deep Research asks:

> **Is this security fundamentally and quantitatively attractive?**

It consists of several independent analytical modules.

---

### 8. Company / Security Profile

Maintain a canonical profile:

```text
ticker
name
exchange
country
currency
asset_class
sector
industry
sub_industry
market_cap
primary_listing
benchmark
sector_benchmark
peer_group
```

Additional company-level metadata can include:

* major products;
* geographic exposure;
* revenue segments;
* key competitors;
* important suppliers;
* important customers;
* primary economic sensitivities.

---

### 9. Fundamental Analysis Engine

#### 9.1 Growth

Analyze:

* revenue growth;
* EPS growth;
* EBITDA growth;
* free-cash-flow growth;
* multi-year CAGR;
* acceleration/deceleration;
* analyst revision trends where available.

---

#### 9.2 Profitability

Analyze:

* gross margin;
* operating margin;
* EBITDA margin;
* net margin;
* free-cash-flow margin;
* ROE;
* ROA;
* ROIC.

---

#### 9.3 Cash generation

Analyze:

* operating cash flow;
* free cash flow;
* FCF conversion;
* capex intensity;
* working-capital behavior.

---

#### 9.4 Balance sheet

Analyze:

* debt/equity;
* net debt;
* net debt/EBITDA;
* interest coverage;
* current ratio;
* quick ratio;
* cash position;
* maturity profile where available.

---

#### 9.5 Earnings quality

Analyze:

* accruals;
* cash earnings vs accounting earnings;
* recurring vs non-recurring items;
* dilution;
* stock-based compensation;
* one-off adjustments.

---

### 10. Industry-Aware Scoring

The same financial ratios should not be treated identically for every security.

Ticker Analyst should select a **Score Profile** based on sector/industry.

Example profiles:

```text
GENERAL_EQUITY
BANK
INSURANCE
SOFTWARE
SEMICONDUCTOR
ENERGY
CONSUMER
INDUSTRIAL
REIT
ETF
```

---

#### Example — Bank

More relevant factors could include:

* ROE;
* net interest margin;
* deposit growth;
* loan growth;
* non-performing loans;
* capital adequacy;
* cost-to-income ratio.

---

#### Example — Software

More relevant factors could include:

* revenue growth;
* recurring revenue;
* gross margin;
* free cash flow;
* R&D efficiency;
* customer retention when available.

---

#### Example — Oil & Gas

More relevant factors could include:

* production;
* reserves;
* realized commodity prices;
* lifting cost;
* capex;
* leverage;
* oil-price sensitivity.

The scoring engine should therefore become:

```text
Base Factors
      +
Industry Profile
      +
Peer Normalization
      +
Regime Adjustment
```

rather than one universal weighting system.

---

### 11. Peer & Relative Analysis

Raw financial metrics are insufficient.

Every important metric should be compared against:

1. the company's own history;
2. direct peers;
3. industry;
4. sector;
5. broader universe where useful.

Example:

```text
AAPL Forward P/E

Absolute:
35×

Historical percentile:
91st percentile

Technology percentile:
78th percentile

Peer percentile:
74th percentile
```

The system should calculate percentile rankings for metrics such as:

* growth;
* margins;
* valuation;
* leverage;
* ROIC;
* momentum;
* volatility;
* FCF yield.

---

### 12. Valuation Engine

Valuation is a separate module rather than merely another factor score.

#### 12.1 Relative valuation

Compare:

* P/E;
* forward P/E;
* EV/EBITDA;
* EV/Sales;
* P/FCF;
* P/B where appropriate;
* dividend yield.

Against:

* historical ranges;
* peers;
* industry.

---

#### 12.2 Fundamental valuation

Where appropriate:

* discounted cash flow;
* dividend discount model;
* residual income;
* sum-of-the-parts.

---

#### 12.3 Scenario valuation

Every researched equity should support:

```text
Bear
Base
Bull
```

Example:

| Scenario | Fair Value | Expected Return |
| -------- | ---------: | --------------: |
| Bear     |       $145 |            -22% |
| Base     |       $190 |             +2% |
| Bull     |       $235 |            +26% |

The assumptions behind each scenario must be stored.

---

### 13. Price & Market Behaviour Engine

Analyze:

* returns over several horizons;
* momentum;
* trend;
* relative strength;
* moving averages;
* volume;
* realized volatility;
* volatility regime;
* drawdown;
* beta;
* downside beta;
* market-relative return;
* sector-relative return;
* abnormal/residual return.

The system should distinguish:

```text
Ticker moved because market moved
```

from:

```text
Ticker behaved abnormally relative to market/sector.
```

---

### 14. News & Event Intelligence

Ticker Analyst should aggregate and classify relevant events.

Categories:

```text
earnings
guidance
filing
M&A
management
regulation
litigation
product
financing
capital_return
analyst_revision
supply_chain
macro
industry
geopolitical
```

Each event should contain:

```text
timestamp
source
category
relevance
severity
sentiment
novelty
confidence
```

---

### 15. Filing / Document Intelligence

The system should process:

* annual reports;
* quarterly reports;
* material filings;
* earnings releases;
* transcripts;
* investor presentations.

AI can assist with:

* summarization;
* risk extraction;
* management commentary;
* guidance extraction;
* comparison with previous filings;
* detecting language changes.

---

### 16. AI Evidence Rules

AI must not be treated as the source of truth.

Every AI-generated research statement should derive from structured evidence.

The system should distinguish:

```text
FACT
CALCULATION
MODEL ESTIMATE
INTERPRETATION
INFERENCE
UNKNOWN
```

Where practical, generated statements should point back to evidence.

Example:

```text
Margins improved materially this quarter.
[FUNDAMENTALS:OPERATING_MARGIN]

Valuation remains above its five-year range.
[VALUATION:HISTORICAL_PE]
```

---

### 17. Macro & Regime Analysis

Ticker attractiveness should be interpreted in the current environment.

Inputs can include:

* market regime;
* sector regime;
* volatility regime;
* inflation;
* rates;
* yield curve;
* FX;
* commodity prices;
* credit conditions;
* country-specific macro variables.

Example output:

```text
Market Regime:
Risk-On / Moderate Volatility

Sector Regime:
Technology Positive

Rate Sensitivity:
High

Current Regime Compatibility:
63/100
```

---

### 18. Independent Model Layer

Ticker Analyst should not rely on a single composite score.

Run independent analytical models.

Suggested analysts:

```text
Fundamental Model
Valuation Model
Momentum Model
ML Return Model
Sentiment Model
Regime Model
Risk Model
```

These models should remain independently visible.

---

### 19. Fundamental Model

Output:

```text
Fundamental Quality
Growth
Profitability
Cash Generation
Balance Sheet
Earnings Quality
```

Example:

```text
Fundamental View:
Bullish

Score:
84/100

Confidence:
87%
```

---

### 20. Valuation Model

Output:

```text
Valuation View:
Expensive

Score:
42/100

Base Fair Value:
$X

Bear/Base/Bull Range:
...
```

---

### 21. Momentum Model

Output:

```text
Momentum:
Bullish

Trend strength:
78

Relative strength:
82

Volatility:
Elevated
```

---

### 22. ML Return Model

Potential outputs:

* expected relative return;
* probability of outperforming;
* return quantiles;
* downside p05;
* forecast horizon;
* model confidence;
* out-of-distribution warning.

Example:

```text
Expected 6M Relative Return:
+5.8%

Probability Outperforming:
64%

5th Percentile:
-18%

ML Confidence:
58%
```

---

### 23. Sentiment Model

Analyze:

* financial news;
* filings;
* transcripts;
* management tone;
* guidance.

Output:

```text
Current Sentiment:
Positive

Change:
Improving

Confidence:
73%
```

---

### 24. Regime Model

Output:

```text
Current Regime:
Growth / Moderate Volatility

Ticker Compatibility:
Positive

Confidence:
69%
```

---

### 25. Model Consensus Engine

Do not silently average conflicting models.

Show agreement and disagreement.

Example:

```text
MODEL CONSENSUS

Fundamentals       BULLISH
Valuation          BEARISH
Momentum           BULLISH
ML Forecast        NEUTRAL
Sentiment          BULLISH
Regime             BEARISH
Risk               MODERATE

Consensus:
MIXED-POSITIVE
```

---

### 26. Model Disagreement Detection

Model disagreement is itself meaningful evidence.

Ticker Analyst should explicitly identify:

```text
MODEL DISAGREEMENT DETECTED
```

Then explain why.

Example:

> Fundamentals and momentum remain strong, but the valuation and current rate regime are unfavorable. The security may be an excellent business without being an attractive entry at the current price.

---

### 27. Confidence Framework

Confidence should not be one unexplained percentage.

Calculate separate components.

```text
Data Completeness
Data Freshness
Model Reliability
Signal Agreement
Regime Familiarity
Historical Coverage
```

Example:

```text
Overall Confidence:        64%

Data completeness:         95%
Data freshness:            92%
Model reliability:         71%
Signal agreement:          53%
Regime familiarity:        66%
```

Low confidence should materially affect downstream recommendations.

---

### 28. Investment Thesis Engine

Only after evidence collection and model analysis should the investment thesis be formed.

The thesis package contains:

#### Investment Question

The central uncertainty being tested.

#### Thesis

Why the security may be mispriced or attractive.

#### Bull Case

Conditions producing significant upside.

#### Base Case

Most probable scenario.

#### Bear Case

Conditions producing material downside.

#### Thesis Breakers

Observable developments that invalidate the investment case.

#### Risk Notes

Important risks that may not directly invalidate the thesis but influence sizing or timing.

---

### 29. AI Research Memo

AI can draft the research memo using validated evidence.

It may:

* summarize;
* synthesize;
* highlight disagreement;
* draft scenarios;
* explain technical model outputs;
* propose questions requiring human review.

It should not fabricate missing financial information.

Missing information should appear explicitly:

```text
Missing / Low-Confidence Data

• analyst revision data unavailable
• incomplete Nigerian balance-sheet history
• earnings transcript unavailable
```

---

### 30. Comparative Alternatives Engine

This connects Ticker Analyst to the new Market Radar relationship system.

Ticker Analyst should answer:

> **Even if this security is attractive, is there a better expression of the same thesis?**

Compare against:

##### Direct competitors

Example:

```text
AAPL vs Samsung
NVDA vs AMD
GTCO vs Zenith vs UBA
```

##### Sector alternatives

Perhaps the sector ETF gives a cleaner exposure.

##### Cross-asset alternatives

Example:

```text
Oil thesis
→ producer equity?
→ energy ETF?
→ crude ETF/future eventually?
```

##### Substitute opportunities

If a company is negatively affected by an event, which competitors might benefit?

---

#### Alternative comparison output

```text
THESIS:
Nigerian banks benefit from current rate environment.

Candidates:

GTCO       Score 81
Zenith     Score 77
UBA        Score 69

Best Fundamental Quality:
GTCO

Best Valuation:
Zenith

Highest Momentum:
GTCO

Lowest Risk:
Zenith
```

This allows the fund to choose the **best expression of an investment thesis**, rather than simply buying the first security discovered.

---

### 31. Portfolio Fit Layer

Ticker analysis and portfolio analysis must remain distinct.

Portfolio Fit asks:

> **Would owning this security improve the current fund?**

Consider:

* current holdings;
* asset allocation;
* sector exposure;
* country exposure;
* factor exposure;
* currency exposure;
* correlations;
* volatility;
* beta;
* drawdown contribution;
* concentration.

Example:

```text
SECURITY VIEW
Attractive

PORTFOLIO FIT
Poor

Reason:
The fund already has 22% semiconductor exposure.

Adding this security would increase:
Technology exposure → 36%
Semiconductor exposure → 28%
Portfolio beta → 1.17

Portfolio Recommendation:
Do not add currently.
```

---

### 32. Risk Review

Ticker Analyst should surface security-level risk before passing the opportunity forward.

Analyze:

* historical volatility;
* expected volatility;
* max drawdown;
* downside beta;
* VaR;
* expected shortfall;
* liquidity;
* earnings risk;
* event risk;
* regulatory risk;
* country risk;
* FX risk;
* factor exposures.

Output:

```text
Security Risk:
HIGH

Primary Risks:
1. Valuation compression
2. Earnings sensitivity
3. Sector concentration

Risk Centre Status:
Review Required
```

Final risk approval still belongs to Risk Centre.

---

### 33. Research Decision

After deep analysis, Ticker Analyst issues a **research-stage decision**, not an executed trade decision.

Allowed statuses:

```text
REJECT
WATCH
RESEARCH FURTHER
INVESTMENT CANDIDATE
```

For existing positions:

```text
MAINTAIN
ADD CANDIDATE
REDUCE REVIEW
EXIT REVIEW
```

---

### 34. Decision Card

This should appear prominently at the top of the Ticker Desk.

Example:

```text
AAPL

RESEARCH VERDICT
INVESTMENT CANDIDATE

Confidence
72%

Research Score
78/100

Position
Not Held

Opportunity Queue
Research

Risk Status
Moderate

Portfolio Fit
Good

Top Drivers
+ Excellent profitability
+ Strong relative momentum
+ Earnings growth

Top Blockers
- Expensive valuation
- Elevated expectations
- High rate sensitivity

Next Action
Run pre-trade review
```

---

### 35. Direct Desk Actions

From Ticker Analyst:

```text
Add to Watchlist
Remove from Watchlist
Move to Opportunity Queue
Run Deep Research
Refresh Analysis
Open News
Open Market Radar Context
Compare Alternatives
Open Risk Centre
Run Portfolio Fit
Run Pre-Trade Check
Save Memo
Open Trade Journal
```

Actions shown should depend on the current lifecycle state.

---

### 36. Opportunity Queue Integration

Ticker Analyst can promote research to the Opportunity Queue.

It should pass:

```text
ticker
discovery_source
research_status
research_score
confidence
model_consensus
thesis
bull_case
base_case
bear_case
thesis_breakers
top_drivers
top_blockers
valuation
portfolio_fit
risk_status
evidence_snapshot
model_versions
timestamp
```

The Queue should therefore receive a complete research package rather than only a ticker.

---

### 37. Watchlist Integration

Ticker Analyst should display whether the security is watched and why.

Watchlist entries can contain:

```text
ticker
watch_reason
date_added
target_conditions
important_events
research_status
```

Market Radar continues monitoring watchlist names.

---

### 38. Existing Position Integration

If the ticker is held, display:

```text
position size
average cost
current price
unrealized P&L
portfolio weight
risk contribution
original thesis
original conviction
current conviction
```

The system should compare the current state against the state at purchase.

---

### 39. Thesis Monitoring

After an investment thesis exists, Ticker Analyst should monitor it continuously.

Monitor:

* earnings;
* guidance;
* margins;
* growth;
* valuation;
* news;
* management;
* macro regime;
* sector regime;
* model prediction;
* price behavior.

Thesis status:

```text
INTACT
STRENGTHENING
WEAKENING
AT RISK
BROKEN
```

---

### 40. Change Detection

Every new analysis should compare against the previous one.

Example:

```text
AAPL

WHAT CHANGED SINCE LAST REVIEW?

Composite research score:
76 → 69

Fundamentals:
82 → 85

Valuation:
48 → 35

Momentum:
79 → 63

Sentiment:
72 → 67

Regime compatibility:
70 → 55
```

AI summary:

> Business fundamentals improved modestly, but the security became more expensive while momentum and regime compatibility weakened.

---

### 41. Material Change Alerts

Ticker Analyst should generate alerts when significant changes occur.

Examples:

```text
THESIS RISK
MODEL REVERSAL
VALUATION EXTREME
FUNDAMENTAL DETERIORATION
EARNINGS EVENT
REGIME CHANGE
PORTFOLIO CONCENTRATION
NEWS EVENT
```

These may be surfaced through Market Radar, the Ticker Desk and Risk Centre.

---

### 42. Ticker Timeline

Every ticker should have a chronological institutional record.

Example:

```text
24 Aug
Radar discovered AAPL

24 Aug
Quick Triage → Research

25 Aug
Deep research completed

25 Aug
Investment Candidate

27 Aug
Added to Opportunity Queue

03 Sep
Material news detected

12 Sep
Pre-trade check completed

12 Sep
Position opened

01 Oct
Thesis strengthened after earnings

...
```

---

### 43. Evidence Ledger

Every recommendation must retain the evidence that existed **at that time**.

Store:

* financial snapshot;
* market-data snapshot;
* news snapshot;
* regime snapshot;
* model predictions;
* scoring version;
* model versions;
* AI memo;
* analyst modifications;
* timestamps.

Historical records should never silently use newer data.

This prevents hindsight bias.

---

### 44. Human Override System

Pease Capital should separately record:

```text
Model Recommendation
PM Decision
Override?
Override Reason
```

Example:

```text
Model:
WATCH

PM:
INVESTMENT CANDIDATE

Override:
YES

Reason:
Upcoming catalyst not captured by current model.
```

Later, performance attribution can measure whether human overrides improve results.

---

### 45. Research Score Architecture

The existing deterministic score should evolve.

Current:

```text
Quality
Growth
Valuation
Momentum
Balance Sheet
```

New system:

```text
Fundamental Quality
Growth
Valuation
Momentum
Financial Risk
Sentiment
Regime Compatibility
```

But the final weighting should depend on:

```text
industry profile
+
historical validation
+
model confidence
```

Do not manually add excessive complexity before sufficient evidence exists.

---

### 46. Score Explainability

Every score must expose its contributors.

Example:

```text
VALUATION SCORE: 42/100

Positive:
+ FCF yield above closest peer
+ PEG below sector median

Negative:
- Forward P/E 91st historical percentile
- EV/EBITDA above industry median
```

No opaque scoring.

---

### 47. ML Research Layer

The existing ML infrastructure remains but becomes integrated as one independent analyst.

Required capabilities:

* feature preparation;
* labels;
* model training;
* validation;
* prediction;
* backtesting;
* feature importance;
* regime analysis;
* portfolio fit;
* warnings.

Outputs should be timestamped and versioned.

---

### 48. ML Guardrails

Ticker Analyst must display warnings for:

* insufficient history;
* stale model;
* feature missingness;
* out-of-distribution observation;
* poor recent model performance;
* low prediction confidence;
* regime not represented sufficiently in training.

Example:

```text
ML WARNING

This prediction has low reliability because the
current volatility regime was underrepresented
in training data.
```

---

### 49. Historical Model Accuracy

Where sufficient data exists, show:

```text
Model:
XGBoost Relative Return v3.2

Rolling hit rate:
61%

Recent hit rate:
54%

IC:
0.08

Calibration:
Acceptable

Current confidence:
58%
```

This prevents the user from treating an ML probability as unquestionable truth.

---

### 50. Recommended UI Structure

The persistent Ticker Desk should use sections or tabs.

#### Overview

* Research Verdict;
* confidence;
* top drivers;
* blockers;
* next action;
* position;
* Queue status;
* watchlist;
* Risk status.

#### Discovery

* Market Radar evidence;
* source;
* why now;
* industry event;
* related securities.

#### Fundamentals

* growth;
* profitability;
* cash generation;
* balance sheet;
* peer percentiles.

#### Valuation

* relative valuation;
* historical valuation;
* scenarios;
* DCF.

#### Market

* price;
* trend;
* momentum;
* volatility;
* relative strength.

#### Models

* independent model outputs;
* ML report;
* consensus;
* disagreements;
* confidence.

#### Thesis

* investment question;
* thesis;
* bull/base/bear;
* thesis breakers;
* risk notes.

#### Alternatives

* competitors;
* substitute securities;
* sector alternatives;
* ranking.

#### Portfolio

* portfolio fit;
* exposure changes;
* correlations;
* pro-forma weight.

#### News

* material events;
* AI summaries;
* filings.

#### History

* previous analyses;
* score changes;
* thesis changes;
* timeline.

---

### 51. API Scope

The current endpoints can evolve toward explicit workflow boundaries.

Suggested structure:

```text
GET  /ticker-analyst/{ticker}/desk

GET  /ticker-analyst/{ticker}/prefill
POST /ticker-analyst/{ticker}/triage

POST /ticker-analyst/{ticker}/research
GET  /ticker-analyst/{ticker}/research/latest

GET  /ticker-analyst/{ticker}/fundamentals
GET  /ticker-analyst/{ticker}/valuation
GET  /ticker-analyst/{ticker}/market
GET  /ticker-analyst/{ticker}/news
GET  /ticker-analyst/{ticker}/regime

GET  /ticker-analyst/{ticker}/models
GET  /ticker-analyst/{ticker}/consensus

POST /ticker-analyst/{ticker}/ai/memo

GET  /ticker-analyst/{ticker}/alternatives
GET  /ticker-analyst/{ticker}/portfolio-fit

POST /ticker-analyst/{ticker}/decision

GET  /ticker-analyst/{ticker}/changes
GET  /ticker-analyst/{ticker}/timeline

GET  /ticker-analyst/memos
GET  /ticker-analyst/memos/{memo_id}
```

The exact route structure can remain compatible with the current implementation while the domain model is upgraded.

---

### 52. Persistence Model

Core records should include:

```text
Instrument
TickerAnalysis
FeatureSnapshot
ModelRecommendation
ModelPrediction
ModelConsensus
EvidenceSnapshot
TickerMemo
InvestmentThesis
ThesisVersion
ResearchDecision
HumanOverride
TickerEvent
TickerRelationship
PortfolioFitSnapshot
RiskSnapshot
SystemLog
```

Existing tables should be reused where possible rather than rewritten unnecessarily.

---

### 53. Workflow Status

Ticker research should have an explicit lifecycle.

```text
UNREVIEWED
TRIAGED
WATCH
RESEARCHING
RESEARCHED
INVESTMENT_CANDIDATE
REJECTED
MONITORING
HELD
EXITED
```

This lifecycle should remain distinct from Opportunity Queue status.

---

### 54. Relationship With Market Radar

Market Radar:

> **What deserves attention?**

Ticker Analyst:

> **What does it mean, and is the security attractive?**

Radar provides:

* discovery;
* anomaly;
* industry context;
* news context;
* alternatives;
* relationship signals.

Ticker Analyst provides:

* security underwriting;
* valuation;
* fundamental analysis;
* model analysis;
* thesis;
* comparative selection.

---

### 55. Relationship With Opportunity Queue

Ticker Analyst determines whether a researched idea deserves progression.

Opportunity Queue answers:

> **Where is this idea in the investment process?**

It coordinates workflow rather than duplicating analysis.

---

### 56. Relationship With Risk Centre

Ticker Analyst calculates **security-level risks**.

Risk Centre evaluates **fund-level risk**.

Ticker Analyst:

```text
How risky is AAPL?
```

Risk Centre:

```text
What happens to Pease Capital if we add AAPL?
```

---

### 57. Relationship With Portfolio Engine

Ticker Analyst determines attractiveness.

Portfolio Engine determines allocation suitability.

A security can therefore have:

```text
Research Verdict:
Investment Candidate

Portfolio Verdict:
Do Not Add

Reason:
Excess sector concentration
```

This distinction must remain visible.

---

### 58. Relationship With Trade Journal

When a security becomes a live position, Trade Journal receives:

* original thesis;
* analysis snapshot;
* model recommendation;
* PM decision;
* risk conditions;
* pre-trade snapshot.

This allows later post-mortem analysis.

---

### 59. V2 Minimum Build

The immediate upgrade should prioritize the architecture without attempting everything simultaneously.

#### Must build

1. Persistent Ticker Desk
2. Discovery Context
3. Quick Triage
4. Research-stage verdict
5. Top drivers and blockers
6. Industry-aware score profiles
7. Peer-relative metrics
8. Model Consensus panel
9. Model Disagreement
10. Confidence decomposition
11. Deep Research flow
12. Existing AI memo
13. Portfolio Fit integration
14. Risk status
15. Opportunity Queue promotion
16. Watchlist controls
17. Analysis history
18. Change detection
19. Evidence persistence
20. Human override logging

---

### 60. V2.5

Then add:

1. full scenario valuation;
2. automated filing comparison;
3. alternatives ranking;
4. industry-specific fundamental models;
5. thesis monitoring;
6. event-triggered reanalysis;
7. AI change summaries;
8. historical model-reliability display.

---

### 61. V3

Later:

1. learned factor weights;
2. richer peer discovery;
3. cross-sectional equity ranking;
4. causal/event research;
5. alternative-data features;
6. deeper supply-chain relationships;
7. options-implied signals;
8. analyst revisions;
9. advanced portfolio interaction;
10. automated research-agent workflows.

---

### 62. Definition of Done

Ticker Analyst is successful when a researcher can open any supported ticker and answer:

##### Discovery

Why are we looking at this?

##### Fundamentals

Is this a strong business/security?

##### Valuation

What assumptions are embedded in the price?

##### Relative attractiveness

Is it better or worse than its alternatives?

##### Market

What is price action telling us?

##### Models

What do independent models conclude?

##### Confidence

How trustworthy is the conclusion?

##### Thesis

Why might the market be wrong?

##### Downside

What would invalidate our thesis?

##### Portfolio

Does the security improve the fund?

##### Risk

What could hurt us?

##### Decision

Should this advance toward capital allocation?

##### Monitoring

Has anything materially changed since we made that decision?

---

### 63. Final Ticker Analyst Mandate

> **Ticker Analyst is Pease Capital's persistent security-underwriting and research-intelligence system. It converts a security discovered through Market Radar, the watchlist, portfolio monitoring, news, the Opportunity Queue, or manual research into an evidence-backed investment thesis. It combines fundamental analysis, valuation, peer comparison, market behavior, financial-document intelligence, sentiment, macro regimes, machine-learning predictions, risk analysis and portfolio compatibility while preserving independent model opinions and uncertainty. It determines whether a security should be rejected, watched, researched further, or promoted as an investment candidate. It does not independently authorize trades or final position sizes. After a thesis is created, Ticker Analyst continuously monitors changes to the evidence and maintains the complete institutional history of the security.**

The mental model for the whole feature is therefore:

```text
              TICKER ANALYST

              WHY NOW?
                  │
                  ▼
          QUICK TRIAGE
      "Worth our attention?"
                  │
                  ▼
          DEEP RESEARCH
       "Is it attractive?"
                  │
                  ▼
        INDEPENDENT MODELS
      "What does each see?"
                  │
                  ▼
          MODEL CONSENSUS
      "How strong is evidence?"
                  │
                  ▼
       INVESTMENT THESIS
       "Where is the edge?"
                  │
                  ▼
          ALTERNATIVES
    "Is there a better trade?"
                  │
                  ▼
         PORTFOLIO FIT
     "Does the fund need it?"
                  │
                  ▼
           RISK REVIEW
       "Can we afford it?"
                  │
                  ▼
       RESEARCH DECISION
                  │
        ┌─────────┼──────────┐
        ▼         ▼          ▼
      Reject     Watch    Candidate
                              │
                              ▼
                      Opportunity Queue
                              │
                              ▼
                   Fund-level capital process

                 AFTER DECISION
                       │
                       ▼
                 MONITOR CHANGE
                       │
                       ▼
                THESIS STILL TRUE?
```

This keeps Ticker Analyst from becoming another stock-recommendation screen. It becomes the **security research desk of the hedge fund**.

---

# 9. Central portfolio-construction engine

The fund will not simply invest equally in every attractive ticker.

The portfolio engine will combine:

* expected return;
* model confidence;
* estimated volatility;
* downside risk;
* correlation;
* liquidity;
* current regime;
* strategy allocation;
* transaction costs.

## Portfolio methods to research

* equal risk contribution;
* volatility targeting;
* inverse-volatility weighting;
* risk parity;
* minimum variance;
* maximum diversification;
* constrained mean-variance optimisation;
* Black–Litterman;
* hierarchical risk parity;
* conviction-weighted allocation.

No optimizer may produce unrestricted allocations.

All portfolio methods must include practical constraints.

---

# 10. Central risk system

The Central Risk Office has authority over every strategy and position.

This structure is inspired primarily by Citadel’s centralized approach to portfolio construction and risk oversight.

## 10.1 Position-level controls

Each position will have:

* maximum portfolio weight;
* expected holding period;
* volatility estimate;
* stop or thesis-review condition;
* exit criteria;
* event-risk flag;
* liquidity assessment.

## 10.2 Strategy-level controls

Each pod will have:

* capital allocation;
* risk budget;
* drawdown limit;
* volatility target;
* turnover ceiling;
* approved instruments;
* shutdown criteria.

## 10.3 Portfolio-level controls

The overall fund will monitor:

* gross exposure;
* net exposure;
* factor concentration;
* sector concentration;
* asset-class concentration;
* portfolio volatility;
* maximum drawdown;
* expected shortfall;
* liquidity;
* regime exposure;
* correlation between pods.

## 10.4 Risk hierarchy

```text
Level 1: Position warning
Level 2: Position reduction
Level 3: Strategy capital reduction
Level 4: Strategy suspension
Level 5: Portfolio-wide defensive mode
Level 6: Full trading halt
```

## 10.5 Initial live risk limits

Until more evidence exists:

```text
Maximum single-equity position:       5%
Maximum ETF position:                25%
Maximum sector exposure:             30%
Minimum cash allocation:             15%
Maximum target portfolio drawdown:   10%
Maximum experimental allocation:      5%
Uncovered leverage:                    0%
```

These limits may be revised as the capital base and research quality change.

---

# 11. Capital-allocation framework

This component borrows from Millennium’s pod model.

Each strategy competes for capital based on evidence.

## Pod evaluation criteria

* out-of-sample return;
* Sharpe ratio;
* Sortino ratio;
* maximum drawdown;
* stability across regimes;
* turnover;
* transaction costs;
* correlation with other pods;
* model confidence;
* operational reliability.

## Pod lifecycle

```text
Research
→ candidate
→ paper trading
→ probationary capital
→ core strategy
→ increased allocation
```

A strategy may also move backwards:

```text
Core strategy
→ reduced allocation
→ probation
→ suspension
→ retirement
```

Past success will not guarantee permanent capital.

---

# 12. Research and technology platform

This component borrows heavily from D. E. Shaw’s research-driven structure.

## Core platform capabilities

### Data ingestion

* market prices;
* corporate fundamentals;
* company filings;
* macroeconomic data;
* earnings transcripts;
* analyst-estimate data where available;
* news;
* alternative data later.

### Market data vendors

Yahoo Finance is not an official market-data API. It may remain a research convenience for ad-hoc history, but it must not be the production source for quotes, universe membership, or the daily radar.

Pease Capital will use a **multi-vendor stack**. No single vendor is required to do every job. Licensed, documented APIs are preferred over scraping.

Phase One vendor map:

```text
US ticker catalog, snapshots, official US bars
  Polygon (Massive)

US batch quotes for the working set
  Tiingo IEX (primary live marks)
  Polygon previous close / snapshot (fallback)

US identity, sector, industry, fundamentals, ratios
  Financial Modeling Prep (FMP)
  Polygon ticker details as fallback identity

Nigerian equities and ETFs
  NGN Market

FX (USD/NGN and later pairs)
  Dedicated FX feed already used by the live-price platform

Filings
  SEC EDGAR for US issuers
```

Vendor rules:

* Quotes for the live book and the radar working set must come from Polygon, Tiingo, FMP or NGN Market — not Yahoo.
* Historical bars used in models should prefer the same licensed sources. Yahoo backfill is a last resort and must be labelled as such.
* Sector and industry used for grouping must come from FMP or Polygon identity, not from operator typing.
* If a vendor fails, the next vendor in the map is used. A gap is logged. The radar does not silently go blank.
* The fund may add a paid news or unusual-activity vendor later. That is not required to launch the radar.

Approximately 100 names per day is well inside the capacity of the vendors already configured. The constraint is research quality and operator attention, not API quotas.

### Market radar

The platform must maintain a discovery and market-intelligence layer that does not require the operator to already know the ticker. The full mandate, engines and UI are defined in section 18.8.

Nightly or intra-day cycle:

```text
Sync Universe Manager (catalog + metadata + always-watched names)
→ refresh quotes, bars and event/news inputs for the working universe
→ run signal engines
     price and volume anomalies (history-normalised)
     relative moves vs market / sector / industry / peers
     industry and sector state
     news and event classification
     fundamental and corporate-event changes (as data allows)
     macro context
     relationship and alternatives suggestions
→ compute multi-dimensional scores and priority tiers
→ present Overview / Industries / Discoveries / Relationships / Watchlist
→ optionally narrate with AI (facts, model output and interpretation separated)
→ promote high-priority discoveries into Opportunity Queue as Discovered
   with a full evidence package for Ticker Analyst
→ store observations for historical memory and later evaluation
```

Anomaly detection is cross-sectional as well as time-series. A name is interesting if it is unusual versus itself, versus its industry or peers, or because of a material event with confirming market behaviour.

The radar does not place trades or size positions. It only creates discovery events with evidence (what moved, by how much, versus what baseline, related assets, as-of timestamp, data vendor, and confidence).

### Data validation

* missing-value checks;
* duplicate detection;
* timestamp validation;
* corporate-action adjustment;
* survivorship-bias prevention;
* point-in-time data handling;
* data-version tracking.

### Research environment

* notebooks for exploration;
* reusable Python modules;
* experiment tracking;
* model registry;
* feature registry;
* reproducible environments;
* automated tests.

### Backtesting engine

The engine must support:

* walk-forward testing;
* transaction costs;
* slippage;
* delayed execution;
* rebalancing rules;
* survivorship-bias controls;
* look-ahead-bias prevention;
* benchmark comparison;
* regime analysis.

### Production environment

Research code must not directly execute live trades.

The development stages will be:

```text
Research
→ validated model
→ paper-trading service
→ production candidate
→ approved deployment
```

---

# 13. Model governance

Every model will have a model card containing:

* purpose;
* owner;
* version;
* training data;
* features;
* target;
* assumptions;
* evaluation metrics;
* known weaknesses;
* approved use;
* prohibited use;
* retraining schedule;
* shutdown criteria.

## Model validation requirements

A model must pass:

* in-sample testing;
* validation testing;
* out-of-sample testing;
* walk-forward testing;
* cost-adjusted testing;
* regime testing;
* sensitivity analysis;
* stability analysis;
* baseline comparison.

## Model confidence

Confidence will depend on:

* data quality;
* model stability;
* agreement between models;
* distance from the training distribution;
* recent performance;
* regime familiarity.

Low-confidence predictions must receive lower capital allocations.

---

# 14. Artificial-intelligence research assistant

The fund will include an AI research layer that helps:

* summarize filings;
* extract structured facts;
* compare reporting periods;
* identify risks;
* draft investment memos;
* explain model outputs;
* generate research questions;
* monitor thesis changes.

The AI assistant will not be permitted to invent financial data or override validated numerical systems.

Its outputs must distinguish between:

```text
Verified fact
Calculated value
Model estimate
Interpretation
Inference
Unknown information
```

The AI layer acts as a research interface and analyst, not as an unrestricted portfolio manager.

---

# 15. Performance attribution

The fund must determine where returns came from.

Performance will be decomposed by:

* pod;
* strategy;
* ticker;
* asset class;
* sector;
* market regime;
* factor exposure;
* model;
* discretionary override;
* realized and unrealized gains;
* transaction costs.

## Key performance metrics

* total return;
* annualized return;
* volatility;
* Sharpe ratio;
* Sortino ratio;
* maximum drawdown;
* Calmar ratio;
* beta;
* alpha;
* correlation;
* hit rate;
* profit factor;
* turnover;
* value at risk;
* expected shortfall.

A positive return without attribution is not considered sufficient evidence of skill.

---

# 16. Reporting system

## Daily internal report

* portfolio value;
* current positions;
* daily profit and loss;
* exposure;
* risk warnings;
* regime state;
* new signals;
* upcoming events.

## Weekly investment review

* pod performance;
* position changes;
* model disagreements;
* thesis updates;
* risk changes;
* research pipeline.

## Monthly investor letter

Even with one investor, the fund will produce a professional monthly letter containing:

* net asset value;
* monthly and cumulative return;
* benchmark comparison;
* major contributors;
* major detractors;
* portfolio positioning;
* market commentary;
* risk statistics;
* strategy changes;
* current research.

## Quarterly strategy review

Each pod must defend:

* its continued edge;
* its performance;
* its drawdown;
* its correlation;
* its use of capital;
* whether it should be expanded, reduced or closed.

---

# 17. Additions borrowed from leading hedge funds

## From Citadel

Pease Capital will adopt:

* centralized risk management;
* shared data and technology infrastructure;
* multi-strategy diversification;
* centralized portfolio construction;
* continuous exposure monitoring;
* stress testing;
* separation between investing and risk control.

## From Millennium

Pease Capital will adopt:

* independent strategy pods;
* clear capital allocations;
* pod-level performance accountability;
* rapid reduction of underperforming strategies;
* centralized infrastructure;
* regular capital reallocation.

## From D. E. Shaw

Pease Capital will adopt:

* scientific hypothesis testing;
* strong engineering infrastructure;
* separation of research and production;
* systematic model governance;
* extensive data processing;
* combined quantitative and discretionary research;
* reproducibility.

## From Bridgewater

Pease Capital will adopt:

* macroeconomic regime classification;
* systematic conversion of economic reasoning into rules;
* cross-asset analysis;
* risk-balanced portfolio research;
* scenario thinking;
* probabilistic rather than absolute market views.

## From TCI

Pease Capital will adopt:

* deep fundamental research;
* concentrated watchlists;
* explicit valuation work;
* written investment theses;
* long-term thinking;
* clearly defined thesis breakers;
* willingness to hold cash when opportunities are unattractive.

---

# 18. Proprietary Pease Capital features

Pease Capital will add several capabilities that are not simply copied from another fund.

## 18.1 Ticker Intelligence System

A complete, repeatable research process for any supported security.

## 18.2 Human-versus-model tracking

The system will separately record:

* model recommendation;
* portfolio-manager decision;
* reason for override;
* eventual outcome.

This will reveal whether discretion improves or weakens performance.

## 18.3 Thesis monitoring

After a position is opened, the system will monitor whether the original thesis remains valid.

It will detect:

* earnings deterioration;
* guidance changes;
* valuation changes;
* new risks;
* management-language changes;
* regime changes;
* unexpected price behaviour.

## 18.4 Model disagreement engine

The system will identify disagreements such as:

```text
Fundamentals: bullish
Valuation: bearish
Momentum: bullish
Macro regime: bearish
Sentiment: neutral
```

Disagreement will not be hidden inside one score. It will be presented as a source of uncertainty.

## 18.5 Evidence ledger

Every recommendation will include the underlying evidence available at the time.

This prevents future hindsight from altering the historical thesis.

## 18.6 Opportunity queue

Potential investments will move through:

```text
Discovered
→ screening
→ research
→ watchlist
→ investment candidate
→ approved
→ active position
→ exited
→ post-mortem
```

## 18.7 Automated post-mortems

After each closed position, the system will determine:

* whether the thesis was correct;
* whether timing was correct;
* whether sizing was appropriate;
* whether the model behaved as expected;
* whether the outcome was driven by luck;
* what the fund should change.

## 18.8 Market Radar

### Mandate

Market Radar is Pease Capital’s real-time discovery and market-intelligence system.

It continuously watches:

* investable securities;
* industries and sectors;
* watchlist names;
* existing positions;
* queued opportunities;
* macro variables and relevant proxies;
* news and events;
* related, substitute and economically linked assets.

Its purpose is to answer five questions:

```text
What is unusual right now?
Why might it be unusual?
Is this isolated or part of a broader industry / market move?
What other assets may benefit or suffer because of it?
Does this deserve deeper research in Ticker Analyst?
```

**Formal definition:**

> Market Radar is Pease Capital’s real-time discovery and market-intelligence system. It identifies abnormal activity across securities, sectors and industries; monitors watchlist and portfolio names for meaningful changes; analyzes events, news and macro conditions; maps first- and second-order relationships between affected assets; identifies potential substitutes and beneficiaries; and produces evidence-backed research candidates for the Opportunity Queue and Ticker Analyst. Market Radar does not authorize trades or determine position sizes.

**Defining edge:**

> Not merely discovering what moved, but understanding the network of relationships around the move and identifying where the next opportunity may emerge.

Target behaviour example:

```text
Nigeria’s oil and gas sector is undergoing an unusually broad selloff.
The move coincides with falling crude prices and is statistically larger
than the broader NGX decline. Historically, similar energy shocks have
coincided with relative strength in X and Y industries over the next
5–20 sessions. Those industries are beginning to show confirmation today.
Here are the three liquid names worth opening in Ticker Analyst.
```

At that point Radar is no longer only a scanner. It behaves like a research desk looking for second-order opportunities.

### Architecture

```text
MARKET RADAR
│
├── Universe Manager
├── Watchlist Monitor
├── Price & Volume Anomaly Engine
├── Relative Movement Engine
├── Industry & Sector Intelligence
├── Cross-Asset / Alternatives Engine
├── Event & News Intelligence
├── Fundamental Change Detector
├── Macro Context Engine
├── Relationship Graph
├── AI Market Narrator
│
└── Discovery & Priority Engine
         ↓
Opportunity Queue (Discovered + evidence package)
         ↓
Ticker Analyst
```

### Universe Manager

The universe is a structured catalog, not merely “liquid US/NG names plus movers.”

Each instrument should carry metadata such as:

* ticker, exchange, country, currency;
* sector, industry, sub-industry;
* market_cap, liquidity_class, asset_type;
* benchmark, sector_benchmark;
* primary_macro_exposures;
* known_peers, known_substitutes, known_suppliers, known_customers.

The universe should include:

* US equities;
* Nigerian equities;
* ETFs;
* indices;
* commodities relevant to monitored sectors;
* rates and FX proxies;
* existing positions;
* watchlist names;
* Opportunity Queue names;
* vendor movers and unusual-activity lists.

Additional markets may be added later without changing the architecture.

### Watchlist Monitor

Every radar run must explicitly check watchlist names, and separately treat existing positions and queued opportunities as always-watched.

Watchlist monitoring looks for:

* abnormal price movement;
* abnormal volume;
* volatility spikes;
* new filings;
* earnings and guidance;
* analyst revisions;
* management changes;
* corporate actions;
* regulatory news;
* material company news;
* industry news affecting the name.

Sensitivity is intentionally higher for names the fund already cares about.

Example priority thresholds:

```text
General universe:     flag when priority is high enough for discovery
Watchlist:            flag meaningful change earlier (lower threshold)
Existing position:    flag risk-relevant change earliest (lowest threshold)
```

Illustrative defaults (tunable):

```text
General universe priority >= 8
Watchlist priority       >= 5
Existing position        >= 3
```

### Price & Volume Anomaly Engine

This is the core fast-moving signal layer.

Track, as data allows:

* daily return and intraday return;
* gap;
* return z-score and historical rarity / percentile;
* relative volume and volume z-score;
* realized volatility and volatility jump;
* intraday range;
* distance from moving averages;
* jump since previous scan;
* unusual options activity later.

Moves are normalised against the ticker’s own history, not only against fixed percentage thresholds.

Example:

```text
AAPL +4%          historical rarity: 98th percentile → highly unusual
Small biotech +4% historical rarity: 61st percentile → less unusual
```

Same absolute move, different importance.

### Relative Movement Engine

Every ticker should be compared, where possible, against:

* broad market;
* country index;
* sector;
* industry;
* peer group.

Example:

```text
Dangote Sugar:     -5.0%
Consumer Staples:  -0.8%
Peer basket:       -1.1%
Abnormal residual: -3.9%
```

That residual indicates a likely company-specific move rather than a pure market-wide move.

### Industry & Sector Intelligence

Industry state is a first-class radar output, not only a grouping for stock lists.

Example:

```text
NIGERIA — OIL & GAS

Sector return:      -4.8%
Names declining:    7 / 9
Relative volume:    1.7x
Volatility:         elevated
Industry breadth:   weak
Oil price:          -3.1%
NGN/USD:            +0.8%
News intensity:     high

Sector Radar Status: BROAD NEGATIVE EVENT
```

Radar must classify whether a movement is:

* an isolated stock event;
* an industry event;
* a national market event;
* a global macro event.

### Cross-Asset / Alternatives Engine

This is a primary proprietary ambition over time.

Question the engine exists to answer:

```text
If oil and gas falls in Nigeria, what else tends to rise or fall —
and is that showing confirmation today?
```

Call it the **Capital Rotation & Alternatives Engine**. Its job is to discover where capital or relative strength has historically flowed when Asset or Industry A experiences event X — without treating historical association as causal certainty.

Relationship types:

**A. Substitutes**  
Investors or customers may switch into competitors or alternatives when one name weakens.

**B. Sector rotation**  
Capital may leave one sector and enter another. Test empirically; do not assume.

**C. Input–output relationships**  
One industry’s cost is another industry’s revenue.

```text
Oil price ↓ → airline fuel costs improve → airlines may benefit
Oil price ↓ → oil producers lose revenue → energy equities may weaken
```

**D. Supply-chain relationships**  
Shortage or shock at one node can benefit producers and pressure customers (or the reverse).

**E. Macro substitutes**  
Examples: equity stress versus bonds or gold; NGN weakness versus exporters versus import-sensitive companies; rising rates versus banks versus leveraged companies. Again, test empirically.

Every alternatives output must remain research-oriented:

```text
Primary event: Nigeria Oil & Gas -4.8%

Potential beneficiaries:
  1. Consumer sector
  2. Airlines
  3. Selected industrials

Potential negatively exposed:
  1. Energy producers
  2. Oil services
  3. Certain government-revenue-sensitive assets

Historical confidence: Medium
Relationship basis: Economic + historical
Recommended action: Investigate top alternative candidates
```

Wording is **potential beneficiaries**, never **buy these stocks**.

### Relationship Graph

Market Radar should maintain a graph or graph-like structure of economic and statistical relationships.

Examples:

```text
Brent Crude
├── positive exposure → Seplat
├── positive exposure → TotalEnergies Nigeria
├── negative cost exposure → Airlines
├── inflation link → CPI
└── FX / fiscal link → NGN / Nigeria revenues

NVDA
├── competitor → AMD
├── customer relationship → cloud providers
├── supplier ecosystem → TSMC
├── industry → Semiconductors
└── macro sensitivity → rates / AI capex
```

Each relationship edge should carry:

* relationship_type;
* direction;
* strength;
* confidence;
* historical_support;
* time_horizon;
* last_updated.

### Statistical relationship discovery

Some relationships are known economically. Others are learned from data.

Tests may include:

* rolling correlations;
* lead–lag and cross-correlations;
* Granger causality;
* cointegration;
* conditional and regime-specific correlations;
* sector flows;
* relative-return response after shocks.

Example discovery statement:

```text
When Nigerian oil-and-gas equities fall by more than two standard
deviations, banking stocks have outperformed over the following five
sessions 63% of the time.
```

The system must label this as:

```text
Historical association — not causal certainty.
```

Relationships can disappear. Confidence and last-updated fields matter.

### Event-response library

Market Radar should accumulate a library of events and historical responses.

Examples:

```text
EVENT: Brent crude falls > 5%

HISTORICAL RESPONSE (illustrative):
Nigeria Oil & Gas   -3.4%
Airlines            +1.8%
Consumer Staples    +0.7%
USD/NGN             mixed

Measured at 1-day, 5-day and 20-day horizons.
```

```text
EVENT: US CPI exceeds consensus by > 0.3%

Historical reaction:
QQQ   negative
TLT   negative
USD   positive
Banks mixed-positive
Gold  regime-dependent
```

Eventually Radar should be able to say:

```text
This resembles N historical events.
Here is the typical response path.
Here is what is confirming in the live tape today.
```

That is stronger than merely summarising news.

### Event & News Intelligence

News and events should be classified, for example into:

* earnings, guidance;
* M&A;
* management;
* regulation, litigation;
* product;
* financing, dividend, buyback;
* macro, industry, geopolitical;
* analyst rating;
* supply-chain.

Each item should be scored for:

* relevance;
* novelty;
* severity;
* sentiment;
* confidence;
* affected_entities.

A story about one issuer may affect more than that issuer. The relationship graph should propagate impact to competitors, suppliers, services, related ETFs, country peers and linked commodities.

### News propagation

Example:

```text
NEWS: OPEC unexpectedly increases production

Direct:        Brent crude
First-order:   oil producers
Second-order:  oil services, oil-exporting economies
Possible beneficiaries: airlines, transportation, certain manufacturers
```

AI may explain the hierarchy. Market Radar must then test whether observed market data is confirming it.

### Fundamental Change Detector

As data coverage allows, Radar should detect material fundamental or corporate changes relevant to watched and discovered names: filings, earnings surprises, guidance changes, estimate revisions, balance-sheet events and other point-in-time fundamentals that change the research case.

### Macro Context Engine

Radar should place anomalies in macro context using available rates, FX, commodity, inflation, growth and risk proxies. Macro context is an explanation and classification input, not a standalone trade signal.

### Multi-dimensional scoring and priority tiers

Replace a single one-dimensional anomaly score with dimensions such as:

* Anomaly Score;
* Event Score;
* Relative-Move Score;
* Industry Score;
* Relationship / Alternatives Score;
* Watchlist Relevance;
* Portfolio Relevance;
* Liquidity Score.

These feed a final **Radar Priority Score**.

Illustrative scorecard:

```text
Price anomaly            82
Volume anomaly           91
Relative move            76
Event significance       88
Industry breadth         93
Alternative opportunity  71
Portfolio relevance      40
Final priority           84
```

Priority tiers:

```text
P0 — Critical
  Existing-position risk or extraordinary systemic event

P1 — High priority
  Strong anomaly + meaningful event + liquid opportunity

P2 — Research candidate
  Interesting but not urgent

P3 — Background observation
  Worth storing; do not open immediately
```

Tiers keep the interface usable and prevent Opportunity Queue spam.

### Opportunity promotion

When Market Radar pushes something into **Discovered**, it must send an evidence package, not only a ticker.

Example:

```text
Opportunity: GTCO
Discovery:   Market Radar
Priority:    P1

Reasons:
- +3.7σ abnormal return
- 2.4x volume
- banking sector outperforming NGX
- earnings released
- net interest income above expectations

Related observations:
- Zenith also strong
- Access flat
- NGN stable

Potential alternatives:
- Zenith
- UBA

AI summary:
Banking strength appears driven by ...
```

Ticker Analyst then begins with context instead of a blank screen. Radar must also surface whether the fund has already researched the name (prior memo, opportunity or analysis).

### AI Market Narrator

AI belongs in Radar with a controlled job: turn structured signals into concise market narrative. It must not invent facts.

Narrative levels:

* Market summary — what is happening across the whole market;
* Sector summary — what is happening in a sector or industry today;
* Ticker summary — what changed for one name;
* Watchlist summary — anything important on cared-about names;
* Event summary — why a cluster moved;
* Relationship summary — what else could benefit or suffer.

Every summary must separate:

```text
FACTS
  price, volume, filings, news, macro prints

MODEL OUTPUT
  abnormal return, regime, historical relationships, priority score

AI INTERPRETATION
  likely explanation, possible second-order effects
```

This prevents the model from presenting guesses as facts.

Example:

```text
Structured input:
SEPLAT -6.1%, Brent -4.3%, oil sector breadth weak, volume 2.2x,
NGX -0.7%, news: crude demand forecast revised downward

Narrator output:
Nigerian energy stocks are showing broad weakness rather than a
single-name event. Seplat is down 6.1% on more than twice normal
volume while Brent has declined 4.3%. Most tracked energy names are
lower, suggesting sector-wide pressure coincident with weaker crude-
demand expectations. Selected consumer and transportation names show
relative strength and may warrant investigation as potential
beneficiaries of lower energy costs.
```

### Product UI

Market Radar should expose five main surfaces:

**Overview**  
Market state, biggest anomalies, sector heatmap, important events, watchlist alerts, AI market summary.

**Industries**  
Country → sector/industry drill-down (for example Nigeria Banks / Oil & Gas / Consumer / Industrials; US Technology / Financials / Energy / Healthcare). Each industry shows return, breadth, volatility, volume, anomaly count, news intensity, regime and AI summary.

**Discoveries**  
Every flagged security ranked by priority tier and score.

**Relationships**  
Visible edge surface: given a primary event, show historically related beneficiaries and negatively exposed names, plus live confirmation or non-confirmation.

**Watchlist**  
Everything relevant to tracked names: price event, news event, fundamental change, industry change, risk alert, AI summary.

### Historical memory

Market Radar must remember its own calls.

For each observation store:

* what Radar detected;
* what AI said;
* what alternatives were suggested;
* what happened 1, 5 and 20 days later.

Over time measure:

* discovery precision;
* false-positive rate;
* Opportunity Queue conversion;
* alternative-signal accuracy;
* industry-event accuracy;
* AI narrative usefulness.

This is how the edge becomes empirical rather than anecdotal.

### Future ML layer

Only after sufficient labelled memory exists. Then models may predict:

* discovery quality — which anomalies are worth researching;
* rotation probability — given a sector shock, where relative strength is most likely;
* event propagation — which related securities are likely to respond;
* watchlist urgency — which news/event combinations historically mattered;
* opportunity conversion — which discoveries become high-conviction Ticker Analyst candidates.

This is preferred over a generic “stock goes up or down” model.

### Hard boundaries

Market Radar:

* does not authorize trades;
* does not determine position sizes;
* does not present historical associations as causal certainty;
* does not auto-promote low-priority background observations into the Opportunity Queue without evidence and priority controls.

---

# 19. Product features

The eventual Pease Capital application should contain the following major sections.

## Fund Dashboard

* net asset value;
* cash;
* portfolio allocation;
* performance;
* current risk;
* benchmark comparison.

## Ticker Analyst

* complete ticker research;
* model scores;
* valuation;
* risks;
* investment memo.

## Research Lab

* notebooks;
* datasets;
* features;
* experiments;
* backtests;
* model comparison.

## Strategy Pods

* strategy mandate;
* current signals;
* allocation;
* performance;
* drawdown;
* lifecycle status.

## Risk Centre

* portfolio exposures;
* stress tests;
* correlations;
* limits;
* warnings;
* shutdown controls.

## Market Radar

* structured monitored universe with industry-first navigation;
* daily working set of about 100 names;
* multi-dimensional anomaly, event, relative-move and industry scoring;
* priority tiers (P0–P3) and watchlist / position-sensitive thresholds;
* sector and industry state, not only stock lists;
* relationship / alternatives surface with live confirmation;
* news and event intelligence with propagation to related entities;
* AI Market Narrator with facts, model output and interpretation separated;
* evidence-package promotion into the Opportunity Queue;
* historical memory of radar calls and outcomes.

## Opportunity Queue

* screening results;
* watchlist;
* research progress;
* approved candidates.

## Trade Journal

* trades;
* rationales;
* model signals;
* overrides;
* execution quality.

## Reports and Performance Attribution

* daily report;
* weekly review;
* monthly investor letter;
* quarterly strategy report;
* returns by pod;
* returns by ticker;
* returns by factor;
* returns by regime;
* cost analysis.

## Administration

* model versions;
* data versions;
* portfolio rules;
* risk policies;
* system logs.

---

# 20. Initial build scope

The first release should not attempt to implement every future strategy.

## This version must include

1. Fund dashboard
2. Portfolio and cash ledger
3. Market-data ingestion
4. Fundamental-data ingestion
5. Ticker Intelligence System
6. Basic valuation engine
7. Fundamental scoring model
8. Momentum and trend signals
9. HMM market-regime model
10. Central risk dashboard
11. Manual trade journal
12. Backtesting engine
13. Model registry
14. Monthly report generation
15. Human-versus-model decision log
16. Monitored universe and industry-grouped market radar (about 100 names per day), including history-normalised price/volume flags, sector-relative context, “already researched?” surfacing, priority-gated Opportunity Queue promotion with evidence, and watchlist/position-sensitive alerting
17. Licensed multi-vendor market data (Polygon, Tiingo, FMP, NGN Market); Yahoo is not the production quote source

## Market Radar roadmap (after the Phase One radar above)

Build toward section 18.8 without delaying the operating desk:

* richer Universe Manager metadata (peers, substitutes, macro exposures);
* peer-residual Relative Movement Engine;
* first-class Industry & Sector state objects;
* Event & News classification plus propagation;
* Relationship Graph seed (economic + curated edges);
* Capital Rotation & Alternatives suggestions with confidence labels;
* AI Market Narrator with mandatory facts / model / interpretation separation;
* event-response library and historical memory of radar calls;
* multi-dimensional scoring and P0–P3 priority tiers;
* only later: statistical relationship discovery at scale and the ML layer trained on radar memory

## This version strategies

* macro regime allocation;
* cross-asset trend;
* quantitative equity ranking;
* fundamental ticker research.

## This version will not yet include

* automated live execution;
* leveraged strategies;
* complex options;
* high-frequency trading;
* fully automated short selling;
* institutional alternative data;
* external investor administration;
* production unusual-options radar signals;
* treating relationship discoveries as causal trade authority.

---

# 21. Real-Time Data and Market Intelligence

## Objective

Pease Capital's data infrastructure should provide **near-real-time market awareness** without requiring every internal feature to independently poll external vendors.

The previous 10-30 minute model should evolve into a hybrid architecture:

```text
REAL-TIME STREAMS
+
EVENT-DRIVEN PROCESSING
+
SHORT-INTERVAL POLLING
+
SLOW REFERENCE-DATA REFRESH
```

Different information changes at different speeds. Data should be refreshed according to how quickly the underlying information changes, not according to one global scheduler.

This is not high-frequency trading infrastructure. The goal is for Pease Capital to know that something important is happening within seconds or minutes rather than 10-30 minutes later.

## Target latency

```text
US price change -> Pease Capital     < 5 seconds
FX change -> Pease Capital           < 5 seconds
Portfolio value update              5-15 seconds
Watchlist market alert              < 30 seconds
Radar anomaly detection             30-60 seconds
Existing-position risk alert        < 30 seconds
News discovery                      1-2 minutes
Radar AI event summary              1-3 minutes
Ticker Analyst market metrics       < 1 minute old
Macro data                          source-dependent
Fundamentals                        event/daily
```

## Core architecture

```text
                     EXTERNAL DATA
          Tiingo          SEC          NGX Provider
             |             |                |
      WebSocket + REST  Events/API       REST/Stream
             |             |                |
             +-------------+----------------+
                           |
                           v
                    PROVIDER ADAPTERS
                           |
                           v
                     EVENT INGESTION
                           |
             +-------------+-------------+
             v             v             v
          Quotes          News           FX
             |             |             |
             +-------------+-------------+
                           |
                           v
                       EVENT BUS
                           |
        +------------------+------------------+
        v                  v                  v
 Snapshot Store     Feature Engine     Historical Store
        |                  |
        +------------------+------------------+
                           |
                           v
                      FUND SYSTEMS
                           |
        +------------------+------------------+
        v                  v                  v
 Market Radar       Ticker Analyst       Portfolio
        |                  |                  |
        v                  v                  v
 Opportunity         Risk Centre       Performance
 Queue
```

## Tiingo streaming role

Tiingo should become a streaming provider for US market data and FX where the subscribed plan supports it.

Do not poll Tiingo every few minutes for prices. Use Tiingo's WebSocket feeds:

```text
wss://api.tiingo.com/iex
wss://api.tiingo.com/fx
```

For Pease Capital's current use case, a real-time reference-price stream is sufficient for Radar, monitoring and portfolio valuation. The fund is not currently building an execution algorithm requiring full exchange order-book reconstruction.

## Equity streaming strategy

Do not consume every market event from every US-listed security. Subscribe intelligently rather than indiscriminately.

Use subscription tiers:

```text
Tier 0  Existing positions
Tier 1  Active investment candidates
Tier 2  Watchlist
Tier 3  Market Radar universe
```

## Tier 0: Existing positions

Current portfolio holdings are the most important securities in the fund.

Subscribe continuously during the trading session.

Target:

```text
Provider update -> internal snapshot: immediate
Feature refresh: 5-15 seconds
Risk evaluation: 5-15 seconds
```

Changes should immediately update:

* portfolio NAV;
* position P&L;
* exposure;
* portfolio weights;
* stop/thesis conditions;
* Risk Centre.

## Tier 1: Active investment candidates

Includes:

* investment candidates;
* P0/P1 Opportunity Queue names;
* securities currently undergoing deep research.

Stream continuously.

Target:

```text
Market snapshot: real-time
Radar evaluation: 15-30 seconds
Ticker Analyst metrics: <30 seconds old
```

## Tier 2: Watchlist

All explicit watchlist names should be streamed where coverage permits.

Target:

```text
Price monitoring: real-time stream
Feature evaluation: 30 seconds
Material alert: <60 seconds
```

## Tier 3: Market Radar universe

The liquid Radar universe should consume streaming prices, but Radar should not react to every individual tick.

Instead:

```text
WebSocket events
  -> short rolling buffer
  -> 30-60 second aggregation
  -> Radar feature calculation
```

Example:

```text
10:31:00-10:31:59
NVDA: open, high, low, last, volume delta
-> calculate 1-minute observation
```

Market Radar therefore receives new signal information approximately every minute without polling the vendor every minute.

## New Radar cadence

Replace:

```text
Every 30 minutes: scan market
```

with:

```text
CONTINUOUS: receive market events
EVERY 30-60 SECONDS: update Radar features
WHEN SIGNAL THRESHOLD CROSSED: create/update Radar event immediately
```

An abnormal move should not wait until the next scheduler.

## Event-driven Radar

Radar should maintain state for every monitored instrument.

Example:

```text
AAPL
Previous state: return_z = 1.1
New state: return_z = 3.0
Threshold: 2.5
```

When a threshold is crossed:

```text
THRESHOLD CROSS
  -> Radar Event
  -> Priority calculation
  -> Relationship analysis
  -> News lookup
  -> AI summary if material
```

## Radar evaluation frequency

Recommended:

```text
Tier 0 positions       5-15 seconds
Tier 1 opportunities   15-30 seconds
Tier 2 watchlist       30 seconds
Tier 3 liquid universe 60 seconds
```

This does not mean calling Tiingo every 60 seconds. The stream is continuous. The recalculation happens from locally received data.

## Market Radar feature windows

Radar should maintain several windows simultaneously:

```text
1 minute
5 minutes
15 minutes
1 hour
1 day
```

Example:

```text
AAPL
1M abnormal move       1.4 sigma
5M abnormal move       2.8 sigma
15M abnormal move      3.1 sigma
1H abnormal move       2.2 sigma
1D abnormal move       1.7 sigma
```

Radar should distinguish sudden shocks from persistent session trends.

## Volume monitoring

Do not wait for daily volume. Maintain cumulative volume and compare expected volume at that time of day.

Move from:

```text
Current volume / Average daily volume
```

to:

```text
Volume as of 11:15 AM / Historical average volume as of 11:15 AM
```

This gives Radar a better abnormal-volume signal.

## Existing position monitoring

Positions should receive the fastest monitoring in the fund.

Pipeline:

```text
Price Event
  -> Position Snapshot
  -> P&L
  -> Exposure
  -> Risk Limits
  -> Thesis Conditions
```

Target:

```text
5-15 seconds
```

Example:

```text
AAPL
Move: -4.8%
Intraday z-score: -3.1
Volume: 2.7x expected
Existing position: YES
Result: P0 POSITION REVIEW
```

This should immediately surface in:

* Risk Centre;
* Portfolio;
* Market Radar;
* Ticker Desk.

## Portfolio valuation

The portfolio should no longer fetch prices directly. It should consume the current internal market snapshot.

```text
WebSocket
  -> MarketSnapshot
  -> Portfolio valuation
```

Target UI update:

```text
5-15 seconds
```

## FX architecture

FX should also move from polling to WebSockets where provider coverage permits.

Maintain live FX snapshots such as:

```text
USDNGN
EURUSD
GBPUSD
EURNGN
```

Pipeline:

```text
FX stream
  -> FXSnapshot
  -> Portfolio conversion
  -> Risk
  -> Performance
```

Target:

```text
FX snapshot: <5 seconds old
Portfolio recalculation: 5-15 seconds
```

## News monitoring

News is different from prices. Do not needlessly poll every ticker.

Maintain one central news ingestion process.

Target:

```text
every 60-120 seconds
```

Pipeline:

```text
Tiingo News
  -> fetch only articles newer than cursor
  -> deduplicate
  -> entity extraction
  -> map to instruments / sectors
  -> materiality filter
  -> event engine
```

The same article can then affect:

* Market Radar;
* Watchlist;
* Ticker Analyst;
* Position Monitoring;
* Industry Radar.

One fetch. Multiple consumers.

## Watchlist news

Watchlist names receive increased sensitivity.

Example:

```text
News arrives
  -> Entity = AAPL
  -> AAPL is watchlisted
  -> Event importance threshold reduced
```

Target:

```text
News discovered: 1-2 minutes
Watchlist event: <2 minutes
AI summary: <3 minutes
```

## Position news

Current holdings should receive the highest priority.

```text
Article
  -> Current position affected?
  -> YES
  -> Materiality analysis
  -> Risk/thesis alert
```

Target:

```text
1-2 minutes
```

## AI market summaries

AI should not run according to a fixed 30-minute timer. Run AI when something meaningful happens.

Trigger examples:

```text
P0/P1 Radar event
Sector anomaly
Material position news
Watchlist material news
Industry breadth shock
Macro event
Relationship/rotation event
```

Pipeline:

```text
Structured Event
  -> Evidence bundle
  -> AI summary
```

## AI summary latency

For important events:

```text
market event occurs
  -> Radar detects:       <60 sec
  -> evidence collected:  <90 sec
  -> AI summary:          ~1-3 min total
```

## Industry Radar

Sector and industry analysis should recompute approximately every minute using locally stored streamed observations.

Track:

* industry return;
* breadth;
* abnormal return;
* volume;
* volatility;
* number of flagged names;
* relative strength.

Example:

```text
SEMICONDUCTORS

11:32:00
Breadth:     82% positive
Return:      +2.1%
Rel volume:  1.6x
Anomalies:   7

11:33:00
Breadth:     91% positive
Return:      +2.8%
Rel volume:  1.9x
Anomalies:   12
```

## Capital Rotation Engine

The Alternatives/Rotation engine should also become event-driven.

When an industry reaches an anomaly threshold:

```text
Oil & Gas shock detected
  -> query relationship graph
  -> retrieve historical alternatives
  -> check current relative strength
  -> rank potential beneficiaries
```

Target:

```text
within 1-2 minutes of industry event
```

## Ticker Analyst freshness

Ticker Analyst should use multiple freshness classes:

```text
Market data    <60 seconds
News           <2 minutes where possible
Radar context  real-time / latest event
FX             <15 seconds
Fundamentals   event-driven on filings + daily consistency refresh
```

Fundamentals do not require real-time polling.

## Quick Triage

When Ticker Analyst opens a ticker, do not fire five external API calls.

It should already have:

```text
latest market snapshot
latest Radar features
latest industry state
latest news
latest fundamentals
current regime
portfolio position
watchlist status
```

Then Quick Triage becomes effectively instant.

Target:

```text
<1 second internal response
```

Only missing enrichment should trigger external calls.

## Fundamental refresh

Financial statements that have not changed should not consume API capacity every minute.

Use:

```text
SEC filing event -> immediately refresh affected company
Daily -> consistency refresh
```

## SEC filing monitor

For US securities:

```text
Portfolio, opportunities, watchlist: 5 minutes
Broader universe: 15 minutes
```

Or use an event-capable source later.

New filing flow:

```text
detect
  -> ingest
  -> extract differences
  -> Ticker Analyst update
  -> AI filing summary
```

## Macro and regime updates

Market-derived regime inputs update from streams:

* equity prices;
* volatility proxies;
* bonds;
* commodities;
* FX.

Update target:

```text
1 minute
```

Economic releases such as CPI, unemployment and GDP should update when the data is released, not every minute.

## Data priority matrix

| Data | Acquisition | Internal update target |
| --- | --- | ---: |
| Current positions | WebSocket | 5-15 sec |
| Investment candidates | WebSocket | 15-30 sec |
| Watchlist prices | WebSocket | 30 sec |
| Radar universe | WebSocket | 60 sec aggregation |
| Portfolio NAV | Internal | 5-15 sec |
| FX | WebSocket | <5 sec snapshot |
| Sector/industry state | Internal | 60 sec |
| Radar anomaly | Internal | 30-60 sec |
| Rotation signals | Event-driven | 1-2 min |
| News | REST incremental | 1-2 min |
| Watchlist news alerts | Event-driven | 1-2 min |
| AI summaries | Event-driven | 1-3 min |
| Ticker Analyst price | Internal | <60 sec |
| Fundamentals | Event/daily | filing-dependent |
| SEC filings | Incremental | ~5 min priority |
| Instrument metadata | Scheduled | weekly |

## Internal event bus

A real-time fund needs events.

Example events:

```text
PRICE_UPDATED
FX_UPDATED
RADAR_THRESHOLD_CROSSED
RADAR_PRIORITY_CHANGED
SECTOR_ANOMALY_DETECTED
INDUSTRY_ROTATION_DETECTED
NEWS_RECEIVED
MATERIAL_NEWS_DETECTED
FILING_RECEIVED
WATCHLIST_ALERT
POSITION_ALERT
THESIS_RISK_DETECTED
```

Systems subscribe only to the events they care about.

## Example: market event flow

Suppose NVDA begins moving unusually:

```text
10:42:06 Tiingo reference price update
10:42:10 Internal MarketSnapshot updated
10:42:30 1-minute Radar features recalculated
          Return z-score: 2.9
          Relative volume: 2.2x
          Sector residual: +3.1%
10:42:31 RADAR_THRESHOLD_CROSSED
```

Immediately:

```text
Radar Priority Engine
Industry Engine
Relationship Engine
News Lookup
```

By approximately 10:43-10:44, the system could produce an enriched explanation:

```text
NVDA has broken significantly above semiconductor peers on elevated volume.
The movement appears company-specific rather than simply sector-wide.
Two related semiconductor names are beginning to show sympathetic strength.
Relevant news...
```

## Example: portfolio risk event

```text
AAPL held by fund
14:06:04 price update
14:06:12 portfolio weight recalculated
14:06:15 position volatility threshold crossed
```

Result:

```text
POSITION_ALERT
AAPL P0
Reason: Intraday move exceeds risk threshold
Volume unusually high
Position contributes 22% of current portfolio VaR
```

## Stream processing rules

Do not recalculate every expensive model on every tick.

Use a hierarchy:

```text
EVERY PRICE UPDATE
  -> update raw snapshot

EVERY 5-15 SEC
  -> portfolio/risk lightweight calculations

EVERY 30-60 SEC
  -> Radar features

WHEN THRESHOLD CROSSED
  -> deeper analysis

WHEN MATERIAL EVENT OCCURS
  -> AI / Ticker Analyst / relationship models
```

This gives speed without waste.

## Model recalculation

Models also have different speeds.

Very fast:

```text
returns
volume
momentum
volatility
relative strength
sector residual
```

Recalculate every 30-60 seconds.

Medium:

```text
regime probabilities
portfolio correlations
short-horizon ML signals
```

Recalculate every 5-15 minutes or on material state change.

Slow:

```text
fundamental model
valuation
long-horizon ML
```

Recalculate daily or when underlying data changes.

## Data latency versus model latency

Pease Capital wants data near real-time, but it does not need DCF valuation every second.

A ticker can have a new price every second while its fundamental valuation updates only after:

* earnings;
* guidance;
* a material event;
* a meaningful price threshold.

## Tiingo bandwidth protection

WebSockets reduce REST request pressure, but streaming a full firehose can generate substantial bandwidth.

Use:

```text
Positions
Candidates
Watchlist
Liquid Radar universe
```

Do not subscribe to every available US security.

## Tiingo reference price

Tiingo can provide a real-time derived equity reference price through its IEX WebSocket using `thresholdLevel 6`, subject to the subscribed plan and Tiingo's current product terms.

This is well suited for Pease Capital's current needs:

* fresh reference prices;
* movement detection;
* portfolio valuation;
* anomaly signals.

The fund does not currently require a complete exchange-level order book. If full IEX TOPS data is later required, exchange licensing requirements should be reviewed at that time.

## Nigeria

Nigeria should maintain the current provider structure until the upgraded NGX-capable plan is available.

The rest of Pease Capital should not care whether the update came from:

```text
WebSocket
```

or:

```text
REST poll
```

Both should normalize into the same internal `MarketSnapshot`.

## Failure strategy

If a stream disconnects:

```text
WebSocket disconnected
  -> mark provider degraded
  -> attempt reconnect
  -> temporarily use REST
  -> restore stream
```

The application should never silently serve indefinitely stale data.

Display:

```text
Market feed: DEGRADED
Last valid update: 46 seconds ago
```

## Freshness metadata

Every snapshot must expose:

```text
provider_timestamp
received_at
processed_at
age_seconds
source
stream_status
```

Example:

```text
AAPL Price: $XXX
Source: Tiingo IEX Reference
Market timestamp: 15:32:05.218
Received: 15:32:05.401
Age: 2.1 sec
```

## Data Health Dashboard

Add a small internal system dashboard.

Example:

```text
PEASE CAPITAL DATA STATUS
US Equities LIVE   Latency: 1.4 sec
FX LIVE            Latency: 0.8 sec
News LIVE          Last poll: 42 sec ago
NGX LIVE           Last update: 74 sec ago
SEC HEALTHY        Last check: 3 min ago
```

This becomes important once the portfolio depends on automation.

## Revised Market Radar architecture

Market Radar should become:

```text
                 MARKET RADAR
                     STREAM
                       |
                       v
               Live Market State
                       |
                       v
              1-Minute Features
                       |
         +-------------+-------------+
         v             v             v
   Security       Industry       Cross-Asset
   Anomalies      Anomalies      Relationships
         |             |             |
         +-------------+-------------+
                       |
                       v
                Priority Engine
                       |
              threshold crossed?
                       |
                      YES
                       |
                       v
              Evidence Enrichment
                       |
              +--------+--------+
              v                 v
            News          Relationships
              |                 |
              +--------+--------+
                       |
                       v
                  AI Summary
                       |
                       v
              Opportunity Candidate
```

## Revised timing philosophy

Pease Capital should no longer think:

```text
Run every X minutes.
```

It should think:

```text
Listen continuously.
Aggregate intelligently.
React when state changes.
```

Desired operating model:

```text
Prices       seconds
FX           seconds
Portfolio    seconds
Risk         seconds
Radar        <1 minute
News         1-2 minutes
AI           event-driven, ~1-3 minutes
Ticker Desk  near-current
Fundamental  when reality changes
```

## Immediate implementation priority

Phase 1: Streaming foundation

1. Tiingo equity WebSocket client
2. Tiingo FX WebSocket client
3. Reconnect / heartbeat handling
4. Ticker subscription management
5. Normalized `MarketSnapshot`
6. Normalized `FXSnapshot`
7. Local current-state cache

Phase 2: Real-time consumers

8. Portfolio consumes live snapshots
9. Risk Centre consumes live snapshots
10. Watchlist consumes live snapshots
11. Ticker Desk consumes snapshots

Phase 3: Real-time Radar

12. Rolling 1-minute bar builder
13. Rolling feature engine
14. Threshold detection
15. Event bus
16. Sector/industry aggregation
17. Radar priority recalculation

Phase 4: Intelligence

18. News polling every 60-120 seconds
19. News deduplication
20. Event materiality
21. Relationship engine triggers
22. Alternatives / rotation engine
23. AI evidence summaries

Phase 5: Reliability

24. Fallback REST mode
25. Provider-health tracking
26. Latency metrics
27. Stale-data detection
28. Usage/bandwidth monitoring
29. Data-health dashboard

## Final target

The new data infrastructure should create this experience:

> If something material begins happening to a security, industry, watchlist name, portfolio position, FX rate or related market, Pease Capital should generally become aware of the market movement within seconds, classify it within roughly a minute, and produce enriched intelligence within a few minutes.

This replaces:

```text
10-30 MINUTE POLLING SYSTEM
```

with:

```text
CONTINUOUS DATA
+
~1 MINUTE MARKET INTELLIGENCE
+
EVENT-DRIVEN RESEARCH
```

That is much closer to the architecture appropriate for Market Radar, Ticker Analyst, Risk Centre and the portfolio system.

---

# 22. Definition of success

The fund’s first year will be considered successful when:

* all decisions are documented;
* all live strategies were tested first;
* no risk rule was ignored without a recorded exception;
* the portfolio avoided catastrophic loss;
* model outputs are reproducible;
* actual costs are measured;
* live results are compared with backtests;
* each strategy’s contribution is known;
* the fund can produce an institutional-quality track record;
* the technology can support a larger capital base without being redesigned completely.

The objective is not merely to grow $1,000.

The objective is to build an investment institution whose first capital base happens to be $1,000.

---

# 23. Final operating model

Pease Capital will be:

> A technology-driven, multi-strategy hedge fund that combines systematic macro analysis, quantitative equity research, trend following, fundamental security analysis and centralized risk management.

Its defining structure will be:

```text
D. E. Shaw-style research
+
Millennium-style strategy pods
+
Citadel-style centralized risk
+
Bridgewater-style regime analysis
+
TCI-style fundamental conviction
+
Pease Capital’s ticker intelligence and model-accountability system
```

The fund will pursue ambition through research depth, system quality and disciplined capital allocation—not through uncontrolled leverage or unnecessary risk.
