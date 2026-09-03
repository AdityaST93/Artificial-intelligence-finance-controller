"""
Synthetic data generator for Razorpay AI Finance Controller.

Generates 4 source files that mirror what real Indian merchants upload:
  1. Razorpay settlement report (CSV)
  2. Bank statement (CSV)
  3. Internal OMS orders (CSV)
  4. GST tax invoices (CSV)

Seeds realistic exceptions to demonstrate honest reconciliation:
  - 2 on-hold payments
  - 1 partial refund
  - 1 fee rate variance
  - 1 missing bank credit
  - 1 orphan bank credit
  - 1 amount mismatch
  - 1 ghost OMS order
  - 1 cancelled order
  - 1 GST on MDR variance
  - T+2 settlement timing
  - Decimal-safe money (Decimal, not float)
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
from faker import Faker

fake = Faker("en_IN")
random.seed(42)
Faker.seed(42)


def _reset_seeds():
    """Reset RNG so each generator produces identical output on re-run."""
    random.seed(42)
    Faker.seed(42)

DATA_DIR = Path(__file__).parent / "synthetic"
DATA_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def inr(amount: float | Decimal) -> Decimal:
    """Round to 2 dp, Decimal-safe. Never use float for money."""
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def gen_utr() -> str:
    """Razorpay-style 22-char UTR (e.g. HDFCN52026071400ABCD)."""
    return f"HDFCN5{random.randint(20260101, 20260830):08d}{fake.lexify('????').upper()}"


# ---------------------------------------------------------------------------
# 1. Razorpay Settlement Report (~60 rows)
# ---------------------------------------------------------------------------

def generate_razorpay_settlement() -> pd.DataFrame:
    _reset_seeds()
    rows = []
    base_date = datetime(2026, 8, 1)

    for i in range(60):
        payment_id = f"pay_S{30000 + i}"
        order_receipt = f"WC-{1001 + i}"
        gross = inr(random.uniform(200, 15000))
        method = random.choices(
            ["upi", "card", "netbanking", "wallet"],
            weights=[70, 15, 10, 5],
        )[0]
        # Razorpay MDR: UPI 0% (post-2021 RBI), card ~2%
        if method == "upi":
            fee_rate = Decimal("0.0000")
        elif method == "card":
            fee_rate = Decimal("0.0200")
        else:
            fee_rate = Decimal("0.0150")
        fee = inr(gross * fee_rate)
        tax = inr(fee * Decimal("0.18"))  # 18% GST on fee
        net = inr(gross - fee - tax)
        created_at = base_date + timedelta(days=random.randint(0, 25), hours=random.randint(0, 23))
        # T+2 settlement
        settled_at = created_at + timedelta(days=2, hours=random.randint(0, 8))
        on_hold = "No"
        utr = gen_utr()
        rows.append({
            "entity": "payment",
            "payment_id": payment_id,
            "order_receipt": order_receipt,
            "amount": float(gross),
            "currency": "INR",
            "fee": float(fee),
            "tax": float(tax),
            "credit": float(net),
            "debit": 0.0,
            "on_hold": on_hold,
            "settlement_utr": utr,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "settled_at": settled_at.strftime("%Y-%m-%d %H:%M:%S"),
            "method": method,
        })

    df = pd.DataFrame(rows)

    # Seed exceptions --------------------------------------------------------
    # (a) 2 on-hold payments (no settled_at)
    df.loc[5, "on_hold"] = "Yes"
    df.loc[5, "settled_at"] = ""
    df.loc[5, "settlement_utr"] = ""
    df.loc[12, "on_hold"] = "Yes"
    df.loc[12, "settled_at"] = ""
    df.loc[12, "settlement_utr"] = ""

    # (b) 1 partial refund (negative debit)
    refund_row = {
        "entity": "refund",
        "payment_id": "pay_S30006",
        "order_receipt": "WC-1007",
        "amount": 1500.00,
        "currency": "INR",
        "fee": 0.00,
        "tax": 0.00,
        "credit": 0.00,
        "debit": 1500.00,
        "on_hold": "No",
        "settlement_utr": gen_utr(),
        "created_at": (base_date + timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S"),
        "settled_at": (base_date + timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"),
        "method": "upi",
    }
    df = pd.concat([df, pd.DataFrame([refund_row])], ignore_index=True)

    # (c) 1 fee rate variance (contracted 1.6% but charged 2%)
    df.loc[20, "fee"] = float(inr(Decimal(str(df.loc[20, "amount"])) * Decimal("0.016")))
    df.loc[20, "tax"] = float(inr(Decimal(str(df.loc[20, "fee"])) * Decimal("0.18")))

    # (d) 1 row with rounding variance (paise mismatch)
    df.loc[30, "amount"] = 1234.57
    df.loc[30, "fee"] = 24.69
    df.loc[30, "tax"] = 4.45

    return df


# ---------------------------------------------------------------------------
# 2. Bank Statement (~25 rows)
# ---------------------------------------------------------------------------

def generate_bank_statement(razorpay_df: pd.DataFrame) -> pd.DataFrame:
    """Match bank credits to Razorpay settlements, with 4 seeded exceptions."""
    _reset_seeds()
    rows = []
    base_date = datetime(2026, 8, 3)
    balance = Decimal("500000.00")

    # Matched credits: every settled Razorpay row → one bank credit
    settled = razorpay_df[razorpay_df["on_hold"] == "No"].copy()
    for _, r in settled.iterrows():
        amount = Decimal(str(r["credit"]))
        balance += amount
        rows.append({
            "date": r["settled_at"][:10],
            "narration": f"NEFT CR-{fake.bothify('????-')}{r['settlement_utr'][:8]}-RAZORPAY SETTLEMENT",
            "utr": r["settlement_utr"],
            "debit": 0.0,
            "credit": float(amount),
            "balance": float(balance),
        })

    # Mirror the truncated UTR: full UTR in Razorpay but truncated in bank
    # (so Tier 1 fails, Tier 2 fuzzy can recover)
    # Find the row with truncated UTR and ensure bank has the same truncated form
    truncated_rows = razorpay_df[razorpay_df["settlement_utr"].str.len() < 22]
    for _, tr in truncated_rows.iterrows():
        # The bank already has the truncated UTR (we just iterated the razorpay rows
        # and copied settlement_utr verbatim). But the Razorpay side still has the
        # full UTR — let's also truncate Razorpay so the join works at Tier 2.
        # We'll handle this in the reconcile engine instead.
        pass

    df = pd.DataFrame(rows)

    # Seed exceptions --------------------------------------------------------
    # (a) 1 missing settlement — drop a row
    drop_utr = df.iloc[10]["utr"]
    df = df[df["utr"] != drop_utr].reset_index(drop=True)

    # (b) 1 orphan credit — bank has credit Razorpay doesn't show
    orphan_credit = Decimal("8750.00")
    balance += orphan_credit
    df.loc[len(df)] = {
        "date": (base_date + timedelta(days=15)).strftime("%Y-%m-%d"),
        "narration": "NEFT CR-MANUAL-ADJ-RAZORPAY-MISC",
        "utr": "MANUAL20260815008750",
        "debit": 0.0,
        "credit": float(orphan_credit),
        "balance": float(balance),
    }

    # (c) 1 amount mismatch — UTR same but amount ₹2 off
    target_utr = df.iloc[5]["utr"]
    mismatch_idx = df.index[df["utr"] == target_utr][0]
    original = Decimal(str(df.loc[mismatch_idx, "credit"]))
    df.loc[mismatch_idx, "credit"] = float(original - Decimal("2.00"))
    df.loc[mismatch_idx, "balance"] = float(Decimal(str(df.loc[mismatch_idx, "balance"])) - Decimal("2.00"))

    # (d) 1 customer refund debit (not from Razorpay file)
    debit_amount = Decimal("500.00")
    balance -= debit_amount
    df.loc[len(df)] = {
        "date": (base_date + timedelta(days=20)).strftime("%Y-%m-%d"),
        "narration": "NEFT DR-CUSTOMER-REFUND-MISC",
        "utr": "REVERSAL2026082000500",
        "debit": float(debit_amount),
        "credit": 0.0,
        "balance": float(balance),
    }

    return df.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. Internal OMS Orders (~50 rows)
# ---------------------------------------------------------------------------

def generate_oms_orders(razorpay_df: pd.DataFrame) -> pd.DataFrame:
    """Orders in the merchant's online store. Should match Razorpay payments 1:1."""
    _reset_seeds()
    rows = []
    base_date = datetime(2026, 8, 1)

    # Matched: every Razorpay payment → one OMS order
    for _, r in razorpay_df[razorpay_df["entity"] == "payment"].iterrows():
        rows.append({
            "order_id": r["order_receipt"],
            "order_date": r["created_at"][:10],
            "order_status": "paid" if r["on_hold"] == "No" else "processing",
            "order_total": r["amount"],
            "currency": "INR",
            "payment_method": r["method"],
            "transaction_id": r["payment_id"],
            "customer_email": fake.email(),
        })

    df = pd.DataFrame(rows)

    # Seed exceptions --------------------------------------------------------
    # (a) 2 cancelled orders (no payment expected, but Razorpay captured)
    df.loc[3, "order_status"] = "cancelled"
    df.loc[3, "transaction_id"] = ""
    df.loc[42, "order_status"] = "cancelled"
    df.loc[42, "transaction_id"] = ""

    # (b) 1 ghost order in OMS (no Razorpay payment — failed UPI retry)
    df.loc[len(df)] = {
        "order_id": "WC-9999",
        "order_date": (base_date + timedelta(days=18)).strftime("%Y-%m-%d"),
        "order_status": "paid",
        "order_total": 2599.00,
        "currency": "INR",
        "payment_method": "upi",
        "transaction_id": "pay_FAILED_GHOST",
        "customer_email": fake.email(),
    }

    # (c) 1 amount mismatch (OMS total ≠ Razorpay gross)
    df.loc[15, "order_total"] = float(Decimal(str(df.loc[15, "order_total"])) + Decimal("50.00"))

    # (d) 1 amount mismatch (rounding error > tolerance)
    df.loc[33, "order_total"] = float(Decimal(str(df.loc[33, "order_total"])) + Decimal("2.00"))

    return df


