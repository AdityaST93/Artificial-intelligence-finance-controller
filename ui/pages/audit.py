"""
ui.pages.audit — per-payment audit trail.

Reads from `st.session_state["result"]` and renders:
  - A per-payment audit trail
  - User can enter a payment_id
  - Shows source rows from all 4 files, what matched, what didn't, why
  - Has a "drill into any payment" feature (click-to-drill from tables)
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.design_system import kpi_card, section_header


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_metrics(result: Any) -> dict:
    if result is None:
        return {}
    m = getattr(result, "metrics", None)
    return m if isinstance(m, dict) else {}


def _row_matches_payment(df: pd.DataFrame, payment_id: str) -> pd.DataFrame:
    """Return rows in ``df`` that match ``payment_id`` across known key columns."""
    if df is None or df.empty or not payment_id:
        return df.iloc[0:0]
    pid = str(payment_id).strip().lower()
    if not pid:
        return df.iloc[0:0]
    candidate_cols = [
        "payment_id", "razorpay_payment_id", "utr", "transaction_id",
        "order_id", "invoice_no", "order_receipt",
    ]
    cols = [c for c in candidate_cols if c in df.columns]
    if not cols:
        return df.iloc[0:0]
    mask = pd.Series(False, index=df.index)
    for c in cols:
        mask |= df[c].astype(str).str.lower().str.contains(pid, na=False)
    return df[mask]


def _build_audit_trail(payment_id: str, result: Any) -> dict[str, Any]:
    """Build the audit-trail dictionary for a single payment_id."""
    trail: dict[str, Any] = {
        "payment_id": payment_id,
        "sources": {},
        "matched": [],
        "unmatched": [],
        "reasons": [],
        "in_exception_table": False,
    }

    if result is None or not payment_id:
        return trail

    # 1) Razorpay (the canonical source)
    rzp = getattr(result, "razorpay", None)
    if rzp is not None:
        trail["sources"]["razorpay"] = _row_matches_payment(rzp, payment_id)

    # 2) Bank
    bank = getattr(result, "bank", None)
    if bank is not None:
        trail["sources"]["bank"] = _row_matches_payment(bank, payment_id)

    # 3) OMS
    oms = getattr(result, "oms", None)
    if oms is not None:
        trail["sources"]["oms"] = _row_matches_payment(oms, payment_id)

    # 4) GST
    gst = getattr(result, "gst", None)
    if gst is not None:
        trail["sources"]["gst"] = _row_matches_payment(gst, payment_id)

    # Matched (the result.df holds joined records)
    matched_df = getattr(result, "df", pd.DataFrame())
    if matched_df is not None and not matched_df.empty and "payment_id" in matched_df.columns:
        trail["matched"] = _row_matches_payment(matched_df, payment_id)

    # Exception table
    ex_df = getattr(result, "exceptions", pd.DataFrame())
    if ex_df is not None and not ex_df.empty:
        ex_hits = _row_matches_payment(ex_df, payment_id)
        if not ex_hits.empty:
            trail["in_exception_table"] = True
            for _, r in ex_hits.iterrows():
                trail["unmatched"].append({
                    "category": r.get("exception_category", "uncategorised"),
                    "reason": r.get("reason", ""),
                    "amount": r.get("amount", None),
                })
                trail["reasons"].append(r.get("reason", ""))

    return trail


def _render_source_block(name: str, df: pd.DataFrame) -> None:
    """Render a single source block (Razorpay / Bank / OMS / GST)."""
    st.markdown(f"##### {name}")
    if df is None or df.empty:
        st.caption(f"_(no row in {name.lower()} matches this payment_id)_")
        return
    st.caption(f"{len(df):,} row(s) found")
    st.dataframe(
        df.fillna("—"),
        use_container_width=True,
        hide_index=True,
        height=180,
    )


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_audit(result: Any = None) -> None:
    """Render the audit-trail page."""
    if result is None:
        result = st.session_state.get("result")

    if result is None:
        st.info("Run reconciliation in the sidebar first.")
        return

    m = _safe_metrics(result)

    # ------------------------------------------------------------------
    # 1) Top-of-page summary
    # ------------------------------------------------------------------
    section_header(
        "Per-payment audit trail",
        "Pick a payment_id and see the full reconciliation story across all 4 sources.",
    )

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            kpi_card(
                "Razorpay",
                f"{int(m.get('razorpay_payments', 0)):,}",
                "rows",
            ),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            kpi_card(
                "Matched",
                f"{int(m.get('tier1_matched_payments', 0)):,}",
                "in tier-1",
                tone="green",
            ),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            kpi_card(
                "Exceptions",
                f"{int(m.get('tier1_exceptions', 0)):,}",
                "named",
                tone="amber",
            ),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            kpi_card(
                "GST",
                f"{int(m.get('gst_invoices', 0)):,}",
                "invoices",
            ),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # 2) Payment-ID picker
    # ------------------------------------------------------------------
    section_header(
        "Drill into a payment",
        "Type a payment_id (or pick one from a quick-pick list).",
    )

    # Build a quick-pick list: a few IDs from matched + a few from exceptions
    quick_picks: list[str] = []
    try:
        matched_df = getattr(result, "df", pd.DataFrame())
        if matched_df is not None and "payment_id" in matched_df.columns:
            quick_picks.extend(matched_df["payment_id"].dropna().astype(str).head(5).tolist())
    except Exception:
        pass
    try:
        ex_df = getattr(result, "exceptions", pd.DataFrame())
        if ex_df is not None and "payment_id" in ex_df.columns:
            quick_picks.extend(ex_df["payment_id"].dropna().astype(str).head(5).tolist())
    except Exception:
        pass
    quick_picks = [p for p in quick_picks if p and p != "—"]
    quick_picks = list(dict.fromkeys(quick_picks))[:10]  # dedupe, first 10

    # Payment-ID input
    pc1, pc2 = st.columns([2, 1])
    with pc1:
        # Use session_state to remember the current pick across reruns
        if "audit_payment_id" not in st.session_state:
            st.session_state["audit_payment_id"] = quick_picks[0] if quick_picks else ""
        payment_id = st.text_input(
            "payment_id",
            value=st.session_state.get("audit_payment_id", ""),
            placeholder="e.g. pay_ABC123 or pay_abc123",
            key="audit_payment_id_input",
        )
        if payment_id != st.session_state.get("audit_payment_id"):
            st.session_state["audit_payment_id"] = payment_id
    with pc2:
        if quick_picks:
            pick = st.selectbox(
                "Quick-pick",
                options=["(select)"] + quick_picks,
                index=0,
                key="audit_quick_pick",
            )
            if pick and pick != "(select)":
                st.session_state["audit_payment_id"] = pick
                st.rerun()

    st.markdown("<div style='height: 0.6rem'></div>", unsafe_allow_html=True)

    if not payment_id or not str(payment_id).strip():
        st.info("Enter a payment_id above to drill in.")
        return

    # ------------------------------------------------------------------
    # 3) Build & render the audit trail
    # ------------------------------------------------------------------
    trail = _build_audit_trail(str(payment_id).strip(), result)

    # Status banner
    if trail["in_exception_table"]:
        st.error(
            f"**Payment `{payment_id}` is in the exception table.** "
            f"It could not be cleanly reconciled."
        )
    elif not trail["matched"].empty:
        st.success(
            f"**Payment `{payment_id}` is matched.** It appears in the joined record set."
        )
    else:
        st.warning(
            f"**Payment `{payment_id}` is not in the matched set, but is not in "
            f"the exception table either.** It may not exist in any source file."
        )

    # Reasons
    if trail["reasons"]:
        st.markdown("##### Why it didn't reconcile")
        for r in trail["reasons"]:
            st.markdown(f"- {r}")

    # Source rows
    st.markdown("---")
    section_header(
        "Source rows",
        "Each source file's row (or absence) for this payment_id.",
    )

    src_cols = st.columns(2)
    sources = trail.get("sources", {})
    items = list(sources.items())
    for i, (name, df) in enumerate(items):
        col = src_cols[i % 2]
        with col:
            _render_source_block(name.upper(), df)

    # Matched-row detail
    st.markdown("---")
    section_header(
        "Joined record",
        "The matched record (from result.df) for this payment_id, if any.",
    )
    if trail["matched"].empty:
        st.caption("_(no joined record for this payment_id)_")
    else:
        st.dataframe(
            trail["matched"].fillna("—"),
            use_container_width=True,
            hide_index=True,
            height=180,
        )

    # Unmatched / exception details
    if trail["unmatched"]:
        st.markdown("---")
        section_header(
            "Exception detail",
            "How this payment was classified as an exception.",
        )
        st.dataframe(
            pd.DataFrame(trail["unmatched"]),
            use_container_width=True,
            hide_index=True,
            height=200,
        )
