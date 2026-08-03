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

## 8.2 Required analysis modules

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

## 8.3 Standard ticker memo

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

## 8.4 Example output

```text
Ticker:                  XYZ
Classification:          Buy candidate
Time horizon:            6–12 months
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

## Performance Attribution

* returns by pod;
* returns by ticker;
* returns by factor;
* returns by regime;
* cost analysis.

## Reports

* daily report;
* weekly review;
* monthly investor letter;
* quarterly strategy report.

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
* external investor administration.

---

# 21. Definition of success

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

# 22. Final operating model

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
