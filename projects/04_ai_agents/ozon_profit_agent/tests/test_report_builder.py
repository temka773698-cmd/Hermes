import csv

from src.profit_calculator import ProfitResult
from src.report_builder import build_summary_text, count_statuses, write_danger_report_csv


def test_count_statuses_counts_all_known_statuses():
    results = [
        ProfitResult("A", "A", 100, 90, 10, 10, "OK", "", ""),
        ProfitResult("B", "B", 100, 110, -10, -10, "LOSS", "", ""),
        ProfitResult("C", "C", 100, 95, 5, 5, "LOW_MARGIN", "", ""),
        ProfitResult("D", "D", 100, None, None, None, "NO_COST_DATA", "", ""),
    ]

    counts = count_statuses(results)

    assert counts == {
        "total": 4,
        "OK": 1,
        "LOW_MARGIN": 1,
        "LOW_PROFIT": 0,
        "LOSS": 1,
        "NO_COST_DATA": 1,
        "CHECK_REQUIRED": 0,
    }


def test_build_summary_text_shows_dangerous_products_first():
    results = [
        ProfitResult("OK-1", "Нормальный", 5000, 4000, 800, 16, "OK", "Цена и маржа в норме", "Не трогать товар"),
        ProfitResult("LOSS-1", "Убыточный", 1000, 1200, -300, -30, "LOSS", "Цена ниже безопасной", "Поднять цену"),
        ProfitResult("NO-1", "Без себестоимости", 1000, None, None, None, "NO_COST_DATA", "Нет данных", "Заполнить себестоимость"),
    ]

    text = build_summary_text(results)

    assert "Всего товаров: 3" in text
    assert "В норме: 1" in text
    assert "В убытке: 1" in text
    assert "Без себестоимости: 1" in text
    assert text.index("1. Убыточный") < text.index("2. Без себестоимости")
    assert "Нормальный" not in text


def test_write_danger_report_csv_contains_only_problem_products_with_price_delta(tmp_path):
    results = [
        ProfitResult("OK-1", "Нормальный", 5000, 4000, 800, 16, "OK", "Цена и маржа в норме", "Не трогать товар"),
        ProfitResult("LOSS-1", "Убыточный", 1000, 1200, -300, -30, "LOSS", "Минус", "Поднять цену"),
        ProfitResult("LOW-1", "Мало прибыли", 900, 1100, 100, 11, "LOW_PROFIT", "Мало", "Поднять цену"),
    ]
    path = tmp_path / "danger_report.csv"

    write_danger_report_csv(results, path)

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert [row["offer_id"] for row in rows] == ["LOSS-1", "LOW-1"]
    assert rows[0]["price_delta_to_safe"] == "200"
    assert rows[1]["price_delta_to_safe"] == "200"
    assert rows[0]["action"] == "Поднять цену"
