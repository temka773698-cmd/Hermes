import json
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import server


def test_build_message_uses_readable_html_format():
    payload = {
        'name': 'Иван',
        'phone': '+7 999 123-45-67',
        'location': 'Казань',
        'need': 'Скважина под ключ',
        'comment': 'Нужна вода в доме',
        'page': '/index.html',
        'source': 'http://127.0.0.1:8765/index.html',
    }

    message = server.build_message(payload)

    assert '💧 <b>Новая заявка с сайта</b>' in message
    assert '<b>Имя:</b> Иван' in message
    assert '<b>Телефон:</b> +7 999 123-45-67' in message
    assert '<b>Источник:</b> http://127.0.0.1:8765/index.html' in message


def test_append_lead_log_writes_jsonl_backup(tmp_path, monkeypatch):
    log_path = tmp_path / 'leads.jsonl'
    monkeypatch.setattr(server, 'LEADS_LOG_PATH', log_path)

    payload = {'name': 'Иван', 'phone': '+7 999 123-45-67'}
    entry = server.append_lead_log(payload, telegram_status='sent', telegram_detail={'ok': True})

    assert log_path.exists()
    saved = json.loads(log_path.read_text(encoding='utf-8').strip())
    assert saved['payload'] == payload
    assert saved['telegram_status'] == 'sent'
    assert saved['telegram_detail'] == {'ok': True}
    assert saved['lead_id'] == entry['lead_id']
    assert 'created_at' in saved


def test_describe_telegram_error_includes_status_and_hint():
    body = json.dumps({'ok': False, 'description': 'Bad Request: chat not found'}).encode('utf-8')
    error = HTTPError(
        url='https://api.telegram.org/botTOKEN/sendMessage',
        code=400,
        msg='Bad Request',
        hdrs=None,
        fp=None,
    )
    error.read = lambda: body

    detail = server.describe_telegram_error(error)

    assert detail['kind'] == 'http_error'
    assert detail['status_code'] == 400
    assert detail['telegram_description'] == 'Bad Request: chat not found'
    assert 'chat_id' in detail['hint']


def test_send_to_telegram_uses_html_parse_mode(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({'ok': True, 'result': {'message_id': 42}}).encode('utf-8')

    def fake_urlopen(req, timeout=0):
        captured['data'] = req.data.decode('utf-8')
        return FakeResponse()

    monkeypatch.setattr(server.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(server, 'BOT_TOKEN', 'token')
    monkeypatch.setattr(server, 'CHAT_ID', '123')

    ok, detail = server.send_to_telegram('<b>Hello</b>')

    assert ok is True
    assert detail['ok'] is True
    assert 'parse_mode=HTML' in captured['data']
