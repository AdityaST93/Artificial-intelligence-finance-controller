"""
LangChain agent with tools for Q&A over reconciled finance data.

Uses OpenRouter's free tier (e.g. meta-llama/llama-3.3-70b-instruct:free)
as the LLM backbone. Tools expose deterministic queries over the
reconciled DataFrame so the LLM never invents numbers.

If no API key is set, falls back to a deterministic answer mode
(answers come from pandas queries, no LLM call).

Compatible with LangChain 1.x.
"""

from __future__ import annotations

import logging
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from core import rag as rag_module

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "minimax/minimax-m3:free")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def get_llm():
    """Return a LangChain LLM pointed at OpenRouter, or None if no key."""
    if not OPENROUTER_API_KEY or OPENROUTER_API_KEY.startswith("sk-or-v1-your"):
        return None
    return ChatOpenAI(
        model=OPENROUTER_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE,
        temperature=0.0,
        max_tokens=800,
    )


# ---------------------------------------------------------------------------
# Cached reconciliation result
# ---------------------------------------------------------------------------

_cached_result = None


def get_cached_result():
    global _cached_result
    if _cached_result is None:
        from core.reconcile import run_reconciliation
        _cached_result = run_reconciliation()
    return _cached_result


def reset_cache():
    global _cached_result
    _cached_result = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_all() -> dict:
    DATA_DIR = Path(__file__).parent.parent / "data" / "synthetic"
    return {
        "razorpay": pd.read_csv(DATA_DIR / "razorpay_settlement.csv"),
        "bank": pd.read_csv(DATA_DIR / "bank_statement.csv"),
        "oms": pd.read_csv(DATA_DIR / "oms_orders.csv"),
        "gst": pd.read_csv(DATA_DIR / "gst_invoices.csv"),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def explain_payment(payment_id: str) -> str:
    """
    Explain a single Razorpay payment: amount, fee, tax, net, settlement status,
    bank match, OMS match, GST match. Use when user asks 'Why is payment X short?'
    or 'Show me details of pay_XXX'.
    """
    sources = _load_all()
    rzp, bank, oms, gst = sources["razorpay"], sources["bank"], sources["oms"], sources["gst"]

    payment = rzp[rzp["payment_id"] == payment_id]
    if payment.empty:
        return f"Payment {payment_id} not found in Razorpay settlement file."

    p = payment.iloc[0]
    gross = Decimal(str(p["amount"]))
    fee = Decimal(str(p["fee"]))
    tax = Decimal(str(p["tax"]))
    net = gross - fee - tax

    lines = [
        f"Payment: {payment_id}",
        f"  Order receipt: {p['order_receipt']}",
        f"  Method: {p['method']}",
        f"  Gross amount: Rs {gross:.2f}",
        f"  Razorpay fee: Rs {fee:.2f} ({float(fee/gross*100):.2f}%)" if gross > 0 else f"  Razorpay fee: Rs {fee:.2f}",
        f"  GST on fee:   Rs {tax:.2f} (18% of fee)",
        f"  Net settled:  Rs {net:.2f}",
        f"  Created: {p['created_at']}",
        f"  Settled: {p['settled_at'] or 'NOT SETTLED'}",
        f"  On hold: {p['on_hold']}",
        f"  UTR: {p['settlement_utr'] or '(none)'}",
    ]

    if p["on_hold"] == "No":
        bm = bank[bank["utr"] == p["settlement_utr"]]
        if not bm.empty:
            b = bm.iloc[0]
            lines.append(f"\nBank match (UTR={b['utr'][:14]}...):")
            lines.append(f"  Date: {b['date']}")
            lines.append(f"  Credit: Rs {b['credit']:.2f}")
            diff = abs(Decimal(str(b["credit"])) - net)
            if diff > Decimal("0.05"):
                lines.append(f"  *** AMOUNT MISMATCH: bank Rs {b['credit']:.2f}, expected Rs {net:.2f} (diff Rs {diff:.2f})")
        else:
            lines.append("\n*** Bank match: NOT FOUND. Settlement in transit or missing.")

    om = oms[oms["transaction_id"] == payment_id]
    if not om.empty:
        o = om.iloc[0]
        lines.append(f"\nOMS match (order {o['order_id']}):")
        lines.append(f"  Status: {o['order_status']}")
        lines.append(f"  Order total: Rs {o['order_total']:.2f}")
        if abs(Decimal(str(o['order_total'])) - gross) > Decimal("0.05"):
            lines.append(f"  *** OMS AMOUNT MISMATCH: OMS Rs {o['order_total']:.2f}, Razorpay Rs {gross:.2f}")
        if o["order_status"] == "cancelled":
            lines.append("  *** ORDER CANCELLED but Razorpay captured. Initiate refund.")
    else:
        lines.append("\n*** OMS match: NOT FOUND. Possible fraud or webhook miss.")

    g = gst[gst["razorpay_payment_id"] == payment_id]
    if not g.empty:
        gi = g.iloc[0]
        lines.append(f"\nGST invoice {gi['invoice_no']}:")
        lines.append(f"  Taxable: Rs {gi['taxable_value']:.2f}")
        lines.append(f"  CGST: Rs {gi['cgst']:.2f}  SGST: Rs {gi['sgst']:.2f}")
        lines.append(f"  Total: Rs {gi['total']:.2f}")
        if abs(Decimal(str(gi['total'])) - gross) > Decimal("0.05"):
            lines.append(f"  *** GST TOTAL MISMATCH: invoice Rs {gi['total']:.2f}, Razorpay Rs {gross:.2f}")
    else:
        lines.append("\n*** GST invoice: MISSING. Generate invoice for ITC claim.")

    return "\n".join(lines)


@tool
def list_exceptions(category: str = "all") -> str:
    """
    List reconciliation exceptions. Optional category filter.
    """
    r = get_cached_result()
    if r.exceptions.empty:
        return "No exceptions found. Clean reconciliation."

    if category == "all":
        ex = r.exceptions
        header = f"All {len(ex)} exceptions:"
    else:
        ex = r.exceptions[r.exceptions["exception_category"] == category]
        if ex.empty:
            return f"No exceptions of category '{category}'."
        header = f"{len(ex)} exceptions of category '{category}':"

    lines = [header, ""]
    for _, e in ex.iterrows():
        pid = e.get("payment_id") or e.get("utr") or e.get("order_id") or "(unknown)"
        lines.append(f"  - {pid}: {e['exception_category']} | {e['reason']}")
    return "\n".join(lines)


@tool
def reconcile_summary() -> str:
    """Top-level reconciliation summary: total records, match rate, exception counts."""
    r = get_cached_result()
    m = r.metrics
    lines = [
        "Reconciliation summary:",
        f"  Razorpay payments: {m.get('razorpay_payments', 0)}",
        f"  Bank credits:      {m.get('bank_credits', 0)}",
        f"  OMS orders:        {m.get('oms_orders', 0)}",
        f"  GST invoices:      {m.get('gst_invoices', 0)}",
        f"  Match rate:        {m.get('match_rate', 0):.2%}",
        f"  Payments matched:  {m.get('tier1_matched_payments', 0)}",
        f"  Clean payments:    {m.get('clean_payments', 0)}",
        f"  Exceptions found:  {m.get('tier1_exceptions', 0)}",
        "",
        "Exception breakdown:",
    ]
    for cat, count in m.get("exception_categories", {}).items():
        lines.append(f"  - {cat}: {count}")
    return "\n".join(lines)


@tool
def fee_variance_analysis() -> str:
    """Identify rows where Razorpay fee deviates from the expected rate."""
    sources = _load_all()
    rzp = sources["razorpay"]
    expected = {"upi": 0.0, "card": 0.02, "netbanking": 0.015, "wallet": 0.015, "emi": 0.02}
    lines = ["Fee variance analysis (vs expected rate):", ""]
    found = 0
    for _, r in rzp[rzp["entity"] == "payment"].iterrows():
        method = r["method"]
        if method not in expected:
            continue
        expected_fee = Decimal(str(r["amount"])) * Decimal(str(expected[method]))
        actual_fee = Decimal(str(r["fee"]))
        diff = abs(actual_fee - expected_fee)
        if diff > Decimal("0.05"):
            found += 1
            lines.append(
                f"  {r['payment_id']} ({method}): expected Rs {expected_fee:.2f}, actual Rs {actual_fee:.2f} (diff Rs {diff:.2f})"
            )
    if found == 0:
        return "No fee variance detected. All rates match contract."
    lines.insert(1, f"Found {found} rows with fee variance:")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Direct-call helpers (used by fallback and Streamlit)
# ---------------------------------------------------------------------------

def call_tool(name: str, **kwargs) -> str:
    """Direct tool call (bypasses LLM). Used by fallback and Streamlit quick-actions."""
    if name == "explain_payment":
        return explain_payment.invoke(kwargs)
    if name == "list_exceptions":
        return list_exceptions.invoke(kwargs)
    if name == "reconcile_summary":
        return reconcile_summary.invoke(kwargs)
    if name == "fee_variance_analysis":
        return fee_variance_analysis.invoke(kwargs)
    return f"Unknown tool: {name}"


# ---------------------------------------------------------------------------
# Agent factory (LangChain 1.x style)
# ---------------------------------------------------------------------------

def get_agent():
    """Build a tool-calling agent. Returns None if no API key is set."""
    llm = get_llm()
    if llm is None:
        return None

    try:
        from langchain.agents import create_agent
        tools = [explain_payment, list_exceptions, reconcile_summary, fee_variance_analysis]
        agent = create_agent(llm, tools)
        return agent
    except Exception as e:
        logger.warning(f"create_agent failed: {e}")
        return None


# ---------------------------------------------------------------------------
# RAG context retrieval (vector search via ChromaDB)
# ---------------------------------------------------------------------------

def _retrieve_rag_context(question: str, k: int = 5) -> List[Dict[str, Any]]:
    """Best-effort RAG retrieval. Returns [] on any failure (no index,
    no embedder, etc.) so the rest of the pipeline keeps working.
    """
    try:
        return rag_module.retrieve_context(question, k=k)
    except Exception as e:  # noqa: BLE001
        logger.warning("RAG retrieve_context failed: %s", e)
        return []


def _build_rag_system_prompt(question: str, k: int = 5) -> str:
    """Return a system prompt containing the top-k retrieved rows, or a
    short notice if no context was available. Designed to be prepended
    to the LLM call so the model answers from the actual data.
    """
    rows = _retrieve_rag_context(question, k=k)
    if not rows:
        return (
            "You are a finance controller. No vector index is available yet, "
            "so answer using only the tools provided and any data already in "
            "this conversation. Cite payment IDs, UTRs, and order IDs when "
            "you state numbers. If you do not know, say so."
        )
    block = rag_module.format_context_for_prompt(rows)
    return (
        "You are a finance controller. Use the retrieved context below as "
        "your primary source of truth. Always cite the [index] of the row "
        "you are quoting (e.g. 'see [2]'). If the context is insufficient, "
        "you may also call the available tools. Never invent numbers.\n\n"
        f"Retrieved context (top {len(rows)} of {len(rows)}):\n{block}"
    )


def _format_citation_footer(rows: List[Dict[str, Any]]) -> str:
    """Append a small 'sources' block to the answer."""
    if not rows:
        return ""
    lines = ["\n\nSources:"]
    for i, r in enumerate(rows, 1):
        meta = r.get("metadata") or {}
        src = meta.get("source", "?")
        ident = (
            meta.get("payment_id")
            or meta.get("order_id")
            or meta.get("utr")
            or meta.get("invoice_no")
            or r.get("id", "?")
        )
        lines.append(f"  [{i}] {src} / {ident} (score={r.get('score', 0):.3f})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ask (the public Q&A entry point)
# ---------------------------------------------------------------------------

def ask(question: str) -> str:
    """Ask a question. RAG context is retrieved first, then the LLM is
    called with that context + tool descriptions. Falls back to a
    deterministic answer if no LLM is available, and surfaces the
    retrieved context even in fallback mode (so users still see cites).
    """
    rag_rows = _retrieve_rag_context(question, k=5)
    system_prompt = _build_rag_system_prompt(question, k=5)

    # LLM path: inject retrieved context as a system message
    agent = get_agent()
    if agent is not None:
        try:
            result = agent.invoke(
                {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question},
                    ]
                }
            )
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.__class__.__name__ == "AIMessage":
                    answer = msg.content
                    if rag_rows:
                        return answer + _format_citation_footer(rag_rows)
                    return answer
            return str(result)
        except Exception as e:
            logger.warning(f"Agent error: {e}; falling back to deterministic")
            return f"[Agent error: {e}]\n\n{_fallback_answer(question, rag_rows)}"

    # No LLM: deterministic answer, but include retrieved context as cites
    return _fallback_answer(question, rag_rows)


