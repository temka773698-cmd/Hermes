from dataclasses import dataclass


@dataclass(frozen=True)
class ProductInput:
    offer_id: str
    name: str
    current_price: float
    ozon_expenses: float
    ad_expenses: float
    in_promo: bool = False
    sku: str = ""


@dataclass(frozen=True)
class CostInput:
    offer_id: str
    purchase_price: float
    packaging: float
    extra_expenses: float
    tax_percent: float
    min_profit: float
    min_margin_percent: float


@dataclass(frozen=True)
class ProfitResult:
    offer_id: str
    name: str
    current_price: float
    safe_price: float | None
    profit: float | None
    margin_percent: float | None
    status: str
    reason: str
    recommendation: str


def calculate_product_profit(product: ProductInput, cost: CostInput | None) -> ProfitResult:
    if cost is None:
        return ProfitResult(
            offer_id=product.offer_id,
            name=product.name,
            current_price=product.current_price,
            safe_price=None,
            profit=None,
            margin_percent=None,
            status="NO_COST_DATA",
            reason="Нет данных по себестоимости",
            recommendation="Заполнить себестоимость и обязательные расходы",
        )

    safe_price = (
        cost.purchase_price
        + product.ozon_expenses
        + cost.packaging
        + cost.extra_expenses
        + product.ad_expenses
        + cost.min_profit
    )
    tax_amount = product.current_price * cost.tax_percent / 100
    profit = (
        product.current_price
        - cost.purchase_price
        - product.ozon_expenses
        - cost.packaging
        - cost.extra_expenses
        - product.ad_expenses
        - tax_amount
    )
    margin_percent = profit / product.current_price * 100 if product.current_price else 0

    if profit < 0:
        reason = "Расчётная прибыль ниже нуля"
        if product.in_promo:
            reason += "; товар участвует в акции"
            recommendation = f"Срочно поднять цену минимум до {safe_price:.0f} ₽ или выйти из акции"
        else:
            recommendation = f"Срочно поднять цену минимум до {safe_price:.0f} ₽"
        status = "LOSS"
    elif product.current_price < safe_price:
        status = "LOW_PROFIT"
        reason = f"Прибыль ниже цели: {profit:.0f} ₽ меньше минимальной прибыли {cost.min_profit:.0f} ₽"
        if product.in_promo:
            reason += "; товар участвует в акции"
            recommendation = f"Поднять цену минимум до {safe_price:.0f} ₽ или выйти из акции"
        else:
            recommendation = f"Поднять цену минимум до {safe_price:.0f} ₽"
    elif margin_percent < cost.min_margin_percent:
        status = "LOW_MARGIN"
        reason = f"Низкая маржа: {margin_percent:.1f}% ниже цели {cost.min_margin_percent:.1f}%"
        recommendation = f"Проверить цену; желательно поднять выше {safe_price:.0f} ₽"
    else:
        status = "OK"
        reason = "Цена и маржа в норме"
        recommendation = "Не трогать товар"

    return ProfitResult(
        offer_id=product.offer_id,
        name=product.name,
        current_price=product.current_price,
        safe_price=round(safe_price, 2),
        profit=round(profit, 2),
        margin_percent=round(margin_percent, 2),
        status=status,
        reason=reason,
        recommendation=recommendation,
    )
