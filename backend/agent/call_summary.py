"""Builds the end-of-call summary from the seller report and conversation state.

Deterministic Python (no extra LLM call): every number comes from the report,
and only actions the seller actually agreed to are listed as commitments.
"""

from backend.agent.seller_agent import INVESTIGATION_TOPICS
from backend.analysis.seller_analysis import format_inr

DEFAULT_RECOMMENDATIONS = [
    "Check and replenish high-demand products that are out of stock.",
    "Investigate the reasons for increased cancellations.",
    "Review product visibility and conversion metrics with the seller before changing listings.",
]

TOPIC_NEXT_STEPS = {
    "stockouts": "Confirm which out-of-stock products are best-sellers and how long they have been unavailable.",
    "cancellations": "Find out the main reasons for cancellations (seller-side stock or packing delays, customer-initiated, courier or returns).",
    "visibility": "Review product views and conversion with the seller before suggesting listing changes (no traffic data was available).",
}

DISCLAIMER = (
    "Based on sample data and this conversation. Nothing listed here has been done yet; "
    "recommendations are suggestions and commitments are plans."
)


def _signed(value) -> str:
    return f"{value:+g}"


def build_call_summary(report: dict, state) -> dict:
    last, this, ch = report["last_month"], report["this_month"], report["changes"]

    # Main problem
    verb = "declined" if ch["sales_change_pct"] < 0 else "grew"
    orders_dir = "down" if ch["orders_change_pct"] < 0 else "up"
    main_problem = (
        f"Sales {verb} {abs(ch['sales_change_pct'])}% month over month "
        f"({format_inr(last['sales'])} → {format_inr(this['sales'])}), with orders "
        f"{orders_dir} {abs(ch['orders_change_pct'])}% ({last['orders']} → {this['orders']})."
    )
    if ch["avg_selling_price_change_pct"] == 0:
        main_problem += (
            " The average selling price is unchanged, so the drop looks "
            "volume-driven rather than price-driven."
        )

    # Evidence (all from the report)
    price_note = (
        "unchanged"
        if ch["avg_selling_price_change_pct"] == 0
        else f"{_signed(ch['avg_selling_price_change_pct'])}%"
    )
    evidence = [
        f"Sales: {format_inr(last['sales'])} → {format_inr(this['sales'])} ({_signed(ch['sales_change_pct'])}%)",
        f"Orders: {last['orders']} → {this['orders']} ({_signed(ch['orders_change_pct'])}%)",
        f"Average selling price: {format_inr(last['avg_selling_price'])} → {format_inr(this['avg_selling_price'])} ({price_note})",
        f"Cancellation rate: {last['cancellation_rate']}% → {this['cancellation_rate']}% ({_signed(ch['cancellation_change_pp'])} percentage points)",
        f"Out-of-stock products: {last['out_of_stock_products']} → {this['out_of_stock_products']} ({_signed(ch['out_of_stock_change'])})",
    ]

    # Possible contributing factors: flagged signals + what the seller reported
    factor_ids = {"stockouts_up", "cancellations_up"}
    possible_factors = [s["finding"] for s in report["warning_signals"] if s["id"] in factor_ids]
    possible_factors += [f"Reported by the seller: {fact}" for fact in state.seller_facts]

    # Recommendations
    if state.recommendations:
        recommendations, rec_note = list(state.recommendations[:3]), None
    else:
        recommendations = list(DEFAULT_RECOMMENDATIONS)
        rec_note = "Suggested from the data. These were not fully discussed on this call."

    # Next steps
    next_steps = [
        f"{action} (seller's commitment; not yet completed)" for action in state.agreed_actions
    ]
    if not state.agreed_actions:
        next_steps.append("Agree with the seller on which of the recommended actions to start with.")
    for topic in INVESTIGATION_TOPICS:
        if topic not in state.covered_topics:
            next_steps.append(TOPIC_NEXT_STEPS[topic])
    next_steps.append(
        "Re-check sales, cancellation rate and stockout count next month to see whether things have improved."
    )

    return {
        "main_problem": main_problem,
        "evidence": evidence,
        "possible_factors": possible_factors,
        "recommendations": recommendations,
        "recommendations_note": rec_note,
        "agreed_actions": list(state.agreed_actions),
        "next_steps": next_steps,
        "disclaimer": DISCLAIMER,
    }


def summary_to_markdown(summary: dict) -> str:
    def bullets(items):
        return "\n".join(f"- {item}" for item in items)

    recs = "\n".join(f"{i}. {r}" for i, r in enumerate(summary["recommendations"], start=1))
    lines = [
        "### Main problem identified",
        summary["main_problem"],
        "",
        "### Evidence from seller metrics",
        bullets(summary["evidence"]),
        "",
        "### Possible contributing factors (to be confirmed, not proven causes)",
        bullets(summary["possible_factors"]) or "None identified yet.",
        "",
        "### Recommendations",
    ]
    if summary["recommendations_note"]:
        lines.append(f"*{summary['recommendations_note']}*")
    lines += [
        recs,
        "",
        "### Actions agreed by the seller",
        bullets(summary["agreed_actions"]) or "No commitments were recorded on this call.",
        "",
        "### Next steps",
        bullets(summary["next_steps"]),
        "",
        f"*{summary['disclaimer']}*",
    ]
    return "\n".join(lines)