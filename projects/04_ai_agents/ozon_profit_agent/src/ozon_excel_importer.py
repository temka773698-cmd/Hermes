from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from typing import Any

from src.profit_calculator import CostInput, ProductInput

NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def parse_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace("%", "").replace(" ", "").replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_percent(value: Any) -> float:
    return parse_number(value)


def parse_yes(value: Any) -> bool:
    return str(value).strip().upper() in {"ДА", "YES", "TRUE", "1"}


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    index = 0
    for ch in letters:
        index = index * 26 + ord(ch.upper()) - 64
    return index - 1


def _shared_strings(zip_file: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []
    root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("a:si", NS):
        values.append("".join(text.text or "" for text in item.findall(".//a:t", NS)))
    return values


def _workbook_sheet_paths(zip_file: ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zip_file.read("xl/workbook.xml"))
    rels = ET.fromstring(zip_file.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    result: dict[str, str] = {}
    for sheet in workbook.findall(".//a:sheet", NS):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = rel_targets[rel_id]
        if not target.startswith("worksheets/"):
            target = "worksheets/" + target.split("/")[-1]
        result[name] = "xl/" + target
    return result


def _sheet_rows(zip_file: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(zip_file.read(sheet_path))
    rows: list[list[str]] = []
    for row in root.findall(".//a:sheetData/a:row", NS):
        values_by_index: dict[int, str] = {}
        max_index = -1
        for cell in row.findall("a:c", NS):
            index = _column_index(cell.attrib.get("r", "A1"))
            max_index = max(max_index, index)
            cell_type = cell.attrib.get("t")
            value_node = cell.find("a:v", NS)
            value = ""
            if value_node is not None:
                raw_value = value_node.text or ""
                if cell_type == "s" and raw_value.isdigit():
                    shared_index = int(raw_value)
                    value = shared_strings[shared_index] if shared_index < len(shared_strings) else raw_value
                else:
                    value = raw_value
            elif cell_type == "inlineStr":
                value = "".join(text.text or "" for text in cell.findall(".//a:t", NS))
            values_by_index[index] = value
        rows.append([values_by_index.get(index, "") for index in range(max_index + 1)])
    return rows


def read_ozon_price_xlsx(path: str | Path, sheet_name: str = "Товары и цены") -> list[dict[str, str]]:
    with ZipFile(path) as zip_file:
        shared = _shared_strings(zip_file)
        sheet_paths = _workbook_sheet_paths(zip_file)
        if sheet_name not in sheet_paths:
            raise ValueError(f"В файле нет листа {sheet_name!r}")
        rows = _sheet_rows(zip_file, sheet_paths[sheet_name], shared)

    if len(rows) < 5:
        return []
    headers = rows[1]
    data_rows = rows[4:]
    items: list[dict[str, str]] = []
    for row in data_rows:
        item = {header: row[index] if index < len(row) else "" for index, header in enumerate(headers) if header}
        if item.get("Артикул"):
            items.append(item)
    return items


def excel_row_to_inputs(
    row: dict[str, str],
    min_profit: float = 300,
    min_margin_percent: float = 15,
) -> tuple[ProductInput, CostInput]:
    offer_id = row.get("Артикул", "").strip()
    current_price = parse_number(row.get("Цена с учетом акции или стратегии, руб."))
    if current_price <= 0:
        current_price = parse_number(row.get("Текущая цена (со скидкой), руб."))

    sales_percent_fbs = parse_percent(row.get("Вознаграждение Ozon, FBS, %"))
    ozon_commission = current_price * sales_percent_fbs / 100
    ozon_expenses = round(
        ozon_commission
        + parse_number(row.get("Эквайринг"))
        + parse_number(row.get("Обработка отправления, максимум FBS"))
        + parse_number(row.get("Логистика Ozon, максимум, FBS"))
        + parse_number(row.get("Доставка до места выдачи, FBS")),
        2,
    )

    product = ProductInput(
        offer_id=offer_id,
        name=row.get("Название товара", "").strip() or offer_id,
        current_price=current_price,
        ozon_expenses=ozon_expenses,
        ad_expenses=0,
        in_promo=parse_yes(row.get("Автодобавление товара в акции")) or current_price != parse_number(row.get("Текущая цена (со скидкой), руб.")),
        sku=str(row.get("SKU", "")).strip(),
    )
    cost = CostInput(
        offer_id=offer_id,
        purchase_price=parse_number(row.get("Себестоимость")),
        packaging=0,
        extra_expenses=0,
        tax_percent=parse_percent(row.get("НДС, %")),
        min_profit=min_profit,
        min_margin_percent=min_margin_percent,
    )
    return product, cost


def load_products_and_costs_from_xlsx(
    path: str | Path,
    min_profit: float = 300,
    min_margin_percent: float = 15,
) -> tuple[list[ProductInput], dict[str, CostInput]]:
    rows = read_ozon_price_xlsx(path)
    products: list[ProductInput] = []
    costs: dict[str, CostInput] = {}
    for row in rows:
        product, cost = excel_row_to_inputs(row, min_profit=min_profit, min_margin_percent=min_margin_percent)
        products.append(product)
        costs[product.offer_id] = cost
    return products, costs
