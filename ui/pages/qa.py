"""
ui.pages.qa — Ask-the-data chat page.

Reads `st.session_state["chat_history"]` for history and stores new
turns there. Uses `core.agent.ask(question)` to generate answers.
Suggested question chips at the top; chat input at the bottom.

Reads (and tolerates missing) from session_state:
  - result    : ReconcileResult (used for context only)
  - chat_history : list[{role, content, ts}] (managed here)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from ui.design_system import section_header


# ---------------------------------------------------------------------------
# Suggested questions
# ---------------------------------------------------------------------------

SUGGESTED_QUESTIONS: list[str] = [
    "Why is match rate below 95%?",
    "What is the largest exception this week?",
    "Summarise bank vs. Razorpay differences",
    "Which invoice has the most GST mismatch?",
    "Top 3 reasons for unmatched OMS orders",
    "Forecast 13-week cash flow at worst case",
    "Which payments are missing GST invoices?",
    "Give me a fee-variance analysis",
]


def _format_answer(answer: str) -> str:
    """Format the LLM answer:
    - Convert inline payment IDs like ``pay_ABC123`` to code blocks
    - Convert inline ``Rs 1,234.56`` to code blocks
    - Pass plain text otherwise.

    We keep it conservative — only patterns that look like payment IDs
    or amounts are converted.
    """
    import re

    if not answer:
        return ""

    formatted = answer

    # Highlight payment IDs (e.g. pay_ABC123, pay-ABC123, pay-1234567)
    formatted = re.sub(
        r"\b(pay[_-][A-Za-z0-9]{4,})\b",
        r"`\1`",
        formatted,
    )

    # Highlight order IDs (e.g. order_ABC123)
    formatted = re.sub(
        r"\b(order[_-][A-Za-z0-9]{4,})\b",
        r"`\1`",
        formatted,
    )

    # Highlight amounts in Rs
    formatted = re.sub(
        r"(?<!\`)(Rs\.?\s?\d[\d,]*(?:\.\d+)?)",
        r"`\1`",
        formatted,
    )

    return formatted


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_qa(result: Any = None) -> None:
    """Render the Q&A chat page."""
    if result is None:
        result = st.session_state.get("result")

    section_header(
        "Ask the data",
        "Natural-language questions, grounded in your reconciled sources.",
    )

    # Initialise chat history in session_state
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    # ------------------------------------------------------------------
    # Suggested question chips (top)
    # ------------------------------------------------------------------
    st.markdown("##### Suggested questions")
    st.caption("Click a chip to ask. Or type your own below.")

    # Render chips in a 2x4 grid
    rows: list[list[str]] = [SUGGESTED_QUESTIONS[i:i + 2] for i in range(0, len(SUGGESTED_QUESTIONS), 2)]
    for row in rows:
        cols = st.columns(len(row))
        for col, q in zip(cols, row):
            with col:
                if st.button(q, key=f"chip_{q}", use_container_width=True):
                    _ask(q, result)

    st.markdown("<div style='height: 0.8rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Chat history
    # ------------------------------------------------------------------
    st.markdown("##### Conversation")

    history = st.session_state.get("chat_history", [])
    if not history:
        st.info("No questions yet. Pick a chip or type your own question below.")
    else:
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            ts = turn.get("ts", "")
            with st.chat_message(role):
                if role == "user":
                    st.markdown(content)
                else:
                    # Assistant: render with formatting + citations footer
                    formatted = _format_answer(content)
                    st.markdown(formatted)
                if ts:
                    st.caption(f"{ts}")

    st.markdown("<div style='height: 0.8rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Clear-history button
    # ------------------------------------------------------------------
    col1, col2, col3 = st.columns([1, 4, 1])
    with col3:
        if st.button("Clear history", use_container_width=True):
            st.session_state["chat_history"] = []
            st.rerun()

    # ------------------------------------------------------------------
    # Chat input at the bottom
    # ------------------------------------------------------------------
    st.markdown("---")
    user_q = st.chat_input("Ask anything about your reconciliation…")
    if user_q:
        _ask(user_q, result)


def _ask(question: str, result: Any) -> None:
    """Send ``question`` to the agent and append the turn to history."""
    if not question or not question.strip():
        return

    # Append user turn
    st.session_state["chat_history"].append({
        "role": "user",
        "content": question.strip(),
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    # Get answer from agent
    try:
        from core.agent import ask as agent_ask
        answer = agent_ask(question.strip())
    except Exception as e:
        answer = (
            f"_(Sorry, the agent failed: {e})_\n\n"
            f"You asked: **{question.strip()}**\n\n"
            f"Try re-running reconciliation, or check the OpenRouter API key "
            f"in Settings."
        )

    # Append assistant turn
    st.session_state["chat_history"].append({
        "role": "assistant",
        "content": answer or "(no answer returned)",
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    st.rerun()
