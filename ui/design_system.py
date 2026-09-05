"""
Razorpay-inspired production design system for Streamlit.

Public surface:
  - PALETTE             : color dict (navy/blue/cyan/green + supporting tokens)
  - PLOTLY_THEME        : Plotly figure theme (applied by style_plotly)
  - CUSTOM_CSS          : full stylesheet as a Python string
  - kpi_card(...)       : HTML string for a glassmorphic KPI card
  - hero(...)           : None (renders hero banner via st.markdown)
  - footer(...)         : None (renders footer via st.markdown)
  - style_plotly(fig)   : None (applies theme to a Plotly figure)
  - section_header(...) : None (renders a section header with gradient title)

All HTML rendering uses st.markdown(..., unsafe_allow_html=True).
"""

from __future__ import annotations

import streamlit as st

# ============================================================================
# Palette
# ============================================================================

PALETTE: dict[str, str] = {
    # Brand
    "navy":         "#0a2540",
    "navy_2":       "#0e3a66",
    "blue":         "#3395ff",
    "cyan":         "#00d4ff",
    "green":        "#10b981",
    # Supporting
    "amber":        "#f59e0b",
    "red":          "#ef4444",
    "purple":       "#8b5cf6",
    "pink":         "#ec4899",
    "teal":         "#06b6d4",
    "lime":         "#84cc16",
    "orange":       "#f97316",
    # Slates (neutral)
    "slate_900":    "#0f172a",
    "slate_700":    "#334155",
    "slate_500":    "#64748b",
    "slate_400":    "#94a3b8",
    "slate_300":    "#cbd5e1",
    "slate_200":    "#e2e8f0",
    "slate_100":    "#f1f5f9",
    "slate_50":     "#f8fafc",
    "white":        "#ffffff",
    "black":        "#000000",
    # Glass tokens
    "glass":        "rgba(255, 255, 255, 0.55)",
    "glass_border": "rgba(255, 255, 255, 0.65)",
    "glass_dark":   "rgba(10, 37, 64, 0.45)",
}

# Plotly theme tokens
PLOTLY_THEME: dict = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor":  "rgba(0,0,0,0)",
    "font":          {"family": "Inter, system-ui, sans-serif", "color": "#0f172a"},
    "colorway": [
        PALETTE["blue"], PALETTE["cyan"], PALETTE["green"],
        PALETTE["amber"], PALETTE["red"], PALETTE["purple"],
        PALETTE["pink"],
    ],
    "margin": {"l": 24, "r": 24, "t": 48, "b": 24},
}

# ============================================================================
# Full stylesheet
# ============================================================================

