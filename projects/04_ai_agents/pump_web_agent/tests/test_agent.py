import json
from pathlib import Path

from agent import PumpQualifier, extract_lead_summary, LeadStore


def test_agent_starts_with_task_question():
    agent = PumpQualifier()
    reply = agent.start()
    assert "для какой задачи" in reply.lower()
    assert "насос" in reply.lower()


def test_agent_asks_for_pump_or_full_kit_and_water_treatment():
    agent = PumpQualifier()
    agent.start()
    reply = agent.reply("Нужен насос для скважины 50 метров")
    low = reply.lower()
    assert "только насос" in low
    assert "комплект" in low
    assert "водо" in low or "анализ" in low


def test_agent_does_not_require_budget_urgency_or_pressure():
    agent = PumpQualifier()
    prompts = [agent.start()]
    for msg in [
        "скважина глубина 50 зеркало 30 диаметр 110",
        "нужен полный комплект, анализ воды нужен",
        "дом 4 человека, 2 санузла, кухня, баня",
        "расстояние до дома 20 метров, электричество 220",
        "Иван, телефон +79990000000, город Казань",
    ]:
        prompts.append(agent.reply(msg))
    combined = "\n".join(prompts).lower()
    forbidden = ["бюджет", "сроч", "давлен"]
    assert all(word not in combined for word in forbidden)


def test_agent_creates_lead_when_contact_received():
    agent = PumpQualifier()
    agent.start()
    messages = [
        "нужен насос для скважины, глубина 50, зеркало 30, диаметр 110",
        "полный комплект, водоочистка нужна",
        "дом 4 человека, 2 санузла, кухня",
        "расстояние 20 метров, город Казань",
        "Меня зовут Иван, телефон +79990000000",
    ]
    reply = ""
    for message in messages:
        reply = agent.reply(message)
    assert agent.is_ready_for_handoff() is True
    assert "передаю заявку" in reply.lower()
    lead = extract_lead_summary(agent.state)
    assert "Иван" in lead
    assert agent.state.facts["name"] == "Иван"
    assert "+79990000000" in lead
    assert "Казань" in lead


def test_lead_store_appends_jsonl(tmp_path):
    target = tmp_path / "leads.jsonl"
    store = LeadStore(target)
    store.append({"name": "Иван", "phone": "+79990000000"})
    rows = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["phone"] == "+79990000000"
