from telegram_notify import build_telegram_payload


def test_build_telegram_payload_uses_group_chat_id():
    payload = build_telegram_payload(
        bot_token="123:abc",
        chat_id="-1001234567890",
        text="Новая заявка",
    )
    assert payload["url"] == "https://api.telegram.org/bot123:abc/sendMessage"
    assert payload["body"]["chat_id"] == "-1001234567890"
    assert payload["body"]["text"] == "Новая заявка"
    assert payload["body"]["parse_mode"] == "HTML"