# ---------------------------------------------------------------------------
# 4. GST Tax Invoices (~20 rows)
# ---------------------------------------------------------------------------

def generate_gst_invoices(razorpay_df: pd.DataFrame) -> pd.DataFrame:
    """Tax invoices claimed by the merchant. Sum of taxable values = revenue."""
    _reset_seeds()
    rows = []
    base_date = datetime(2026, 8, 1)
    merchant_gstin = "23ABCDE1234F1Z5"  # Madhya Pradesh (matches user location!)

    payments = razorpay_df[razorpay_df["entity"] == "payment"].reset_index(drop=True)
    for i, r in payments.iterrows():
        taxable = Decimal(str(r["amount"])) / Decimal("1.18")  # remove GST
        taxable = taxable.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cgst = (taxable * Decimal("0.09")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sgst = (taxable * Decimal("0.09")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = taxable + cgst + sgst
        rows.append({
            "invoice_no": f"INV-2026-08-{1000 + i:04d}",
            "invoice_date": r["created_at"][:10],
            "gstin": merchant_gstin,
            "taxable_value": float(taxable),
            "cgst": float(cgst),
            "sgst": float(sgst),
            "igst": 0.0,
            "total": float(total),
            "razorpay_payment_id": r["payment_id"],
        })

    df = pd.DataFrame(rows)

    # Seed exception ---------------------------------------------------------
    # 1 GST on MDR variance (different from Razorpay's tax column) at index 10
    df.loc[10, "cgst"] = 2.43
    df.loc[10, "sgst"] = 2.43
    df.loc[10, "total"] = float(Decimal(str(df.loc[10, "taxable_value"])) + Decimal("4.86"))

    # 1 missing invoice — drop the row for pay_S30025 to test "missing_gst_invoice"
    df = df[df["razorpay_payment_id"] != "pay_S30025"].reset_index(drop=True)

    # 2nd missing invoice — pay_S30040 (delayed invoice generation)
    df = df[df["razorpay_payment_id"] != "pay_S30040"].reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Generating synthetic data...")
    rzp = generate_razorpay_settlement()
    bank = generate_bank_statement(rzp)
    oms = generate_oms_orders(rzp)
    gst = generate_gst_invoices(rzp)

    rzp.to_csv(DATA_DIR / "razorpay_settlement.csv", index=False)
    bank.to_csv(DATA_DIR / "bank_statement.csv", index=False)
    oms.to_csv(DATA_DIR / "oms_orders.csv", index=False)
    gst.to_csv(DATA_DIR / "gst_invoices.csv", index=False)

    print(f"  razorpay_settlement.csv: {len(rzp)} rows")
    print(f"  bank_statement.csv:      {len(bank)} rows")
    print(f"  oms_orders.csv:          {len(oms)} rows")
    print(f"  gst_invoices.csv:        {len(gst)} rows")
    print()
    print("Seeded exceptions:")
    print("  2 on-hold payments (no UTR, no settled_at)")
    print("  1 partial refund (negative debit)")
    print("  1 fee rate variance (contracted vs actual)")
    print("  1 missing bank credit (settlement not in statement)")
    print("  1 orphan bank credit (bank has, Razorpay doesn't)")
    print("  1 amount mismatch (UTR same, Rs 2 off)")
    print("  1 ghost OMS order (failed UPI retry)")
    print("  1 cancelled order (no payment expected)")
    print("  1 GST on MDR variance (ITC claim)")
    print("  T+2 settlement timing across all rows")


if __name__ == "__main__":
    main()
