from backend.agent.call_summary import (
    DEFAULT_RECOMMENDATIONS,
    build_call_summary,
    summary_to_markdown,
)
from backend.agent.seller_agent import ConversationState
from backend.analysis.seller_analysis import generate_report


def test_summary_uses_real_numbers():
    s = build_call_summary(generate_report(), ConversationState())
    assert "32.5%" in s["main_problem"]
    assert any("5 → 18" in line for line in s["evidence"])
    assert any("8% → 14%" in line for line in s["evidence"])


def test_no_commitments_unless_agreed():
    s = build_call_summary(generate_report(), ConversationState())
    assert s["agreed_actions"] == []
    assert "No commitments" in summary_to_markdown(s)


def test_falls_back_to_default_recommendations_with_note():
    s = build_call_summary(generate_report(), ConversationState())
    assert s["recommendations"] == DEFAULT_RECOMMENDATIONS
    assert s["recommendations_note"]


def test_agreed_actions_and_open_topics():
    state = ConversationState(
        covered_topics={"stockouts"},
        recommendations=["Restock best-sellers", "Review cancellations"],
        agreed_actions=["Restock best-sellers this week"],
        seller_facts=["Three best-sellers out of stock"],
    )
    s = build_call_summary(generate_report(), state)
    assert s["recommendations"] == ["Restock best-sellers", "Review cancellations"]
    assert s["recommendations_note"] is None
    assert s["agreed_actions"] == ["Restock best-sellers this week"]
    assert any("not yet completed" in step for step in s["next_steps"])
    assert any("cancellations" in step.lower() for step in s["next_steps"])  # topic still open
    assert any("Three best-sellers" in f for f in s["possible_factors"])