from __future__ import annotations

import html
import json
import os
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent import LeadStore, PumpQualifier, extract_lead_summary
from telegram_notify import send_telegram_message

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LEADS_PATH = DATA_DIR / "leads.jsonl"
SESSIONS: dict[str, PumpQualifier] = {}


def load_env_file(path: Path = BASE_DIR / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def serialize_state(agent: PumpQualifier) -> dict[str, Any]:
    return {
        "messages": agent.state.messages,
        "facts": agent.state.facts,
        "ready_for_handoff": agent.is_ready_for_handoff(),
    }


def notify_telegram(summary: str) -> dict[str, Any] | None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_GROUP_CHAT_ID")
    if not token or not chat_id:
        return None
    text = "<b>Новая заявка с web-агента</b>\n\n" + html.escape(summary)
    return send_telegram_message(token, chat_id, text)


def handle_chat(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id") or uuid.uuid4())
    message = str(payload.get("message") or "").strip()
    agent = SESSIONS.get(session_id)

    if agent is None:
        agent = PumpQualifier()
        SESSIONS[session_id] = agent
        if not message:
            reply = agent.start()
            return {"session_id": session_id, "reply": reply, "state": serialize_state(agent)}

    if not message:
        return {"session_id": session_id, "reply": "Напишите сообщение, и я продолжу диалог.", "state": serialize_state(agent)}

    was_ready = agent.is_ready_for_handoff()
    reply = agent.reply(message)

    telegram_status = None
    if agent.is_ready_for_handoff() and not was_ready and not agent.state.lead_sent:
        summary = extract_lead_summary(agent.state)
        LeadStore(LEADS_PATH).append({"session_id": session_id, "summary": summary, "facts": agent.state.facts})
        telegram_status = notify_telegram(summary)
        agent.state.lead_sent = True

    return {
        "session_id": session_id,
        "reply": reply,
        "state": serialize_state(agent),
        "telegram_status": telegram_status,
    }


class PumpAgentHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(BASE_DIR / "public"), **kwargs)

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw or "{}")
            response = handle_chat(payload)
            self._send_json(response)
        except Exception as exc:  # pragma: no cover - defensive server boundary
            self._send_json({"error": str(exc)}, status=500)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    load_env_file()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8080"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), PumpAgentHandler)
    print(f"Pump Web Agent running: http://{host}:{port}")
    print("Для отправки заявок в группу Telegram укажите TELEGRAM_BOT_TOKEN и TELEGRAM_GROUP_CHAT_ID")
    server.serve_forever()


if __name__ == "__main__":
    main()