CUSTOM_CSS: str = r"""
<style>
  /* =========================================================================
     Razorpay-inspired Design System
     ========================================================================= */

  /* ---------- 1. Root + tokens ---------- */
  :root {
    --rp-navy:        #0a2540;
    --rp-navy-2:      #0e3a66;
    --rp-blue:        #3395ff;
    --rp-cyan:        #00d4ff;
    --rp-green:       #10b981;
    --rp-amber:       #f59e0b;
    --rp-red:         #ef4444;
    --rp-purple:      #8b5cf6;
    --rp-pink:        #ec4899;

    --rp-slate-900:   #0f172a;
    --rp-slate-700:   #334155;
    --rp-slate-500:   #64748b;
    --rp-slate-400:   #94a3b8;
    --rp-slate-300:   #cbd5e1;
    --rp-slate-200:   #e2e8f0;
    --rp-slate-100:   #f1f5f9;
    --rp-slate-50:    #f8fafc;

    --rp-glass:        rgba(255, 255, 255, 0.55);
    --rp-glass-strong: rgba(255, 255, 255, 0.72);
    --rp-glass-border: rgba(255, 255, 255, 0.65);
    --rp-glass-shadow: 0 8px 32px 0 rgba(10, 37, 64, 0.10);

    --rp-shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.06);
    --rp-shadow:    0 4px 12px rgba(15, 23, 42, 0.08);
    --rp-shadow-lg: 0 20px 60px -20px rgba(10, 37, 64, 0.35);

    --rp-radius-sm: 8px;
    --rp-radius:    12px;
    --rp-radius-lg: 18px;
    --rp-radius-xl: 22px;

    --rp-ease: cubic-bezier(0.4, 0, 0.2, 1);
  }

  /* ---------- 2. Fonts (Inter + JetBrains Mono) ---------- */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

  html, body, [data-testid="stAppViewContainer"] {
    font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif !important;
    color: var(--rp-slate-900);
    background:
      radial-gradient(1200px 600px at 100% 0%,  rgba(51, 149, 255, 0.10), transparent 60%),
      radial-gradient(1000px 500px at 0% 100%,  rgba(0, 212, 255, 0.08),  transparent 60%),
      linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%) !important;
    background-attachment: fixed !important;
  }

  /* Force numeric / code into JetBrains Mono */
  code, kbd, samp, pre,
  .rp-mono, .rp-kpi .value, .rp-hero-metric .v,
  [data-testid="stMetricValue"], [data-testid="stCodeBlock"] {
    font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace !important;
    font-variant-numeric: tabular-nums;
  }

  /* Hide Streamlit chrome */
  #MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }
  [data-testid="stDecoration"] { display: none; }

  /* Ensure the sidebar collapse/expand arrow always stays visible + on top */
  [data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999999 !important;
    position: relative !important;
  }
  header[data-testid="stHeader"] {
    visibility: visible !important;
    z-index: 999998 !important;
  }

  /* ---------- 3. Custom scrollbar ---------- */
  *::-webkit-scrollbar { width: 10px; height: 10px; }
  *::-webkit-scrollbar-track {
    background: rgba(15, 23, 42, 0.04);
    border-radius: 999px;
  }
  *::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--rp-blue) 0%, var(--rp-cyan) 100%);
    border-radius: 999px;
    border: 2px solid transparent;
    background-clip: padding-box;
  }
  *::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(180deg, var(--rp-navy) 0%, var(--rp-blue) 100%);
    background-clip: padding-box;
  }
  * { scrollbar-color: var(--rp-blue) rgba(15, 23, 42, 0.04); scrollbar-width: thin; }

  /* ---------- 4. Animated gradient hero + SVG mesh ---------- */
  .rp-hero {
    position: relative;
    overflow: hidden;
    border-radius: var(--rp-radius-xl);
    padding: 2.6rem 2.8rem 2.8rem 2.8rem;
    margin-bottom: 1.4rem;
    color: #fff;
    background:
      radial-gradient(1200px 400px at 80% 0%,  rgba(51, 149, 255, 0.35), transparent 60%),
      radial-gradient(900px  300px at 0%  100%, rgba(0, 212, 255, 0.25),  transparent 60%),
      linear-gradient(135deg, #0a2540 0%, #0e3a66 50%, #0a2540 100%);
    background-size: 200% 200%;
    animation: rp-hero-shift 18s ease-in-out infinite;
    box-shadow: var(--rp-shadow-lg);
    isolation: isolate;
  }
  @keyframes rp-hero-shift {
    0%   { background-position:   0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position:   0% 50%; }
  }
  .rp-hero::before {
    /* SVG mesh background */
    content: "";
    position: absolute; inset: 0;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 400' preserveAspectRatio='none'><defs><radialGradient id='g1' cx='20%25' cy='20%25' r='40%25'><stop offset='0%25' stop-color='%233395ff' stop-opacity='0.25'/><stop offset='100%25' stop-color='%233395ff' stop-opacity='0'/></radialGradient><radialGradient id='g2' cx='80%25' cy='60%25' r='50%25'><stop offset='0%25' stop-color='%2300d4ff' stop-opacity='0.20'/><stop offset='100%25' stop-color='%2300d4ff' stop-opacity='0'/></radialGradient><radialGradient id='g3' cx='50%25' cy='100%25' r='50%25'><stop offset='0%25' stop-color='%238b5cf6' stop-opacity='0.15'/><stop offset='100%25' stop-color='%238b5cf6' stop-opacity='0'/></radialGradient><pattern id='grid' width='40' height='40' patternUnits='userSpaceOnUse'><path d='M 40 0 L 0 0 0 40' fill='none' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='1'/></pattern></defs><rect width='800' height='400' fill='url(%23grid)'/><rect width='800' height='400' fill='url(%23g1)'/><rect width='800' height='400' fill='url(%23g2)'/><rect width='800' height='400' fill='url(%23g3)'/></svg>");
    background-size: cover;
    background-position: center;
    pointer-events: none;
    z-index: 0;
    opacity: 0.9;
  }
  .rp-hero::after {
    /* Subtle dot pattern overlay */
    content: "";
    position: absolute; inset: 0;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='60' height='60' viewBox='0 0 60 60'><circle cx='1' cy='1' r='1' fill='%23ffffff' fill-opacity='0.06'/></svg>");
    pointer-events: none;
    z-index: 0;
  }
  .rp-hero > * { position: relative; z-index: 1; }

  .rp-hero h1 {
    font-size: 2.25rem;
    font-weight: 800;
    margin: 0 0 .4rem 0;
    background: linear-gradient(90deg, #ffffff 0%, #00d4ff 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
            color: transparent;
    letter-spacing: -0.025em;
    line-height: 1.15;
  }
  .rp-hero p {
    color: rgba(255, 255, 255, 0.82);
    margin: 0;
    font-size: 1.02rem;
    line-height: 1.55;
    max-width: 70ch;
  }
  .rp-chip {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.22);
    color: #cbd5e1;
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.85rem;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
  }
  .rp-hero-metric {
    display: inline-block;
    padding: 10px 18px;
    margin: 12px 8px 0 0;
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 12px;
    color: #fff;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    transition: transform .18s var(--rp-ease), background .18s var(--rp-ease);
  }
  .rp-hero-metric:hover {
    transform: translateY(-2px);
    background: rgba(255, 255, 255, 0.16);
  }
  .rp-hero-metric .v {
    font-size: 1.4rem;
    font-weight: 800;
    color: #00d4ff;
    line-height: 1.1;
    font-family: "JetBrains Mono", ui-monospace, monospace;
  }
  .rp-hero-metric .l {
    font-size: 0.7rem;
    color: #cbd5e1;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
    margin-top: 2px;
  }

  /* ---------- 5. Glass cards ---------- */
  .rp-glass {
    background: var(--rp-glass);
    border: 1px solid var(--rp-glass-border);
    border-radius: var(--rp-radius-lg);
    backdrop-filter: blur(18px) saturate(140%);
    -webkit-backdrop-filter: blur(18px) saturate(140%);
    box-shadow: var(--rp-glass-shadow);
    padding: 1.2rem 1.3rem;
  }

  /* ---------- 6. Section header ---------- */
  .rp-section-header { margin: 1.2rem 0 0.8rem 0; }
  .rp-section-header h2 {
    margin: 0 0 .2rem 0 !important;
    font-size: 1.35rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em;
    background: linear-gradient(90deg, var(--rp-navy) 0%, var(--rp-blue) 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
            color: transparent;
  }
  .rp-section-header .sub {
    color: var(--rp-slate-500);
    font-size: 0.92rem;
    margin: 0;
  }

  /* ---------- 7. KPI cards (animated counters, sparkline, gradient border) ---------- */
  .rp-kpi {
    position: relative;
    background: #ffffff;
    border: 1px solid var(--rp-slate-200);
    border-radius: var(--rp-radius-lg);
    padding: 1.1rem 1.2rem 1rem 1.2rem;
    box-shadow: var(--rp-shadow-sm);
    transition: transform .18s var(--rp-ease), box-shadow .18s var(--rp-ease), border-color .18s var(--rp-ease);
    overflow: hidden;
    isolation: isolate;
  }
  .rp-kpi::before {
    content: "";
    position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--rp-blue) 0%, var(--rp-cyan) 100%);
    z-index: 2;
  }
  .rp-kpi::after {
    /* Subtle gradient border glow on hover */
    content: "";
    position: absolute; inset: 0;
    border-radius: inherit;
    padding: 1px;
    background: linear-gradient(135deg, var(--rp-blue), var(--rp-cyan));
    -webkit-mask:
      linear-gradient(#000 0 0) content-box,
      linear-gradient(#000 0 0);
    -webkit-mask-composite: xor;
            mask-composite: exclude;
    opacity: 0;
    transition: opacity .18s var(--rp-ease);
    pointer-events: none;
  }
  .rp-kpi:hover {
    transform: translateY(-3px);
    box-shadow: var(--rp-shadow);
    border-color: transparent;
  }
  .rp-kpi:hover::after { opacity: 1; }

  .rp-kpi .label {
    color: var(--rp-slate-500);
    font-size: 0.74rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .rp-kpi .value {
    color: var(--rp-slate-900);
    font-size: 1.9rem;
    font-weight: 800;
    letter-spacing: -0.025em;
    margin-top: 0.25rem;
    line-height: 1.1;
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-variant-numeric: tabular-nums;
  }
  .rp-kpi .delta {
    color: var(--rp-green);
    font-size: 0.82rem;
    font-weight: 700;
    margin-top: 0.35rem;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .rp-kpi .delta.down { color: var(--rp-red); }
  .rp-kpi .sparkline {
    margin-top: 0.6rem;
    height: 28px;
    width: 100%;
  }
  .rp-kpi .sparkline svg { width: 100%; height: 100%; display: block; }

  .rp-kpi.amber::before  { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
  .rp-kpi.red::before    { background: linear-gradient(90deg, #ef4444, #f87171); }
  .rp-kpi.green::before  { background: linear-gradient(90deg, #10b981, #34d399); }
  .rp-kpi.purple::before { background: linear-gradient(90deg, #8b5cf6, #c4b5fd); }

  .rp-kpi.amber::after  { background: linear-gradient(135deg, #f59e0b, #fbbf24); }
  .rp-kpi.red::after    { background: linear-gradient(135deg, #ef4444, #f87171); }
  .rp-kpi.green::after  { background: linear-gradient(135deg, #10b981, #34d399); }
  .rp-kpi.purple::after { background: linear-gradient(135deg, #8b5cf6, #c4b5fd); }

  /* ---------- 8. Empty state / onboarding ---------- */
  .rp-empty {
    text-align: center;
    padding: 1.4rem 0 0.6rem 0;
  }
  .rp-empty .title {
    font-size: 1.8rem;
    font-weight: 800;
    background: linear-gradient(90deg, var(--rp-navy) 0%, var(--rp-blue) 100%);
    -webkit-background-clip: text;
            background-clip: text;
    -webkit-text-fill-color: transparent;
            color: transparent;
    margin: 0.4rem 0 0.2rem 0;
    letter-spacing: -0.02em;
  }
  .rp-empty .sub {
    color: var(--rp-slate-500);
    font-size: 0.98rem;
    max-width: 60ch;
    margin: 0 auto 1.4rem auto;
  }
  .rp-onboard {
    background: var(--rp-glass);
    border: 1px solid var(--rp-glass-border);
    border-radius: var(--rp-radius-lg);
    backdrop-filter: blur(16px) saturate(140%);
    -webkit-backdrop-filter: blur(16px) saturate(140%);
    padding: 1.1rem 1.2rem;
    height: 100%;
    transition: transform .18s var(--rp-ease), box-shadow .18s var(--rp-ease);
    text-align: left;
  }
  .rp-onboard:hover {
    transform: translateY(-3px);
    box-shadow: var(--rp-shadow);
  }
  .rp-onboard .icon {
    width: 36px; height: 36px;
    border-radius: 10px;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 1.15rem;
    background: linear-gradient(135deg, rgba(51, 149, 255, 0.18), rgba(0, 212, 255, 0.18));
    color: var(--rp-blue);
    margin-bottom: 0.55rem;
  }
  .rp-onboard h4 {
    margin: 0 0 0.25rem 0 !important;
    font-size: 0.98rem !important;
    font-weight: 700 !important;
    color: var(--rp-slate-900) !important;
  }
  .rp-onboard p {
    margin: 0 !important;
    color: var(--rp-slate-500) !important;
    font-size: 0.85rem !important;
    line-height: 1.5 !important;
  }

  /* ---------- 9. Tabs (sliding underline indicator) ---------- */
  .stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background: transparent;
    padding: 0;
    border-bottom: 1px solid var(--rp-slate-200);
    position: relative;
  }
  .stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    border-radius: 8px 8px 0 0;
    padding: 12px 20px;
    font-weight: 600;
    color: var(--rp-slate-500);
    transition: color .18s var(--rp-ease);
    position: relative;
  }
  .stTabs [data-baseweb="tab"]:hover { color: var(--rp-navy); }
  .stTabs [aria-selected="true"] {
    color: var(--rp-navy) !important;
    background: transparent !important;
  }
  .stTabs [aria-selected="true"]::after {
    content: "";
    position: absolute;
    left: 12px; right: 12px; bottom: -1px;
    height: 3px;
    border-radius: 3px 3px 0 0;
    background: linear-gradient(90deg, var(--rp-blue) 0%, var(--rp-cyan) 100%);
    box-shadow: 0 2px 8px -2px rgba(51, 149, 255, 0.6);
    animation: rp-tab-slide .25s var(--rp-ease);
  }
  @keyframes rp-tab-slide {
    from { transform: scaleX(0.4); opacity: 0; }
    to   { transform: scaleX(1);   opacity: 1; }
  }

  /* ---------- 10. Sidebar (dark + glass cards) ---------- */
  [data-testid="stSidebar"] {
    background:
      radial-gradient(800px 400px at 0% 0%,   rgba(0, 212, 255, 0.18), transparent 60%),
      radial-gradient(700px 350px at 100% 100%, rgba(51, 149, 255, 0.20), transparent 60%),
      linear-gradient(180deg, #0a2540 0%, #0e3a66 100%) !important;
    color: #fff;
    border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
  }
  [data-testid="stSidebar"]::before {
    content: "";
    position: absolute; inset: 0;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40' viewBox='0 0 40 40'><path d='M 40 0 L 0 0 0 40' fill='none' stroke='%23ffffff' stroke-opacity='0.04' stroke-width='1'/></svg>");
    pointer-events: none;
  }
  [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3,
  [data-testid="stSidebar"] h4 {
    color: #ffffff !important;
    font-weight: 700 !important;
  }
  [data-testid="stSidebar"] hr {
    border-color: rgba(255, 255, 255, 0.10) !important;
    margin: 0.6rem 0 !important;
  }
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
  [data-testid="stSidebar"] .stMarkdown small {
    color: #94a3b8 !important;
  }
  /* Sidebar glass block */
  [data-testid="stSidebar"] .rp-glass,
  [data-testid="stSidebar"] .rp-sidebar-card {
    background: rgba(255, 255, 255, 0.06) !important;
    border: 1px solid rgba(255, 255, 255, 0.10) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(14px) saturate(140%) !important;
    -webkit-backdrop-filter: blur(14px) saturate(140%) !important;
    padding: 0.9rem 1rem !important;
    color: #e2e8f0 !important;
    margin-bottom: 0.6rem;
  }
  /* Sidebar inputs */
  [data-testid="stSidebar"] input[type="password"],
  [data-testid="stSidebar"] input[type="text"] {
    background: rgba(255, 255, 255, 0.08) !important;
    border: 1px solid rgba(255, 255, 255, 0.18) !important;
    color: #ffffff !important;
    border-radius: 10px !important;
  }
  [data-testid="stSidebar"] label { color: #cbd5e1 !important; }

  /* ---------- 11. Buttons ---------- */
  .stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em;
    transition: transform .12s var(--rp-ease), box-shadow .18s var(--rp-ease), background .18s var(--rp-ease) !important;
  }
  .stButton > button:hover { transform: translateY(-1px); }
  .stButton > button:active { transform: translateY(0); }

  /* Primary button */
  [data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--rp-blue) 0%, var(--rp-cyan) 100%) !important;
    color: var(--rp-navy) !important;
    border: none !important;
    font-weight: 700 !important;
    box-shadow: 0 6px 20px -6px rgba(51, 149, 255, 0.65);
  }
  [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    box-shadow: 0 10px 30px -8px rgba(51, 149, 255, 0.85);
  }

  /* Default buttons (e.g. suggestion chips) */
  .stButton > button[kind="secondary"] {
    background: #ffffff !important;
    border: 1px solid var(--rp-slate-200) !important;
    color: var(--rp-slate-700) !important;
  }
  .stButton > button[kind="secondary"]:hover {
    border-color: var(--rp-blue) !important;
    color: var(--rp-blue) !important;
    box-shadow: 0 4px 12px -4px rgba(51, 149, 255, 0.35) !important;
  }

  /* ---------- 12. Headings + captions ---------- */
  h1, h2, h3, h4 {
    color: var(--rp-slate-900) !important;
    font-weight: 700 !important;
    letter-spacing: -0.015em;
  }
  .stCaption, [data-testid="stCaptionContainer"] {
    color: var(--rp-slate-500) !important;
  }

  /* ---------- 13. DataFrames ---------- */
  .stDataFrame {
    border: 1px solid var(--rp-slate-200) !important;
    border-radius: var(--rp-radius) !important;
    overflow: hidden;
    box-shadow: var(--rp-shadow-sm);
  }

  /* ---------- 14. Alerts ---------- */
  .stAlert {
    border-radius: var(--rp-radius) !important;
    border: 1px solid #fde68a !important;
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%) !important;
  }

  /* ---------- 15. Chat ---------- */
  [data-testid="stChatMessage"] {
    background: #ffffff !important;
    border: 1px solid var(--rp-slate-200) !important;
    border-radius: 14px !important;
    padding: 1rem 1.2rem !important;
    box-shadow: var(--rp-shadow-sm);
  }
  [data-testid="stChatMessage"][data-testid*="user"] {
    background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%) !important;
    border-color: #bae6fd !important;
  }

  /* ---------- 16. Download buttons ---------- */
  .stDownloadButton > button {
    background: linear-gradient(135deg, var(--rp-blue) 0%, var(--rp-cyan) 100%) !important;
    color: var(--rp-navy) !important;
    border: none !important;
    font-weight: 700 !important;
    box-shadow: 0 6px 18px -6px rgba(51, 149, 255, 0.5);
  }
  .stDownloadButton > button:hover {
    box-shadow: 0 10px 28px -8px rgba(51, 149, 255, 0.75) !important;
  }

  /* ---------- 17. Footer ---------- */
  .rp-footer {
    text-align: center;
    color: var(--rp-slate-500);
    font-size: 0.88rem;
    padding: 2rem 0 1rem 0;
    margin-top: 2.4rem;
    border-top: 1px solid var(--rp-slate-200);
  }
  .rp-footer a {
    color: var(--rp-blue);
    text-decoration: none;
    font-weight: 600;
    transition: color .15s var(--rp-ease);
  }
  .rp-footer a:hover { color: var(--rp-cyan); text-decoration: underline; }
  .rp-footer .rp-socials {
    display: inline-flex;
    gap: 10px;
    margin: 0 8px;
    vertical-align: middle;
  }
  .rp-footer .rp-socials a {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px; height: 28px;
    border-radius: 8px;
    background: rgba(51, 149, 255, 0.10);
    color: var(--rp-blue);
    transition: background .15s var(--rp-ease), color .15s var(--rp-ease), transform .15s var(--rp-ease);
  }
  .rp-footer .rp-socials a:hover {
    background: var(--rp-blue);
    color: #ffffff;
    transform: translateY(-1px);
    text-decoration: none;
  }
  .rp-footer .rp-socials svg { width: 14px; height: 14px; fill: currentColor; }

  /* ---------- 18. Expander ---------- */
  .streamlit-expanderHeader, [data-testid="stExpander"] details summary {
    background: var(--rp-glass) !important;
    border: 1px solid var(--rp-glass-border) !important;
    border-radius: var(--rp-radius) !important;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    font-weight: 600 !important;
    color: var(--rp-slate-700) !important;
  }

  /* ---------- 19. Animated number counter ---------- */
  .rp-counter {
    display: inline-block;
    font-variant-numeric: tabular-nums;
  }

  /* ---------- 20. Responsive (basic) ---------- */
  @media (max-width: 768px) {
    .rp-hero  { padding: 1.6rem 1.4rem 1.8rem 1.4rem; border-radius: 18px; }
    .rp-hero h1 { font-size: 1.6rem; }
    .rp-hero p  { font-size: 0.92rem; }
    .rp-kpi .value { font-size: 1.5rem; }
    .rp-onboard { padding: 0.9rem 1rem; }
    [data-testid="stSidebar"] { width: 85vw !important; }
  }
</style>
"""

