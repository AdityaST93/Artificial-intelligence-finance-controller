"""
ui.components — Streamlit UI components for Razorpay connection, PDF upload,
Excel preview, and LLM agent response rendering.

Public surface:
  - razorpay_connection_section() -> None
  - pdf_upload_section()         -> None
  - excel_preview_section(result) -> None
  - agent_response_card(text)     -> None

All HTML rendering uses ``st.markdown(..., unsafe_allow_html=True)`` and the
class names from :mod:`ui.design_system` so the page stays visually consistent
with the rest of the Razorpay-inspired design system.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import streamlit as st

from core.pdf_ingest import parse_pdf
from core.razorpay_client import RazorpayClient

from ui.design_system import section_header


# ============================================================================
# 1) Razorpay connection section
# ============================================================================

def _ensure_rzp_client() -> RazorpayClient:
    """Return a cached RazorpayClient stored in st.session_state."""
    client = st.session_state.get("rzp_client")
    if client is None:
        client = RazorpayClient()
        st.session_state["rzp_client"] = client
    return client


def _connection_status_pill(ok: bool, message: str) -> str:
    """Render a coloured status pill (HTML) for the Razorpay connection."""
    if ok:
        bg = "linear-gradient(135deg, #10b981 0%, #34d399 100%)"
        icon = "✓"
    else:
        bg = "linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)"
        icon = "!"
    return (
        f'<div style="display:inline-flex; align-items:center; gap:8px; '
        f'padding:6px 12px; border-radius:999px; background:{bg}; '
        f'color:#0a2540; font-weight:700; font-size:0.78rem; '
        f'box-shadow:0 4px 12px -4px rgba(16,185,129,0.4);">'
        f'<span style="display:inline-flex; align-items:center; justify-content:center; '
        f'width:18px; height:18px; border-radius:50%; background:rgba(255,255,255,0.35); '
        f'font-size:0.7rem;">{icon}</span>'
        f'<span>{html.escape(message)}</span>'
        f'</div>'
    )


def razorpay_connection_section() -> None:
    """Render the Razorpay connection status + 'Pull data' controls.

    - Shows the result of :meth:`RazorpayClient.test_connection`.
    - Two buttons: "Pull latest payments" and "Pull latest settlements".
      Each calls the corresponding list_* method with ``count=50`` and stores
      the resulting DataFrame in ``st.session_state`` under
      ``rzp_payments_df`` / ``rzp_settlements_df``.
    - Renders the pulled data in an expander with a dataframe.
    - A toggle "Switch to live data" controls
      ``st.session_state["use_live_rzp_data"]`` so the reconciliation
      pipeline can opt-in to the freshly-pulled API data.
    """
    section_header(
        "Razorpay API",
        subtitle="Connect to the Razorpay REST API and pull live payments/settlements.",
    )

    client = _ensure_rzp_client()

    # --- Status pill ---
    ok, message = client.test_connection()
    st.markdown(_connection_status_pill(ok, message), unsafe_allow_html=True)

    if not client.has_real_keys:
        st.caption(
            "Running in **synthetic mode** — set `RAZORPAY_KEY_ID` and "
            "`RAZORPAY_KEY_SECRET` to pull real data. The buttons below will "
            "return the deterministic synthetic dataset from "
            "`data/synthetic/razorpay_settlement.csv`."
        )

    st.markdown("")

    # --- Pull buttons (side by side) ---
    col_pay, col_set = st.columns(2)
    with col_pay:
        pull_payments = st.button(
            "Pull latest payments",
            use_container_width=True,
            disabled=False,
            key="rzp_pull_payments",
        )
    with col_set:
        pull_settlements = st.button(
            "Pull latest settlements",
            use_container_width=True,
            disabled=False,
            key="rzp_pull_settlements",
        )

    if pull_payments:
        with st.spinner("Pulling payments from Razorpay…"):
            try:
                df = client.list_payments(count=50)
                st.session_state["rzp_payments_df"] = df
                st.session_state["rzp_payments_pulled_at"] = pd.Timestamp.now()
                st.success(f"✓ Pulled {len(df)} payment rows")
            except Exception as e:  # pragma: no cover - defensive
                st.error(f"Failed to pull payments: {e}")

    if pull_settlements:
        with st.spinner("Pulling settlements from Razorpay…"):
            try:
                df = client.list_settlements(count=50)
                st.session_state["rzp_settlements_df"] = df
                st.session_state["rzp_settlements_pulled_at"] = pd.Timestamp.now()
                st.success(f"✓ Pulled {len(df)} settlement rows")
            except Exception as e:  # pragma: no cover - defensive
                st.error(f"Failed to pull settlements: {e}")

    # --- Live-data toggle ---
    has_payments = "rzp_payments_df" in st.session_state
    has_settlements = "rzp_settlements_df" in st.session_state
    use_live = st.toggle(
        "Switch to live data (reconciliation uses pulled data)",
        value=st.session_state.get("use_live_rzp_data", False),
        disabled=not (has_payments or has_settlements),
        key="use_live_rzp_data",
        help=(
            "When on, the reconciliation engine reads from the pulled DataFrames "
            "above instead of the synthetic CSV. Disabled until at least one "
            "pull completes."
        ),
    )
    if use_live and not (has_payments or has_settlements):
        st.caption("Pull payments or settlements first to enable live mode.")

    # --- Show pulled data in an expander ---
    if has_payments or has_settlements:
        with st.expander("Pulled data (preview)", expanded=False):
            if has_payments:
                p_df: pd.DataFrame = st.session_state["rzp_payments_df"]
                ts = st.session_state.get("rzp_payments_pulled_at")
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts is not None else "—"
                st.markdown(
                    f"**Payments** · {len(p_df)} rows · pulled at {ts_str}"
                )
                st.dataframe(p_df, use_container_width=True, hide_index=True)
            if has_settlements:
                s_df: pd.DataFrame = st.session_state["rzp_settlements_df"]
                ts = st.session_state.get("rzp_settlements_pulled_at")
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if ts is not None else "—"
                st.markdown(
                    f"**Settlements** · {len(s_df)} rows · pulled at {ts_str}"
                )
                st.dataframe(s_df, use_container_width=True, hide_index=True)


# ============================================================================
# 2) PDF upload section
# ============================================================================

# Filename → kind mapping. Heuristics, content-based detection is the fallback.
_KIND_FILENAME_HINTS: list[tuple[str, str]] = [
    ("razorpay", "razorpay_settlement"),
    ("rzp",      "razorpay_settlement"),
    ("settle",   "razorpay_settlement"),
    ("bank",     "bank_statement"),
    ("statement", "bank_statement"),
    ("hdfc",     "bank_statement"),
    ("icici",    "bank_statement"),
    ("sbi",      "bank_statement"),
    ("axis",     "bank_statement"),
    ("gst",      "gst_invoice"),
    ("invoice",  "gst_invoice"),
    ("tax",      "gst_invoice"),
]


def _detect_kind_from_filename(name: str) -> str:
    """Return the best-guess kind based on the filename (lower-cased)."""
    n = name.lower()
    for token, kind in _KIND_FILENAME_HINTS:
        if token in n:
            return kind
    return "auto"


def _save_dataframe_to_synthetic(df: pd.DataFrame, kind: str, src_name: str) -> Path:
    """Write the parsed DataFrame to ``data/synthetic/`` using a kind-based name.

    Filenames mirror the existing synthetic files:
      - razorpay_settlement.csv  (append/overwrite)
      - bank_statement.csv       (append/overwrite)
      - gst_invoices.csv         (append/overwrite)
    """
    base = Path(__file__).resolve().parent.parent / "data" / "synthetic"
    base.mkdir(parents=True, exist_ok=True)

    target_map = {
        "razorpay_settlement": "razorpay_settlement.csv",
        "bank_statement":      "bank_statement.csv",
        "gst_invoice":         "gst_invoices.csv",
    }
    fname = target_map.get(kind, f"uploaded_{Path(src_name).stem}.csv")
    out = base / fname
    df.to_csv(out, index=False)
    return out


def pdf_upload_section() -> None:
    """Render the multi-PDF uploader, parser, preview, and save flow.

    For each uploaded file:
      1. Detect the kind from the filename (fallback: ``auto``).
      2. Run :func:`core.pdf_ingest.parse_pdf` with that kind.
      3. Show a preview of the parsed DataFrame.
      4. Expose a "Save to data/synthetic" button.
      5. Surface parser warnings as a single consolidated warning.
    """
    section_header(
        "PDF Upload",
        subtitle=(
            "Drop one or more financial PDFs (Razorpay settlement, bank statement, "
            "or GST invoice). We'll detect the kind, parse it, and let you save it "
            "into `data/synthetic/` for the next reconciliation run."
        ),
    )

    uploads = st.file_uploader(
        "Upload PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if not uploads:
        st.caption("No PDFs uploaded yet. Drop one or more files above to begin.")
        return

    # Lazy-init the per-session results store.
    if "pdf_results" not in st.session_state:
        st.session_state["pdf_results"] = []

    # We persist parsed results in session state keyed by file id so that
    # reruns don't re-parse the same upload.
    seen_ids = {r["file_id"] for r in st.session_state["pdf_results"]}

    for uploaded in uploads:
        if uploaded.file_id in seen_ids:
            continue

        # Write to a temp file so parse_pdf (which expects a path) can read it.
        tmp_dir = Path(st.session_state.get("pdf_tmp_dir", str(Path.cwd() / ".pdf_tmp")))
        tmp_dir.mkdir(parents=True, exist_ok=True)
        st.session_state["pdf_tmp_dir"] = str(tmp_dir)
        tmp_path = tmp_dir / uploaded.name
        with open(tmp_path, "wb") as f:
            f.write(uploaded.getbuffer())

        detected_kind = _detect_kind_from_filename(uploaded.name)
        try:
            result = parse_pdf(tmp_path, kind=detected_kind)
        except Exception as e:  # pragma: no cover - defensive
            result = None
            parse_error = repr(e)
        else:
            parse_error = None

        st.session_state["pdf_results"].append(
            {
                "file_id": uploaded.file_id,
                "name": uploaded.name,
                "size": uploaded.size,
                "detected_kind": detected_kind,
                "result": result,
                "parse_error": parse_error,
                "tmp_path": str(tmp_path),
                "saved_to": None,
            }
        )

    # Render a card per uploaded file.
    for i, entry in enumerate(list(st.session_state["pdf_results"])):
        name = entry["name"]
        kind = entry["detected_kind"]
        result = entry["result"]
        parse_error = entry["parse_error"]
        saved_to = entry.get("saved_to")

        kind_badge = {
            "razorpay_settlement": ("#3395ff", "Razorpay settlement"),
            "bank_statement":      ("#10b981", "Bank statement"),
            "gst_invoice":         ("#8b5cf6", "GST invoice"),
            "auto":                ("#94a3b8", "Auto-detect"),
            "unknown":             ("#94a3b8", "Unknown"),
        }.get(kind, ("#94a3b8", kind))

        with st.container(border=True):
            top = st.columns([0.7, 0.3])
            with top[0]:
                st.markdown(
                    f'<div style="font-weight:700; color:#0f172a;">'
                    f'{html.escape(name)}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with top[1]:
                color, label = kind_badge
                st.markdown(
                    f'<div style="text-align:right;">'
                    f'<span style="display:inline-block; padding:3px 10px; '
                    f'border-radius:999px; background:{color}; color:#fff; '
                    f'font-size:0.72rem; font-weight:700; letter-spacing:0.04em;">'
                    f'{html.escape(label)}</span></div>',
                    unsafe_allow_html=True,
                )

            if parse_error is not None:
                st.error(f"Parser raised an exception: `{parse_error}`")
                continue

            if result is None:
                st.warning("Parser returned no result.")
                continue

            warnings: list[str] = list(result.warnings or [])
            if not result.ok:
                st.warning(
                    "Could not extract tabular data from this PDF. "
                    + (" | ".join(warnings) if warnings else "Try a different file.")
                )
            elif warnings:
                st.warning(" | ".join(warnings))

            # Show the parsed DataFrame preview.
            if not result.df.empty:
                st.caption(
                    f"{len(result.df)} rows · {len(result.df.columns)} cols · "
                    f"source: `{result.source}` · {result.pages} page(s)"
                )
                st.dataframe(
                    result.df.head(50),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Empty DataFrame — nothing to preview.")

            # Save button (only if we have actual rows).
            save_disabled = result.df.empty or kind not in {
                "razorpay_settlement", "bank_statement", "gst_invoice"
            }
            save_label = "Save to data/synthetic"
            if saved_to:
                save_label = f"✓ Saved to {saved_to}"
            if st.button(
                save_label,
                key=f"save_pdf_{i}",
                disabled=save_disabled or bool(saved_to),
                use_container_width=False,
            ):
                try:
                    out = _save_dataframe_to_synthetic(result.df, kind, name)
                    entry["saved_to"] = str(out)
                    st.success(f"Saved → `{out}`")
                except Exception as e:  # pragma: no cover - defensive
                    st.error(f"Failed to save: {e}")


# ============================================================================
# 3) Excel preview section
# ============================================================================

def _coerce_to_bytes(value: Any) -> bytes | None:
    """Accept bytes, bytearray, BytesIO, or a file-like object and return bytes."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if hasattr(value, "getvalue"):
        try:
            return value.getvalue()
        except Exception:  # pragma: no cover - defensive
            return None
    if hasattr(value, "read"):
        try:
            return value.read()
        except Exception:  # pragma: no cover - defensive
            return None
    return None


