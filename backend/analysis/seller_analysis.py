"""Seller performance analysis. All business math lives here, not in the LLM."""

import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "seller.json"

# Thresholds for raising a warning signal (simple, explainable rules)
SALES_DROP_WARN_PCT = 10        # warn if sales fall by 10% or more
CANCELLATION_WARN_PP = 3        # warn if cancellation rate rises by 3+ percentage points
STOCKOUT_WARN_INCREASE = 5      # warn if out-of-stock products rise by 5 or more


def load_seller_data(path: Path = DATA_PATH) -> dict:
    """Load seller data from JSON."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pct_change(old: float, new: float) -> float:
    """Percentage change from old to new, rounded to 1 decimal. Negative = decrease."""
    if old == 0:
        raise ValueError("Cannot calculate percentage change from a zero baseline.")
    return round((new - old) / old * 100, 1)


def format_inr(amount: float) -> str:
    """Format a number in the Indian digit grouping, e.g. 200000 -> ₹2,00,000."""
    n = int(round(amount))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{'-' if n < 0 else ''}₹{s}"


def calculate_changes(last: dict, this: dict) -> dict:
    """Compute all metric changes between two months."""
    return {
        "sales_change_pct": pct_change(last["sales"], this["sales"]),
        "orders_change_pct": pct_change(last["orders"], this["orders"]),
        "avg_selling_price_change_pct": pct_change(
            last["avg_selling_price"], this["avg_selling_price"]
        ),
        "cancellation_change_pp": round(
            this["cancellation_rate"] - last["cancellation_rate"], 1
        ),
        "out_of_stock_change": this["out_of_stock_products"]
        - last["out_of_stock_products"],
    }


def identify_warning_signals(last: dict, this: dict, changes: dict) -> list[dict]:
    """Flag possible contributing factors. These are signals to investigate, not proven causes."""
    signals = []

    if changes["sales_change_pct"] <= -SALES_DROP_WARN_PCT:
        signals.append({
            "id": "sales_decline",
            "severity": "high",
            "finding": (
                f"Sales fell {abs(changes['sales_change_pct'])}% "
                f"({format_inr(last['sales'])} to {format_inr(this['sales'])})."
            ),
        })

    if changes["orders_change_pct"] <= -SALES_DROP_WARN_PCT:
        signals.append({
            "id": "orders_decline",
            "severity": "high",
            "finding": (
                f"Orders fell {abs(changes['orders_change_pct'])}% "
                f"({last['orders']} to {this['orders']})."
            ),
        })

    if changes["out_of_stock_change"] >= STOCKOUT_WARN_INCREASE:
        signals.append({
            "id": "stockouts_up",
            "severity": "medium",
            "finding": (
                f"Out-of-stock products rose from {last['out_of_stock_products']} "
                f"to {this['out_of_stock_products']}. This may have limited sales "
                "if best-sellers are affected; needs confirmation from the seller."
            ),
        })

    if changes["cancellation_change_pp"] >= CANCELLATION_WARN_PP:
        signals.append({
            "id": "cancellations_up",
            "severity": "medium",
            "finding": (
                f"Cancellation rate rose from {last['cancellation_rate']}% "
                f"to {this['cancellation_rate']}% "
                f"(+{changes['cancellation_change_pp']} percentage points). "
                "Reasons are unknown and need investigation."
            ),
        })

    if changes["avg_selling_price_change_pct"] == 0:
        signals.append({
            "id": "price_unchanged",
            "severity": "info",
            "finding": (
                "Average selling price is unchanged "
                f"({format_inr(this['avg_selling_price'])}), so the drop looks "
                "volume-driven rather than price-driven."
            ),
        })

    return signals


def generate_report(data: dict | None = None) -> dict:
    """Build the structured seller performance report used by the AI agent."""
    data = data or load_seller_data()
    last = data["metrics"]["last_month"]
    this = data["metrics"]["this_month"]
    changes = calculate_changes(last, this)
    return {
        "seller": {
            "id": data["seller_id"],
            "name": data["seller_name"],
            "business_name": data["business_name"],
            "category": data["category"],
        },
        "last_month": last,
        "this_month": this,
        "changes": changes,
        "warning_signals": identify_warning_signals(last, this, changes),
        "data_disclaimer": "Sample/simulated data for demo purposes.",
    }