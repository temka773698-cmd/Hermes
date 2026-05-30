from src.profit_calculator import CostInput, ProductInput, calculate_product_profit


def test_marks_positive_profit_below_min_profit_as_low_profit_not_loss():
    product = ProductInput(
        offer_id="LOW-PROFIT-1",
        name="Маленькая прибыль",
        current_price=1000,
        ozon_expenses=300,
        ad_expenses=0,
        in_promo=True,
    )
    cost = CostInput(
        offer_id="LOW-PROFIT-1",
        purchase_price=250,
        packaging=50,
        extra_expenses=0,
        tax_percent=0,
        min_profit=500,
        min_margin_percent=10,
    )

    result = calculate_product_profit(product, cost)

    assert result.profit == 400
    assert result.safe_price == 1100
    assert result.status == "LOW_PROFIT"
    assert "прибыль ниже цели" in result.reason.lower()
