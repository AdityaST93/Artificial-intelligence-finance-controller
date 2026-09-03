"""
Adversarial holdout test for the Razorpay reconciliation engine.

Loads the separate holdout data set (data/holdout/) with KNOWN GROUND TRUTH,
runs the engine against it, and computes honest precision/recall on UNSEEN
data so judges can see the engine holds quality outside the seed=42 main set.

Outputs:
  - data/holdout/results.json   full metric breakdown
  - stdout                     confusion matrix + per-record scores

Assertions:
  - precision > 0.90
  - recall    > 0.85

Run with:
  python -m pytest tests/test_adversarial_holdout.py -v -p no:ethereum
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.reconcile import run_reconciliation  # noqa: E402

HOLDOUT_DIR = Path(__file__).parent.parent / "data" / "holdout"

PRECISION_THRESHOLD = 0.90
RECALL_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ground_truth() -> dict[str, str]:
    with open(HOLDOUT_DIR / "ground_truth.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def result(ground_truth):  # noqa: ARG001  (dependency to ensure ordering)
    return run_reconciliation(data_dir=HOLDOUT_DIR)


@pytest.fixture(scope="module")
def evaluation(result, ground_truth) -> dict:
    """
    Walk the ground truth and the engine output, classify each record as
    TP / FP / FN / TN, and build a confusion matrix keyed by category.
    """
    exceptions_df: pd.DataFrame = result.exceptions
    ex_list = exceptions_df.to_dict("records") if not exceptions_df.empty else []

    # Build a lookup: ground_truth_key -> engine exception row (or None)
    key_to_pred: dict[str, str | None] = {}
    for key in ground_truth:
        source, identifier = key.split("/", 1)
        # Find the engine exception row that corresponds to this key.
        match = _find_engine_exception(source, identifier, ex_list)
        if match is not None:
            key_to_pred[key] = str(match.get("exception_category", "unknown"))
        else:
            key_to_pred[key] = None  # "matched" (no exception)

    tp = fp = fn = tn = 0
    confusion: dict[str, Counter] = {}  # actual -> Counter(predicted)

    for key, actual in ground_truth.items():
        predicted = key_to_pred[key]
        if actual == "matched" and predicted is None:
            tn += 1
        elif actual == "matched" and predicted is not None:
            fp += 1
        elif actual != "matched" and predicted is not None:
            tp += 1
            confusion.setdefault(actual, Counter())[predicted] += 1
        else:  # actual != "matched" and predicted is None
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    # Flatten confusion matrix for JSON
    confusion_dict: dict[str, dict[str, int]] = {
        actual: dict(counter) for actual, counter in confusion.items()
    }

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "total_records": len(ground_truth),
        "total_exceptions_truth": sum(1 for v in ground_truth.values() if v != "matched"),
        "total_exceptions_predicted": sum(1 for v in key_to_pred.values() if v is not None),
        "confusion": confusion_dict,
        "key_to_pred": key_to_pred,
    }


def _find_engine_exception(
    source: str, identifier: str, ex_list: list[dict]
) -> dict | None:
    """
    Find the engine exception row corresponding to a ground truth key.

    Mapping rules:
      razorpay/<payment_id>  -> match on payment_id
      bank/<utr>             -> match on utr (bank-side exceptions)
      oms/<order_id>         -> match on order_id
                                (razorpay-side exceptions also fill in
                                order_id when the OMS join succeeds)
      gst/<invoice_no>       -> match on invoice_no
                                (engine GST exceptions also carry invoice_no)
    """
    candidates: list[dict] = []
    for row in ex_list:
        if source == "razorpay":
            if str(row.get("payment_id", "")) == identifier:
                candidates.append(row)
        elif source == "bank":
            if str(row.get("utr", "")) == identifier:
                candidates.append(row)
        elif source == "oms":
            if str(row.get("order_id", "")) == identifier:
                candidates.append(row)
        elif source == "gst":
            if str(row.get("invoice_no", "")) == identifier:
                candidates.append(row)
    if not candidates:
        return None
    # Prefer the first match; the engine rarely emits two exceptions for the
    # same record. (This is fine for evaluation — duplicates would only matter
    # for confusion matrix detail.)
    return candidates[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_holdout_files_exist():
    """Sanity check: the generator produced all 5 holdout artifacts."""
    for name in [
        "razorpay_settlement.csv",
        "bank_statement.csv",
        "oms_orders.csv",
        "gst_invoices.csv",
        "ground_truth.json",
    ]:
        p = HOLDOUT_DIR / name
        assert p.exists(), f"Missing holdout file: {p}"
        assert p.stat().st_size > 0, f"Holdout file is empty: {p}"


def test_holdout_has_expected_size():
    """~80 records per source (vs 60 in main set)."""
    rzp = pd.read_csv(HOLDOUT_DIR / "razorpay_settlement.csv")
    bank = pd.read_csv(HOLDOUT_DIR / "bank_statement.csv")
    oms = pd.read_csv(HOLDOUT_DIR / "oms_orders.csv")
    gst = pd.read_csv(HOLDOUT_DIR / "gst_invoices.csv")
    for name, df in [("razorpay", rzp), ("bank", bank), ("oms", oms), ("gst", gst)]:
        assert 70 <= len(df) <= 85, f"{name} has {len(df)} rows, expected ~80"


def test_holdout_is_different_from_main():
    """Seed=2026 must produce a different file from seed=42."""
    rzp_holdout = pd.read_csv(HOLDOUT_DIR / "razorpay_settlement.csv")
    rzp_main = pd.read_csv(
        Path(__file__).parent.parent / "data" / "synthetic" / "razorpay_settlement.csv"
    )
    # Different number of rows (80 vs 60+1)
    assert len(rzp_holdout) != len(rzp_main), "Holdout must differ from main set"
    # Different payment_id ranges (pay_H4xxxx vs pay_S3xxxx)
    assert not set(rzp_holdout["payment_id"]).intersection(set(rzp_main["payment_id"]))


def test_precision_meets_threshold(evaluation):
    """precision = TP / (TP + FP) > 0.90 on the holdout set."""
    precision = evaluation["precision"]
    assert precision > PRECISION_THRESHOLD, (
        f"Precision {precision:.4f} below threshold {PRECISION_THRESHOLD} "
        f"(TP={evaluation['tp']}, FP={evaluation['fp']})"
    )


def test_recall_meets_threshold(evaluation):
    """recall = TP / (TP + FN) > 0.85 on the holdout set."""
    recall = evaluation["recall"]
    assert recall > RECALL_THRESHOLD, (
        f"Recall {recall:.4f} below threshold {RECALL_THRESHOLD} "
        f"(TP={evaluation['tp']}, FN={evaluation['fn']})"
    )


def test_results_json_written(result, evaluation, ground_truth):
    """Write the full metric breakdown to data/holdout/results.json."""
    out: dict = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "thresholds": {"precision": PRECISION_THRESHOLD, "recall": RECALL_THRESHOLD},
        "metrics": {
            "precision": round(evaluation["precision"], 4),
            "recall": round(evaluation["recall"], 4),
            "f1": round(evaluation["f1"], 4),
            "tp": evaluation["tp"],
            "fp": evaluation["fp"],
            "fn": evaluation["fn"],
            "tn": evaluation["tn"],
        },
        "totals": {
            "records": evaluation["total_records"],
            "exceptions_ground_truth": evaluation["total_exceptions_truth"],
            "exceptions_predicted": evaluation["total_exceptions_predicted"],
        },
        "confusion_matrix": evaluation["confusion"],
        "reconciliation_metrics": result.metrics,
        "assertions": {
            "precision_above_0.90": evaluation["precision"] > PRECISION_THRESHOLD,
            "recall_above_0.85": evaluation["recall"] > RECALL_THRESHOLD,
        },
    }
    out_path = HOLDOUT_DIR / "results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True, default=str)
    assert out_path.exists()
    assert out_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# Reporting helpers (called from the test session)
# ---------------------------------------------------------------------------


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Print confusion matrix + headline metrics after the test run."""
    # Reload the freshly written results.json (test_results_json_written ran)
    results_path = HOLDOUT_DIR / "results.json"
    if not results_path.exists():
        return
    with open(results_path, encoding="utf-8") as f:
        data = json.load(f)
    m = data["metrics"]
    print("\n" + "=" * 60)
    print("ADVERSARIAL HOLDOUT RESULTS")
    print("=" * 60)
    print(f"  Records:           {data['totals']['records']}")
    print(f"  Exceptions (GT):   {data['totals']['exceptions_ground_truth']}")
    print(f"  Exceptions (pred): {data['totals']['exceptions_predicted']}")
    print(f"  TP: {m['tp']}  FP: {m['fp']}  FN: {m['fn']}  TN: {m['tn']}")
    print(f"  Precision: {m['precision']:.4f}  (threshold > {data['thresholds']['precision']})")
    print(f"  Recall:    {m['recall']:.4f}  (threshold > {data['thresholds']['recall']})")
    print(f"  F1:        {m['f1']:.4f}")
    print()
    print("Confusion matrix (actual -> predicted):")
    print("-" * 60)
    cm = data["confusion_matrix"]
    if not cm:
        print("  (no exception rows in ground truth)")
    else:
        all_cats = sorted({c for row in cm.values() for c in row.keys()} | set(cm.keys()))
        # header
        header = f"  {'actual':<32}" + "".join(f"{c:>18}" for c in all_cats)
        print(header)
        for actual in sorted(cm.keys()):
            row_str = f"  {actual:<32}"
            for pred in all_cats:
                count = cm[actual].get(pred, 0)
                row_str += f"{count:>18}"
            print(row_str)
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-p", "no:ethereum"]))
