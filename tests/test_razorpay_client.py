"""
Tests for the Razorpay test-mode API client.

We assert:
  - Without API keys, the client gracefully falls back to the
    deterministic synthetic generator (the app must keep working
    even if the merchant hasn't configured Razorpay credentials yet).
  - The exported CSV matches the schema produced by ``data/generate.py``
    column-for-column so the reconciliation, forecast, and GST engines
    downstream are schema-compatible.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pandas as pd
import pytest

# Make project root importable when pytest is invoked from any cwd
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.razorpay_client import (  # noqa: E402
    SETTLEMENT_CSV_COLUMNS,
    RazorpayClient,
)
from data.generate import generate_razorpay_settlement  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client_without_keys(monkeypatch: pytest.MonkeyPatch) -> RazorpayClient:
    """Force the client into synthetic mode by clearing env vars."""
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    return RazorpayClient()


@pytest.fixture
def client_with_dummy_keys(monkeypatch: pytest.MonkeyPatch) -> RazorpayClient:
    """Client that *thinks* it has real keys (because the prefix matches).

    We use a non-resolving host so any real network call would fail —
    the ``has_real_keys`` predicate must catch the dummy host and
    short-circuit before we hit the network.
    """
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_localhost_dummy")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "dummy_secret")
    return RazorpayClient(base_url="http://127.0.0.1:1")  # closed port


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_synthetic_fallback(client_without_keys: RazorpayClient) -> None:
    """Without API keys, every fetcher returns the synthetic DataFrame."""
    # No real keys -> should be in synthetic mode
    assert client_without_keys.has_real_keys is False
    ok, msg = client_without_keys.test_connection()
    assert ok is False
    assert "synthetic" in msg.lower()

    # list_payments returns the same row count as the generator
    payments = client_without_keys.list_payments()
    expected = generate_razorpay_settlement()
    assert isinstance(payments, pd.DataFrame)
    assert len(payments) == len(expected)
    assert set(payments.columns) == set(expected.columns)

    # list_settlements also returns synthetic data
    settlements = client_without_keys.list_settlements()
    assert isinstance(settlements, pd.DataFrame)
    assert len(settlements) == len(expected)

    # list_refunds returns just the embedded refund row(s)
    refunds = client_without_keys.list_refunds()
    if not refunds.empty:
        assert (refunds["entity"] == "refund").all()

    # list_orders returns the OMS-shaped DataFrame
    orders = client_without_keys.list_orders()
    assert isinstance(orders, pd.DataFrame)
    assert "order_id" in orders.columns


def test_settlement_csv_format(client_without_keys: RazorpayClient) -> None:
    """The CSV export must match the synthetic schema exactly."""
    csv_str = client_without_keys.to_settlement_csv()

    # Parse it back and check headers + shape
    reader = csv.reader(io.StringIO(csv_str))
    header = next(reader)
    assert (
        header == SETTLEMENT_CSV_COLUMNS
    ), f"CSV header drift: {header} != {SETTLEMENT_CSV_COLUMNS}"

    rows = list(reader)
    assert len(rows) > 0, "Settlement CSV should not be empty"

    # Every row has the right number of fields
    for i, row in enumerate(rows[:5]):
        assert len(row) == len(SETTLEMENT_CSV_COLUMNS), f"Row {i} has wrong column count"

    # Round-trip through pandas and assert the schema matches
    df = pd.read_csv(io.StringIO(csv_str))
    assert list(df.columns) == SETTLEMENT_CSV_COLUMNS
    # The seed file is the ground truth — its columns must match
    expected_df = generate_razorpay_settlement()
    assert list(expected_df.columns) == SETTLEMENT_CSV_COLUMNS

    # Every payment_id from the source generator must appear
    assert set(df["payment_id"]) == set(expected_df["payment_id"])

    # The on-hold / refund semantics are preserved
    on_hold = df[df["on_hold"] == "Yes"]
    assert len(on_hold) == 2, f"Expected 2 on-hold rows, got {len(on_hold)}"
    refunds = df[df["entity"] == "refund"]
    assert len(refunds) == 1, f"Expected 1 refund, got {len(refunds)}"

    # Numeric columns are coerced to float
    for col in ("amount", "fee", "tax", "credit", "debit"):
        assert pd.api.types.is_numeric_dtype(df[col]), f"{col} should be numeric"


# ---------------------------------------------------------------------------
# Bonus coverage (not part of the 2 required tests, but cheap to add)
# ---------------------------------------------------------------------------


def test_real_keys_predicate(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key starting with rzp_test_ that isn't the dummy placeholder counts as real."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_ABC123")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "a-real-secret")
    c = RazorpayClient()
    assert c.has_real_keys is True
    ok, _ = c.test_connection()
    # test_connection will try a real call; on a CI box with no network
    # that's expected to fail, but it must NOT raise.
    assert isinstance(ok, bool)


def test_custom_dataframe_round_trip() -> None:
    """to_settlement_csv() should accept an arbitrary DataFrame and reorder cols."""
    raw = pd.DataFrame(
        {
            "method": ["upi"],
            "amount": [100.0],
            "payment_id": ["pay_TEST"],
            # intentionally scrambled + missing columns
        }
    )
    c = RazorpayClient()
    out = c.to_settlement_csv(raw)
    header = out.splitlines()[0].split(",")
    assert header == SETTLEMENT_CSV_COLUMNS
    assert "pay_TEST" in out
