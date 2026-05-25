from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHONE_RE = re.compile(r"(?:\+7|8)?[\s\-\(]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
DEPTH_RE = re.compile(r"(?:глубин\w*|скважин\w*)\D{0,20}(\d{1,3})|(?:\b(\d{1,3})\s*(?:м|метр))", re.I)


@dataclass
class DialogState:
    messages: list[dict[str, str]] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    lead_sent: bool = False


class PumpQualifier:
    """Rule-based MVP qualifier for pump requests.

    Это первая версия: она не делает инженерный подбор, а аккуратно собирает
    данные для передачи менеджеру.
    """

    def __init__(self) -> None:
        self.state = DialogState()

    def start(self) -> str:
        reply = (
            "Здравствуйте! Я помогу собрать данные для подбора насоса. "
            "Для какой задачи нужен насос: скважина, колодец, дренаж, канализация "
            "или что-то другое?"
        )
        self._add("assistant", reply)
        return reply

    def reply(self, user_message: str) -> str:
        self._add("user", user_message)
        self._extract_facts(user_message)

        if self.is_ready_for_handoff():
            reply = (
                "Спасибо, основные данные собраны. Передаю заявку менеджеру.\n\n"
                + extract_lead_summary(self.state)
            )
        else:
            reply = self._next_question()

        self._add("assistant", reply)
        return reply

    def is_ready_for_handoff(self) -> bool:
        facts = self.state.facts
        return bool(facts.get("contact")) and len(self.state.messages) >= 6

    def _add(self, role: str, content: str) -> None:
        self.state.messages.append({"role": role, "content": content})

    def _extract_facts(self, text: str) -> None:
        low = text.lower()
        facts = self.state.facts
        facts["raw_request"] = (facts.get("raw_request", "") + "\n" + text).strip()

        if "скваж" in low:
            facts["task"] = "Скважинный насос"
        elif "колод" in low:
            facts["task"] = "Колодезный насос"
        elif "дренаж" in low:
            facts["task"] = "Дренажный насос"
        elif "канализа" in low or "фекал" in low:
            facts["task"] = "Канализационный/фекальный насос"
        elif "давлен" in low:
            facts["task"] = "Повышение давления"

        phone = PHONE_RE.search(text)
        if phone:
            facts["contact"] = phone.group(0).strip()

        name = re.search(r"(?:меня\s+зовут\s+|^я\s+)([А-ЯЁA-Z][а-яёa-z]{2,})", text, re.I)
        if name:
            facts["name"] = name.group(1)

        city = re.search(r"(?:город|из)\s+([А-ЯЁA-Z][а-яёa-z\- ]{2,})", text)
        if city:
            facts["city"] = city.group(1).strip()

        if "комплект" in low:
            facts["scope"] = "Полный комплект"
        elif "только насос" in low or "один насос" in low:
            facts["scope"] = "Только насос"

        if "водоочист" in low or "водоподготов" in low or "анализ воды" in low or "анализ" in low:
            facts["water_treatment"] = "Нужен вопрос по анализу/водоочистке"

        people = re.search(r"(\d{1,2})\s*(?:человек|чел|люд)", low)
        if people:
            facts["people"] = people.group(1)

        bathrooms = re.search(r"(\d{1,2})\s*(?:сануз|ванн)", low)
        if bathrooms:
            facts["bathrooms"] = bathrooms.group(1)

        distance = re.search(r"(?:расстояние|до дома)\D{0,15}(\d{1,4})", low)
        if distance:
            facts["distance_m"] = distance.group(1)

        diameter = re.search(r"(?:диаметр|труб[аы])\D{0,15}(\d{2,3})", low)
        if diameter:
            facts["casing_diameter_mm"] = diameter.group(1)

        if "зеркало" in low:
            mirror = re.search(r"зеркало\D{0,15}(\d{1,3})", low)
            if mirror:
                facts["water_level_m"] = mirror.group(1)

        if "глуб" in low:
            depth = re.search(r"глуб\w*\D{0,15}(\d{1,3})", low)
            if depth:
                facts["well_depth_m"] = depth.group(1)

    def _next_question(self) -> str:
        facts = self.state.facts
        if not facts.get("task"):
            return "Понял. Уточните, пожалуйста, для какой задачи насос: скважина, колодец, дренаж, канализация или другая задача?"

        if not facts.get("scope") or not facts.get("water_treatment"):
            return (
                "Важно уточнить два момента:\n"
                "1. Вам нужен только насос или полный комплект: насос, кабель, труба, автоматика, защита?\n"
                "2. Нужна ли водоочистка или есть анализ воды?"
            )

        if facts.get("task") == "Скважинный насос" and not (
            facts.get("well_depth_m") and facts.get("water_level_m") and facts.get("casing_diameter_mm")
        ):
            return "Для скважины нужны данные: глубина скважины, зеркало воды и диаметр обсадной трубы. Напишите, что известно."

        if not facts.get("people") or not facts.get("bathrooms"):
            return "Сколько человек будет пользоваться водой и сколько точек водоразбора: санузлы, кухня, душ, баня, полив?"

        if not facts.get("distance_m"):
            return "Какое расстояние от источника воды до дома/объекта? Если знаете — укажите ещё этажность и напряжение 220/380 В."

        if not facts.get("contact"):
            return "Оставьте, пожалуйста, имя, город и контакт для связи — телефон или Telegram. Я передам заявку менеджеру."

        return "Спасибо, уточняю последние детали и готовлю заявку для менеджера."


class LeadStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, lead: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"created_at": datetime.now(timezone.utc).isoformat(), **lead}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def extract_lead_summary(state: DialogState) -> str:
    facts = state.facts
    lines = ["## Заявка на насосное оборудование"]
    mapping = [
        ("name", "Имя"),
        ("city", "Город"),
        ("contact", "Контакт"),
        ("task", "Задача"),
        ("scope", "Объём поставки"),
        ("water_treatment", "Водоочистка/анализ воды"),
        ("well_depth_m", "Глубина скважины, м"),
        ("water_level_m", "Зеркало воды, м"),
        ("casing_diameter_mm", "Диаметр трубы, мм"),
        ("people", "Пользователей"),
        ("bathrooms", "Санузлов/ванных"),
        ("distance_m", "Расстояние до объекта, м"),
    ]
    for key, label in mapping:
        value = facts.get(key)
        if value:
            lines.append(f"- {label}: {value}")
    lines.append("\nИсходные сообщения клиента:")
    lines.append(facts.get("raw_request", "—"))
    return "\n".join(lines)