def _read_workbook_safely(raw: bytes) -> dict[str, pd.DataFrame] | None:
    """Read an .xlsx byte stream into a dict of sheet_name -> DataFrame.

    Returns None on failure.
    """
    if not raw:
        return None
    try:
        from io import BytesIO
        return pd.read_excel(BytesIO(raw), sheet_name=None)
    except Exception:  # pragma: no cover - defensive
        return None


def _table_html(sheet_name: str, df: pd.DataFrame, max_rows: int = 5) -> str:
    """Render a tiny HTML preview of a sheet's head as a compact table."""
    if df is None or df.empty:
        body = (
            '<tr><td colspan="1" style="padding:8px; color:#64748b; '
            'font-style:italic;">(empty sheet)</td></tr>'
        )
        header_cells = ""
    else:
        headers = [html.escape(str(c)) for c in df.columns]
        header_cells = "".join(
            f'<th style="text-align:left; padding:8px 10px; '
            f'background:linear-gradient(90deg, #0a2540 0%, #0e3a66 100%); '
            f'color:#fff; font-weight:600; font-size:0.78rem; '
            f'border-bottom:1px solid rgba(255,255,255,0.1);">{h}</th>'
            for h in headers
        )
        rows_html = []
        for _, row in df.head(max_rows).iterrows():
            cells = "".join(
                f'<td style="padding:6px 10px; border-bottom:1px solid #e2e8f0; '
                f'font-family:"JetBrains Mono", ui-monospace, monospace; '
                f'font-size:0.78rem; color:#334155;">{html.escape(str(v) if v is not None else "")}</td>'
                for v in row.values
            )
            rows_html.append(f"<tr>{cells}</tr>")
        body = "".join(rows_html)

    return (
        f'<table style="width:100%; border-collapse:collapse; '
        f'border:1px solid #e2e8f0; border-radius:10px; overflow:hidden; '
        f'box-shadow:0 1px 3px rgba(15, 23, 42, 0.04);">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{body}</tbody>'
        f'</table>'
    )


