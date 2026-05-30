import csv
from pathlib import Path
from typing import Iterable

from src.profit_calculator import ProfitResult

KNOWN_STATUSES = ["OK", "LOW_MARGIN", "LOW_PROFIT", "LOSS", "NO_COST_DATA", "CHECK_REQUIRED"]
PROBLEM_STATUSES = {"LOSS", "LOW_PROFIT", "LOW_MARGIN", "NO_COST_DATA", "CHECK_REQUIRED"}
STATUS_PRIORITY = {"LOSS": 0, "LOW_PROFIT": 1, "NO_COST_DATA": 2, "LOW_MARGIN": 3, "CHECK_REQUIRED": 4}


def count_statuses(results: Iterable[ProfitResult]) -> dict[str, int]:
    items = list(results)
    counts = {"total": len(items)}
    for status in KNOWN_STATUSES:
        counts[status] = sum(1 for item in items if item.status == status)
    return counts


def build_summary_text(results: Iterable[ProfitResult], limit: int = 10) -> str:
    items = list(results)
    counts = count_statuses(items)
    dangerous = _problem_items(items)

    lines = [
        "Ежедневный отчёт Ozon-антиубыток",
        "",
        f"Всего товаров: {counts['total']}",
        f"В норме: {counts['OK']}",
        f"Низкая прибыль: {counts['LOW_MARGIN']}",
        f"Прибыль ниже цели: {counts['LOW_PROFIT']}",
        f"В убытке: {counts['LOSS']}",
        f"Без себестоимости: {counts['NO_COST_DATA']}",
        f"Требуют проверки: {counts['CHECK_REQUIRED']}",
        "",
        "Главные проблемы:",
    ]

    if not dangerous:
        lines.append("Проблемных товаров не найдено.")
        return "\n".join(lines)

    for index, item in enumerate(dangerous[:limit], start=1):
        safe_price = "нет данных" if item.safe_price is None else f"{item.safe_price:.0f} ₽"
        profit = "нет данных" if item.profit is None else f"{item.profit:.0f} ₽"
        lines.extend(
            [
                f"{index}. {item.name}",
                f"   Артикул: {item.offer_id}",
                f"   Статус: {item.status}",
                f"   Текущая цена: {item.current_price:.0f} ₽",
                f"   Безопасная цена: {safe_price}",
                f"   Прибыль: {profit}",
                f"   Причина: {item.reason}",
                f"   Рекомендация: {item.recommendation}",
            ]
        )
    return "\n".join(lines)


def write_report_csv(results: Iterable[ProfitResult], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "offer_id",
        "name",
        "current_price",
        "safe_price",
        "profit",
        "margin_percent",
        "status",
        "reason",
        "recommendation",
    ]
    with target.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            writer.writerow({field: getattr(item, field) for field in fieldnames})


def _problem_items(items: Iterable[ProfitResult]) -> list[ProfitResult]:
    problems = [item for item in items if item.status in PROBLEM_STATUSES]
    problems.sort(key=lambda item: (STATUS_PRIORITY.get(item.status, 99), item.profit if item.profit is not None else 10**9, item.offer_id))
    return problems


def write_danger_report_csv(results: Iterable[ProfitResult], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "offer_id",
        "name",
        "current_price",
        "safe_price",
        "price_delta_to_safe",
        "profit",
        "margin_percent",
        "reason",
        "action",
    ]
    with target.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in _problem_items(list(results)):
            if item.safe_price is None:
                price_delta = ""
            else:
                price_delta = round(max(item.safe_price - item.current_price, 0), 2)
            writer.writerow(
                {
                    "status": item.status,
                    "offer_id": item.offer_id,
                    "name": item.name,
                    "current_price": item.current_price,
                    "safe_price": item.safe_price,
                    "price_delta_to_safe": price_delta,
                    "profit": item.profit,
                    "margin_percent": item.margin_percent,
                    "reason": item.reason,
                    "action": item.recommendation,
                }
            )
