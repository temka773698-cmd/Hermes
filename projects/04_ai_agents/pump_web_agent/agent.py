from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+7|8)[\s\-\(\)]*)?\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")
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
        if facts.get("task") == "Дренажный насос":
            return bool(
                facts.get("contact")
                and facts.get("drainage_place")
                and facts.get("drainage_water")
                and facts.get("drainage_depth")
            )
        if facts.get("task") == "Повышение давления":
            return bool(facts.get("contact") and facts.get("scope") and facts.get("people") and facts.get("bathrooms"))
        return bool(facts.get("contact") and facts.get("water_treatment")) and len(self.state.messages) >= 6

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
        elif "дренаж" in low or "откач" in low or "ливн" in low or "лявн" in low or "подвал" in low or "добвал" in low:
            facts["task"] = "Дренажный насос"
        elif "канализа" in low or "фекал" in low:
            facts["task"] = "Канализационный/фекальный насос"
        elif "давлен" in low or "центральн" in low or "централ" in low:
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

        normalized = low.strip(" .,!?:;—-")
        task_known = bool(facts.get("task"))
        full_kit_answers = {"полный", "полная", "полное", "да", "надо", "нужно", "вместе", "вмести", "все", "всё"}
        if "насосная станц" in low or "станция" in normalized:
            if "защит" in low or "холост" in low or "ход" in low:
                facts["scope"] = "Насосная станция с защитой"
            else:
                facts["scope"] = "Насосная станция"
        elif "комплект" in low or (task_known and not facts.get("scope") and normalized in full_kit_answers):
            facts["scope"] = "Полный комплект"
        elif "только насос" in low or "один насос" in low or (task_known and normalized == "насос"):
            facts["scope"] = "Только насос"

        if "подвал" in low or "добвал" in low:
            facts["drainage_place"] = "Подвал"
        elif "погреб" in low:
            facts["drainage_place"] = "Погреб"
        elif "участ" in low or "двор" in low or "канава" in low:
            facts["drainage_place"] = "Участок/улица"

        if "ливн" in low or "лявн" in low or "дожд" in low:
            facts["drainage_water"] = "Дождевая/ливневая вода"
        elif "гряз" in low:
            facts["drainage_water"] = "Грязная вода"
        elif "чист" in low:
            facts["drainage_water"] = "Чистая вода"

        drainage_depth = re.search(r"(?:глубин|яма|приям|уровень)\D{0,15}(\d{1,3})\s*(?:м|метр|см)?", low)
        if drainage_depth:
            facts["drainage_depth"] = drainage_depth.group(1)

        if "водоочист" in low or "водоподготов" in low or "анализ воды" in low or "анализ" in low:
            facts["water_treatment"] = "Нужен вопрос по анализу/водоочистке"

        number_words = {
            "один": "1", "одна": "1", "два": "2", "две": "2", "три": "3", "четыре": "4",
            "пять": "5", "шесть": "6", "семь": "7", "восемь": "8", "девять": "9", "десять": "10",
        }
        bare_number = re.fullmatch(r"\d{1,2}", normalized)
        word_number = number_words.get(normalized)

        people_matches = re.findall(r"(\d{1,2})\s*(?:человек|человека|чел|люд|челек)", low)
        if people_matches:
            facts["people"] = people_matches[-1]
        elif not facts.get("people") and (bare_number or word_number) and facts.get("scope"):
            facts["people"] = bare_number.group(0) if bare_number else word_number

        bathroom_matches = re.findall(r"(\d{1,2})\s*(?:сануз|ванн|точ(?:ек|ки|ка|к)|кран|душ)", low)
        if bathroom_matches:
            facts["bathrooms"] = bathroom_matches[-1]
        elif facts.get("people") and not facts.get("bathrooms") and (bare_number or word_number):
            candidate = bare_number.group(0) if bare_number else word_number
            if candidate != facts.get("people"):
                facts["bathrooms"] = candidate

        phase = re.search(r"\b([123])\s*фаз", low)
        if phase:
            n = phase.group(1)
            facts["power_phase"] = f"{n} {'фаза' if n == '1' else 'фазы'}"

        distance = re.search(r"(?:расстояние|до дома)\D{0,15}(\d{1,4})", low)
        if distance:
            facts["distance_m"] = distance.group(1)

        diameter = re.search(r"(?:диаметр|диамент|диам\w*|труб[аы])\D{0,15}(\d{2,3})", low)
        if not diameter:
            diameter = re.search(r"(\d{2,3})\s*(?:мм)?\s*(?:диаметр|диамент|диам\w*)", low)
        if diameter:
            facts["casing_diameter_mm"] = diameter.group(1)

        if facts.get("task") == "Скважинный насос":
            if "зеркало" in low:
                mirror_before_word = re.search(r"(\d{1,3})\s*зеркал\w*", low)
                mirror_after_word = re.search(r"зеркало\s*(?:на\s*)?(\d{1,3})", low)
                mirror = mirror_before_word or mirror_after_word
                if mirror:
                    facts["water_level_m"] = mirror.group(1)
            natural_water_level = re.search(r"(?:вод[аы]|вода\s+стоит|уровень\s+воды)\D{0,15}(\d{1,3})\s*(?:м|метр)", low)
            if natural_water_level and not facts.get("water_level_m"):
                facts["water_level_m"] = natural_water_level.group(1)

            if "глуб" in low:
                depth = re.search(r"глуб\w*\D{0,15}(\d{1,3})", low)
                if depth:
                    facts["well_depth_m"] = depth.group(1)
            natural_well_depth = re.search(r"скважин\w*\D{0,15}(\d{1,3})\s*(?:м|метр)", low)
            if natural_well_depth:
                facts["well_depth_m"] = natural_well_depth.group(1)
            if not facts.get("well_depth_m"):
                first_meter_number = re.search(r"^\D*(\d{1,3})\s*(?:м|метр\w*)", low)
                if first_meter_number:
                    facts["well_depth_m"] = first_meter_number.group(1)

    def _next_question(self) -> str:
        facts = self.state.facts
        if not facts.get("task"):
            return "Понял. Уточните, пожалуйста, для какой задачи насос: скважина, колодец, дренаж, канализация или другая задача?"

        if facts.get("task") == "Дренажный насос":
            return self._next_drainage_question()

        if facts.get("task") == "Повышение давления":
            return self._next_pressure_boost_question()

        if not facts.get("scope"):
            return "Вам нужен только насос или полный комплект: насос, кабель, труба, автоматика, защита?"

        if facts.get("task") == "Скважинный насос" and not (
            facts.get("well_depth_m") and facts.get("water_level_m") and facts.get("casing_diameter_mm")
        ):
            return "Для скважины нужны данные: глубина скважины, зеркало воды и диаметр обсадной трубы. Напишите, что известно."

        if facts.get("well_depth_m") and facts.get("water_level_m"):
            well_depth = int(facts["well_depth_m"])
            water_level = int(facts["water_level_m"])
            if water_level > well_depth:
                return (
                    f"Уточните, пожалуйста: глубина скважины {well_depth} м, а вода/зеркало указано на {water_level} м. "
                    "Зеркало воды не может быть глубже самой скважины. На какой глубине вода от поверхности?"
                )

        if not facts.get("people") or not facts.get("bathrooms"):
            return "Сколько человек будет пользоваться водой и сколько точек водоразбора: санузлы, кухня, душ, баня, полив?"

        if not facts.get("distance_m"):
            if facts.get("power_phase"):
                return f"Понял, электричество: {facts['power_phase']}. Какое расстояние от источника воды до дома/объекта?"
            return "Какое расстояние от источника воды до дома/объекта? Если знаете — укажите ещё этажность и напряжение 220/380 В."

        if not facts.get("water_treatment"):
            return "В конце уточню по воде: есть ли анализ воды и нужна ли водоочистка/фильтры?"

        if not facts.get("contact"):
            return "Оставьте, пожалуйста, имя, город и контакт для связи — телефон или Telegram. Я передам заявку менеджеру."

        return "Спасибо, уточняю последние детали и готовлю заявку для менеджера."

    def _next_pressure_boost_question(self) -> str:
        facts = self.state.facts
        if not facts.get("scope"):
            return "Для повышения давления нужна насосная станция/насос с автоматикой или уже есть часть оборудования?"

        if not facts.get("people") or not facts.get("bathrooms"):
            return "Для какого объекта повышаем давление: баня/дом/дача? Сколько точек водоразбора будет работать: душ, кран, туалет, полив?"

        if not facts.get("distance_m"):
            return "Уточните, пожалуйста: где будет стоять станция и примерно какое расстояние до точек водоразбора?"

        if not facts.get("contact"):
            return "Оставьте, пожалуйста, имя, город и контакт для связи — телефон или Telegram. Я передам заявку менеджеру."

        return "Спасибо, уточняю последние детали и готовлю заявку для менеджера."

    def _next_drainage_question(self) -> str:
        facts = self.state.facts
        if not facts.get("drainage_place") or not facts.get("drainage_water"):
            return (
                "Уточните по дренажному насосу: откуда нужно откачивать воду "
                "(подвал, погреб, приямок, участок) и какая вода — чистая, грязная, дождевая/ливневая?"
            )

        if not facts.get("drainage_depth"):
            return "Какая примерно глубина воды/приямка и куда нужно отводить воду: в канаву, ливнёвку, на участок?"

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
        ("drainage_place", "Место откачки"),
        ("drainage_water", "Тип воды для откачки"),
        ("drainage_depth", "Глубина воды/приямка"),
        ("well_depth_m", "Глубина скважины, м"),
        ("water_level_m", "Зеркало воды, м"),
        ("casing_diameter_mm", "Диаметр трубы, мм"),
        ("people", "Пользователей"),
        ("bathrooms", "Санузлов/ванных"),
        ("distance_m", "Расстояние до объекта, м"),
        ("power_phase", "Электричество"),
    ]
    for key, label in mapping:
        value = facts.get(key)
        if value:
            lines.append(f"- {label}: {value}")
    lines.append("\nИсходные сообщения клиента:")
    lines.append(facts.get("raw_request", "—"))
    return "\n".join(lines)
