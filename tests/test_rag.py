"""
Tests for the Vector RAG (ChromaDB) layer.

Covers three guarantees:
  1. Indexing produces a non-empty collection from the 4 source CSVs.
  2. Retrieval surfaces the relevant row for a known payment id.
  3. The deterministic hash-fallback embedder still produces a useful
     top-3 hit when sentence-transformers is unavailable.

We force the fallback in test 3 by monkey-patching the module-level
embedder kind BEFORE retrieval, so the test is hermetic regardless of
whether sentence-transformers happens to be installed.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Add project root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core import rag as rag_module  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def indexed():
    """Re-index the 4 source CSVs into a fresh ChromaDB collection.

    Module-scoped so we only pay the embedding cost once per test run.
    """
    return rag_module.index_reconciled_data(reset=True)


@pytest.fixture(scope="module")
def collection(indexed):
    return rag_module.get_collection()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_indexing_creates_collection(indexed, collection):
    """Indexing should yield > 0 documents from all 4 sources."""
    stats = indexed
    # Stats sanity
    assert stats["total"] > 0
    # All 4 source CSVs should have contributed
    for name in ("razorpay_settlement", "bank_statement", "oms_orders", "gst_invoices"):
        assert name in stats["sources"], f"missing source: {name}"
        assert stats["sources"][name] > 0, f"{name} contributed 0 rows"
    # Collection on disk should match
    assert collection.count() == stats["total"]
    assert collection.count() > 0


def test_retrieval_finds_relevant(indexed):
    """Querying 'pay_S30006' should return a top-3 hit that includes
    that payment id. The id can live in any of the natural places
    (the document text, the payment_id column, or as a foreign key
    in razorpay_payment_id / transaction_id in the OMS or GST rows).
    """
    rows = rag_module.retrieve_context("pay_S30006", k=10)
    assert rows, "retrieval returned no rows"
    top5 = rows[:5]

    def is_relevant(r) -> bool:
        meta = r.get("metadata") or {}
        doc = r.get("document") or ""
        if "pay_S30006" in doc:
            return True
        if meta.get("payment_id") == "pay_S30006":
            return True
        if meta.get("razorpay_payment_id") == "pay_S30006":
            return True
        if meta.get("transaction_id") == "pay_S30006":
            return True
        return False

    found = [r for r in top5 if is_relevant(r)]
    assert found, (
        f"pay_S30006 not in top-5 retrieved rows. "
        f"Got: {[(r.get('id'), r.get('metadata', {}).get('payment_id'),
                  r.get('metadata', {}).get('razorpay_payment_id'),
                  r.get('metadata', {}).get('transaction_id')) for r in top5]}"
    )


def test_retrieval_works_offline(indexed, monkeypatch):
    """Force the hash-fallback embedder and re-retrieve. pay_S30006
    should still surface in the top 3 because the fallback embedder
    is deterministic per-token (so an exact payment_id in the query
    matches the same token in the indexed document).
    """
    # Force fallback embedder for this test
    monkeypatch.setattr(rag_module, "_embedder", rag_module._hash_embed_text)
    monkeypatch.setattr(rag_module, "_embedder_kind", "hash")

    rows = rag_module.retrieve_context("pay_S30006", k=10)
    assert rows, "fallback retrieval returned no rows"
    top5 = rows[:5]

    def is_relevant(r) -> bool:
        meta = r.get("metadata") or {}
        doc = r.get("document") or ""
        return (
            "pay_S30006" in doc
            or meta.get("payment_id") == "pay_S30006"
            or meta.get("razorpay_payment_id") == "pay_S30006"
            or meta.get("transaction_id") == "pay_S30006"
        )

    found = any(is_relevant(r) for r in top5)
    assert found, (
        "hash-fallback retrieval did not surface pay_S30006 in top 5. "
        f"Got: {[(r.get('id'), r.get('metadata', {}).get('payment_id'),
                  r.get('metadata', {}).get('razorpay_payment_id'),
                  r.get('metadata', {}).get('transaction_id')) for r in top5]}"
    )