# ============================================================================
# Counter + sparkline helpers (pure HTML, no JS frameworks)
# ============================================================================

def _animated_counter(value: str, duration_ms: int = 1100) -> str:
    """Wrap a numeric value in a span that counts up from 0 (client-side).

    Non-numeric prefixes (e.g. '₹', '$', '%') are preserved.
    """
    import re
    m = re.match(r"^(\D*)?([\d,\.]+)(.*)$", value)
    if not m:
        return f'<span class="rp-counter">{value}</span>'
    prefix, num, suffix = m.group(1) or "", m.group(2), m.group(3) or ""
    digits_only = num.replace(",", "")
    try:
        target = float(digits_only)
    except ValueError:
        return f'<span class="rp-counter">{value}</span>'
    decimals = 0
    if "." in digits_only:
        decimals = len(digits_only.split(".", 1)[1])
    # JSON-safe payload
    return (
        f'<span class="rp-counter" '
        f'rp-counter-target="{target}" '
        f'rp-counter-decimals="{decimals}" '
        f'rp-counter-duration="{duration_ms}" '
        f'rp-counter-prefix="{prefix}" '
        f'rp-counter-suffix="{suffix}">'
        f'{prefix}0{suffix}</span>'
    )


def _sparkline_svg(values: list[float], color: str = "#3395ff",
                   fill: str = "rgba(51, 149, 255, 0.18)") -> str:
    """Tiny inline SVG sparkline (no JS, no external deps)."""
    if not values or len(values) < 2:
        return ""
    vmin, vmax = min(values), max(values)
    span = (vmax - vmin) or 1
    width, height = 100, 28
    step = width / (len(values) - 1)
    pts = []
    for i, v in enumerate(values):
        x = i * step
        y = height - ((v - vmin) / span) * height
        pts.append(f"{x:.2f},{y:.2f}")
    line_pts = " ".join(pts)
    area_pts = f"0,{height} " + line_pts + f" {width},{height}"
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
        f'<polygon points="{area_pts}" fill="{fill}"/>'
        f'<polyline points="{line_pts}" fill="none" stroke="{color}" '
        f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


