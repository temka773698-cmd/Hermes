from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def build_telegram_payload(bot_token: str, chat_id: str, text: str) -> dict[str, Any]:
    return {
        "url": f"https://api.telegram.org/bot{bot_token}/sendMessage",
        "body": {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    }


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> dict[str, Any]:
    payload = build_telegram_payload(bot_token, chat_id, text)
    data = json.dumps(payload["body"], ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        payload["url"],
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            details = json.loads(body)
        except json.JSONDecodeError:
            details = {"description": body}
        description = details.get("description", "")
        raise RuntimeError(f"Telegram API error {exc.code}: {description}") from exc
