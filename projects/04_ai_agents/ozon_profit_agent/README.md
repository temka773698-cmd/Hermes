# Ozon Profit Agent

Локальный прототип агента «Ozon-антиубыток».

## Что делает MVP

- читает тестовые товары из `data/products.csv`;
- читает себестоимость и правила из `data/costs.csv`;
- умеет читать Ozon Excel с листом `Товары и цены`;
- считает прибыльность;
- присваивает статус `OK`, `LOW_MARGIN`, `LOW_PROFIT`, `LOSS`, `NO_COST_DATA`, `CHECK_REQUIRED`;
- создаёт полный отчёт `data/report.csv`;
- создаёт проблемный отчёт `data/danger_report.csv`;
- для Excel-источника создаёт безопасный preview-файл `data/ozon_price_upload_preview.xlsx` для ручной загрузки первых проблемных цен обратно в Ozon.

## Быстрый запуск

```bash
cd /home/art/04_ai_agents/ozon_profit_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main
```

## Тесты

```bash
pytest -q
```

## Excel Ozon и preview для загрузки цен

```bash
python -m src.main \
  --source xlsx \
  --xlsx "/path/to/Цены товаров.xlsx" \
  --min-profit 300 \
  --min-margin 15 \
  --price-preview-limit 5
```

После запуска создаются:

- `data/report.csv` — полный отчёт по всем товарам;
- `data/danger_report.csv` — только проблемные товары;
- `data/ozon_price_upload_preview.csv` — что именно агент предлагает поменять;
- `data/ozon_price_upload_preview.xlsx` — копия Excel-шаблона Ozon, где заполнены только первые 2–5 проблемных товаров.

В preview-файле агент заполняет колонки:

- `Новая цена (со скидкой), руб.`;
- `Новая минимальная цена, руб.`;
- `Подключать подходящие акции` = `Нет`;
- `Учитывать минимальную цену при автодобавлении в акции или продлить действие настройки` = `Да`;
- `Автоматически добавлять товар в акции` = `Нет`.

## Важно

Первая версия ничего не меняет в кабинете Ozon. Она только считает и показывает риски.
