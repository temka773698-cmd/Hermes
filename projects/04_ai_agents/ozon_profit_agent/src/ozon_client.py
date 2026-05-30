import json
import os
import urllib.request
from pathlib import Path
from typing import Any

from src.profit_calculator import ProductInput

API_BASE_URL = "https://api-seller.ozon.ru"


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


class OzonClient:
    def __init__(self, client_id: str, api_key: str, base_url: str = API_BASE_URL):
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @classmethod
    def from_env(cls) -> "OzonClient":
        load_env_file()
        client_id = os.environ.get("OZON_CLIENT_ID")
        api_key = os.environ.get("OZON_API_KEY")
        if not client_id or not api_key:
            raise RuntimeError("Не заполнены OZON_CLIENT_ID и OZON_API_KEY в .env")
        return cls(client_id=client_id, api_key=api_key)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Client-Id": self.client_id,
                "Api-Key": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch_price_items(self, limit: int = 100) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        last_id = ""
        while len(items) < limit:
            page_limit = min(100, limit - len(items))
            payload: dict[str, Any] = {"filter": {"visibility": "ALL"}, "limit": page_limit}
            if last_id:
                payload["last_id"] = last_id
            data = self.post("/v5/product/info/prices", payload)
            page_items = data.get("items", [])
            items.extend(page_items)
            last_id = data.get("last_id") or data.get("cursor") or ""
            if not page_items or not last_id:
                break
        return items

    def fetch_names_by_offer_id(self, offer_ids: list[str]) -> dict[str, str]:
        names: dict[str, str] = {}
        for start in range(0, len(offer_ids), 100):
            batch = offer_ids[start : start + 100]
            if not batch:
                continue
            data = self.post("/v3/product/info/list", {"offer_id": batch})
            for item in data.get("items", []):
                offer_id = item.get("offer_id")
                name = item.get("name")
                if offer_id and name:
                    names[offer_id] = name.strip()
        return names

    def fetch_products(self, limit: int = 100) -> list[ProductInput]:
        price_items = self.fetch_price_items(limit=limit)
        offer_ids = [item.get("offer_id", "") for item in price_items if item.get("offer_id")]
        names = self.fetch_names_by_offer_id(offer_ids)
        return [price_item_to_product_input(item, names) for item in price_items]


def price_item_to_product_input(item: dict[str, Any], names_by_offer_id: dict[str, str]) -> ProductInput:
    offer_id = str(item.get("offer_id") or "")
    product_id = item.get("product_id")
    price = item.get("price") or {}
    current_price = float(price.get("marketing_seller_price") or price.get("price") or 0)
    commissions = item.get("commissions") or {}

    sales_percent = float(commissions.get("sales_percent_fbs") or commissions.get("sales_percent_fbo") or 0)
    sales_commission = current_price * sales_percent / 100
    logistics = float(
        commissions.get("fbs_direct_flow_trans_max_amount")
        or commissions.get("fbo_direct_flow_trans_max_amount")
        or 0
    )
    first_mile = float(commissions.get("fbs_first_mile_max_amount") or 0)
    acquiring = float(item.get("acquiring") or 0)
    ozon_expenses = round(sales_commission + logistics + first_mile + acquiring, 2)

    actions = ((item.get("marketing_actions") or {}).get("actions") or [])
    in_promo = bool(actions) or bool(price.get("auto_action_enabled"))

    return ProductInput(
        offer_id=offer_id,
        name=names_by_offer_id.get(offer_id) or offer_id,
        current_price=current_price,
        ozon_expenses=ozon_expenses,
        ad_expenses=0,
        in_promo=in_promo,
        sku=str(product_id or ""),
    )
