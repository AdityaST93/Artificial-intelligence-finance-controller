"""
ui.pages — dedicated page modules for the Streamlit app.

Each module exposes a single `render_*` function that draws one page
on top of the cached `st.session_state["result"]` / `["forecast"]` /
`["gst"]` objects. The home app dispatches into these.

Public surface (re-exported for convenience):
  - dashboard.render_dashboard
  - reconciliation.render_reconciliation
  - forecast.render_forecast
  - gst.render_gst
  - qa.render_qa
  - exceptions.render_exceptions
  - audit.render_audit
  - settings.render_settings
"""

from . import (  # noqa: F401
    dashboard,
    reconciliation,
    forecast,
    gst,
    qa,
    exceptions,
    audit,
    settings,
)

__all__ = [
    "dashboard",
    "reconciliation",
    "forecast",
    "gst",
    "qa",
    "exceptions",
    "audit",
    "settings",
]
