TRACK_ID=PS03

# StockSage AI

> Know What Sells. Predict What’s Next.

An AI-powered Sales and Inventory Decision Copilot for small retail businesses.

StockSage AI transforms sales and inventory data into prioritized, evidence-backed business decisions. It helps managers understand:
- What needs attention?
- Why does it matter?
- What action should be considered?
- What evidence supports the recommendation?

## PROBLEM STATEMENT

Small retailers may have sales and stock data but still struggle to quickly identify:
- products likely to run out
- excess inventory
- slow/non-moving products
- unusual sales spikes
- unusual sales drops
- high-priority business issues
- emerging sales opportunities

Managers should be able to ask natural-language questions and receive answers based on actual data. The system must avoid guessing when available data cannot answer a question.

## OUR SOLUTION

StockSage AI combines:
- deterministic Python analytics
- SQLite retail data
- inventory risk detection
- sales anomaly detection
- priority scoring
- business impact estimation
- evidence-backed recommendations
- Gemini natural-language interaction
- deterministic what-if simulation
- opportunity detection
- basket intelligence where sufficient transaction evidence exists
- decision audit trail

Gemini handles language interaction. Python analytics and SQLite remain the source of numerical truth. Gemini does not calculate or invent the business metrics.

## KEY FEATURES

1. **Retail Command Dashboard**
   - latest sales overview
   - products at risk
   - slow/non-moving inventory
   - sales anomalies
   - estimated revenue at risk
   - What Needs Attention Today
   - sales trend
   - top products
   - inventory health

2. **Inventory Intelligence**
   - stock-out risk
   - excess inventory / overstock
   - slow-moving products
   - non-moving products
   - days remaining
   - priority score
   - evidence inspection
   - store/category filtering where implemented

3. **Sales Intelligence**
   - sales spike detection
   - sales drop detection
   - baseline comparison
   - growth/opportunity signals
   - high performers
   - demand growth with low-stock opportunities

4. **StockSage Priority Score**
   - deterministic 0–100 prioritization
   - combines relevant risk/severity/impact/urgency/confidence signals according to the actual implementation
   - helps managers focus on important issues first

5. **Business Impact Estimation**
   - Estimated Revenue at Risk for stock-out situations
   - Retail Value of slow/non-moving or excess inventory where applicable
   - Sales Value Gap vs Baseline for drops where applicable
   - Incremental Sales Value for spikes where applicable
   *(Note: These are estimates. We do not use "capital locked", "cash locked", or claim actual financial loss.)*

6. **Evidence-Backed AI Copilot**
   - natural-language retail questions
   - deterministic analytics first
   - verified results passed to Gemini for language generation
   - evidence-backed responses
   - recommendations grounded in local retail data

7. **Grounding and Safe Failure**
   - refuses unsupported profit/margin questions when cost data is absent
   - does not invent missing values
   - handles unknown/ambiguous products
   - blocks unsupported arbitrary SQL behavior
   - avoids unsupported causal claims
   - handles Gemini/API failure gracefully

8. **What-If Simulator**
   - deterministic scenario simulation
   - demand velocity adjustment
   - stock adjustment
   - recalculated stock coverage
   - recalculated risk
   - estimated revenue-at-risk comparison where available
   *(Note: What-If scenarios are simulations, not forecasts.)*

9. **Opportunity Intelligence**
   - high-performing products
   - sustained/demand growth signals where implemented
   - low-stock + growing-demand opportunities
   - cross-sell/basket opportunities where sufficient evidence exists

10. **Decision Audit Trail**
    - recommendations
    - manager actions (Accept, Dismiss, Review)
    - history stored using SQLite

## APPLICATION PAGES

1. **Dashboard**: High-level overview of sales trends, inventory health, and key priorities.
2. **AI Copilot**: Natural-language conversational interface grounded in retail data.
3. **Inventory Intelligence**: Detailed breakdown of stock-out risks, excess stock, and slow-moving items.
4. **Sales Intelligence**: Detection of anomalies like sales spikes and drops compared to baseline.
5. **What-If Simulator**: Tool to simulate changes in demand velocity or stock levels to assess risk.
6. **Decision History**: Audit trail of manager decisions on AI recommendations.

## SYSTEM ARCHITECTURE

Retail Sales + Inventory Data
          |
          v
      SQLite Database
          |
          v
