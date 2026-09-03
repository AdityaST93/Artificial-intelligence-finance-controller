"""
Forward cash flow forecaster for Razorpay AI Finance Controller.

Projects the next 13 weeks of cash inflows (Razorpay settlements, net of fees)
and outflows (refunds, expected vendor payouts). Output: weekly opening /
inflow / outflow / closing balance with low-balance alert.

This is a deterministic projection based on historical averages and the
reconciled settlement pipeline — NOT a forecasting ML model. For a real
production system, plug in Prophet or a gradient-boosted regressor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "synthetic"


def _inr(x: float | Decimal) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class ForecastResult:
    df: pd.DataFrame  # weekly projections
    opening_balance: Decimal
    closing_balance: Decimal
    lowest_balance: Decimal
    lowest_week: int
    weeks: int
    total_inflow: Decimal
    total_outflow: Decimal
    alert: str | None


def forecast_cash(
    opening_balance: Decimal = Decimal("500000.00"),
    weeks: int = 13,
    historical_inflow_per_week: Decimal | None = None,
    historical_outflow_per_week: Decimal | None = None,
    growth_rate: float = 0.02,
    refund_rate: float = 0.05,
) -> ForecastResult:
    """
    Project the next `weeks` weeks of cash flow.

    Args:
        opening_balance: starting bank balance (Rs)
        weeks: forecast horizon
        historical_inflow_per_week: override (auto-computed from reconciled data if None)
        historical_outflow_per_week: override
        growth_rate: weekly revenue growth (default 2%)
        refund_rate: weekly refunds as fraction of inflow (default 5%)
    """
    # Auto-compute historicals from reconciled settlement data
    if historical_inflow_per_week is None or historical_outflow_per_week is None:
        rzp = pd.read_csv(DATA_DIR / "razorpay_settlement.csv")
        bank = pd.read_csv(DATA_DIR / "bank_statement.csv")

        settled = rzp[(rzp["entity"] == "payment") & (rzp["on_hold"] == "No")]
        total_credits = _inr(settled["credit"].sum())
        refunds = _inr(rzp[rzp["entity"] == "refund"]["debit"].sum())
        # Approximate the data window: 30 days = ~4.3 weeks
        weeks_in_data = 4.3
        if historical_inflow_per_week is None:
            historical_inflow_per_week = _inr(total_credits / Decimal(str(weeks_in_data)))
        if historical_outflow_per_week is None:
            historical_outflow_per_week = _inr(refunds / Decimal(str(weeks_in_data)))

    # Project weekly
    rows = []
    balance = opening_balance
    start = datetime.now()

    total_inflow = Decimal("0")
    total_outflow = Decimal("0")
    lowest_balance = balance
    lowest_week = 0

    for week in range(1, weeks + 1):
        # Apply growth (compounding)
        growth = Decimal(str((1 + growth_rate) ** (week - 1)))
        inflow = _inr(historical_inflow_per_week * growth)
        outflow = _inr(historical_outflow_per_week * growth)

        net = inflow - outflow
        closing = balance + net
        week_start = start + timedelta(weeks=week - 1)
        week_end = week_start + timedelta(days=6)

        rows.append({
            "week": week,
            "week_start": week_start.strftime("%Y-%m-%d"),
            "week_end": week_end.strftime("%Y-%m-%d"),
            "opening": float(balance),
            "inflow": float(inflow),
            "outflow": float(outflow),
            "net": float(net),
            "closing": float(closing),
        })

        total_inflow += inflow
        total_outflow += outflow
        balance = closing
        if closing < lowest_balance:
            lowest_balance = closing
            lowest_week = week

    # Alert: if closing dips below 10% of opening
    threshold = opening_balance * Decimal("0.10")
    alert = None
    if lowest_balance < threshold:
        alert = f"LOW BALANCE ALERT: week {lowest_week} closing Rs {lowest_balance:.2f} is below 10% of opening (Rs {threshold:.2f})"
    elif lowest_balance < opening_balance * Decimal("0.50"):
        alert = f"Caution: week {lowest_week} closing Rs {lowest_balance:.2f} is below 50% of opening"

    return ForecastResult(
        df=pd.DataFrame(rows),
        opening_balance=opening_balance,
        closing_balance=balance,
        lowest_balance=lowest_balance,
        lowest_week=lowest_week,
        weeks=weeks,
        total_inflow=total_inflow,
        total_outflow=total_outflow,
        alert=alert,
    )


if __name__ == "__main__":
    result = forecast_cash()
    print(f"\n=== 13-WEEK CASH FORECAST ===")
    print(f"Opening balance: Rs {result.opening_balance:,.2f}")
    print(f"Closing balance: Rs {result.closing_balance:,.2f}")
    print(f"Lowest balance:  Rs {result.lowest_balance:,.2f} (week {result.lowest_week})")
    print(f"Total inflow:    Rs {result.total_inflow:,.2f}")
    print(f"Total outflow:   Rs {result.total_outflow:,.2f}")
    if result.alert:
        print(f"\n*** {result.alert} ***")
    print(f"\n{result.df.to_string(index=False)}")