# ============================================================================
# Public component helpers
# ============================================================================

def kpi_card(
    label: str,
    value: str,
    delta: str = "",
    tone: str = "default",
    *,
    sparkline: list[float] | None = None,
    animate: bool = True,
) -> str:
    """Render a glassmorphic KPI card as an HTML string.

    Parameters
    ----------
    label   : Small uppercase label.
    value   : Big value (auto-animated if numeric).
    delta   : Optional sub-line (e.g. "12% MoM" or "↓ 3%").
    tone    : "default" | "green" | "amber" | "red" | "purple".
    sparkline: Optional list of floats to render as a 28px sparkline.
    animate : If True (default), numeric values count up on render.
    """
    cls = "rp-kpi"
    if tone in ("green", "amber", "red", "purple"):
        cls += f" {tone}"

    delta_html = ""
    if delta:
        is_down = delta.strip().startswith(("↓", "-", "−"))
        delta_cls = "delta down" if is_down else "delta"
        delta_html = f'<div class="{delta_cls}">{delta}</div>'

    sparkline_html = ""
    if sparkline and len(sparkline) >= 2:
        color_map = {
            "green":  "#10b981", "amber":  "#f59e0b",
            "red":    "#ef4444", "purple": "#8b5cf6",
            "default": "#3395ff",
        }
        fill_map = {
            "green":  "rgba(16, 185, 129, 0.18)",
            "amber":  "rgba(245, 158, 11, 0.18)",
            "red":    "rgba(239, 68, 68, 0.18)",
            "purple": "rgba(139, 92, 246, 0.18)",
            "default": "rgba(51, 149, 255, 0.18)",
        }
        t = tone if tone in color_map else "default"
        sparkline_html = (
            f'<div class="sparkline">'
            f'{_sparkline_svg(sparkline, color=color_map[t], fill=fill_map[t])}'
            f'</div>'
        )

    value_html = _animated_counter(value) if animate else f'<span class="rp-counter">{value}</span>'

    return f"""
    <div class="{cls}">
      <div class="label">{label}</div>
      <div class="value">{value_html}</div>
      {delta_html}
      {sparkline_html}
    </div>
    """


