"""
ui package — Razorpay-inspired design system for the Streamlit app.

Re-exports the public surface of :mod:`ui.design_system` so callers can simply
write ``from ui import CUSTOM_CSS, PALETTE, kpi_card, hero, ...``.
"""
from .design_system import (  # noqa: F401
    PALETTE,
    PLOTLY_THEME,
    CUSTOM_CSS,
    COUNTER_RUNTIME,
    kpi_card,
    hero,
    footer,
    style_plotly,
    section_header,
    empty_state,
    inject,
)

__all__ = [
    "PALETTE",
    "PLOTLY_THEME",
    "CUSTOM_CSS",
    "COUNTER_RUNTIME",
    "kpi_card",
    "hero",
    "footer",
    "style_plotly",
    "section_header",
    "empty_state",
    "inject",
]