Deterministic Python Analytics
          |
          +------------------------------+
          |                              |
          v                              v
Inventory Risk Engine             Sales Analysis
Anomaly Detection                 Opportunity Analysis
Priority Scoring                  Basket Analysis
Impact Estimation
          |
          v
Evidence + Verified Metrics
          |
          v
Grounding / Query Routing
          |
          v
Gemini Natural-Language Layer
          |
          v
Evidence-Backed Manager Response

## DECISION PIPELINE

Data → Detect Issue → Measure Risk → Rank Priority → Estimate Business Impact → Generate Evidence → Recommend Action → Simulate What-If Scenario → Record Manager Decision

## TECHNOLOGY STACK

Frontend:
- HTML
- CSS
- JavaScript

Backend:
- Python
- Flask

Database:
- SQLite

Analytics:
- Pandas
- NumPy

Generative AI:
- Google Gemini API

Testing:
- pytest

Version Control:
- Git
- GitHub

## DATASET

This repository uses a generated synthetic retail dataset for hackathon demonstration and testing.
Characteristics include:
- 3 stores
- approximately 60 products
- multiple retail categories
- approximately 120 days of sales history
- thousands of sales records
- inventory data
- deliberately represented business situations such as stock-out risks, overstock, non-moving/slow-moving products, and sales anomalies

Key files:
- `data/stocksage.db`
- `data/products.csv`
- `data/stores.csv`
- `data/sales.csv`
- `data/inventory.csv`

## CORE ANALYTICS

- **Average Daily Sales (ADS)** = Units Sold During Window / Calendar Days in Window
- **Days Remaining** = Current Stock / Average Daily Sales
- **Stock-out risk** is classified based on days remaining according to the actual implementation.
- For **what-if simulation**: Adjusted ADS = Baseline ADS × (1 + Demand Change %), and stock adjustment is applied deterministically. Scenario ≠ Forecast.

## GEMINI INTEGRATION & GROUNDING

User Question → Intent Interpretation / Routing → Supported Intent Validation → Deterministic Analytics → Verified Evidence → Gemini Language Generation → Grounded Response

Gemini is NOT the source of numerical truth. Numerical results come from deterministic local analytics over SQLite data. If data is insufficient, StockSage explains what information is missing instead of guessing.
For example, if asked "What profit did we make?", since product cost/margin data is absent, StockSage explicitly states it cannot calculate profit.

## LOCAL SETUP AND RUN INSTRUCTIONS

Requires Python 3.11 compatible.
From the repository root:

1. Clone repository
2. Create/activate virtual environment if desired
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure Gemini API key via environment variable:
   - MacOS/Linux: `export GEMINI_API_KEY="your-key-here"`
   - Windows: `set GEMINI_API_KEY="your-key-here"`
5. Run:
   ```bash
   python app.py
   ```
6. Open: http://localhost:8000

## GEMINI API KEY SAFETY

- `GEMINI_API_KEY` is read from the environment.
- `.env` is excluded by `.gitignore`.
- Real API keys must never be committed. No real key should appear anywhere in README/source/history.

## TESTING

Run tests using:
```bash
python -m pytest
```
Current validated result before Phase 13: 203 passed.
Coverage includes stock-out detection, overstock logic, slow/non-moving detection, anomaly detection, entity resolution, grounding, unsupported questions, Gemini failure handling, what-if simulation, basket intelligence, opportunity detection, and audit trail.

## RESPONSIBLE AI / DESIGN PRINCIPLES

- Deterministic numbers before generated language
- Evidence-backed recommendations
- Explicit assumptions
- No fabricated missing values
- Cautious root-cause language
- Scenario simulation is not prediction
- Human manager remains the decision-maker

## LIMITATIONS

- Synthetic hackathon dataset
- No cost/margin data, so actual profit cannot be calculated
- What-if module is scenario simulation, not forecasting
- Recommendations depend on available sales/inventory history
- Gemini requires a valid GEMINI_API_KEY for natural-language generation
- Basket relationships require sufficient co-purchase evidence
- No claim of proven causality from correlation alone

## Demo Video

Demo link:
https://youtu.be/CHTUnU3EZD0

## REPOSITORY STRUCTURE

- `app.py`
- `README.md`
- `requirements.txt`
- `data/`
- `src/`
- `static/`
- `templates/`
- `tests/`
