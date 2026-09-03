"""
PDF and Excel export for reconciliation reports.

Two public functions:
  - export_excel(result, output_path): produces a 5-sheet .xlsx workbook
  - export_pdf_report(result, output_path): produces a multi-page PDF

The exporter is defensive — it accepts either a real ReconcileResult or any
duck-typed object with .df, .exceptions, and .metrics attributes. Empty
DataFrames and missing keys are handled gracefully.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

logger = logging.getLogger(__name__)

# Suggested action per documented exception category.
# Mirrors the taxonomy in app.py.
SUGGESTED_ACTIONS: dict[str, str] = {
    "missing_bank_credit": "Wait 24h for settlement; raise with Razorpay support if still missing",
    "orphan_bank_credit": "Investigate; log to suspense ledger and reconcile manually",
    "amount_mismatch": "Compare fee schedule; raise dispute if fee variance > Rs 0.05",
    "oms_amount_mismatch": "Reconcile cart; refund/adjust OMS order",
    "missing_oms_order": "Investigate; possibly fraud — escalate to risk team",
    "ghost_oms_order": "Verify with customer; flag for fraud review",
    "cancelled_order_with_payment": "Initiate refund via Razorpay API",
    "fee_rate_variance": "Update fee schedule; raise with account manager",
    "gst_amount_mismatch": "Regenerate invoice; fix tax engine",
    "missing_gst_invoice": "Generate invoice; late-file if past due",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_metrics(result: Any) -> dict:
    if hasattr(result, "metrics") and isinstance(result.metrics, dict):
        return result.metrics
    return {}


def _get_df(result: Any, name: str) -> pd.DataFrame:
    """Return result.df (matched) or result.exceptions, defensively."""
    attr = "exceptions" if name == "exceptions" else "df"
    if hasattr(result, attr):
        val = getattr(result, attr)
        if isinstance(val, pd.DataFrame):
            return val
    return pd.DataFrame()


def _autosize_columns(ws, max_width: int = 60) -> None:
    """Set column widths based on max content length, capped at max_width."""
    for col_idx, col_cells in enumerate(ws.columns, start=1):
        try:
            max_len = max(
                (len(str(c.value)) for c in col_cells if c.value is not None),
                default=10,
            )
        except Exception:
            max_len = 10
        # Header row + cell content + small padding
        width = min(max(max_len + 2, 10), max_width)
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width


def _apply_header_style(ws, header_fill: str = "FF1F2937", font_color: str = "FFFFFFFF") -> None:
    """Bold + colored background + white text on the header row."""
    from openpyxl.styles import Font, PatternFill, Alignment

    bold_font = Font(bold=True, color=font_color, size=11)
    fill = PatternFill(start_color=header_fill, end_color=header_fill, fill_type="solid")
    align = Alignment(horizontal="left", vertical="center")
    for cell in ws[1]:
        cell.font = bold_font
        cell.fill = fill
        cell.alignment = align
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def export_excel(result: Any, output_path: str | Path) -> Path:
    """
    Create a 5-sheet .xlsx workbook for the reconciliation result.

    Sheets:
      1. Summary              — KPIs + by-category counts
      2. Matched              — every matched record (result.df)
      3. Exceptions           — every exception with category, reason, suggested action
      4. By Category          — exception breakdown with counts
      5. GST Reconciliation   — match results from result.df (subset where GST join succeeded)

    Returns the output Path.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    metrics = _get_metrics(result)
    matched_df = _get_df(result, "df")
    exceptions_df = _get_df(result, "exceptions")

    wb = Workbook()
    wb.remove(wb.active)  # we'll add our own

    # ------------------------------------------------------------------
    # Sheet 1: Summary
    # ------------------------------------------------------------------
    ws = wb.create_sheet("Summary")
    ws["A1"] = "Razorpay AI Finance Controller — Reconciliation Summary"
    ws["A1"].font = Font(bold=True, size=16, color="FF1F2937")
    ws.merge_cells("A1:D1")
    ws.row_dimensions[1].height = 26

    ws["A2"] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws["A2"].font = Font(italic=True, color="FF6B7280")
    ws.merge_cells("A2:D2")

    # KPI block
    ws["A4"] = "Key Metrics"
    ws["A4"].font = Font(bold=True, size=13, color="FF1F2937")

    kpi_rows: list[tuple[str, Any]] = [
        ("Match rate", f"{metrics.get('match_rate', 0):.2%}"),
        ("Clean payments", metrics.get("clean_payments", 0)),
        ("Total input records", metrics.get("total_input_records", 0)),
        ("Razorpay payments", metrics.get("razorpay_payments", 0)),
        ("Bank credits", metrics.get("bank_credits", 0)),
        ("OMS orders", metrics.get("oms_orders", 0)),
        ("GST invoices", metrics.get("gst_invoices", 0)),
        ("Tier-1 matched payments", metrics.get("tier1_matched_payments", 0)),
        ("Tier-1 match attempts", metrics.get("tier1_match_attempts", 0)),
        ("Exception count", metrics.get("tier1_exceptions", len(exceptions_df))),
    ]

    kpi_header_fill = PatternFill(start_color="FF1F2937", end_color="FF1F2937", fill_type="solid")
    kpi_value_fill = PatternFill(start_color="FFF3F4F6", end_color="FFF3F4F6", fill_type="solid")
    border = Border(
        left=Side(style="thin", color="FFD1D5DB"),
        right=Side(style="thin", color="FFD1D5DB"),
        top=Side(style="thin", color="FFD1D5DB"),
        bottom=Side(style="thin", color="FFD1D5DB"),
    )

    ws.cell(row=5, column=1, value="Metric").font = Font(bold=True, color="FFFFFFFF")
    ws.cell(row=5, column=1).fill = kpi_header_fill
    ws.cell(row=5, column=2, value="Value").font = Font(bold=True, color="FFFFFFFF")
    ws.cell(row=5, column=2).fill = kpi_header_fill

    for i, (k, v) in enumerate(kpi_rows, start=6):
        ws.cell(row=i, column=1, value=k).border = border
        ws.cell(row=i, column=2, value=v).border = border
        ws.cell(row=i, column=2).fill = kpi_value_fill
        ws.cell(row=i, column=1).font = Font(bold=True)

    # By Category block
    cats: Mapping[str, int] = metrics.get("exception_categories", {}) or {}
    cat_start = 6 + len(kpi_rows) + 2

    ws.cell(row=cat_start, column=1, value="Exception Categories").font = Font(bold=True, size=13, color="FF1F2937")
    ws.cell(row=cat_start + 1, column=1, value="Category").font = Font(bold=True, color="FFFFFFFF")
    ws.cell(row=cat_start + 1, column=1).fill = kpi_header_fill
    ws.cell(row=cat_start + 1, column=2, value="Count").font = Font(bold=True, color="FFFFFFFF")
    ws.cell(row=cat_start + 1, column=2).fill = kpi_header_fill

    if cats:
        for i, (cat, count) in enumerate(
            sorted(cats.items(), key=lambda kv: kv[1], reverse=True), start=cat_start + 2
        ):
            ws.cell(row=i, column=1, value=cat).border = border
            ws.cell(row=i, column=2, value=count).border = border
            ws.cell(row=i, column=2).fill = kpi_value_fill
    else:
        ws.cell(row=cat_start + 2, column=1, value="(no exceptions)").font = Font(italic=True, color="FF6B7280")

    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 22

    # ------------------------------------------------------------------
    # Sheet 2: Matched
    # ------------------------------------------------------------------
    ws_matched = wb.create_sheet("Matched")
    if not matched_df.empty:
        # Drop noisy columns
        cols = [c for c in matched_df.columns if c not in {"_merge", "level_0", "index"}]
        ws_matched.append(cols)
        # Coerce datetime cells to string for safe xlsx write
        for row in matched_df[cols].itertuples(index=False, name=None):
            ws_matched.append([_excel_safe(v) for v in row])
        _apply_header_style(ws_matched)
        _autosize_columns(ws_matched)
    else:
        ws_matched["A1"] = "(no matched records)"
        ws_matched["A1"].font = Font(italic=True, color="FF6B7280")

    # ------------------------------------------------------------------
    # Sheet 3: Exceptions
    # ------------------------------------------------------------------
    ws_exc = wb.create_sheet("Exceptions")
    if not exceptions_df.empty:
        base_cols = [c for c in exceptions_df.columns if c not in {"_merge", "level_0", "index"}]
        # We'll write: base columns + "suggested_action"
        header = list(base_cols) + ["suggested_action"]
        ws_exc.append(header)
        for _, r in exceptions_df.iterrows():
            row_vals = [_excel_safe(r.get(c)) for c in base_cols]
            cat = r.get("exception_category")
            row_vals.append(SUGGESTED_ACTIONS.get(cat, "Investigate; manual review"))
            ws_exc.append(row_vals)
        _apply_header_style(ws_exc, header_fill="FFB91C1C")
        _autosize_columns(ws_exc)
    else:
        ws_exc["A1"] = "No exceptions — clean reconciliation!"
        ws_exc["A1"].font = Font(italic=True, color="FF059669", bold=True)

    # ------------------------------------------------------------------
    # Sheet 4: By Category
    # ------------------------------------------------------------------
    ws_cat = wb.create_sheet("By Category")
    ws_cat.append(["Category", "Count", "Suggested Action"])
    if cats:
        for cat, count in sorted(cats.items(), key=lambda kv: kv[1], reverse=True):
            ws_cat.append([cat, int(count), SUGGESTED_ACTIONS.get(cat, "Investigate; manual review")])
    else:
        ws_cat.append(["(none)", 0, ""])
    _apply_header_style(ws_cat, header_fill="FF0E7490")
    _autosize_columns(ws_cat)

    # ------------------------------------------------------------------
    # Sheet 5: GST Reconciliation
    # ------------------------------------------------------------------
    ws_gst = wb.create_sheet("GST Reconciliation")
    gst_cols = [
        "payment_id", "invoice_no", "taxable_value", "cgst", "sgst", "total",
        "razorpay_payment_id", "status", "tier", "reason",
    ]
    if not matched_df.empty:
        gst_view = matched_df[[c for c in gst_cols if c in matched_df.columns]].copy()
        if gst_view.empty:
            # Fallback: include all matched rows, not just GST-joined ones
            gst_view = matched_df.copy()
        ws_gst.append(list(gst_view.columns))
        for row in gst_view.itertuples(index=False, name=None):
            ws_gst.append([_excel_safe(v) for v in row])
        _apply_header_style(ws_gst, header_fill="FF065F46")
        _autosize_columns(ws_gst)
    else:
        ws_gst["A1"] = "(no GST match data)"
        ws_gst["A1"].font = Font(italic=True, color="FF6B7280")

    wb.save(out)
    logger.info(f"Wrote Excel report to {out}")
    return out


