# Exception Taxonomy — Honest Classification

We classify every unresolved record into one of **10 categories**. Each carries:
- A **category** (machine-readable)
- A **reason** (human-readable, one line)
- A **suggested action** (what a finance ops person should do next)

The goal: **no record is silently dropped**. Every row in the input is either matched or explicitly named.

| # | Category | Trigger | Reason | Suggested Action |
|---|---|---|---|---|
| 1 | `missing_bank_credit` | Razorpay has settled payment, bank has no matching UTR | Settlement not yet credited (T+2 still in transit, or hold) | Wait 24h; if still missing, raise with Razorpay support |
| 2 | `orphan_bank_credit` | Bank has credit, Razorpay has no matching UTR | Manual adjustment, interest credit, or unknown source | Investigate source; if unknown, log to suspense ledger |
| 3 | `amount_mismatch` | UTR matches but credit differs > ₹0.05 | Fee variance, partial capture, FX rounding | Compare fee schedule; if unexplained, raise dispute |
| 4 | `oms_amount_mismatch` | Razorpay amount ≠ OMS order total | Cart bug, manual discount applied after payment | Reconcile cart; refund/adjust OMS |
| 5 | `missing_oms_order` | Razorpay payment has no matching OMS order | Cart-recovery bug, fraud (stolen card), webhook miss | Investigate; if fraud, block customer + raise chargeback |
| 6 | `ghost_oms_order` | OMS marks order paid but no Razorpay payment | Customer claimed paid without paying, status bug | Verify with customer; if fraud, mark order fraud |
| 7 | `cancelled_order_with_payment` | OMS order cancelled but Razorpay captured payment | Cancellation flow didn't trigger refund | Initiate refund via `/v1/payments/:id/refund` |
| 8 | `fee_rate_variance` | Razorpay fee ≠ contracted MDR | Contract terms vs actual, plan migration | Update fee schedule; if persistent, raise with account manager |
| 9 | `gst_amount_mismatch` | Invoice total ≠ Razorpay amount | Tax calculation error, invoice generated before fee | Regenerate invoice; if systematic, fix tax engine |
| 10 | `missing_gst_invoice` | Payment has no matching GST invoice | Invoice not generated, supplier not filed | Generate invoice; if past period, late-filing in next return |

## Why this list

Drawn from real Razorpay merchant pain points and Indian finance ops practice:
- 60%+ merchants still reconcile on spreadsheets (Razorpay blog)
- FinOps teams burn 65% of time on reconciliation
- Common exceptions in production: on-hold, refunds, fee variance, T+2 timing

We do **not** include "unknown" as a category. If we can't classify, the LLM agent flags it for human review with the raw source rows attached.
