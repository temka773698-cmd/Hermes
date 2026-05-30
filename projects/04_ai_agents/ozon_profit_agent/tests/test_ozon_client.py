from src.ozon_client import price_item_to_product_input


def test_price_item_to_product_input_uses_marketing_price_and_commissions():
    item = {
        "offer_id": "SKU-1",
        "product_id": 123,
        "price": {
            "price": 1000,
            "marketing_seller_price": 850,
        },
        "commissions": {
            "sales_percent_fbs": 10,
            "fbs_direct_flow_trans_max_amount": 120,
            "fbs_first_mile_max_amount": 30,
        },
        "marketing_actions": {
            "actions": [{"title": "Акция", "value": 100}],
        },
    }
    names = {"SKU-1": "Тестовый товар"}

    product = price_item_to_product_input(item, names)

    assert product.offer_id == "SKU-1"
    assert product.name == "Тестовый товар"
    assert product.current_price == 850
    assert product.ozon_expenses == 235
    assert product.ad_expenses == 0
    assert product.in_promo is True
    assert product.sku == "123"


def test_price_item_to_product_input_falls_back_to_offer_id_as_name():
    item = {
        "offer_id": "SKU-2",
        "product_id": 456,
        "price": {"price": 2000, "marketing_seller_price": 0},
        "commissions": {},
        "marketing_actions": {"actions": []},
    }

    product = price_item_to_product_input(item, {})

    assert product.name == "SKU-2"
    assert product.current_price == 2000
    assert product.ozon_expenses == 0
    assert product.in_promo is False