def _excel_safe(v: Any) -> Any:
    """Coerce a value to something openpyxl can write safely."""
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, float):
        return round(v, 2)
    return v


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

def export_pdf_report(result: Any, output_path: str | Path) -> Path:
    """
    Generate a multi-page PDF report for the reconciliation result.

    Pages:
      1. Cover                  — title, date, key metrics in a framed box
      2. Executive summary      — match rate, exception count, bar chart
      3. Exception details      — top 20 exceptions as a table
      4+ Per-record audit trail — one paragraph per exception
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
        KeepTogether,
    )
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderPDF
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    metrics = _get_metrics(result)
    matched_df = _get_df(result, "df")
    exceptions_df = _get_df(result, "exceptions")
    cats: Mapping[str, int] = metrics.get("exception_categories", {}) or {}
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=22, textColor=colors.HexColor("#1F2937"), spaceAfter=14)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=15, textColor=colors.HexColor("#1F2937"), spaceAfter=10)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=12, textColor=colors.HexColor("#374151"), spaceAfter=8)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=6)
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=8, textColor=colors.HexColor("#6B7280"))
    centered = ParagraphStyle("Centered", parent=styles["BodyText"], fontSize=11, alignment=TA_CENTER)

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        footer_text = f"Generated by Razorpay AI Finance Controller  |  {timestamp}  |  Page {doc.page}"
        canvas.drawCentredString(A4[0] / 2.0, 12 * mm, footer_text)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Razorpay Reconciliation Report",
        author="Razorpay AI Finance Controller",
    )

    story: list = []

    # ==================================================================
    # Page 1 — Cover
    # ==================================================================
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph("Razorpay AI Finance Controller", h1))
    story.append(Paragraph("Reconciliation Report", h2))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(f"Generated: {timestamp}", body))
    story.append(Paragraph(
        "Multi-source reconciliation across Razorpay settlements, bank credits, OMS orders, and GST invoices.",
        body,
    ))
    story.append(Spacer(1, 1.2 * cm))

    # KPI box
    match_rate = float(metrics.get("match_rate", 0) or 0)
    clean = int(metrics.get("clean_payments", 0) or 0)
    total = int(metrics.get("total_input_records", 0) or 0)
    exc_count = int(metrics.get("tier1_exceptions", len(exceptions_df)) or 0)

    kpi_data = [
        ["Key Metric", "Value"],
        ["Match rate", f"{match_rate:.2%}"],
        ["Clean payments", str(clean)],
        ["Total input records", str(total)],
        ["Exception count", str(exc_count)],
    ]
    kpi_table = Table(kpi_data, colWidths=[6 * cm, 6 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#1F2937")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F9FAFB"), colors.white]),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "<i>This report covers Tier-1 (deterministic) reconciliation across 4 sources, "
        "with exception taxonomy and per-record audit trail.</i>",
        small,
    ))
    story.append(PageBreak())

    # ==================================================================
    # Page 2 — Executive summary + bar chart
    # ==================================================================
    story.append(Paragraph("Executive Summary", h1))
    story.append(Paragraph(
        f"Out of <b>{total}</b> input records across 4 sources, <b>{clean}</b> Razorpay payments "
        f"reconciled cleanly (<b>{match_rate:.2%}</b> match rate). "
        f"<b>{exc_count}</b> exceptions were detected, distributed across "
        f"<b>{len(cats)}</b> documented categories.",
        body,
    ))
    story.append(Spacer(1, 0.4 * cm))

    if cats:
        story.append(Paragraph("Exceptions by category", h3))
        # Bar chart
        drawing = Drawing(450, 200)
        bc = VerticalBarChart()
        bc.x = 50
        bc.y = 30
        bc.height = 140
        bc.width = 360
        bc.data = [list(cats.values())]
        bc.categoryAxis.categoryNames = list(cats.keys())
        bc.bars[0].fillColor = colors.HexColor("#3B82F6")
        bc.valueAxis.valueMin = 0
        bc.valueAxis.valueMax = max(cats.values()) * 1.2 if cats else 1
        bc.categoryAxis.labels.fontSize = 7
        bc.categoryAxis.labels.angle = 30
        bc.valueAxis.labels.fontSize = 8
        drawing.add(bc)
        story.append(drawing)
        story.append(Spacer(1, 0.4 * cm))

        cat_rows = [["Category", "Count", "Suggested Action"]]
        for cat, count in sorted(cats.items(), key=lambda kv: kv[1], reverse=True):
            cat_rows.append([
                cat,
                str(int(count)),
                SUGGESTED_ACTIONS.get(cat, "Investigate"),
            ])
        cat_table = Table(cat_rows, colWidths=[5 * cm, 1.5 * cm, 10.5 * cm])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0E7490")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#0E7490")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F0F9FF"), colors.white]),
        ]))
        story.append(cat_table)
    else:
        story.append(Paragraph("No exceptions — clean reconciliation!", body))

    story.append(PageBreak())

    # ==================================================================
    # Page 3 — Exception details (top 20)
    # ==================================================================
    story.append(Paragraph("Exception Details (Top 20)", h1))
    if exceptions_df.empty:
        story.append(Paragraph("No exceptions detected.", body))
    else:
        story.append(Paragraph(
            f"Showing the first 20 of {len(exceptions_df)} exceptions. Each row links a payment "
            "to its category, reason, and recommended action.",
            body,
        ))
        story.append(Spacer(1, 0.3 * cm))

        detail_rows = [["#", "Payment ID", "Category", "Reason"]]
        top = exceptions_df.head(20)
        for idx, (_, r) in enumerate(top.iterrows(), start=1):
            pid = str(r.get("payment_id") or "—")
            cat = str(r.get("exception_category") or "—")
            reason = str(r.get("reason") or "—")
            # Truncate long reasons for layout
            if len(reason) > 60:
                reason = reason[:57] + "…"
            detail_rows.append([str(idx), pid, cat, reason])

        detail_table = Table(detail_rows, colWidths=[0.8 * cm, 3.5 * cm, 4.2 * cm, 8.5 * cm], repeatRows=1)
        detail_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B91C1C")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#B91C1C")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FEF2F2"), colors.white]),
        ]))
        story.append(detail_table)
    story.append(PageBreak())

    # ==================================================================
    # Page 4+ — Per-record audit trail
    # ==================================================================
    story.append(Paragraph("Per-Record Audit Trail", h1))
    if exceptions_df.empty:
        story.append(Paragraph("No exceptions to audit.", body))
    else:
        story.append(Paragraph(
            f"One entry per exception ({len(exceptions_df)} total). Each shows the payment ID, "
            "category, reason, and the suggested next step.",
            body,
        ))
        story.append(Spacer(1, 0.3 * cm))

        for i, (_, r) in enumerate(exceptions_df.iterrows(), start=1):
            pid = str(r.get("payment_id") or "—")
            cat = str(r.get("exception_category") or "—")
            reason = str(r.get("reason") or "—")
            action = SUGGESTED_ACTIONS.get(cat, "Investigate; manual review")
            amount = r.get("amount")
            try:
                amount_str = f"Rs {float(amount):,.2f}" if amount not in (None, "") else "—"
            except Exception:
                amount_str = str(amount) if amount else "—"

            block = [
                Paragraph(f"<b>Exception {i}</b>", h3),
                Paragraph(f"<b>Payment ID:</b> {pid} &nbsp;&nbsp; <b>Amount:</b> {amount_str}", body),
                Paragraph(f"<b>Category:</b> {cat}", body),
                Paragraph(f"<b>Reason:</b> {reason}", body),
                Paragraph(f"<b>Suggested action:</b> {action}", body),
                Spacer(1, 0.3 * cm),
            ]
            story.append(KeepTogether(block))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    logger.info(f"Wrote PDF report to {out}")
    return out


__all__ = ["export_excel", "export_pdf_report", "SUGGESTED_ACTIONS"]
