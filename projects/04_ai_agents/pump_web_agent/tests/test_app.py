from pathlib import Path

from app import load_env_file


def test_load_env_file_sets_missing_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('TELEGRAM_GROUP_CHAT_ID="-100123"\n# comment\nPORT=9090\n', encoding="utf-8")
    monkeypatch.delenv("TELEGRAM_GROUP_CHAT_ID", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    load_env_file(env_file)

    assert __import__("os").environ["TELEGRAM_GROUP_CHAT_ID"] == "-100123"
    assert __import__("os").environ["PORT"] == "9090"
