import pytest

from src.profit_calculator import ProductInput, CostInput, calculate_product_profit


def test_marks_product_as_loss_when_current_price_below_safe_price():
    product = ProductInput(
        offer_id="PUMP-001",
        name="Насос тестовый",
        current_price=4490,
        ozon_expenses=700,
        ad_expenses=200,
        in_promo=True,
    )
    cost = CostInput(
        offer_id="PUMP-001",
        purchase_price=3200,
        packaging=150,
        extra_expenses=100,
        tax_percent=6,
        min_profit=400,
        min_margin_percent=15,
    )

    result = calculate_product_profit(product, cost)

    assert result.safe_price == pytest.approx(4750)
    assert result.profit == pytest.approx(-129.4)
    assert result.margin_percent == pytest.approx(-2.88, abs=0.01)
    assert result.status == "LOSS"
    assert "выйти из акции" in result.recommendation.lower()


def test_marks_product_as_ok_when_profit_and_margin_are_enough():
    product = ProductInput(
        offer_id="FILTER-001",
        name="Фильтр тестовый",
        current_price=3990,
        ozon_expenses=500,
        ad_expenses=100,
        in_promo=False,
    )
    cost = CostInput(
        offer_id="FILTER-001",
        purchase_price=1800,
        packaging=100,
        extra_expenses=100,
        tax_percent=6,
        min_profit=500,
        min_margin_percent=15,
    )

    result = calculate_product_profit(product, cost)

    assert result.safe_price == pytest.approx(3100)
    assert result.profit == pytest.approx(1150.6)
    assert result.margin_percent == pytest.approx(28.84, abs=0.01)
    assert result.status == "OK"
    assert result.recommendation == "Не трогать товар"


def test_marks_product_as_low_margin_when_above_safe_price_but_margin_is_low():
    product = ProductInput(
        offer_id="LOW-001",
        name="Товар с низкой маржой",
        current_price=3200,
        ozon_expenses=500,
        ad_expenses=100,
        in_promo=False,
    )
    cost = CostInput(
        offer_id="LOW-001",
        purchase_price=2100,
        packaging=100,
        extra_expenses=100,
        tax_percent=6,
        min_profit=200,
        min_margin_percent=15,
    )

    result = calculate_product_profit(product, cost)

    assert result.safe_price == pytest.approx(3100)
    assert result.profit == pytest.approx(108)
    assert result.margin_percent == pytest.approx(3.38, abs=0.01)
    assert result.status == "LOW_MARGIN"
    assert "низкая маржа" in result.reason.lower()


def test_marks_product_as_no_cost_data_when_cost_is_missing():
    product = ProductInput(
        offer_id="UNKNOWN-001",
        name="Нет себестоимости",
        current_price=1500,
        ozon_expenses=300,
        ad_expenses=0,
        in_promo=False,
    )

    result = calculate_product_profit(product, None)

    assert result.status == "NO_COST_DATA"
    assert result.safe_price is None
    assert result.profit is None
    assert "заполнить себестоимость" in result.recommendation.lower()