# ---------------------------------------------------------------------------
# Fallback (no LLM) — pattern-matches common questions
# ---------------------------------------------------------------------------

def _fallback_answer(question: str, rag_rows: Optional[List[Dict[str, Any]]] = None) -> str:
    q = question.lower()

    # "Why is pay_X short?"
    m = re.search(r"pay_[A-Za-z0-9]+", question, re.IGNORECASE)
    if m:
        body = call_tool("explain_payment", payment_id=m.group(0).upper())
        if rag_rows:
            return body + _format_citation_footer(rag_rows)
        return body

    if any(w in q for w in ["summary", "match rate", "how many", "metrics", "status", "overview"]):
        return call_tool("reconcile_summary")

    if "fee" in q and ("variance" in q or "different" in q or "wrong" in q or "rate" in q):
        return call_tool("fee_variance_analysis")

    if "exception" in q or "unmatched" in q or "missing" in q or "fail" in q:
        cats = [
            "missing_bank_credit", "orphan_bank_credit", "amount_mismatch",
            "oms_amount_mismatch", "missing_oms_order", "ghost_oms_order",
            "cancelled_order_with_payment", "fee_rate_variance",
            "gst_amount_mismatch", "missing_gst_invoice",
        ]
        for c in cats:
            if c.replace("_", " ") in q or c in q:
                return call_tool("list_exceptions", category=c)
        return call_tool("list_exceptions", category="all")

    # Default: show summary + suggest questions
    return (
        "I can answer questions like:\n"
        "  - 'Why is pay_S30000 short?'\n"
        "  - 'Show reconciliation summary'\n"
        "  - 'List all exceptions'\n"
        "  - 'List missing_bank_credit exceptions'\n"
        "  - 'Show fee variance'\n\n"
        f"{call_tool('reconcile_summary')}"
    )


if __name__ == "__main__":
    import sys
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Show reconciliation summary"
    print(ask(question))
