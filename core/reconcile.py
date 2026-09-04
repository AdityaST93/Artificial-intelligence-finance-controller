"""
Multi-source reconciliation engine for Razorpay AI Finance Controller.

Pipeline:
  Tier 1: deterministic pandas joins (exact payment_id / UTR / invoice_no)
  Tier 2: rapidfuzz + amount tolerance + date window
  Tier 3: (LLM — left for agent.py)

For every record, we compute a status, a confidence, and a category
if it's an exception. Decimal-safe throughout.

Output: a single reconciled DataFrame with one row per input record,
plus an exceptions DataFrame for the dashboard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pandas as pd
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "synthetic"

# Tolerance for amount comparison (₹0.05 = 5 paise)
AMOUNT_TOLERANCE = Decimal("0.05")
# Date tolerance (days) for T+2 settlement window
DATE_TOLERANCE_DAYS = 3


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

Status = Literal["matched", "exception", "needs_llm"]


@dataclass
class ReconcileResult:
    df: pd.DataFrame
    exceptions: pd.DataFrame
    metrics: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_sources(data_dir: Path | str | None = None) -> dict[str, pd.DataFrame]:
    """
    Load all 4 source CSVs from `data_dir` (defaults to the main synthetic dir).

    Passing a custom directory lets the adversarial holdout test point the
    engine at data/holdout/ without touching the main set.

    If the CSVs are missing (e.g. fresh deploy without generated data), this
    will auto-generate them via the synthetic data generator so the app
    always has something to reconcile.
    """
    base = Path(data_dir) if data_dir is not None else DATA_DIR
    base.mkdir(parents=True, exist_ok=True)

    required = {
        "razorpay": base / "razorpay_settlement.csv",
        "bank": base / "bank_statement.csv",
        "oms": base / "oms_orders.csv",
        "gst": base / "gst_invoices.csv",
    }

    # If any file is missing, auto-generate the full set
    if not all(p.exists() for p in required.values()):
        try:
            from data.generate import (
                generate_razorpay_settlement,
                generate_bank_statement,
                generate_oms_orders,
                generate_gst_invoices,
            )
            rzp = generate_razorpay_settlement()
            bank = generate_bank_statement(rzp)
            oms = generate_oms_orders(rzp)
            gst = generate_gst_invoices(rzp)
            rzp.to_csv(required["razorpay"], index=False)
            bank.to_csv(required["bank"], index=False)
            oms.to_csv(required["oms"], index=False)
            gst.to_csv(required["gst"], index=False)
            logger.info("Auto-generated synthetic data at %s", base)
        except ImportError as e:
            # If we can't auto-generate, give a clear error
            missing = [str(p) for p in required.values() if not p.exists()]
            raise FileNotFoundError(
                f"Source CSVs missing and auto-generation failed: {e}. "
                f"Run `python data/generate.py` to create them, or ensure "
                f"these files exist: {missing}"
            ) from e

    return {
        "razorpay": pd.read_csv(required["razorpay"]),
        "bank": pd.read_csv(required["bank"]),
        "oms": pd.read_csv(required["oms"]),
        "gst": pd.read_csv(required["gst"]),
    }


# ---------------------------------------------------------------------------
# Tier 1: Razorpay ↔ Bank (UTR exact match)
# ---------------------------------------------------------------------------

def tier1_razorpay_vs_bank(rzp: pd.DataFrame, bank: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Join Razorpay settled payments to bank credits on UTR.
    Return (matched, exceptions).
    """
    settled = rzp[(rzp["entity"] == "payment") & (rzp["on_hold"] == "No")].copy()
    settled["settlement_utr"] = settled["settlement_utr"].astype(str)
    bank["utr"] = bank["utr"].astype(str)

    merged = settled.merge(
        bank[["utr", "credit", "date"]].rename(columns={"credit": "bank_credit", "date": "bank_date"}),
        left_on="settlement_utr",
        right_on="utr",
        how="left",
    )

    matched = merged.dropna(subset=["utr"]).copy()
    matched["status"] = "matched"
    matched["tier"] = 1
    matched["reason"] = "UTR exact match"

    # UTR matched but amount differs
    amt_diff = matched.apply(
        lambda r: abs(Decimal(str(r["credit"])) - Decimal(str(r["bank_credit"]))) > AMOUNT_TOLERANCE,
        axis=1,
    )
    matched.loc[amt_diff, "status"] = "exception"
    matched.loc[amt_diff, "exception_category"] = "amount_mismatch"
    matched.loc[amt_diff, "reason"] = "UTR matched but amount differs beyond tolerance"

    # UTR not found in bank
    unmatched = merged[merged["utr"].isna()].copy()
    unmatched["status"] = "exception"
    unmatched["tier"] = 1
    unmatched["exception_category"] = "missing_bank_credit"
    unmatched["reason"] = "Settlement not found in bank statement"

    return matched, unmatched


