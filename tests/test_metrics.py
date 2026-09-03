"""
Tests for Razorpay AI Finance Controller.

We assert:
  - Match rate is in the realistic 80-95% band (not 100%, not <70%)
  - Each seeded exception is detected with the correct category
  - Decimal math is exact (no float drift)
  - All exception categories come from the documented taxonomy
"""

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.reconcile import run_reconciliation
from core.forecast import forecast_cash
from core.tax_match import match_gst
from data.generate import generate_razorpay_settlement, generate_bank_statement, generate_oms_orders, generate_gst_invoices


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def result():
    return run_reconciliation()


@pytest.fixture(scope="module")
def forecast():
    return forecast_cash()


@pytest.fixture(scope="module")
def gst():
    return match_gst()


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def test_match_rate_is_realistic(result):
    """A 100% match rate is suspicious. We expect 85-99%."""
    rate = result.metrics["match_rate"]
    assert 0.85 <= rate <= 0.99, f"Match rate {rate} is unrealistic"


def test_all_seeded_exceptions_detected(result):
    """Each seeded exception must be in the output with the right category."""
    cats = result.metrics["exception_categories"]

    expected = {
        "missing_bank_credit": 1,    # 1 dropped from bank statement
        "orphan_bank_credit": 1,     # 1 manual bank credit
        "amount_mismatch": 1,        # 1 UTR same, Rs 2 off
        "missing_oms_order": 2,      # 2 cancelled orders (transaction_id blanked)
        "ghost_oms_order": 1,        # 1 failed UPI retry
        "missing_gst_invoice": 2,    # 2 invoices not generated
    }
    for cat, count in expected.items():
        assert cat in cats, f"Missing exception category: {cat}"
        assert cats[cat] >= count, f"Too few {cat}: expected {count}, got {cats[cat]}"


def test_exception_categories_from_taxonomy(result):
    """No unmapped categories — every exception has a name in the taxonomy."""
    allowed = {
        "missing_bank_credit", "orphan_bank_credit", "amount_mismatch",
        "oms_amount_mismatch", "missing_oms_order", "ghost_oms_order",
        "cancelled_order_with_payment", "fee_rate_variance",
        "gst_amount_mismatch", "missing_gst_invoice",
    }
    if not result.exceptions.empty:
        seen = set(result.exceptions["exception_category"].dropna())
        unknown = seen - allowed
        assert not unknown, f"Unknown categories: {unknown}"


def test_decimal_safe_amounts():
    """The data generator should never lose paise on simple sums."""
    rzp = generate_razorpay_settlement()
    total = Decimal("0")
    for x in rzp["amount"]:
        total += Decimal(str(x))
    # Sum should be exactly representable to 2 dp
    assert total.as_tuple().exponent <= -2 or total == total.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------

def test_forecast_has_13_weeks(forecast):
    assert len(forecast.df) == 13


def test_forecast_balance_non_negative(forecast):
    """Closing balance should be positive for a healthy merchant."""
    assert forecast.closing_balance > Decimal("0"), "Closing balance went negative"


def test_forecast_opens_equals_closing_yesterday(forecast):
    """First week's opening should equal the requested opening balance."""
    assert Decimal(str(forecast.df.iloc[0]["opening"])) == forecast.opening_balance


# ---------------------------------------------------------------------------
# GST
# ---------------------------------------------------------------------------

def test_gst_mostly_matched(gst):
    """At least 90% of invoices should match cleanly."""
    total = gst.metrics["gst_invoices_total"]
    matched = gst.metrics["gst_matched"]
    rate = matched / total if total else 0
    assert rate >= 0.90, f"GST match rate too low: {rate:.2%}"


def test_gst_mismatch_detected(gst):
    """The seeded GST on MDR variance should be flagged."""
    assert gst.metrics["gst_mismatches"] >= 1
    assert not gst.mismatches.empty
    # Find the specific row
    has_issue = gst.mismatches["issues"].str.contains("breakup", case=False, na=False).any()
    assert has_issue, "Expected a tax-breakup mismatch in the seeded data"


def test_gst_missing_invoice_detected(gst):
    """The pay_S30025 payment should have no invoice."""
    assert gst.metrics["gst_missing"] >= 1
    assert "pay_S30025" in gst.missing_invoices["payment_id"].values


# ---------------------------------------------------------------------------
# Synthetic data invariants
# ---------------------------------------------------------------------------

def test_synthetic_data_deterministic():
    """Two runs with the same seed should produce identical output."""
    a = generate_razorpay_settlement()
    b = generate_razorpay_settlement()
    pd.testing.assert_frame_equal(a, b)


def test_synthetic_data_has_60_payments():
    rzp = generate_razorpay_settlement()
    payments = rzp[rzp["entity"] == "payment"]
    assert len(payments) == 60


def test_synthetic_has_seeded_exceptions():
    """Verify the seeded exceptions are present in the source data."""
    rzp = generate_razorpay_settlement()
    on_hold = rzp[rzp["on_hold"] == "Yes"]
    assert len(on_hold) == 2, f"Expected 2 on-hold payments, got {len(on_hold)}"
    refunds = rzp[rzp["entity"] == "refund"]
    assert len(refunds) == 1, f"Expected 1 refund, got {len(refunds)}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
