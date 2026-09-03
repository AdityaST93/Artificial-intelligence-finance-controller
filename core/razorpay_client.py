"""
Razorpay API client (test-mode friendly).

Provides a thin wrapper over the Razorpay REST API for the four endpoints
the AI Finance Controller actually uses: payments, orders, settlements,
and refunds.

Design goals
------------
* Works with `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` from the environment
  (or `.env` via python-dotenv, which is already a dependency).
* Falls back to deterministic synthetic data when no real keys are
  configured — the dashboard should never go blank just because the
  merchant hasn't wired their test keys in yet.
* Returns pandas DataFrames whose schema matches
  ``data/synthetic/razorpay_settlement.csv`` so the downstream
  reconciliation, forecast, and GST engines work unchanged.
* Survives transient network errors with bounded exponential backoff
  (3 attempts, 1s -> 2s -> 4s).
* A ``test_connection()`` helper so the Streamlit sidebar can render a
  green/red status pill without crashing on a 401.

References
----------
* API docs:   https://razorpay.com/docs/api/
* Test keys:  https://dashboard.razorpay.com/app/keys
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

# Reuse the deterministic synthetic generator as a fallback so the
# app behaves identically with or without API credentials.
from data.generate import (
    generate_oms_orders,
    generate_razorpay_settlement,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"

# Standard column order — must match data/synthetic/razorpay_settlement.csv
SETTLEMENT_CSV_COLUMNS = [
    "entity",
    "payment_id",
    "order_receipt",
    "amount",
    "currency",
    "fee",
    "tax",
    "credit",
    "debit",
    "on_hold",
    "settlement_utr",
    "created_at",
    "settled_at",
    "method",
]

# Dummy placeholders. Using the literal "rzp_test_*" pattern tells the
# client (and any future observability) that no live call was made.
_DUMMY_KEY_ID = "rzp_test_dummy_key_id"
_DUMMY_KEY_SECRET = "dummy_key_secret_for_synthetic_mode"


# ---------------------------------------------------------------------------
# Credentials helper
# ---------------------------------------------------------------------------


def _load_credentials() -> tuple[str, str]:
    """Read Razorpay credentials from the environment.

    Returns
    -------
    (key_id, key_secret) : tuple[str, str]
        Falls back to dummy values if either is missing. The caller can
        detect synthetic mode by comparing against the dummy constants
        or by calling :meth:`RazorpayClient.has_real_keys`.
    """
    key_id = os.getenv("RAZORPAY_KEY_ID", _DUMMY_KEY_ID).strip() or _DUMMY_KEY_ID
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", _DUMMY_KEY_SECRET).strip() or _DUMMY_KEY_SECRET
    return key_id, key_secret


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


@dataclass
class _Credentials:
    """Holder so we can pass auth around without re-reading env on every call."""

    key_id: str
    key_secret: str

    @property
    def is_real(self) -> bool:
        return (
            self.key_id != _DUMMY_KEY_ID
            and self.key_secret != _DUMMY_KEY_SECRET
            and self.key_id.startswith("rzp_")
        )


class RazorpayClient:
    """Thin wrapper over the Razorpay REST API.

    Parameters
    ----------
    key_id, key_secret : str, optional
        If omitted, values are read from ``RAZORPAY_KEY_ID`` and
        ``RAZORPAY_KEY_SECRET`` in the environment.
    base_url : str, optional
        Override the API root (mostly useful for mocking in tests).
    timeout : float, optional
        Per-request timeout in seconds. Default 15s.
    max_retries : int, optional
        How many times to retry a request on 429 / 5xx / network errors.
        Default 3 (i.e. 1 original + 2 retries).
    """

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        base_url: str = RAZORPAY_API_BASE,
        timeout: float = 15.0,
        max_retries: int = 3,
    ) -> None:
        env_id, env_secret = _load_credentials()
        self.key_id = key_id or env_id
        self.key_secret = key_secret or env_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(1, int(max_retries))
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "razorpay-finance-controller/1.0",
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @property
    def has_real_keys(self) -> bool:
        """True if the configured credentials look like real Razorpay keys."""
        return _Credentials(self.key_id, self.key_secret).is_real

    def test_connection(self) -> tuple[bool, str]:
        """Ping the API to verify the credentials work.

        Returns
        -------
        (ok, message) : tuple[bool, str]
            ``ok`` is True on a 2xx response, False otherwise. ``message``
            is a short human-readable status. Never raises — all
            exceptions are caught and surfaced as ``(False, str(err))``.
        """
        if not self.has_real_keys:
            return (
                False,
                "Using synthetic data — set RAZORPAY_KEY_ID to use real API",
            )
        try:
            resp = self._get("/payments", params={"count": 1})
            if resp.status_code == 200:
                return (
                    True,
                    f"Connected to Razorpay ({len(resp.json().get('items', []))} sample payment)",
                )
            if resp.status_code == 401:
                return False, "401 Unauthorized — check RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET"
            return False, f"HTTP {resp.status_code}: {resp.text[:120]}"
        except requests.RequestException as exc:
            return False, f"Network error: {exc}"

    # ------------------------------------------------------------------
    # High-level fetchers
    # ------------------------------------------------------------------

    def list_payments(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        count: int = 100,
    ) -> pd.DataFrame:
        """Fetch payments from ``GET /v1/payments``.

        Parameters
        ----------
        from_date, to_date : str, optional
            ISO-8601 dates (or unix timestamps, Razorpay accepts both).
            If omitted, the API returns the most recent ``count`` records.
        count : int
            Page size. Razorpay caps this at 100 per page; we fetch one
            page and return it as a DataFrame.
        """
        if not self.has_real_keys:
            logger.info("Razorpay: no real keys — using synthetic payment data")
            return self._synthetic_payments()

        params: dict[str, Any] = {"count": min(int(count), 100)}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        resp = self._get("/payments", params=params)
        resp.raise_for_status()
        body = resp.json()
        items = body.get("items", body.get("payments", []))
        return self._payments_to_df(items)

    def list_orders(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        count: int = 100,
    ) -> pd.DataFrame:
        """Fetch orders from ``GET /v1/orders``."""
        if not self.has_real_keys:
            return self._synthetic_orders()

        params: dict[str, Any] = {"count": min(int(count), 100)}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        resp = self._get("/orders", params=params)
        resp.raise_for_status()
        body = resp.json()
        items = body.get("items", body.get("orders", []))
        return pd.DataFrame(items)

    def list_settlements(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        count: int = 100,
    ) -> pd.DataFrame:
        """Fetch settlement report rows from ``GET /v1/settlements``.

        The Razorpay Settlements API returns a flat list of settlement
        rows (gross, fee, tax, net) per ``payment_id``. We map it to the
        same schema as the synthetic CSV so downstream code is
        identical.
        """
        if not self.has_real_keys:
            return self._synthetic_settlements()

        params: dict[str, Any] = {"count": min(int(count), 100)}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        resp = self._get("/settlements", params=params)
        resp.raise_for_status()
        body = resp.json()
        items = body.get("items", body.get("settlements", []))
        return self._settlements_to_df(items)

    def list_refunds(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        count: int = 100,
    ) -> pd.DataFrame:
        """Fetch refunds from ``GET /v1/refunds``."""
        if not self.has_real_keys:
            return self._synthetic_refunds()

        params: dict[str, Any] = {"count": min(int(count), 100)}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        resp = self._get("/refunds", params=params)
        resp.raise_for_status()
        body = resp.json()
        items = body.get("items", body.get("refunds", []))
        return pd.DataFrame(items)

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------

    def to_settlement_csv(self, df: pd.DataFrame | None = None) -> str:
        """Convert an API response (or the synthetic DataFrame) to CSV.

        Parameters
        ----------
        df : pandas.DataFrame, optional
            A DataFrame returned by :meth:`list_settlements` or
            :meth:`list_payments`. If omitted, the most recent synthetic
            settlement is used. The output schema always matches
            ``data/synthetic/razorpay_settlement.csv``.
        """
        if df is None:
            df = self._synthetic_settlements()
        # Guarantee column order; missing columns become NaN.
        for col in SETTLEMENT_CSV_COLUMNS:
            if col not in df.columns:
                df[col] = pd.NA
        return df[SETTLEMENT_CSV_COLUMNS].to_csv(index=False)

    # ------------------------------------------------------------------
    # Internal: HTTP with retry
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        """GET with exponential-backoff retry on 429/5xx/network errors."""
        url = f"{self.base_url}{path}"
        auth = HTTPBasicAuth(self.key_id, self.key_secret)
        backoff = 1.0
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._session.get(
                    url,
                    params=params,
                    auth=auth,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning("Razorpay %s attempt %d failed: %s", path, attempt, exc)
                self._sleep_backoff(attempt, backoff)
                backoff *= 2
                continue

            # Retry on transient upstream errors
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                logger.warning(
                    "Razorpay %s attempt %d got HTTP %d; retrying",
                    path,
                    attempt,
                    resp.status_code,
                )
                self._sleep_backoff(attempt, backoff)
                backoff *= 2
                continue

            return resp

        # Exhausted retries
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Razorpay {path} failed after {self.max_retries} attempts")

    @staticmethod
    def _sleep_backoff(attempt: int, backoff: float) -> None:
        # Cap the wait at ~8s so a misconfigured retry policy can't hang the UI.
        delay = min(backoff, 8.0)
        if attempt < 3:  # don't sleep after the final attempt
            time.sleep(delay)

    # ------------------------------------------------------------------
    # Internal: API -> DataFrame mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _payments_to_df(items: list[dict[str, Any]]) -> pd.DataFrame:
        """Map a list of Razorpay payment objects to our CSV schema."""
        if not items:
            return pd.DataFrame(columns=SETTLEMENT_CSV_COLUMNS)

        rows = []
        for p in items:
            fee = p.get("fee", 0) or 0
            tax = p.get("tax", 0) or 0
            amount = p.get("amount", 0) / 100  # Razorpay amounts are in paise
            fee = (fee or 0) / 100
            tax = (tax or 0) / 100
            credit = max(amount - fee - tax, 0)
            rows.append(
                {
                    "entity": "payment",
                    "payment_id": p.get("id", ""),
                    "order_receipt": p.get("order_id", ""),
                    "amount": amount,
                    "currency": p.get("currency", "INR"),
                    "fee": fee,
                    "tax": tax,
                    "credit": credit,
                    "debit": 0.0,
                    "on_hold": "Yes" if p.get("captured") is False else "No",
                    "settlement_utr": p.get("acquirer_data", {}).get("rrn", "") or "",
                    "created_at": _epoch_to_str(p.get("created_at")),
                    "settled_at": "",  # populated from /settlements
                    "method": p.get("method", "upi"),
                }
            )
        return pd.DataFrame(rows, columns=SETTLEMENT_CSV_COLUMNS)

    @staticmethod
    def _settlements_to_df(items: list[dict[str, Any]]) -> pd.DataFrame:
        """Map a list of Razorpay settlement rows to our CSV schema."""
        if not items:
            return pd.DataFrame(columns=SETTLEMENT_CSV_COLUMNS)

        rows = []
        for s in items:
            amount = (s.get("amount", 0) or 0) / 100
            fee = (s.get("fee", 0) or 0) / 100
            tax = (s.get("tax", 0) or 0) / 100
            credit = (s.get("credit", 0) or 0) / 100
            debit = (s.get("debit", 0) or 0) / 100
            rows.append(
                {
                    "entity": "payment",
                    "payment_id": s.get("payment_id", ""),
                    "order_receipt": s.get("order_id", ""),
                    "amount": amount,
                    "currency": s.get("currency", "INR"),
                    "fee": fee,
                    "tax": tax,
                    "credit": credit,
                    "debit": debit,
                    "on_hold": "No" if s.get("settled_at") else "Yes",
                    "settlement_utr": s.get("utr", ""),
                    "created_at": _epoch_to_str(s.get("created_at")),
                    "settled_at": _epoch_to_str(s.get("settled_at")),
                    "method": s.get("method", "upi"),
                }
            )
        return pd.DataFrame(rows, columns=SETTLEMENT_CSV_COLUMNS)

    # ------------------------------------------------------------------
    # Internal: synthetic fallbacks
    # ------------------------------------------------------------------

    @staticmethod
    def _synthetic_payments() -> pd.DataFrame:
        """The 60 deterministic payments from data/generate.py."""
        return generate_razorpay_settlement()

    @staticmethod
    def _synthetic_settlements() -> pd.DataFrame:
        """Alias for payments; the synthetic file is itself a settlement report."""
        return generate_razorpay_settlement()

    @staticmethod
    def _synthetic_orders() -> pd.DataFrame:
        return generate_oms_orders(generate_razorpay_settlement())

    @staticmethod
    def _synthetic_refunds() -> pd.DataFrame:
        """Refunds are embedded in the synthetic settlement as 'entity=refund' rows."""
        rzp = generate_razorpay_settlement()
        refunds = rzp[rzp["entity"] == "refund"].copy()
        if refunds.empty:
            return pd.DataFrame(columns=SETTLEMENT_CSV_COLUMNS)
        return refunds.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _epoch_to_str(value: Any) -> str:
    """Convert a Razorpay unix-timestamp field to ``YYYY-MM-DD HH:MM:SS``."""
    if not value:
        return ""
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return str(value)
    return (
        pd.to_datetime(ts, unit="s", utc=True)
        .tz_convert("Asia/Kolkata")
        .strftime("%Y-%m-%d %H:%M:%S")
    )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    client = RazorpayClient()
    ok, msg = client.test_connection()
    print(f"test_connection: {ok} -> {msg}")
    df = client.list_payments(count=5)
    print(f"payments rows: {len(df)}")
    print(client.to_settlement_csv(df).splitlines()[0])
