# Razorpay AI Finance Controller

> **Razorpay Buildathon — Track 4 (AI Finance Controller)**
> Multi-source reconciliation, settlement Q&A, cash flow forecasting, and GST line matching with measured accuracy and an honest exception list.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Deployed on Streamlit](https://img.shields.io/badge/Streamlit-Live-FF4B4B.svg)](https://streamlit.io/)

## What it does

Close the finance-ops loop for an Indian merchant running on Razorpay:

| Module | What it answers |
|---|---|
| **Multi-source reconciliation** | Did every Razorpay settlement hit the bank? Did every OMS order get paid? Are GST invoices aligned with payments? |
| **Settlement Q&A agent** | "Why is settlement `pay_S30006` short by ₹87?" — cited source rows + math |
| **Forward cash forecaster** | 13-week projection of opening → closing balance with low-balance alert |
| **GST line matcher** | 6-dimension match (GSTIN, invoice no, date, taxable value, tax breakup, HSN) → ITC claimed vs eligible |
| **Exception classifier** | 10 categories with reason + suggested action — every residual honestly labelled |

## The bar we hit

- **Throughput** — every record measured in ms
- **Measured accuracy** — match rate, precision, recall, F1, LLM call %
- **Honest exception list** — no cherry-picking, every exception has a category, a reason, and a next action

## Architecture

```
                    ┌────────────────────────────────────┐
                    │   Streamlit Cloud (Public URL)     │
                    │   Chat UI + Dashboard + Charts     │
                    └──────────────┬─────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │   LangChain Agent (Groq/Gemini)    │
                    │   5 tools: reconcile, Q&A,         │
                    │   forecast, GST match, query       │
                    └──────┬──────────────┬──────────────┘
                           │              │
              ┌────────────▼─┐      ┌─────▼──────────┐
              │  pandas +    │      │  pdfplumber +  │
              │  rapidfuzz   │      │  PyMuPDF       │
              │  (Tier 1+2)  │      │  (PDF ingest)  │
              └──────┬───────┘      └────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
   ┌────▼───┐  ┌─────▼─────┐  ┌───▼────────────┐
   │ Chroma │  │  SQLite   │  │  Synthetic     │
   │ (RAG)  │  │  Ledger   │  │  Data (Faker)  │
   └────────┘  └───────────┘  └────────────────┘
```

### Tier 1+2+3 funnel (LLM never touches money directly)

- **Tier 1 — Deterministic pandas**: exact `payment_id` / UTR / invoice_no match (~85%)
- **Tier 2 — Fuzzy + tolerance**: `rapidfuzz` + amount-tolerance (₹0.05) + date-window (±2 days) (~+7%)
- **Tier 3 — LLM**: only on residue, with **confidence gate ≥ 0.7** (~+4%)
- **Below 0.7 → exception list with category + reason + action**

## Quick start

```bash
# 1. Clone
git clone https://github.com/AdityaST93/razorpay-finance-controller.git
cd razorpay-finance-controller

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Add your OPENROUTER_API_KEY (free at https://openrouter.ai/keys)

# 4. Generate synthetic data
python data/generate.py

# 5. Run reconciliation
python core/reconcile.py

# 6. Launch UI
streamlit run app.py
```

## Repository structure

```
razorpay-finance-controller/
├── app.py                       # Streamlit entry
├── requirements.txt
├── .env.example                 # OPENROUTER_API_KEY template
├── .gitignore
├── data/
│   ├── generate.py              # Faker-based 4-source generator
│   └── synthetic/               # Generated CSVs
├── core/
│   ├── ingest.py                # CSV + PDF parsing
│   ├── reconcile.py             # 4-way match engine
│   ├── exceptions.py            # 10-category classifier
│   ├── forecast.py              # 13-week cash projection
│   ├── tax_match.py             # GST 6-dim match
│   └── agent.py                 # LangChain tools + agent
├── ui/
│   ├── chat.py                  # Q&A interface
│   ├── dashboard.py             # Metrics + charts
│   └── audit.py                 # Per-record trace
├── tests/
│   └── test_metrics.py          # Precision/recall assertions
└── docs/
    ├── architecture.png
    └── exception_taxonomy.md
```

## Results

| Metric | Target | Achieved |
|---|---|---|
| **Match rate** (main set) | 85-92% | **85%** (51/60 payments clean) |
| **Exceptions** | Honest list | **11 across 8 categories** |
| **GST match rate** | > 90% | **96.6%** (57/58 invoices) |
| **Holdout precision** | > 90% | **Verified** (separate seed=2026 test set) |
| **Holdout recall** | > 85% | **Verified** (55 broken records, 9 categories) |
| **Forecast horizon** | 13 weeks | ✅ 13 weeks |
| **Test coverage** | 100% | **33/33 passing** |
| **LLM agent** | Cited answers | ✅ Real data + source rows + math |
| **Throughput** | < 5s | ~1s for 60 payments |

## Why this wins

1. **Razorpay-specific** — UPI, GST, T+2 settlement, MDR fee math, Indian context
2. **Decimal-safe** — `decimal.Decimal` throughout (no float drift on money)
3. **Tier 1+2+3 funnel** — LLM is the residue, not the workhorse
4. **Honest adversarial holdout** — precision/recall on unseen set, not cherry-picked
5. **Cited Q&A** — every answer cites source rows and shows the math
6. **Per-record audit trail** — drill down to why any decision was made
7. **Live deployed** — public URL, no slides

## License

MIT — see [LICENSE](LICENSE).

## Contact

Built by **Aditya Singh Thakur** for the Razorpay AI Buildathon, Track 4.
