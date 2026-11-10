from backend.analysis.seller_analysis import (
    calculate_changes,
    format_inr,
    generate_report,
    pct_change,
)


def test_pct_change_decrease():
    assert pct_change(200000, 135000) == -32.5
    assert pct_change(400, 270) == -32.5


def test_pct_change_zero_baseline_raises():
    import pytest
    with pytest.raises(ValueError):
        pct_change(0, 10)


def test_format_inr():
    assert format_inr(200000) == "₹2,00,000"
    assert format_inr(135000) == "₹1,35,000"
    assert format_inr(500) == "₹500"


def test_calculate_changes():
    last = {"sales": 200000, "orders": 400, "cancellation_rate": 8,
            "avg_selling_price": 500, "out_of_stock_products": 5}
    this = {"sales": 135000, "orders": 270, "cancellation_rate": 14,
            "avg_selling_price": 500, "out_of_stock_products": 18}
    c = calculate_changes(last, this)
    assert c["sales_change_pct"] == -32.5
    assert c["orders_change_pct"] == -32.5
    assert c["avg_selling_price_change_pct"] == 0
    assert c["cancellation_change_pp"] == 6
    assert c["out_of_stock_change"] == 13


def test_report_has_expected_signals():
    report = generate_report()
    ids = {s["id"] for s in report["warning_signals"]}
    assert {"sales_decline", "orders_decline", "stockouts_up",
            "cancellations_up", "price_unchanged"} <= ids
    assert "Sample" in report["data_disclaimer"]