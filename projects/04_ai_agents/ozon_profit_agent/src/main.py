import argparse
import csv
from pathlib import Path

from src.ozon_client import OzonClient
from src.ozon_excel_importer import load_products_and_costs_from_xlsx
from src.price_upload_preview import (
    PriceUploadProposal,
    build_price_upload_proposals,
    write_price_upload_preview_csv,
    write_price_upload_preview_xlsx,
)
from src.profit_calculator import CostInput, ProductInput, calculate_product_profit
from src.report_builder import build_summary_text, write_danger_report_csv, write_report_csv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "да"}


def load_products(path: Path) -> list[ProductInput]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return [
            ProductInput(
                offer_id=row["offer_id"],
                name=row["name"],
                current_price=float(row["current_price"]),
                ozon_expenses=float(row["ozon_expenses"]),
                ad_expenses=float(row["ad_expenses"]),
                in_promo=parse_bool(row.get("in_promo", "false")),
                sku=row.get("sku", ""),
            )
            for row in reader
        ]


def load_costs(path: Path) -> dict[str, CostInput]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return {
            row["offer_id"]: CostInput(
                offer_id=row["offer_id"],
                purchase_price=float(row["purchase_price"]),
                packaging=float(row["packaging"]),
                extra_expenses=float(row["extra_expenses"]),
                tax_percent=float(row["tax_percent"]),
                min_profit=float(row["min_profit"]),
                min_margin_percent=float(row["min_margin_percent"]),
            )
            for row in reader
        }


def write_products_snapshot(products: list[ProductInput], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["offer_id", "name", "current_price", "ozon_expenses", "ad_expenses", "in_promo", "sku"],
        )
        writer.writeheader()
        for product in products:
            writer.writerow(
                {
                    "offer_id": product.offer_id,
                    "name": product.name,
                    "current_price": product.current_price,
                    "ozon_expenses": product.ozon_expenses,
                    "ad_expenses": product.ad_expenses,
                    "in_promo": product.in_promo,
                    "sku": product.sku,
                }
            )


def attach_skus_to_price_proposals(
    proposals: list[PriceUploadProposal], products: list[ProductInput]
) -> list[PriceUploadProposal]:
    skus_by_offer_id = {product.offer_id: product.sku for product in products}
    return [
        PriceUploadProposal(
            status=proposal.status,
            offer_id=proposal.offer_id,
            sku=skus_by_offer_id.get(proposal.offer_id, proposal.sku),
            name=proposal.name,
            current_price=proposal.current_price,
            safe_price=proposal.safe_price,
            proposed_price=proposal.proposed_price,
            price_delta=proposal.price_delta,
            profit=proposal.profit,
            margin_percent=proposal.margin_percent,
            reason=proposal.reason,
            action=proposal.action,
        )
        for proposal in proposals
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Ozon-антиубыток: расчёт прибыльности товаров")
    parser.add_argument("--source", choices=["csv", "api", "xlsx"], default="csv", help="Источник товаров: CSV, Ozon API или Excel-файл Ozon")
    parser.add_argument("--limit", type=int, default=100, help="Сколько товаров забрать из Ozon API")
    parser.add_argument("--xlsx", type=Path, help="Путь к Excel-файлу Ozon с листом 'Товары и цены'")
    parser.add_argument("--min-profit", type=float, default=300, help="Минимальная прибыль на товар, ₽")
    parser.add_argument("--min-margin", type=float, default=15, help="Минимальная маржа, %")
    parser.add_argument(
        "--price-preview-limit",
        type=int,
        default=5,
        help="Сколько товаров включить в безопасный preview-файл для загрузки цен в Ozon; 0 — не создавать",
    )
    args = parser.parse_args()

    if args.source == "api":
        products = OzonClient.from_env().fetch_products(limit=args.limit)
        write_products_snapshot(products, DATA_DIR / "products_ozon.csv")
        costs = load_costs(DATA_DIR / "costs.csv")
    elif args.source == "xlsx":
        if not args.xlsx:
            raise SystemExit("Для --source xlsx нужно указать --xlsx /путь/к/файлу.xlsx")
        products, costs = load_products_and_costs_from_xlsx(
            args.xlsx,
            min_profit=args.min_profit,
            min_margin_percent=args.min_margin,
        )
        write_products_snapshot(products, DATA_DIR / "products_from_xlsx.csv")
    else:
        products = load_products(DATA_DIR / "products.csv")
        costs = load_costs(DATA_DIR / "costs.csv")
    results = [calculate_product_profit(product, costs.get(product.offer_id)) for product in products]

    report_path = DATA_DIR / "report.csv"
    danger_report_path = DATA_DIR / "danger_report.csv"
    write_report_csv(results, report_path)
    write_danger_report_csv(results, danger_report_path)

    price_preview_xlsx_path = DATA_DIR / "ozon_price_upload_preview.xlsx"
    price_preview_csv_path = DATA_DIR / "ozon_price_upload_preview.csv"
    price_preview_count = 0
    if args.source == "xlsx" and args.price_preview_limit > 0 and args.xlsx:
        price_proposals = attach_skus_to_price_proposals(
            build_price_upload_proposals(results, limit=args.price_preview_limit),
            products,
        )
        price_preview_count = len(price_proposals)
        write_price_upload_preview_xlsx(args.xlsx, price_proposals, price_preview_xlsx_path)
        write_price_upload_preview_csv(price_proposals, price_preview_csv_path)

    print(build_summary_text(results))
    print("")
    print(f"CSV-отчёт сохранён: {report_path}")
    print(f"Отчёт по проблемным товарам сохранён: {danger_report_path}")
    if args.source == "api":
        print(f"Снимок товаров Ozon сохранён: {DATA_DIR / 'products_ozon.csv'}")
    if args.source == "xlsx":
        print(f"Снимок товаров из Excel сохранён: {DATA_DIR / 'products_from_xlsx.csv'}")
        if args.price_preview_limit > 0:
            print(f"Preview XLSX для ручной загрузки цен сохранён: {price_preview_xlsx_path}")
            print(f"Preview CSV с предложениями сохранён: {price_preview_csv_path}")
            print(f"В preview включено товаров: {price_preview_count}")


if __name__ == "__main__":
    main()
