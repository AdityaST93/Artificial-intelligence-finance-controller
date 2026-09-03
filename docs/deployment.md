# Deployment Guide — Streamlit Community Cloud

## Prerequisites
- GitHub account (you have one — AdityaST93)
- This repo: `https://github.com/AdityaST93/razorpay-finance-controller`
- OpenRouter API key (free at https://openrouter.ai/keys)

## Steps

### 1. Sign in to Streamlit Cloud
Go to https://share.streamlit.io and sign in with GitHub.

### 2. Click "New app"
- **Repository:** `AdityaST93/razorpay-finance-controller`
- **Branch:** `main`
- **Main file path:** `app.py`
- **App URL:** pick a memorable name (e.g. `razorpay-finance-controller`)

### 3. Add secrets (Advanced settings → Secrets)
Paste the following in TOML format:

```toml
OPENROUTER_API_KEY = "sk-or-v1-YOUR-ACTUAL-KEY"
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
```

> ⚠️ Use the **Secrets** UI, not a `.env` file in the repo. Streamlit Cloud reads secrets from a secure store.

### 4. Click "Deploy"
- First build takes 2-3 minutes (pip install)
- Watch the logs for errors
- App goes live at `https://<your-app-name>.streamlit.app`

### 5. Verify
- Click "Run Reconciliation" in the sidebar
- Should see ~91.67% match rate, 7 exceptions
- Forecast chart should render
- GST tab should show 1 mismatch, 2 missing invoices
- Q&A tab: try "Why is pay_S30006 short?"

## Troubleshooting

| Error | Fix |
|---|---|
| `ModuleNotFoundError: core` | Make sure `core/__init__.py` exists |
| `No OPENROUTER_API_KEY` | App still works — falls back to deterministic answers |
| `Faker seed not reset` | Tests are deterministic; rerun `python data/generate.py` |
| `Plotly chart blank` | Clear Streamlit cache via the "Clear cache" button |

## Custom domain (optional)
Streamlit Cloud supports custom domains on paid plans. For a hackathon submission, the default `*.streamlit.app` URL is fine.

## Cost
- **Streamlit Cloud:** Free for public apps
- **OpenRouter free tier:** 20 RPM, 1K req/day, multi-model
- **No credit card required**
