from src.ozon_excel_importer import excel_row_to_inputs, parse_percent


def test_parse_percent_handles_plain_percent_and_empty_values():
    assert parse_percent("17%") == 17
    assert parse_percent("10") == 10
    assert parse_percent(15) == 15
    assert parse_percent("") == 0
    assert parse_percent("Не облагается") == 0


def test_excel_row_to_inputs_uses_action_price_and_fbs_expenses():
    row = {
        "Артикул": "Трос3_7м_4шт",
        "SKU": "662330046",
        "Название товара": "Нержавеющий трос",
        "Цена с учетом акции или стратегии, руб.": "814",
        "Текущая цена (со скидкой), руб.": "895",
        "Себестоимость": "256",
        "Эквайринг": "8.14",
        "Вознаграждение Ozon, FBS, %": "45",
        "Обработка отправления, максимум FBS": "30",
        "Логистика Ozon, максимум, FBS": "153",
        "Доставка до места выдачи, FBS": "25",
        "Автодобавление товара в акции": "ДА",
    }

    product, cost = excel_row_to_inputs(row, min_profit=300, min_margin_percent=15)

    assert product.offer_id == "Трос3_7м_4шт"
    assert product.name == "Нержавеющий трос"
    assert product.current_price == 814
    assert product.ozon_expenses == 582.44
    assert product.in_promo is True
    assert product.sku == "662330046"
    assert cost.offer_id == "Трос3_7м_4шт"
    assert cost.purchase_price == 256
    assert cost.min_profit == 300
    assert cost.min_margin_percent == 15


def test_excel_row_to_inputs_falls_back_to_current_price_when_action_price_missing():
    row = {
        "Артикул": "SKU-1",
        "SKU": "123",
        "Название товара": "Товар",
        "Цена с учетом акции или стратегии, руб.": "",
        "Текущая цена (со скидкой), руб.": "1000",
        "Себестоимость": "500",
        "Эквайринг": "10",
        "Вознаграждение Ozon, FBS, %": "10",
        "Обработка отправления, максимум FBS": "20",
        "Логистика Ozon, максимум, FBS": "100",
        "Доставка до места выдачи, FBS": "25",
        "Автодобавление товара в акции": "НЕТ",
    }

    product, cost = excel_row_to_inputs(row)

    assert product.current_price == 1000
    assert product.ozon_expenses == 255
    assert product.in_promo is False
    assert cost.purchase_price == 500
