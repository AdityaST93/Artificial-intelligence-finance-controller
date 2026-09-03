"""
Tests for core/pdf_ingest.py.

We don't ship real Razorpay PDFs in the repo. The tests therefore generate
small synthetic PDFs on the fly with reportlab and parse them with the new
``parse_pdf`` API. This keeps the test self-contained while exercising the
real pdfplumber + pymupdf4llm code paths.

Three tests, per the task:
  1. test_parses_razorpay_sample_pdf  — happy path
  2. test_handles_corrupt_pdf_gracefully — bad file does not raise
  3. test_auto_detects_kind — auto kind is identified from headers
"""

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

# Project root on sys.path so ``from core.pdf_ingest import ...`` works
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pdf_ingest import (
    PDFParseResult,
    detect_kind,
    parse_pdf,
)


# ---------------------------------------------------------------------------
# Helpers — build tiny PDF fixtures with reportlab
# ---------------------------------------------------------------------------

def _build_pdf(path: Path, draw_fn) -> Path:
    """Build a one-page PDF by calling ``draw_fn(elements)`` with a Platypus
    list-builder. We use reportlab.platypus.Table so pdfplumber can recover
    the cell structure reliably."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    doc = SimpleDocTemplate(
        str(path), pagesize=letter,
        leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    story = draw_fn(Paragraph, Spacer, Table, TableStyle, colors, styles)
    doc.build(story)
    return path


def _draw_razorpay_settlement(Paragraph, Spacer, Table, TableStyle, colors, styles):
    title = Paragraph("<b>Razorpay Settlement Report</b>", styles["Title"])
    headers = [
        "Entity", "Payment ID", "Amount", "Fee", "Tax", "Credit", "Debit",
        "On Hold", "Settlement UTR", "Created At", "Settled At", "Method",
    ]
    rows = [
        headers,
        ["payment", "pay_P0001", "1000.00", "20.00", "3.60", "976.40", "0.00",
         "No", "UTR1234567890", "2026-01-15 10:00:00", "2026-01-17 10:00:00", "upi"],
        ["payment", "pay_P0002", "500.50", "10.00", "1.80", "488.70", "0.00",
         "No", "UTR1234567891", "2026-01-15 11:00:00", "2026-01-17 11:00:00", "card"],
        ["refund", "pay_P0003", "200.00", "0.00", "0.00", "0.00", "200.00",
         "No", "UTR1234567892", "2026-01-16 09:00:00", "2026-01-18 09:00:00", "netbanking"],
    ]
    tbl = Table(rows, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))
    return [title, Spacer(1, 12), tbl]


def _draw_bank_statement(Paragraph, Spacer, Table, TableStyle, colors, styles):
    title = Paragraph("<b>Bank Statement</b>", styles["Title"])
    headers = ["Date", "Narration", "UTR", "Debit", "Credit", "Balance"]
    rows = [
        headers,
        ["2026-01-15", "NEFT FROM ACME CORP", "UTR1234567890", "0.00",  "976.40", "50000.00"],
        ["2026-01-16", "IMPS REFUND",         "UTR1234567892", "200.00", "0.00",   "49800.00"],
        ["2026-01-17", "CARD SETTLEMENT",     "UTR1234567891", "0.00",   "488.70", "50288.70"],
    ]
    tbl = Table(rows, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    return [title, Spacer(1, 12), tbl]


def _draw_gst_invoice(Paragraph, Spacer, Table, TableStyle, colors, styles):
    title = Paragraph("<b>Tax Invoice</b>", styles["Title"])
    headers = [
        "Invoice No", "Invoice Date", "GSTIN", "Taxable Value",
        "CGST", "SGST", "IGST", "Total",
    ]
    rows = [
        headers,
        ["INV-1001", "2026-01-15", "27ABCDE1234F1Z5", "1000.00", "90.00", "90.00", "0.00", "1180.00"],
        ["INV-1002", "2026-01-16", "29XYZAB5678G2Z9", "500.00",  "0.00",  "0.00",  "90.00", "590.00"],
    ]
    tbl = Table(rows, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    return [title, Spacer(1, 12), tbl]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tmp_pdf_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("pdf_fixtures")
    _build_pdf(d / "razorpay_settlement.pdf", _draw_razorpay_settlement)
    _build_pdf(d / "bank_statement.pdf", _draw_bank_statement)
    _build_pdf(d / "gst_invoice.pdf", _draw_gst_invoice)
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_parses_razorpay_sample_pdf(tmp_pdf_dir: Path) -> None:
    """
    Happy path: build a tiny Razorpay-style PDF, parse it, check schema + values.
    Uses an existing fixture if present, otherwise the in-tree synthetic one.
    """
    sample = tmp_pdf_dir / "razorpay_settlement.pdf"
    assert sample.exists()

    result: PDFParseResult = parse_pdf(sample, kind="razorpay_settlement")

    # We should not have crashed
    assert isinstance(result, PDFParseResult)
    assert result.pages == 1
    assert result.source in ("pdfplumber", "pymupdf")

    # Two of the three rows are "payment" entities; the third is a refund
    df = result.df
    assert not df.empty, f"Expected non-empty df, got warnings={result.warnings}"
    expected_cols = {
        "entity", "payment_id", "amount", "fee", "tax", "credit", "debit",
        "on_hold", "settlement_utr", "created_at", "settled_at", "method",
    }
    assert expected_cols.issubset(set(df.columns)), \
        f"Missing columns: {expected_cols - set(df.columns)}"

    # Money columns are Decimal
    assert isinstance(df["amount"].iloc[0], Decimal)
    # Spot-check a value
    payments = df[df["entity"] == "payment"]
    assert len(payments) >= 1
    assert Decimal(str(payments["amount"].iloc[0])) == Decimal("1000.00")


def test_handles_corrupt_pdf_gracefully(tmp_path: Path) -> None:
    """
    A file that isn't a real PDF must not raise — it returns an empty df
    and a warning.
    """
    bad = tmp_path / "not-a-pdf.pdf"
    bad.write_bytes(b"this is definitely not a PDF, just text\n" * 10)

    result = parse_pdf(bad, kind="razorpay_settlement")

    # No exception raised — that's the main contract
    assert isinstance(result, PDFParseResult)
    assert result.df.empty
    # Either source is "none" (parser gave up) or both parsers tried and failed
    assert result.source == "none" or len(result.warnings) > 0
    assert result.warnings, "Expected at least one warning for a corrupt PDF"

    # Missing file path is also graceful
    missing = tmp_path / "does-not-exist.pdf"
    result2 = parse_pdf(missing, kind="razorpay_settlement")
    assert result2.df.empty
    assert result2.source == "none"
    assert any("not found" in w.lower() or "not exist" in w.lower()
               for w in result2.warnings)


def test_auto_detects_kind(tmp_pdf_dir: Path) -> None:
    """
    With kind='auto', the parser should pick the right schema by inspecting
    the table headers in the first table.
    """
    rzp_pdf = tmp_pdf_dir / "razorpay_settlement.pdf"
    bank_pdf = tmp_pdf_dir / "bank_statement.pdf"
    gst_pdf = tmp_pdf_dir / "gst_invoice.pdf"

    r = parse_pdf(rzp_pdf, kind="auto")
    assert detect_kind(r.df) == "razorpay_settlement", \
        f"auto-detect failed for razorpay; cols={list(r.df.columns)}"
    # After auto-detection, the result df should have the razorpay schema
    assert "settlement_utr" in r.df.columns

    r2 = parse_pdf(bank_pdf, kind="auto")
    assert detect_kind(r2.df) == "bank_statement"
    assert "narration" in r2.df.columns and "balance" in r2.df.columns

    r3 = parse_pdf(gst_pdf, kind="auto")
    assert detect_kind(r3.df) == "gst_invoice"
    assert "invoice_no" in r3.df.columns and "gstin" in r3.df.columns


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