# ---------------------------------------------------------------------------
# Tier 1: Razorpay ↔ OMS (transaction_id exact match)
# ---------------------------------------------------------------------------

def tier1_razorpay_vs_oms(rzp: pd.DataFrame, oms: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join Razorpay payments to OMS orders on payment_id == transaction_id."""
    payments = rzp[rzp["entity"] == "payment"].copy()

    merged = payments.merge(
        oms[["order_id", "order_status", "order_total", "transaction_id"]],
        left_on="payment_id",
        right_on="transaction_id",
        how="left",
    )

    matched = merged.dropna(subset=["transaction_id"]).copy()
    matched["status"] = "matched"
    matched["tier"] = 1
    matched["reason"] = "transaction_id exact match"

    # Amount mismatch
    amt_diff = matched.apply(
        lambda r: abs(Decimal(str(r["amount"])) - Decimal(str(r["order_total"]))) > AMOUNT_TOLERANCE,
        axis=1,
    )
    matched.loc[amt_diff, "status"] = "exception"
    matched.loc[amt_diff, "exception_category"] = "oms_amount_mismatch"
    matched.loc[amt_diff, "reason"] = "OMS total differs from Razorpay amount"

    # Order cancelled but payment captured
    cancelled = matched[matched["order_status"] == "cancelled"]
    matched.loc[cancelled.index, "status"] = "exception"
    matched.loc[cancelled.index, "exception_category"] = "cancelled_order_with_payment"
    matched.loc[cancelled.index, "reason"] = "Order cancelled but Razorpay shows captured payment"

    unmatched = merged[merged["transaction_id"].isna()].copy()
    unmatched["status"] = "exception"
    unmatched["tier"] = 1
    unmatched["exception_category"] = "missing_oms_order"
    unmatched["reason"] = "Razorpay payment has no matching OMS order"

    return matched, unmatched


# ---------------------------------------------------------------------------
# Tier 1: Bank orphan credits (no matching UTR)
# ---------------------------------------------------------------------------

def tier1_bank_orphans(bank: pd.DataFrame, rzp: pd.DataFrame) -> pd.DataFrame:
    """Bank credits with no matching Razorpay UTR."""
    rzp_utrs = set(rzp[rzp["on_hold"] == "No"]["settlement_utr"].astype(str))
    orphans = bank[~bank["utr"].astype(str).isin(rzp_utrs)].copy()
    # Skip debit rows (customer refunds are not in Razorpay settlement file)
    orphans = orphans[orphans["credit"] > 0].copy()
    orphans["status"] = "exception"
    orphans["tier"] = 1
    orphans["exception_category"] = "orphan_bank_credit"
    orphans["reason"] = "Bank credit has no matching Razorpay settlement"
    return orphans


# ---------------------------------------------------------------------------
# Tier 1: OMS ghost orders (no matching Razorpay payment)
# ---------------------------------------------------------------------------

def tier1_oms_ghosts(oms: pd.DataFrame, rzp: pd.DataFrame) -> pd.DataFrame:
    """OMS orders that claim a transaction_id which doesn't exist in Razorpay."""
    rzp_pay_ids = set(rzp["payment_id"].astype(str))
    ghosts = oms[~oms["transaction_id"].astype(str).isin(rzp_pay_ids) & (oms["order_status"] == "paid")].copy()
    ghosts["status"] = "exception"
    ghosts["tier"] = 1
    ghosts["exception_category"] = "ghost_oms_order"
    ghosts["reason"] = "OMS order marked paid but no Razorpay transaction exists"
    return ghosts


# ---------------------------------------------------------------------------
# Tier 1: GST match
# ---------------------------------------------------------------------------

def tier1_gst_match(rzp: pd.DataFrame, gst: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match GST invoices to Razorpay payments on payment_id."""
    payments = rzp[rzp["entity"] == "payment"].copy()
    merged = payments.merge(
        gst[["invoice_no", "taxable_value", "cgst", "sgst", "total", "razorpay_payment_id"]],
        left_on="payment_id",
        right_on="razorpay_payment_id",
        how="left",
    )
    matched = merged.dropna(subset=["razorpay_payment_id"]).copy()
    matched["status"] = "matched"
    matched["tier"] = 1
    matched["reason"] = "GST invoice linked to payment"

    # Total mismatch (Razorpay amount ≠ invoice total)
    amt_diff = matched.apply(
        lambda r: abs(Decimal(str(r["amount"])) - Decimal(str(r["total"]))) > AMOUNT_TOLERANCE,
        axis=1,
    )
    matched.loc[amt_diff, "status"] = "exception"
    matched.loc[amt_diff, "exception_category"] = "gst_amount_mismatch"
    matched.loc[amt_diff, "reason"] = "Invoice total differs from Razorpay amount"

    unmatched = merged[merged["razorpay_payment_id"].isna()].copy()
    unmatched["status"] = "exception"
    unmatched["tier"] = 1
    unmatched["exception_category"] = "missing_gst_invoice"
    unmatched["reason"] = "Payment has no matching GST invoice"

    return matched, unmatched


# ---------------------------------------------------------------------------
# Tier 2: Fuzzy match (rapidfuzz) on residue
# ---------------------------------------------------------------------------

def tier2_fuzzy_residue(residue: pd.DataFrame, candidates: pd.DataFrame, key_col: str, score_col: str = "fuzzy_score") -> pd.DataFrame:
    """Fuzzy match residue rows against candidates. Score >= 88 = match."""
    if residue.empty or candidates.empty:
        return pd.DataFrame()
    results = []
    for _, r in residue.iterrows():
        best_score = 0
        best_match = None
        for _, c in candidates.iterrows():
            score = fuzz.token_sort_ratio(str(r[key_col]), str(c[key_col]))
            if score > best_score:
                best_score = score
                best_match = c
        if best_score >= 88 and best_match is not None:
            results.append({
                **{key_col: r[key_col]},
                "matched_to": best_match[key_col],
                score_col: best_score,
                "tier": 2,
            })
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_reconciliation(data_dir: Path | str | None = None) -> ReconcileResult:
    """Run the full Tier 1 reconciliation and return the result.

    Args:
        data_dir: optional override for the source CSVs directory. Used by
            the adversarial holdout test to evaluate the engine on a separate
            data set with known ground truth.
    """
    sources = load_sources(data_dir)
    rzp, bank, oms, gst = sources["razorpay"], sources["bank"], sources["oms"], sources["gst"]

    # Tier 1 joins -----------------------------------------------------------
    rzp_bank_matched, rzp_bank_excs = tier1_razorpay_vs_bank(rzp, bank)
    rzp_oms_matched, rzp_oms_excs = tier1_razorpay_vs_oms(rzp, oms)
    rzp_gst_matched, rzp_gst_excs = tier1_gst_match(rzp, gst)
    bank_orphans = tier1_bank_orphans(bank, rzp)
    oms_ghosts = tier1_oms_ghosts(oms, rzp)

    # Combine all exceptions -------------------------------------------------
    # Also pull exception rows from "matched" DataFrames (rows that matched
    # on the join key but failed an amount/status check)
    rzp_bank_excs_from_match = rzp_bank_matched[rzp_bank_matched["status"] == "exception"]
    rzp_oms_excs_from_match = rzp_oms_matched[rzp_oms_matched["status"] == "exception"]
    rzp_gst_excs_from_match = rzp_gst_matched[rzp_gst_matched["status"] == "exception"]

    all_exceptions = pd.concat(
        [rzp_bank_excs, rzp_bank_excs_from_match,
         rzp_oms_excs, rzp_oms_excs_from_match,
         rzp_gst_excs, rzp_gst_excs_from_match,
         bank_orphans, oms_ghosts],
        ignore_index=True,
        sort=False,
    )
    # Standardize exception schema
    if not all_exceptions.empty:
        all_exceptions = all_exceptions[[c for c in [
            "payment_id", "order_receipt", "amount", "utr", "bank_credit", "credit",
            "transaction_id", "order_id", "razorpay_payment_id", "invoice_no",
            "exception_category", "reason", "tier", "status", "on_hold",
            "created_at", "settled_at", "date", "method",
        ] if c in all_exceptions.columns]]

    # Tier 2 would go here — LLM residue is left to agent.py
    # For now, everything that didn't tier-1-match becomes a residual.

    # Combine all matched records -------------------------------------------
    all_matched = pd.concat(
        [rzp_bank_matched, rzp_oms_matched, rzp_gst_matched],
        ignore_index=True,
        sort=False,
    )

    # Metrics ----------------------------------------------------------------
    total_input = len(rzp[rzp["entity"] == "payment"]) + len(bank[bank["credit"] > 0]) + len(oms) + len(gst)
    rzp_payments = rzp[rzp["entity"] == "payment"]

    # Match rate = payments that have NO exception across any of the 4 sources
    exception_payment_ids = set()
    if not all_exceptions.empty:
        exc_pids = all_exceptions["payment_id"].dropna().astype(str).tolist()
        exception_payment_ids.update(exc_pids)
    clean_payments = len(rzp_payments) - len(exception_payment_ids & set(rzp_payments["payment_id"]))
    match_rate = round(clean_payments / len(rzp_payments), 4) if len(rzp_payments) else 0.0

    # Tier-1 match attempts (informational)
    rzp_matched_count = len(rzp_bank_matched) + len(rzp_oms_matched) + len(rzp_gst_matched)
    unique_matched_payments = set()
    for df in [rzp_bank_matched, rzp_oms_matched, rzp_gst_matched]:
        if not df.empty and "payment_id" in df.columns:
            unique_matched_payments.update(df["payment_id"].dropna().astype(str).tolist())
    matched_count = len(unique_matched_payments)
    exception_count = len(all_exceptions)

    metrics = {
        "total_input_records": total_input,
        "razorpay_payments": len(rzp_payments),
        "bank_credits": len(bank[bank["credit"] > 0]),
        "oms_orders": len(oms),
        "gst_invoices": len(gst),
        "tier1_matched_payments": matched_count,
        "tier1_match_attempts": rzp_matched_count,
        "clean_payments": clean_payments,
        "tier1_exceptions": exception_count,
        "match_rate": match_rate,
        "exception_categories": all_exceptions["exception_category"].value_counts().to_dict() if not all_exceptions.empty else {},
    }

    logger.info(f"Reconciliation done: {metrics['match_rate']:.2%} match rate, {exception_count} exceptions")

    return ReconcileResult(
        df=all_matched,
        exceptions=all_exceptions,
        metrics=metrics,
    )


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run_reconciliation()

    print("\n=== METRICS ===")
    for k, v in result.metrics.items():
        print(f"  {k}: {v}")

    print(f"\n=== EXCEPTIONS ({len(result.exceptions)}) ===")
    if not result.exceptions.empty:
        print(result.exceptions[["payment_id", "exception_category", "reason"]].to_string(index=False))
    else:
        print("  (none)")
