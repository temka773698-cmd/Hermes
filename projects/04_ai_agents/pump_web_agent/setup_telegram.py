from __future__ import annotations

import json
import os
import urllib.request
from getpass import getpass
from pathlib import Path

from telegram_notify import send_telegram_message

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def read_existing_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env(values: dict[str, str]) -> None:
    content = "\n".join(
        [
            f'TELEGRAM_BOT_TOKEN={values["TELEGRAM_BOT_TOKEN"]}',
            f'TELEGRAM_GROUP_CHAT_ID={values["TELEGRAM_GROUP_CHAT_ID"]}',
            "HOST=127.0.0.1",
            "PORT=8080",
            "",
        ]
    )
    ENV_PATH.write_text(content, encoding="utf-8")


def get_updates(token: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    existing = read_existing_env()
    print("Настройка Telegram для pump_web_agent")
    print("1) Бот должен быть добавлен в группу")
    print("2) Напиши любое сообщение в группе после добавления бота")
    print("3) Потом запусти этот скрипт")
    print()

    token = existing.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        token = getpass("Вставь TELEGRAM_BOT_TOKEN от @BotFather: ").strip()

    chat_id = existing.get("TELEGRAM_GROUP_CHAT_ID") or os.getenv("TELEGRAM_GROUP_CHAT_ID")
    if not chat_id:
        updates = get_updates(token)
        chats = []
        for item in updates.get("result", []):
            message = item.get("message") or item.get("channel_post") or {}
            chat = message.get("chat") or {}
            if chat.get("id") and chat not in chats:
                chats.append(chat)

        if chats:
            print("\nНайденные чаты:")
            for i, chat in enumerate(chats, 1):
                print(f"{i}. id={chat.get('id')} title={chat.get('title') or chat.get('username') or chat.get('first_name')} type={chat.get('type')}")
            choice = input("Выбери номер группы: ").strip()
            chat_id = str(chats[int(choice) - 1]["id"])
        else:
            print("Не нашёл сообщений. Напиши любое сообщение в группе, где есть бот, и повтори запуск.")
            chat_id = input("Или вставь TELEGRAM_GROUP_CHAT_ID вручную: ").strip()

    values = {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_GROUP_CHAT_ID": chat_id}
    write_env(values)
    print(f"\n.env сохранён: {ENV_PATH}")

    try:
        result = send_telegram_message(token, chat_id, "✅ Pump Web Agent подключён. Тестовая заявка будет приходить сюда.")
    except RuntimeError as exc:
        print("\n.env сохранён, но тестовое сообщение не отправилось.")
        print(str(exc))
        print("\nЧто проверить:")
        print("1. В группе AI Насосы бот @nasospodbor_bot не должен быть удалён или заблокирован.")
        print("2. У бота должно быть право отправлять сообщения в группе.")
        print("3. Если сомневаешься — сделай бота администратором группы и запусти скрипт ещё раз.")
        raise SystemExit(1)

    print("Тестовое сообщение отправлено:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
