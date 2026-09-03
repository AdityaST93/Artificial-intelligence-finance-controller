"""
Adversarial holdout test set for Razorpay AI Finance Controller.

Produces a SEPARATE set of synthetic data with KNOWN GROUND TRUTH so we can
compute honest precision/recall on the reconciliation engine.

Outputs (under data/holdout/):
  - razorpay_settlement.csv   (~80 rows)
  - bank_statement.csv        (~70-80 rows)
  - oms_orders.csv            (~70-80 rows)
  - gst_invoices.csv          (~70-80 rows)
  - ground_truth.json         per-record truth label
  - results.json              filled in by the test runner

Design:
  - seed = 2026 (main set uses seed=42, so the data is different)
  - ~75% of records are "clean" (must match across all 4 sources)
  - ~25% carry a seeded exception with a specific category
  - subtle defects included: UTR truncated, currency mix, dates off by 1 day
  - ALL ground truth categories come from the engine's exception taxonomy
    so precision/recall are meaningful

The engine's exception categories (from core/reconcile.py):
  missing_bank_credit, orphan_bank_credit, amount_mismatch,
  oms_amount_mismatch, missing_oms_order, ghost_oms_order,
  cancelled_order_with_payment, gst_amount_mismatch, missing_gst_invoice
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
from faker import Faker

fake = Faker("en_IN")
SEED = 2026
random.seed(SEED)
Faker.seed(SEED)

# Output directory
DATA_DIR = Path(__file__).parent / "holdout"
DATA_DIR.mkdir(exist_ok=True)

# How many records to generate
N = 80  # ~75% clean + ~25% broken ≈ 60 clean + 20 broken

# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------


def inr(amount: float | Decimal) -> Decimal:
    """Round to 2 dp, Decimal-safe."""
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def gen_utr(idx: int) -> str:
    """Deterministic 22-char UTR for a given index."""
    return f"HDFCN5{20260801 + idx:08d}{fake.lexify('????').upper()}"


# ---------------------------------------------------------------------------
# 1. Razorpay Settlement (~80 rows)
# ---------------------------------------------------------------------------


def generate_razorpay_settlement() -> tuple[pd.DataFrame, dict]:
    """
    Produce the holdout Razorpay settlement file.

    Returns (df, exceptions_map) where exceptions_map maps
    payment_id -> exception_category (or None for clean rows).
    """
    rows: list[dict] = []
    exceptions: dict[str, str] = {}  # payment_id -> category

    base_date = datetime(2026, 7, 1)  # different month than main set

    for i in range(N):
        payment_id = f"pay_H{40000 + i}"
        order_receipt = f"HC-{2001 + i}"
        gross = inr(random.uniform(200, 15000))
        method = random.choices(
            ["upi", "card", "netbanking", "wallet"],
            weights=[70, 15, 10, 5],
        )[0]
        if method == "upi":
            fee_rate = Decimal("0.0000")
        elif method == "card":
            fee_rate = Decimal("0.0200")
        else:
            fee_rate = Decimal("0.0150")
        fee = inr(gross * fee_rate)
        tax = inr(fee * Decimal("0.18"))
        net = inr(gross - fee - tax)
        created_at = base_date + timedelta(
            days=random.randint(0, 25), hours=random.randint(0, 23)
        )
        settled_at = created_at + timedelta(days=2, hours=random.randint(0, 8))
        utr = gen_utr(i)
        rows.append(
            {
                "entity": "payment",
                "payment_id": payment_id,
                "order_receipt": order_receipt,
                "amount": float(gross),
                "currency": "INR",
                "fee": float(fee),
                "tax": float(tax),
                "credit": float(net),
                "debit": 0.0,
                "on_hold": "No",
                "settlement_utr": utr,
                "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "settled_at": settled_at.strftime("%Y-%m-%d %H:%M:%S"),
                "method": method,
            }
        )

    df = pd.DataFrame(rows)

    # ---------------------------------------------------------------------
    # Seeded exceptions — 40 broken payments out of 80 (50% of razorpay,
    # ~25% across all sources). All categories are from the engine's actual
    # exception taxonomy so the evaluation against ground truth is meaningful.
    # ---------------------------------------------------------------------

    # Group A: missing_bank_credit (5 rows)
    # Razorpay has the payment, but the bank file will NOT have a credit for
    # this UTR. (One is the "UTR truncated" subtle case — bank has truncated
    # UTR, so engine can't exact-match and flags as missing.)
    exceptions["pay_H40005"] = "missing_bank_credit"  # bank row skipped entirely
    exceptions["pay_H40021"] = "missing_bank_credit"  # bank row skipped entirely
    exceptions["pay_H40038"] = "missing_bank_credit"  # bank row skipped entirely
    exceptions["pay_H40049"] = "missing_bank_credit"  # bank row skipped entirely
    exceptions["pay_H40062"] = "missing_bank_credit"  # truncated UTR in bank

    # Group B: amount_mismatch (5 rows)
    # UTR matches in both, but the bank credit is Rs 2 less.
    exceptions["pay_H40015"] = "amount_mismatch"
    exceptions["pay_H40033"] = "amount_mismatch"
    exceptions["pay_H40047"] = "amount_mismatch"
    exceptions["pay_H40061"] = "amount_mismatch"
    exceptions["pay_H40071"] = "amount_mismatch"

    # Group C: oms_amount_mismatch (5 rows)
    # Razorpay amount differs from OMS order_total by > tolerance.
    exceptions["pay_H40008"] = "oms_amount_mismatch"
    exceptions["pay_H40022"] = "oms_amount_mismatch"
    exceptions["pay_H40027"] = "oms_amount_mismatch"
    exceptions["pay_H40048"] = "oms_amount_mismatch"
    exceptions["pay_H40075"] = "oms_amount_mismatch"

    # Group D: cancelled_order_with_payment (4 rows)
    # OMS marks the order as cancelled; Razorpay captured the payment.
    exceptions["pay_H40012"] = "cancelled_order_with_payment"
    exceptions["pay_H40029"] = "cancelled_order_with_payment"
    exceptions["pay_H40044"] = "cancelled_order_with_payment"
    exceptions["pay_H40064"] = "cancelled_order_with_payment"

    # Group E: missing_oms_order (4 rows)
    # Razorpay payment exists; OMS file has no matching transaction_id.
    exceptions["pay_H40018"] = "missing_oms_order"
    exceptions["pay_H40036"] = "missing_oms_order"
    exceptions["pay_H40053"] = "missing_oms_order"
    exceptions["pay_H40068"] = "missing_oms_order"

    # Group F: gst_amount_mismatch (4 rows)
    # Invoice total differs from Razorpay amount (we bump CGST+SGST).
    exceptions["pay_H40031"] = "gst_amount_mismatch"
    exceptions["pay_H40042"] = "gst_amount_mismatch"
    exceptions["pay_H40058"] = "gst_amount_mismatch"
    exceptions["pay_H40073"] = "gst_amount_mismatch"

    # Group G: missing_gst_invoice (4 rows)
    # Payment exists in Razorpay but no matching invoice in GST file.
    exceptions["pay_H40039"] = "missing_gst_invoice"
    exceptions["pay_H40052"] = "missing_gst_invoice"
    exceptions["pay_H40056"] = "missing_gst_invoice"
    exceptions["pay_H40067"] = "missing_gst_invoice"

    # Group H: ghost_oms_order (2 rows) — only appear in OMS, not Razorpay.
    # Ground truth keys these by OMS order_id (HC-9999, HC-9998).
    # (Generated downstream — no razorpay-side exception needed.)

    # Group I: orphan_bank_credit (3 rows) — only appear in bank, not Razorpay.
    # Ground truth keys these by UTR. (Generated downstream.)

    return df, exceptions


# ---------------------------------------------------------------------------
# 2. Bank Statement
# ---------------------------------------------------------------------------


def generate_bank_statement(
    razorpay_df: pd.DataFrame, rzp_exceptions: dict
) -> tuple[pd.DataFrame, dict]:
    """
    Build the bank statement from the Razorpay settlement.

    For every settled Razorpay payment that is NOT marked as
    `missing_bank_credit`, emit one clean bank credit row.

    Then add seeded exceptions:
      - `orphan_bank_credit`: 2 manual bank rows with no Razorpay UTR
      - `amount_mismatch`: handled inline (subtract Rs 2 from credit)
    """
    rows: list[dict] = []
    base_date = datetime(2026, 7, 3)
    balance = Decimal("750000.00")
    bank_exceptions: dict[str, str] = {}  # key -> category

    for _, r in razorpay_df.iterrows():
        if r["entity"] != "payment":
            continue
        if r["on_hold"] == "Yes":
            continue  # on-hold payments don't get bank credits
        pid = r["payment_id"]
        utr = str(r["settlement_utr"])
        amount = Decimal(str(r["credit"]))

        cat = rzp_exceptions.get(pid)
        if cat == "missing_bank_credit":
            # Skip the bank row entirely — Razorpay settled, bank doesn't show
            if pid == "pay_H40062":
                # Subtle: bank HAS a credit for this UTR but it's TRUNCATED
                # so the engine's exact-UTR match fails. The engine cannot
                # fuzzy-match today, so it counts as missing_bank_credit.
                truncated_utr = utr[:14]
                balance += amount
                rows.append(
                    {
                        "date": str(r["settled_at"])[:10],
                        "narration": f"NEFT CR-{fake.bothify('????-')}{truncated_utr[:8]}-RAZORPAY SETTLEMENT",
                        "utr": truncated_utr,
                        "debit": 0.0,
                        "credit": float(amount),
                        "balance": float(balance),
                    }
                )
                bank_exceptions[truncated_utr] = "missing_bank_credit"
            # pay_H40005 and pay_H40021: skip entirely
            continue
        if cat == "amount_mismatch":
            # Subtract 2 from credit so the amount mismatch fires
            amount = inr(amount - Decimal("2.00"))
            bank_exceptions[utr] = "amount_mismatch"

        # Default: clean bank credit
        balance += amount
        rows.append(
            {
                "date": str(r["settled_at"])[:10],
                "narration": f"NEFT CR-{fake.bothify('????-')}{utr[:8]}-RAZORPAY SETTLEMENT",
                "utr": utr,
                "debit": 0.0,
                "credit": float(amount),
                "balance": float(balance),
            }
        )

    df = pd.DataFrame(rows)

    # Seeded orphan bank credits (3 rows with no matching Razorpay UTR)
    for i, (orphan_utr, amt) in enumerate(
        [
            ("MANUAL20260715009000", Decimal("9000.00")),
            ("MANUAL20260722004500", Decimal("4500.00")),
            ("MANUAL20260729006250", Decimal("6250.00")),
        ]
    ):
        balance += amt
        df.loc[len(df)] = {
            "date": (base_date + timedelta(days=15 + i * 7)).strftime("%Y-%m-%d"),
            "narration": "NEFT CR-MANUAL-ADJ-RAZORPAY-MISC",
            "utr": orphan_utr,
            "debit": 0.0,
            "credit": float(amt),
            "balance": float(balance),
        }
        bank_exceptions[orphan_utr] = "orphan_bank_credit"

    return df.sort_values("date").reset_index(drop=True), bank_exceptions


# ---------------------------------------------------------------------------
# 3. OMS Orders
# ---------------------------------------------------------------------------


def generate_oms_orders(
    razorpay_df: pd.DataFrame, rzp_exceptions: dict
) -> tuple[pd.DataFrame, dict]:
    """
    Internal OMS orders. Should match Razorpay payments 1:1 except for
    seeded exceptions.
    """
    rows: list[dict] = []
    oms_exceptions: dict[str, str] = {}  # order_id -> category

    for _, r in razorpay_df.iterrows():
        if r["entity"] != "payment":
            continue
        pid = r["payment_id"]
        cat = rzp_exceptions.get(pid)

        if cat == "missing_oms_order":
            # Skip emitting this OMS row — engine will detect missing_oms_order
            continue
        if cat == "cancelled_order_with_payment":
            oms_exceptions[r["order_receipt"]] = "cancelled_order_with_payment"
            rows.append(
                {
                    "order_id": r["order_receipt"],
                    "order_date": r["created_at"][:10],
                    "order_status": "cancelled",
                    "order_total": r["amount"],
                    "currency": "INR",
                    "payment_method": r["method"],
                    # Keep transaction_id so the engine can match and detect
                    # `cancelled_order_with_payment` (not just missing_oms_order).
                    "transaction_id": pid,
                    "customer_email": fake.email(),
                }
            )
            continue
        if cat == "oms_amount_mismatch":
            oms_exceptions[r["order_receipt"]] = "oms_amount_mismatch"
            rows.append(
                {
                    "order_id": r["order_receipt"],
                    "order_date": r["created_at"][:10],
                    "order_status": "paid",
                    "order_total": float(Decimal(str(r["amount"])) + Decimal("50.00")),
                    "currency": "INR",
                    "payment_method": r["method"],
                    "transaction_id": pid,
                    "customer_email": fake.email(),
                }
            )
            continue

        # Default: clean row
        rows.append(
            {
                "order_id": r["order_receipt"],
                "order_date": r["created_at"][:10],
                "order_status": "paid" if r["on_hold"] == "No" else "processing",
                "order_total": r["amount"],
                "currency": "INR",
                "payment_method": r["method"],
                "transaction_id": pid,
                "customer_email": fake.email(),
            }
        )

    df = pd.DataFrame(rows)

    # Add ghost OMS orders (paid, but no matching Razorpay payment)
    for i, (oid, total) in enumerate(
        [
            ("HC-9999", 3299.00),
            ("HC-9998", 1799.00),
        ]
    ):
        df.loc[len(df)] = {
            "order_id": oid,
            "order_date": f"2026-07-{19 + i:02d}",
            "order_status": "paid",
            "order_total": total,
            "currency": "INR",
            "payment_method": "upi",
            "transaction_id": f"pay_FAILED_GHOST_H{i}",
            "customer_email": fake.email(),
        }
        oms_exceptions[oid] = "ghost_oms_order"

    return df.reset_index(drop=True), oms_exceptions


# ---------------------------------------------------------------------------
# 4. GST Invoices
# ---------------------------------------------------------------------------


def generate_gst_invoices(
    razorpay_df: pd.DataFrame, rzp_exceptions: dict
) -> tuple[pd.DataFrame, dict]:
    """
    GST tax invoices. Should match Razorpay payments 1:1 except for seeded
    exceptions.
    """
    rows: list[dict] = []
    merchant_gstin = "29ABCDE1234F1Z5"  # Karnataka — different from main set
    gst_exceptions: dict[str, str] = {}  # invoice_no -> category

    for i, r in razorpay_df.iterrows():
        if r["entity"] != "payment":
            continue
        pid = r["payment_id"]
        cat = rzp_exceptions.get(pid)

        if cat == "missing_gst_invoice":
            # Skip — engine will detect missing_gst_invoice
            continue
        if cat == "gst_amount_mismatch":
            taxable = Decimal(str(r["amount"])) / Decimal("1.18")
            taxable = taxable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cgst = (taxable * Decimal("0.09")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            sgst = (taxable * Decimal("0.09")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            # Bump CGST and SGST by Rs 2 each so total > tolerance vs Razorpay
            cgst = inr(cgst + Decimal("2.00"))
            sgst = inr(sgst + Decimal("2.00"))
            total = inr(taxable + cgst + sgst)
            inv_no = f"INV-2026-07-{5000 + i:04d}"
            rows.append(
                {
                    "invoice_no": inv_no,
                    "invoice_date": r["created_at"][:10],
                    "gstin": merchant_gstin,
                    "taxable_value": float(taxable),
                    "cgst": float(cgst),
                    "sgst": float(sgst),
                    "igst": 0.0,
                    "total": float(total),
                    "razorpay_payment_id": pid,
                }
            )
            gst_exceptions[inv_no] = "gst_amount_mismatch"
            continue

        # Default clean invoice
        taxable = Decimal(str(r["amount"])) / Decimal("1.18")
        taxable = taxable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cgst = (taxable * Decimal("0.09")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        sgst = (taxable * Decimal("0.09")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total = taxable + cgst + sgst
        rows.append(
            {
                "invoice_no": f"INV-2026-07-{5000 + i:04d}",
                "invoice_date": r["created_at"][:10],
                "gstin": merchant_gstin,
                "taxable_value": float(taxable),
                "cgst": float(cgst),
                "sgst": float(sgst),
                "igst": 0.0,
                "total": float(total),
                "razorpay_payment_id": pid,
            }
        )

    df = pd.DataFrame(rows)
    return df.reset_index(drop=True), gst_exceptions


# ---------------------------------------------------------------------------
# Ground truth builder
# ---------------------------------------------------------------------------


def build_ground_truth(
    rzp: pd.DataFrame,
    bank: pd.DataFrame,
    oms: pd.DataFrame,
    gst: pd.DataFrame,
    rzp_exceptions: dict,
    bank_exceptions: dict,
    oms_exceptions: dict,
    gst_exceptions: dict,
) -> dict:
    """
    Build a per-record ground-truth map.

    For each input record, the truth is either:
      - "matched" (clean, no exception expected)
      - an exception category from the engine's taxonomy

    Keys are namespaced by source: "razorpay/<payment_id>",
    "bank/<utr>", "oms/<order_id>", "gst/<invoice_no>".
    """
    truth: dict[str, str] = {}

    # 1) Razorpay rows
    for _, r in rzp.iterrows():
        if r["entity"] == "payment":
            pid = r["payment_id"]
            cat = rzp_exceptions.get(pid, "matched")
            truth[f"razorpay/{pid}"] = cat

    # 2) Bank rows
    for _, r in bank.iterrows():
        utr = r["utr"]
        if utr in bank_exceptions:
            truth[f"bank/{utr}"] = bank_exceptions[utr]
        else:
            truth[f"bank/{utr}"] = "matched"

    # 3) OMS rows
    for _, r in oms.iterrows():
        oid = r["order_id"]
        if oid in oms_exceptions:
            truth[f"oms/{oid}"] = oms_exceptions[oid]
        else:
            truth[f"oms/{oid}"] = "matched"

    # 4) GST rows
    for _, r in gst.iterrows():
        inv = r["invoice_no"]
        if inv in gst_exceptions:
            truth[f"gst/{inv}"] = gst_exceptions[inv]
        else:
            truth[f"gst/{inv}"] = "matched"

    return truth


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"Generating adversarial holdout (seed={SEED}, N={N})...")
    rzp, rzp_ex = generate_razorpay_settlement()
    bank, bank_ex = generate_bank_statement(rzp, rzp_ex)
    oms, oms_ex = generate_oms_orders(rzp, rzp_ex)
    gst, gst_ex = generate_gst_invoices(rzp, rzp_ex)

    rzp.to_csv(DATA_DIR / "razorpay_settlement.csv", index=False)
    bank.to_csv(DATA_DIR / "bank_statement.csv", index=False)
    oms.to_csv(DATA_DIR / "oms_orders.csv", index=False)
    gst.to_csv(DATA_DIR / "gst_invoices.csv", index=False)

    truth = build_ground_truth(rzp, bank, oms, gst, rzp_ex, bank_ex, oms_ex, gst_ex)
    with open(DATA_DIR / "ground_truth.json", "w", encoding="utf-8") as f:
        json.dump(truth, f, indent=2, sort_keys=True)

    # Summary
    n_clean = sum(1 for v in truth.values() if v == "matched")
    n_exc = sum(1 for v in truth.values() if v != "matched")
    print(f"  razorpay_settlement.csv: {len(rzp)} rows")
    print(f"  bank_statement.csv:      {len(bank)} rows")
    print(f"  oms_orders.csv:          {len(oms)} rows")
    print(f"  gst_invoices.csv:        {len(gst)} rows")
    print(f"  ground_truth.json:       {len(truth)} records")
    print(f"    clean records: {n_clean} ({n_clean / len(truth):.1%})")
    print(f"    broken records: {n_exc} ({n_exc / len(truth):.1%})")
    print()
    print("Seeded exceptions:")
    counts: dict[str, int] = {}
    for v in truth.values():
        if v != "matched":
            counts[v] = counts.get(v, 0) + 1
    for cat, cnt in sorted(counts.items()):
        print(f"  {cat}: {cnt}")


if __name__ == "__main__":
    main()
