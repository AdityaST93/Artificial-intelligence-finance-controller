"""
Tests for the PDF/Excel exporter (core/exporter.py).

We exercise both export functions with a small mock result object so the
tests do not depend on the full reconciliation pipeline.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytest

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.exporter import export_excel, export_pdf_report


# ---------------------------------------------------------------------------
# Mock result
# ---------------------------------------------------------------------------

@dataclass
class MockResult:
    df: pd.DataFrame
    exceptions: pd.DataFrame
    metrics: dict = field(default_factory=dict)


@pytest.fixture(scope="module")
def mock_result() -> MockResult:
    """A small but realistic mock result for export tests."""
    matched = pd.DataFrame(
        {
            "payment_id": ["pay_S1", "pay_S2", "pay_S3"],
            "order_receipt": ["r1", "r2", "r3"],
            "amount": [100.00, 200.00, 300.00],
            "utr": ["UTR1", "UTR2", "UTR3"],
            "bank_credit": [100.00, 200.00, 300.00],
            "invoice_no": ["INV-1", "INV-2", None],
            "razorpay_payment_id": ["pay_S1", "pay_S2", None],
            "status": ["matched", "matched", "matched"],
            "tier": [1, 1, 1],
            "reason": ["UTR exact match", "transaction_id exact match", "GST invoice linked"],
        }
    )
    exceptions = pd.DataFrame(
        {
            "payment_id": ["pay_X1", "pay_X2", "pay_X3"],
            "amount": [50.00, 75.00, 125.00],
            "utr": [None, "UTR-X2", None],
            "exception_category": [
                "missing_bank_credit",
                "amount_mismatch",
                "missing_gst_invoice",
            ],
            "reason": [
                "Settlement not found in bank statement",
                "UTR matched but amount differs beyond tolerance",
                "Payment has no matching GST invoice",
            ],
            "tier": [1, 1, 1],
            "status": ["exception", "exception", "exception"],
        }
    )
    metrics = {
        "match_rate": 0.92,
        "total_input_records": 12,
        "razorpay_payments": 6,
        "bank_credits": 5,
        "oms_orders": 4,
        "gst_invoices": 3,
        "tier1_matched_payments": 3,
        "tier1_match_attempts": 9,
        "clean_payments": 3,
        "tier1_exceptions": 3,
        "exception_categories": {
            "missing_bank_credit": 1,
            "amount_mismatch": 1,
            "missing_gst_invoice": 1,
        },
    }
    return MockResult(df=matched, exceptions=exceptions, metrics=metrics)


@pytest.fixture()
def tmp_outputs(tmp_path) -> tuple[Path, Path]:
    xlsx = tmp_path / "report.xlsx"
    pdf = tmp_path / "report.pdf"
    return xlsx, pdf


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

def test_excel_export(mock_result, tmp_outputs):
    xlsx_path, _ = tmp_outputs
    out = export_excel(mock_result, xlsx_path)

    assert out.exists(), f"Excel file was not created at {out}"
    assert out == xlsx_path

    # Workbook should have exactly 5 sheets
    from openpyxl import load_workbook
    wb = load_workbook(out, read_only=True)
    try:
        names = wb.sheetnames
        assert len(names) == 5, f"Expected 5 sheets, got {len(names)}: {names}"
        expected = {"Summary", "Matched", "Exceptions", "By Category", "GST Reconciliation"}
        assert set(names) == expected, f"Sheet names mismatch: {names}"
    finally:
        wb.close()

    # Sanity: file should be > 1KB
    assert out.stat().st_size > 1024, f"Excel file too small: {out.stat().st_size} bytes"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def test_pdf_export(mock_result, tmp_outputs):
    _, pdf_path = tmp_outputs
    out = export_pdf_report(mock_result, pdf_path)

    assert out.exists(), f"PDF file was not created at {out}"
    size = out.stat().st_size
    assert size > 1024, f"PDF file too small (< 1KB): {size} bytes"

    # PDF magic bytes
    with open(out, "rb") as f:
        head = f.read(4)
    assert head == b"%PDF", f"Not a valid PDF (header={head!r})"


# ---------------------------------------------------------------------------
# Defensive: empty result
# ---------------------------------------------------------------------------

def test_excel_export_handles_empty_result(tmp_path):
    """Empty df and empty exceptions should not crash."""
    empty = MockResult(
        df=pd.DataFrame(),
        exceptions=pd.DataFrame(),
        metrics={"match_rate": 0.0, "exception_categories": {}},
    )
    out = tmp_path / "empty.xlsx"
    result = export_excel(empty, out)
    assert result.exists()


def test_pdf_export_handles_empty_result(tmp_path):
    empty = MockResult(
        df=pd.DataFrame(),
        exceptions=pd.DataFrame(),
        metrics={"match_rate": 0.0, "exception_categories": {}},
    )
    out = tmp_path / "empty.pdf"
    result = export_pdf_report(empty, out)
    assert result.exists()
    assert result.stat().st_size > 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
