#!/usr/bin/env python3
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'
LEADS_DIR = BASE_DIR / 'data'
LEADS_LOG_PATH = LEADS_DIR / 'leads.jsonl'


def load_env(path: Path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env(ENV_PATH)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '').strip()
SITE_NAME = os.getenv('SITE_NAME', 'Сайт по скважинам').strip()
PORT = int(os.getenv('PORT', '8765'))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def clean_value(value) -> str:
    text = str(value or '').strip()
    return text or '-'


def build_message(payload: dict) -> str:
    submitted_at = clean_value(payload.get('submitted_at'))
    lines = [
        '💧 <b>Новая заявка с сайта</b>',
        f'<b>Бренд:</b> {html.escape(SITE_NAME)}',
        f'<b>Имя:</b> {html.escape(clean_value(payload.get("name")))}',
        f'<b>Телефон:</b> {html.escape(clean_value(payload.get("phone")))}',
        f'<b>Населённый пункт:</b> {html.escape(clean_value(payload.get("location")))}',
        f'<b>Что нужно:</b> {html.escape(clean_value(payload.get("need")))}',
        f'<b>Комментарий:</b> {html.escape(clean_value(payload.get("comment")))}',
        '',
        '📍 <b>Технические детали</b>',
        f'<b>Страница:</b> {html.escape(clean_value(payload.get("page")))}',
        f'<b>Источник:</b> {html.escape(clean_value(payload.get("source")))}',
        f'<b>Время:</b> {html.escape(submitted_at)}',
    ]
    return '\n'.join(lines)


def append_lead_log(payload: dict, telegram_status: str, telegram_detail=None, preview: str | None = None):
    LEADS_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        'lead_id': uuid4().hex[:12],
        'created_at': now_iso(),
        'site_name': SITE_NAME,
        'payload': payload,
        'telegram_status': telegram_status,
        'telegram_detail': telegram_detail,
        'preview': preview,
    }
    with LEADS_LOG_PATH.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return entry


def describe_telegram_error(exc: Exception) -> dict:
    detail = {
        'kind': 'unexpected_error',
        'message': str(exc),
        'hint': 'Проверьте TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID и доступ к api.telegram.org.',
    }

    if isinstance(exc, urllib.error.HTTPError):
        raw_body = b''
        try:
            raw_body = exc.read() or b''
        except Exception:
            raw_body = b''
        parsed = None
        if raw_body:
            try:
                parsed = json.loads(raw_body.decode('utf-8'))
            except Exception:
                parsed = None
        description = parsed.get('description') if isinstance(parsed, dict) else None
        detail = {
            'kind': 'http_error',
            'message': f'Telegram API вернул HTTP {exc.code}: {description or exc.reason or exc.msg}',
            'status_code': exc.code,
            'telegram_description': description,
            'response_body': parsed if parsed is not None else raw_body.decode('utf-8', errors='replace'),
            'hint': telegram_hint(exc.code, description),
        }
    elif isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, 'reason', exc)
        detail = {
            'kind': 'network_error',
            'message': f'Не удалось подключиться к Telegram API: {reason}',
            'reason': str(reason),
            'hint': 'Проверьте интернет/доступ из WSL к api.telegram.org и повторите попытку.',
        }

    return detail


def telegram_hint(status_code: int | None, description: str | None) -> str:
    desc = (description or '').lower()
    if status_code == 400 and 'chat not found' in desc:
        return 'Скорее всего неверный TELEGRAM_CHAT_ID: бот не видит чат или chat_id указан с ошибкой.'
    if status_code == 400 and 'message is too long' in desc:
        return 'Сообщение слишком длинное. Нужно сократить текст заявки или обрезать комментарий.'
    if status_code == 401:
        return 'Похоже, неверный TELEGRAM_BOT_TOKEN. Проверьте токен и перезапустите сервер.'
    if status_code == 403:
        return 'Бот не может писать в этот чат. Добавьте бота в чат / начните диалог с ботом и проверьте права.'
    if status_code == 429:
        return 'Telegram временно ограничил отправку. Подождите и попробуйте снова.'
    return 'Проверьте TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID и ответ Telegram API в details.'


def send_to_telegram(text: str):
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    body = urllib.parse.urlencode({
        'chat_id': CHAT_ID,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': 'true',
    }).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok'):
                return True, data
            return False, {
                'kind': 'telegram_api_error',
                'message': f'Telegram API отклонил сообщение: {data.get("description") or "без описания"}',
                'telegram_description': data.get('description'),
                'response_body': data,
                'hint': telegram_hint(resp.status, data.get('description')),
            }
    except Exception as exc:
        return False, describe_telegram_error(exc)


class LeadHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def end_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/api/lead':
            self.end_json(404, {'error': 'Not found'})
            return

        length = int(self.headers.get('Content-Length', '0') or '0')
        raw = self.rfile.read(length)

        try:
            payload = json.loads(raw.decode('utf-8'))
        except Exception:
            self.end_json(400, {'error': 'Некорректный JSON'})
            return

        if not payload.get('name') or not payload.get('phone'):
            self.end_json(400, {'error': 'Нужны имя и телефон'})
            return

        payload = dict(payload)
        payload.setdefault('submitted_at', now_iso())
        preview = build_message(payload)

        if BOT_TOKEN and CHAT_ID:
            ok, detail = send_to_telegram(preview)
            log_entry = append_lead_log(
                payload,
                telegram_status='sent' if ok else 'failed',
                telegram_detail=detail,
                preview=preview,
            )
            if not ok:
                self.end_json(502, {
                    'error': 'Telegram не принял сообщение',
                    'details': detail,
                    'lead_id': log_entry['lead_id'],
                    'log_path': str(LEADS_LOG_PATH),
                    'preview': preview,
                })
                return
            self.end_json(200, {
                'ok': True,
                'message': 'Заявка отправлена в Telegram и сохранена в резервный лог.',
                'telegram_status': 'sent',
                'lead_id': log_entry['lead_id'],
                'log_path': str(LEADS_LOG_PATH),
                'preview': preview,
            })
            return

        log_entry = append_lead_log(
            payload,
            telegram_status='preview',
            telegram_detail={
                'kind': 'preview_mode',
                'message': 'Telegram не настроен: заявка сохранена только в резервный лог.',
            },
            preview=preview,
        )
        self.end_json(200, {
            'ok': True,
            'message': 'Заявка сохранена в резервный лог. Telegram сейчас не настроен.',
            'telegram_status': 'preview',
            'lead_id': log_entry['lead_id'],
            'log_path': str(LEADS_LOG_PATH),
            'preview': preview,
        })


if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', PORT), LeadHandler)
    print(f'Serving MVP site on http://127.0.0.1:{PORT}')
    print('Telegram mode:', 'enabled' if BOT_TOKEN and CHAT_ID else 'preview only')
    print(f'Reserve lead log: {LEADS_LOG_PATH}')
    server.serve_forever()