def hero(
    title: str,
    subtitle: str = "",
    chip: str = "TRACK 4 · AI FINANCE CONTROLLER",
    metrics: list[tuple[str, str]] | None = None,
) -> None:
    """Render the animated gradient hero banner."""
    metrics_html = ""
    if metrics:
        items = "".join(
            f'<div class="rp-hero-metric"><div class="v">{v}</div><div class="l">{l}</div></div>'
            for l, v in metrics
        )
        metrics_html = f'<div style="margin-top: 1rem;">{items}</div>'
    st.markdown(
        f"""
        <div class="rp-hero">
          <div class="rp-chip">{chip}</div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
          {metrics_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def footer() -> None:
    """Render the page footer with social links."""
    st.markdown(
        """
        <div class="rp-footer">
          <div>
            Built for
            <a href="https://razorpay.com/buildathon/" target="_blank" rel="noopener">Razorpay AI Buildathon</a>
            · Track 4 (AI Finance Controller) · by
            <a href="https://github.com/AdityaST93" target="_blank" rel="noopener">Aditya Singh Thakur</a>
          </div>
          <div style="margin-top: 0.6rem;">
            <span class="rp-socials">
              <a href="https://github.com/AdityaST93/Artificial-intelligence-finance-controller" target="_blank" rel="noopener" title="GitHub">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .5C5.7.5.6 5.6.6 11.9c0 5 3.3 9.3 7.8 10.8.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2.9-.3 1.9-.4 2.9-.4s2 .1 2.9.4c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3.1.8.8 1.2 1.9 1.2 3.1 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.2c0 .3.2.7.8.6 4.5-1.5 7.8-5.8 7.8-10.8C23.4 5.6 18.3.5 12 .5z"/></svg>
              </a>
              <a href="https://x.com/" target="_blank" rel="noopener" title="X / Twitter">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.244 2H21l-6.52 7.45L22 22h-6.84l-4.78-6.26L4.8 22H2l6.97-7.97L2 2h6.91l4.33 5.72L18.244 2zm-2.4 18h1.86L8.24 4H6.3l9.544 16z"/></svg>
              </a>
              <a href="https://www.linkedin.com/" target="_blank" rel="noopener" title="LinkedIn">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.98 3.5a2.5 2.5 0 11-.001 5.001A2.5 2.5 0 014.98 3.5zM3 9.5h4V21H3V9.5zM9 9.5h3.8v1.6h.1c.5-1 1.8-2 3.7-2 4 0 4.7 2.6 4.7 6V21h-4v-5.3c0-1.3 0-2.9-1.8-2.9-1.8 0-2.1 1.4-2.1 2.8V21H9V9.5z"/></svg>
              </a>
              <a href="https://razorpay.com/buildathon/" target="_blank" rel="noopener" title="Razorpay">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 6.5C2 4 4 2 6.5 2H21v6.5C21 12 18 14 14.5 14H8v4.5C8 20.5 6.5 22 4.5 22S2 20.5 2 18.5V6.5z"/></svg>
              </a>
            </span>
            ·
            <a href="https://github.com/AdityaST93/Artificial-intelligence-finance-controller" target="_blank" rel="noopener">Source on GitHub</a>
            · MIT License
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str = "") -> None:
    """Render a section header with a gradient title."""
    sub_html = f'<p class="sub">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f"""
        <div class="rp-section-header">
          <h2>{title}</h2>
          {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(
    title: str = "Welcome 👋",
    subtitle: str = (
        "This dashboard closes the finance-ops loop for an Indian merchant on Razorpay — "
        "reconciliation, settlement Q&A, cash forecasting, and GST line matching, all in one place."
    ),
    onboard: list[dict] | None = None,
) -> None:
    """Render an empty-state hero with up to 4 onboarding cards.

    Each onboarding dict: {"icon": "📊", "title": "...", "desc": "..."}.
    """
    if onboard is None:
        onboard = [
            {"icon": "📊", "title": "Reconciliation",
             "desc": "Match rate, exception breakdown, GST alignment across 4 sources."},
            {"icon": "💵", "title": "Cash Forecast",
             "desc": "13-week projection of opening → closing balance with weekly inflow/outflow."},
            {"icon": "🧾", "title": "GST Match",
             "desc": "6-dimension line match · ITC claimed vs eligible, with at-risk recovery."},
            {"icon": "💬", "title": "Q&A Agent",
             "desc": "Ask in plain English, get cited answers from your reconciled data."},
        ]
    cards = "".join(
        f"""
        <div class="rp-onboard">
          <div class="icon">{o.get("icon", "✨")}</div>
          <h4>{o.get("title", "")}</h4>
          <p>{o.get("desc", "")}</p>
        </div>
        """
        for o in onboard
    )
    st.markdown(
        f"""
        <div class="rp-empty">
          <div class="title">{title}</div>
          <p class="sub">{subtitle}</p>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: 14px; margin: 0.4rem 0 1.4rem 0;">
          {cards}
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_plotly(fig) -> None:
    """Apply the Razorpay-inspired theme to a Plotly figure (in-place)."""
    fig.update_layout(
        paper_bgcolor=PLOTLY_THEME["paper_bgcolor"],
        plot_bgcolor=PLOTLY_THEME["plot_bgcolor"],
        font=PLOTLY_THEME["font"],
        colorway=PLOTLY_THEME["colorway"],
        margin=PLOTLY_THEME["margin"],
        title_font_family="Inter, system-ui, sans-serif",
        title_font_color=PALETTE["slate_900"],
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(15, 23, 42, 0.06)",
            zeroline=False,
            linecolor="rgba(15, 23, 42, 0.12)",
            tickfont=dict(family="Inter, system-ui, sans-serif",
                          color=PALETTE["slate_500"], size=12),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(15, 23, 42, 0.06)",
            zeroline=False,
            linecolor="rgba(15, 23, 42, 0.12)",
            tickfont=dict(family="Inter, system-ui, sans-serif",
                          color=PALETTE["slate_500"], size=12),
        ),
        legend=dict(
            font=dict(family="Inter, system-ui, sans-serif",
                      color=PALETTE["slate_700"], size=12),
            bgcolor="rgba(0,0,0,0)",
        ),
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="rgba(15, 23, 42, 0.12)",
            font=dict(family="Inter, system-ui, sans-serif",
                      color=PALETTE["slate_900"], size=13),
        ),
    )


# ============================================================================
# Inject helpers (CSS + counter runtime)
# ============================================================================

COUNTER_RUNTIME: str = r"""
<script>
(function () {
  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
  function formatNumber(n, decimals) {
    if (decimals > 0) return n.toFixed(decimals);
    return Math.round(n).toLocaleString('en-IN');
  }
  function animate(el) {
    if (el.dataset.rpCounterDone === '1') return;
    var target = parseFloat(el.getAttribute('rp-counter-target') || '0');
    var decimals = parseInt(el.getAttribute('rp-counter-decimals') || '0', 10);
    var duration = parseInt(el.getAttribute('rp-counter-duration') || '1000', 10);
    var prefix = el.getAttribute('rp-counter-prefix') || '';
    var suffix = el.getAttribute('rp-counter-suffix') || '';
    if (!isFinite(target)) { el.dataset.rpCounterDone = '1'; return; }
    var start = performance.now();
    function frame(now) {
      var t = Math.min(1, (now - start) / duration);
      var v = target * easeOutCubic(t);
      el.textContent = prefix + formatNumber(v, decimals) + suffix;
      if (t < 1) requestAnimationFrame(frame);
      else el.dataset.rpCounterDone = '1';
    }
    requestAnimationFrame(frame);
  }
  function runAll() {
    var els = document.querySelectorAll('.rp-counter');
    for (var i = 0; i < els.length; i++) animate(els[i]);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', runAll);
  } else {
    runAll();
  }
  // Re-run on Streamlit re-renders (Streamlit swaps innerHTML on rerun).
  var mo = new MutationObserver(function () {
    var fresh = document.querySelectorAll('.rp-counter:not([data-rp-counter-done])');
    if (fresh.length) {
      for (var i = 0; i < fresh.length; i++) animate(fresh[i]);
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });
})();
</script>
"""


def inject() -> None:
    """Inject the full stylesheet + counter runtime into the current page.

    Call this once at the top of your Streamlit app, right after
    ``st.set_page_config(...)``.
    """
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(COUNTER_RUNTIME, unsafe_allow_html=True)