def excel_preview_section(result: Any) -> None:
    """Render an HTML preview of the Excel export structure.

    Tries (in order):
      1. The bytes in ``result.excel_bytes`` (preferred — no re-export).
      2. Calling ``core.exporter.export_excel(result)`` and reading the result.

    For each sheet, displays: sheet name, row count, column header list, and
    a 5-row preview table.
    """
    section_header(
        "Excel export preview",
        subtitle=(
            "Structural preview of the reconciliation workbook (5 sheets). "
            "Use it to sanity-check what will land in the download before pulling it."
        ),
    )

    if result is None:
        st.caption("Run reconciliation to preview the Excel export.")
        return

    # 1) Try the pre-rendered bytes first.
    raw = None
    excel_attr = getattr(result, "excel_bytes", None)
    if excel_attr is not None:
        raw = _coerce_to_bytes(excel_attr)

    # 2) Fallback: re-export on the fly.
    if raw is None:
        try:
            from core.exporter import export_excel
            buf = export_excel(result)
            raw = _coerce_to_bytes(buf)
        except Exception as e:  # pragma: no cover - defensive
            st.error(f"Could not produce Excel preview: {e}")
            return

    if not raw:
        st.error("Excel export produced no bytes.")
        return

    sheets = _read_workbook_safely(raw)
    if not sheets:
        st.error("Could not parse the Excel bytes for preview.")
        return

    # Sheet summary table (top of the section).
    rows_summary = []
    for name, df in sheets.items():
        rows_summary.append(
            {
                "Sheet": name,
                "Rows": 0 if df is None else len(df),
                "Columns": 0 if df is None else len(df.columns),
            }
        )
    summary_df = pd.DataFrame(rows_summary)
    st.markdown(
        '<div style="margin: 0.2rem 0 0.8rem 0; font-size: 0.86rem; '
        'color:#475569; font-weight:600;">Workbook structure</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    # Per-sheet preview.
    st.markdown(
        '<div style="margin: 0.8rem 0 0.4rem 0; font-size: 0.86rem; '
        'color:#475569; font-weight:600;">Sheet previews (first 5 rows)</div>',
        unsafe_allow_html=True,
    )

    for name, df in sheets.items():
        n_rows = 0 if df is None else len(df)
        n_cols = 0 if df is None else len(df.columns)
        cols_list = (
            " · ".join(f"`{c}`" for c in df.columns) if df is not None and n_cols else "—"
        )
        st.markdown(
            f'<div style="margin: 0.6rem 0 0.2rem 0;">'
            f'<span style="font-weight:700; color:#0a2540;">{html.escape(name)}</span>'
            f'<span style="color:#64748b; font-size:0.82rem; margin-left:8px;">'
            f'{n_rows} rows · {n_cols} columns</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="font-size:0.74rem; color:#94a3b8; margin-bottom:4px;">'
            f'{cols_list}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(_table_html(name, df if df is not None else pd.DataFrame()), unsafe_allow_html=True)


# ============================================================================
# 4) Agent response card
# ============================================================================

# Payment IDs: pay_ + 14 alnum chars (Razorpay convention)
_PAYMENT_ID_RE = re.compile(r"\b(pay_[A-Za-z0-9]{6,18})\b")
# UTRs: 10-18 uppercase alnum (bank UTR / RRN)
_UTR_RE = re.compile(r"\b([A-Z0-9]{10,18})\b")
# Invoice numbers: simple heuristic — letters + digits + dashes/underscores, 4+ chars
_INV_RE = re.compile(
    r"\b((?:INV|RCP|REC|BILL|RZ|ORD)[A-Z0-9_\-]{3,20}|[A-Z]{2,4}[-/]\d{3,12}[-/]?[A-Z0-9]{0,8})\b",
    re.IGNORECASE,
)
# Amounts: Rs/INR/₹ prefix, optional commas + decimals, optional parentheses
_AMOUNT_RE = re.compile(
    r"(?<![A-Za-z])(Rs\.?|INR|₹)\s*\(?\s*-?[\d][\d,]*(?:\.\d{1,2})?\s*\)?"
    r"|(?<![A-Za-z])₹\s*-?[\d][\d,]*(?:\.\d{1,2})?"
    r"|(?<![A-Za-z])-?\(?₹\s*[\d][\d,]*(?:\.\d{1,2})?\)?",
)
# *** markers: any run of * (3 or more)
_ASTERISK_RE = re.compile(r"\*{3,}")


def _classify_token(token: str) -> str:
    """Decide whether a candidate token is pay_id / utr / invoice / amount."""
    if _PAYMENT_ID_RE.fullmatch(token):
        return "pay"
    # If it has pay_ prefix, force pay even if the regex above missed.
    if token.lower().startswith("pay_") and len(token) >= 6:
        return "pay"
    if _INV_RE.fullmatch(token):
        return "inv"
    if _UTR_RE.fullmatch(token) and token.isupper() and any(c.isdigit() for c in token):
        return "utr"
    return "other"


def _inline_code(text: str) -> str:
    return (
        f'<code style="background:rgba(51, 149, 255, 0.12); color:#0a2540; '
        f'padding:1px 6px; border-radius:6px; font-family:"JetBrains Mono", '
        f'ui-monospace, monospace; font-size:0.86em; font-weight:600;">'
        f'{html.escape(text)}</code>'
    )


def _bold_money(text: str) -> str:
    return (
        f'<strong style="color:#0a2540; font-weight:800; '
        f'font-family:"JetBrains Mono", ui-monospace, monospace;">'
        f'{html.escape(text)}</strong>'
    )


def _red_badge(text: str) -> str:
    return (
        f'<span style="display:inline-block; padding:1px 8px; margin:0 2px; '
        f'border-radius:999px; background:linear-gradient(135deg, #ef4444 0%, #f87171 100%); '
        f'color:#fff; font-size:0.72rem; font-weight:800; letter-spacing:0.04em; '
        f'text-transform:uppercase; box-shadow:0 2px 6px -2px rgba(239,68,68,0.5);">'
        f'{html.escape(text)}</span>'
    )


def _convert_markdown_to_html(text: str) -> str:
    """Light-touch markdown conversion: bold + bullet lists + paragraphs.

    Streamlit already renders markdown in chat_message, but ``agent_response_card``
    is meant to be a *card* — a single styled box. We do just enough to keep
    the agent's structured output readable.
    """
    out_lines: list[str] = []
    in_list = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()
        if stripped.startswith(("- ", "* ")):
            if not in_list:
                out_lines.append('<ul style="margin: 0.3rem 0 0.6rem 1.2rem; padding:0;">')
                in_list = True
            out_lines.append(
                f'<li style="margin: 0.15rem 0; color:#334155;">'
                f'{html.escape(stripped[2:])}</li>'
            )
        else:
            if in_list:
                out_lines.append("</ul>")
                in_list = False
            if not line:
                out_lines.append('<div style="height:0.4rem;"></div>')
            else:
                # **bold**
                line_esc = html.escape(line)
                line_esc = re.sub(
                    r"\*\*(.+?)\*\*",
                    r'<strong style="color:#0f172a;">\1</strong>',
                    line_esc,
                )
                out_lines.append(
                    f'<div style="margin: 0.1rem 0; color:#334155; line-height:1.55;">'
                    f'{line_esc}</div>'
                )
    if in_list:
        out_lines.append("</ul>")
    return "".join(out_lines)


def _enrich_text(text: str) -> str:
    """Replace detected tokens with styled HTML fragments.

    We walk the string with a combined regex of all token types so we don't
    double-substitute (payment IDs and invoice numbers can overlap on word
    boundaries). The walker operates left-to-right; whichever match fires
    first wins.
    """
    if not text:
        return ""

    # Build a single alternation regex with named groups so we know which kind
    # fired at each position.
    pattern = re.compile(
        "|".join(
            [
                rf"(?P<pay>{_PAYMENT_ID_RE.pattern})",
                rf"(?P<inv>{_INV_RE.pattern})",
                rf"(?P<utr>{_UTR_RE.pattern})",
                rf"(?P<amt>{_AMOUNT_RE.pattern})",
                rf"(?P<ast>{_ASTERISK_RE.pattern})",
            ]
        )
    )

    parts: list[str] = []
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            parts.append(html.escape(text[pos:m.start()]))
        kind = m.lastgroup
        raw = m.group(0)
        if kind == "pay":
            parts.append(_inline_code(raw))
        elif kind == "inv":
            # Avoid double-flagging payment IDs (they don't match _INV_RE,
            # but the amount regex may match things like Rs. 1,000 in mid-word).
            parts.append(_inline_code(raw))
        elif kind == "utr":
            # Make sure UTR isn't a payment ID we've already styled.
            if _PAYMENT_ID_RE.fullmatch(raw):
                parts.append(_inline_code(raw))
            else:
                parts.append(_inline_code(raw))
        elif kind == "amt":
            parts.append(_bold_money(raw))
        elif kind == "ast":
            # Use the *run* as a generic attention badge. Strip the asterisks.
            tag = raw.strip("*") or "flag"
            parts.append(_red_badge(tag))
        pos = m.end()
    if pos < len(text):
        parts.append(html.escape(text[pos:]))
    return "".join(parts)


def agent_response_card(text: str) -> None:
    """Render an LLM response in a styled card.

    - Payment IDs (``pay_XXX``), UTRs (10-18 alnum, uppercase), and invoice
      numbers are wrapped as inline ``<code>`` chips.
    - Amounts (Rs/INR/₹ prefixed) are rendered in **bold** with the prefix
      preserved.
    - Runs of three or more ``*`` characters (``***``) become red badges.
    - Light markdown (bold, bullets) is also honoured.
    """
    if not text:
        st.markdown(
            '<div class="rp-glass" style="color:#64748b; font-style:italic;">'
            '(no response)</div>',
            unsafe_allow_html=True,
        )
        return

    # First do markdown-light (so the ** markers don't get confused for ***).
    md_html = _convert_markdown_to_html(text)
    # Then enrich the text-only view (so we operate on raw text). To keep
    # things simple and predictable, we run enrichment on the *original* text
    # (so token detection is robust), and stack it under a small "summary"
    # line if both differ significantly.
    enriched = _enrich_text(text)

    # Combine: prefer the enriched (token-styled) view as the primary body,
    # but if the markdown version added structural HTML (lists/paragraphs)
    # we render that as the "structured" view underneath.
    body = (
        f'<div style="margin: 0.2rem 0 0.6rem 0; line-height:1.6;">{enriched}</div>'
    )
    if md_html and md_html != enriched and len(md_html) > len(enriched) + 20:
        body += (
            '<details style="margin-top: 0.6rem;">'
            '<summary style="cursor:pointer; color:#3395ff; font-size:0.78rem; '
            'font-weight:600;">Show structured view</summary>'
            f'<div style="margin-top: 0.4rem;">{md_html}</div>'
            '</details>'
        )

    st.markdown(
        f'<div class="rp-glass" style="border-left: 3px solid #3395ff; '
        f'padding: 0.9rem 1.1rem; margin: 0.3rem 0 0.8rem 0;">'
        f'<div style="display:flex; align-items:center; gap:8px; margin-bottom: 0.4rem;">'
        f'<span style="display:inline-flex; align-items:center; justify-content:center; '
        f'width:24px; height:24px; border-radius:8px; '
        f'background:linear-gradient(135deg, #3395ff 0%, #00d4ff 100%); '
        f'color:#0a2540; font-weight:800; font-size:0.72rem;">AI</span>'
        f'<span style="font-size:0.72rem; color:#64748b; font-weight:700; '
        f'text-transform:uppercase; letter-spacing:0.06em;">Agent response</span>'
        f'</div>'
        f'{body}'
        f'</div>',
        unsafe_allow_html=True,
    )


__all__ = [
    "razorpay_connection_section",
    "pdf_upload_section",
    "excel_preview_section",
    "agent_response_card",
]
