"""
ui.pages.settings — runtime configuration: API keys, tolerance, theme,
data regeneration.

Manages keys in `st.session_state`:
  - openrouter_api_key
  - razorpay_key_id
  - razorpay_key_secret
  - amount_tolerance_inr
  - date_tolerance_days
  - theme (light | dark)

The "Regenerate data" button clears the cached reconciliation result so
the next run will rebuild it from the (regenerated) source files.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.design_system import kpi_card, section_header


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "openrouter_api_key": "",
    "razorpay_key_id": "",
    "razorpay_key_secret": "",
    "amount_tolerance_inr": 0.05,
    "date_tolerance_days": 2,
    "theme": "light",
}


def _ensure_defaults() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _mask_key(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_settings() -> None:
    """Render the settings page."""
    _ensure_defaults()

    section_header(
        "Settings",
        "API keys, reconciliation tolerances, theme, and data actions.",
    )

    # ------------------------------------------------------------------
    # 1) API keys
    # ------------------------------------------------------------------
    section_header(
        "API keys",
        "Stored in session state only — never persisted to disk.",
    )

    st.markdown(
        kpi_card(
            "OpenRouter key",
            "configured" if st.session_state["openrouter_api_key"] else "missing",
            _mask_key(st.session_state["openrouter_api_key"]) or "—",
            tone="green" if st.session_state["openrouter_api_key"] else "amber",
        ),
        unsafe_allow_html=True,
    )

    st.text_input(
        "OpenRouter API key",
        value=st.session_state["openrouter_api_key"],
        type="password",
        key="openrouter_api_key",
        help="Used by the Q&A agent (core.agent.ask). Leave blank to use the built-in fallback.",
    )

    st.markdown("##### Razorpay")
    st.text_input(
        "Razorpay Key ID",
        value=st.session_state["razorpay_key_id"],
        key="razorpay_key_id",
        help="rzp_test_… or rzp_live_…",
    )
    st.text_input(
        "Razorpay Key Secret",
        value=st.session_state["razorpay_key_secret"],
        type="password",
        key="razorpay_key_secret",
    )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 2) Tolerance settings
    # ------------------------------------------------------------------
    section_header(
        "Reconciliation tolerances",
        "How strict the match engine is when comparing amounts and dates.",
    )

    c1, c2 = st.columns(2)
    with c1:
        st.number_input(
            "Amount tolerance (Rs)",
            min_value=0.0,
            max_value=100.0,
            value=float(st.session_state["amount_tolerance_inr"]),
            step=0.01,
            key="amount_tolerance_inr",
            help="Maximum difference between the settled and payment amounts.",
        )
    with c2:
        st.number_input(
            "Date tolerance (days)",
            min_value=0,
            max_value=30,
            value=int(st.session_state["date_tolerance_days"]),
            step=1,
            key="date_tolerance_days",
            help="Maximum gap between the bank-credit and payment dates.",
        )

    st.caption(
        f"Current: ±Rs {float(st.session_state['amount_tolerance_inr']):.2f}, "
        f"±{int(st.session_state['date_tolerance_days'])} day(s)."
    )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 3) Theme toggle
    # ------------------------------------------------------------------
    section_header(
        "Theme",
        "Light / dark. (Dark mode is best-effort; the brand is light-first.)",
    )

    theme_choice = st.radio(
        "Theme",
        options=["light", "dark"],
        index=0 if st.session_state["theme"] == "light" else 1,
        horizontal=True,
        key="theme_radio",
        help="Switches the Streamlit theme on the next rerun.",
    )
    if theme_choice != st.session_state["theme"]:
        st.session_state["theme"] = theme_choice
        # Try to forward to Streamlit's own theme config (best-effort)
        try:
            st._config.set_option("theme.base", "dark" if theme_choice == "dark" else "light")
        except Exception:
            pass

    if st.session_state["theme"] == "dark":
        st.info("Dark mode toggle is set. The full glassmorphic design is light-first; "
                "this mostly affects Streamlit chrome and some surfaces.")
    else:
        st.caption("Light mode (default Razorpay-inspired glass).")

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 4) Data actions
    # ------------------------------------------------------------------
    section_header(
        "Data",
        "Regenerate the source files and clear the cached result.",
    )

    st.caption(
        "Removes the cached `st.session_state['result']` so the next run "
        "re-builds from any regenerated source CSVs."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Clear cached result", use_container_width=True):
            for k in ("result", "forecast", "gst"):
                if k in st.session_state:
                    del st.session_state[k]
            st.success("Cached result/forecast/gst cleared.")
            st.rerun()

    with col_b:
        if st.button("Regenerate source data", type="primary", use_container_width=True):
            with st.spinner("Regenerating source CSVs…"):
                try:
                    from core.regen import regenerate_data  # type: ignore
                    regenerate_data()
                    # Clear cache so the next run re-reads
                    for k in ("result", "forecast", "gst"):
                        if k in st.session_state:
                            del st.session_state[k]
                    st.success("Source data regenerated. Re-run reconciliation from the sidebar.")
                except Exception as e:
                    st.error(
                        f"Regenerate failed: {e}\n\n"
                        f"You can also run `python -m core.regen` from the project root."
                    )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 5) Reset all
    # ------------------------------------------------------------------
    section_header(
        "Reset",
        "Restore every setting to its default.",
    )
    if st.button("Reset all settings to defaults", use_container_width=False):
        for k, v in DEFAULTS.items():
            st.session_state[k] = v
        st.success("Settings restored to defaults.")
        st.rerun()
