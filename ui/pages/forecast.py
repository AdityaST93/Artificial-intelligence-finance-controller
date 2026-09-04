"""
ui.pages.forecast — 13-week cash forecast with scenario selector.

Reads from `st.session_state["forecast"]` and renders:
  - 4 large forecast KPI cards
  - 13-week forecast chart (Plotly line + bars)
  - Weekly details table
  - Scenario selector: Base / Best / Worst (recomputes)
  - Inflow/outflow breakdown
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui.design_system import kpi_card, section_header, style_plotly


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_forecast(forecast: Any):
    return forecast  # typed as ForecastResult but no import-time check


def _scenario_adjust(base: Any, scenario: str) -> Any:
    """Return a new ForecastResult-like with scenario adjustments applied.

    For 'best': grow inflow 1.5x, shrink outflow 0.75x, growth_rate +50%.
    For 'worst': shrink inflow 0.7x, grow outflow 1.25x, growth_rate -50%.
    """
    if base is None:
        return None
    if scenario == "Base":
        return base

    # Build a quick derived dataframe and re-sum
    df = base.df.copy()
    if df.empty:
        return base

    if scenario == "Best":
        inflow_mult, outflow_mult, growth_delta = 1.5, 0.75, +0.01
    else:  # Worst
        inflow_mult, outflow_mult, growth_delta = 0.7, 1.25, -0.01

    # Re-projection: scale each week's inflow/outflow
    df["inflow"] = df["inflow"] * inflow_mult
    df["outflow"] = df["outflow"] * outflow_mult
    df["net"] = df["inflow"] - df["outflow"]

    # Re-walk closing balances
    closings = []
    bal = float(base.opening_balance)
    for _, r in df.iterrows():
        bal = bal + float(r["net"])
        closings.append(bal)
    df["closing"] = closings

    total_inflow = Decimal(str(df["inflow"].sum()))
    total_outflow = Decimal(str(df["outflow"].sum()))
    closing_balance = Decimal(str(closings[-1])) if closings else base.closing_balance
    lowest_balance = min((Decimal(str(c)) for c in closings), default=base.lowest_balance)
    lowest_week = closings.index(min(closings)) + 1 if closings else base.lowest_week

    # Alert logic
    threshold = base.opening_balance * Decimal("0.10")
    if lowest_balance < threshold:
        alert = f"LOW BALANCE ALERT: week {lowest_week} closing Rs {lowest_balance:.2f} is below 10% of opening (Rs {threshold:.2f})"
    elif lowest_balance < base.opening_balance * Decimal("0.50"):
        alert = f"Caution: week {lowest_week} closing Rs {lowest_balance:.2f} is below 50% of opening"
    else:
        alert = None

    # Lightweight stand-in: copy & overwrite
    new = type(base)(
        df=df,
        opening_balance=base.opening_balance,
        closing_balance=closing_balance,
        lowest_balance=lowest_balance,
        lowest_week=lowest_week,
        weeks=base.weeks,
        total_inflow=total_inflow,
        total_outflow=total_outflow,
        alert=alert,
    )
    return new


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_forecast(forecast: Any = None) -> None:
    """Render the forecast page."""
    if forecast is None:
        forecast = st.session_state.get("forecast")

    if forecast is None:
        st.info("Run reconciliation in the sidebar to compute the forecast.")
        return

    # ------------------------------------------------------------------
    # Scenario selector (recomputes)
    # ------------------------------------------------------------------
    section_header(
        "13-week cash flow projection",
        "Deterministic projection from reconciled settlement history (net of fees + refunds).",
    )

    sc_col, _ = st.columns([1, 3])
    with sc_col:
        scenario = st.selectbox(
            "Scenario",
            ["Base", "Best", "Worst"],
            key="forecast_scenario",
            help="Recomputes the projection. Base = historical. Best = +50% inflow, -25% outflow. Worst = -30% inflow, +25% outflow.",
        )

    adjusted = _scenario_adjust(forecast, scenario)
    f = adjusted

    # ------------------------------------------------------------------
    # 1) 4 large forecast KPI cards
    # ------------------------------------------------------------------
    net_delta = f.total_inflow - f.total_outflow
    opening = Decimal(f.opening_balance)
    lowest = Decimal(f.lowest_balance)
    threshold = opening * Decimal("0.10")
    if lowest < threshold:
        low_tone = "red"
    elif lowest < opening * Decimal("0.50"):
        low_tone = "amber"
    else:
        low_tone = "green"

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            kpi_card(
                "Opening",
                f"Rs {Decimal(f.opening_balance):,.0f}",
                "today",
            ),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            kpi_card(
                "Closing",
                f"Rs {Decimal(f.closing_balance):,.0f}",
                f"in {f.weeks} weeks",
                tone="green",
            ),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            kpi_card(
                "Lowest",
                f"Rs {lowest:,.0f}",
                f"week {f.lowest_week}",
                tone=low_tone,
            ),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            kpi_card(
                "Net Δ",
                f"Rs {net_delta:,.0f}",
                "inflows − outflows",
                tone="green" if net_delta >= 0 else "red",
            ),
            unsafe_allow_html=True,
        )

    if f.alert:
        st.warning(f"⚠️  {f.alert}")

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 2) 13-week forecast chart (Plotly line + bars)
    # ------------------------------------------------------------------
    section_header(
        "Weekly cash flow",
        f"Closing balance line over 13 weeks · bars: inflow (+) / outflow (−).",
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=f.df["week"],
        y=f.df["closing"],
        mode="lines+markers",
        name="Closing balance",
        line=dict(color="#3395ff", width=3, shape="spline"),
        marker=dict(size=8, color="#00d4ff",
                    line=dict(color="#3395ff", width=2)),
        fill="tozeroy",
        fillcolor="rgba(51, 149, 255, 0.10)",
        hovertemplate="<b>Week %{x}</b><br>Closing: Rs %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=f.df["week"],
        y=f.df["inflow"],
        name="Inflow",
        marker=dict(color="rgba(16, 185, 129, 0.6)"),
        hovertemplate="<b>Week %{x}</b><br>Inflow: Rs %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=f.df["week"],
        y=-f.df["outflow"],
        name="Outflow",
        marker=dict(color="rgba(239, 68, 68, 0.6)"),
        hovertemplate="<b>Week %{x}</b><br>Outflow: Rs %{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="<b>13-Week Cash Forecast</b>", x=0,
                   font=dict(size=18, color="#0f172a")),
        xaxis=dict(title="Week", showgrid=False, zeroline=False),
        yaxis=dict(title="Rs (INR)", showgrid=True,
                   gridcolor="rgba(15, 23, 42, 0.06)"),
        barmode="overlay",
        hovermode="x unified",
        height=520,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
    )
    style_plotly(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 3) Inflow / outflow breakdown
    # ------------------------------------------------------------------
    section_header(
        "Inflow / outflow breakdown",
        f"Total inflow vs. outflow across the {f.weeks}-week horizon.",
    )

    i1, i2 = st.columns(2)
    with i1:
        st.markdown(
            kpi_card(
                "Total inflow",
                f"Rs {f.total_inflow:,.0f}",
                f"over {f.weeks} weeks",
                tone="green",
            ),
            unsafe_allow_html=True,
        )
    with i2:
        st.markdown(
            kpi_card(
                "Total outflow",
                f"Rs {f.total_outflow:,.0f}",
                f"over {f.weeks} weeks",
                tone="red",
            ),
            unsafe_allow_html=True,
        )

    # Weekly breakdown as a small Plotly stacked bar
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=f.df["week"], y=f.df["inflow"],
        name="Inflow", marker_color="#10b981",
        hovertemplate="<b>Week %{x}</b><br>Inflow: Rs %{y:,.2f}<extra></extra>",
    ))
    fig2.add_trace(go.Bar(
        x=f.df["week"], y=f.df["outflow"],
        name="Outflow", marker_color="#ef4444",
        hovertemplate="<b>Week %{x}</b><br>Outflow: Rs %{y:,.2f}<extra></extra>",
    ))
    fig2.update_layout(
        barmode="group",
        title=dict(text="<b>Weekly inflow vs. outflow</b>", x=0,
                   font=dict(size=16, color="#0f172a")),
        xaxis=dict(title="Week"),
        yaxis=dict(title="Rs (INR)", gridcolor="rgba(15, 23, 42, 0.06)"),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1),
    )
    style_plotly(fig2)
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 4) Weekly details table
    # ------------------------------------------------------------------
    section_header(
        "Weekly details",
        f"Row per week for the {f.weeks}-week horizon.",
    )

    table_df = f.df.copy()
    # Pretty formatting if numeric
    for col in ["opening", "inflow", "outflow", "net", "closing"]:
        if col in table_df.columns:
            table_df[col] = table_df[col].apply(
                lambda v: f"Rs {float(v):,.2f}" if pd.notna(v) else "—"
            )
    st.dataframe(table_df, use_container_width=True, hide_index=True, height=420)
