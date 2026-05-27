import json
from pathlib import Path

from agent import PumpQualifier, extract_lead_summary, LeadStore


def test_agent_starts_with_task_question():
    agent = PumpQualifier()
    reply = agent.start()
    assert "для какой задачи" in reply.lower()
    assert "насос" in reply.lower()


def test_agent_asks_for_pump_or_full_kit_before_water_treatment():
    agent = PumpQualifier()
    agent.start()
    reply = agent.reply("Нужен насос для скважины 50 метров")
    low = reply.lower()
    assert "только насос" in low
    assert "комплект" in low
    assert "водо" not in low
    assert "анализ" not in low


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


def test_well_understands_numbers_before_depth_level_diameter_labels():
    agent = PumpQualifier()
    agent.start()
    agent.reply("скважина")
    agent.reply("комплект")
    agent.reply("50 глубина 20 уровень 125 диаметр")
    assert agent.state.facts["well_depth_m"] == "50"
    assert agent.state.facts["water_level_m"] == "20"
    assert agent.state.facts["casing_diameter_mm"] == "125"


def test_well_understands_level_typo_before_diameter_label():
    agent = PumpQualifier()
    agent.start()
    agent.reply("скважина")
    agent.reply("комплект")
    agent.reply("50 глубина 20 уроыень 125 диаметр")
    assert agent.state.facts["well_depth_m"] == "50"
    assert agent.state.facts["water_level_m"] == "20"
    assert agent.state.facts["casing_diameter_mm"] == "125"


def test_well_level_does_not_create_drainage_depth():
    agent = PumpQualifier()
    agent.start()
    agent.reply("скважина")
    agent.reply("комплект")
    agent.reply("50 глубина 20 уровень 125 диаметр")
    assert "drainage_depth" not in agent.state.facts


def test_well_mirror_after_word_not_overwritten_by_depth():
    agent = PumpQualifier()
    agent.start()
    agent.reply("скважина")
    agent.reply("комплект")
    agent.reply("50 метров зеркало 20 диаметр 100")
    assert agent.state.facts["well_depth_m"] == "50"
    assert agent.state.facts["water_level_m"] == "20"
    assert agent.state.facts["casing_diameter_mm"] == "100"


def test_agent_extracts_full_russian_phone_without_losing_last_digit():
    agent = PumpQualifier()
    agent.reply("Телефон 89991234567, зовут Иван")
    assert agent.state.facts["contact"] == "89991234567"


def test_well_flow_understands_short_full_kit_synonyms():
    agent = PumpQualifier()
    agent.start()
    agent.reply("колодец")
    for answer in ["полный", "да", "надо", "вмести", "все"]:
        local_agent = PumpQualifier()
        local_agent.start()
        local_agent.reply("колодец")
        reply = local_agent.reply(answer)
        assert local_agent.state.facts["scope"] == "Полный комплект"
        assert "только насос" not in reply.lower()


def test_usage_question_understands_number_words_and_bare_numbers_in_context():
    agent = PumpQualifier()
    agent.start()
    agent.reply("колодец")
    agent.reply("комплект")
    reply = agent.reply("пять")
    assert agent.state.facts["people"] == "5"
    assert "сколько человек" in reply.lower()
    reply = agent.reply("2")
    assert agent.state.facts["bathrooms"] == "2"
    assert "сколько человек" not in reply.lower()


def test_usage_question_understands_typos_points_and_people_in_any_order():
    agent = PumpQualifier()
    agent.start()
    agent.reply("колодец")
    agent.reply("полный")
    reply = agent.reply("5 челек 4 человека")
    assert agent.state.facts["people"] == "4"
    assert "сколько человек" in reply.lower()

    reply = agent.reply("5 точек 2 человека")
    assert agent.state.facts["people"] == "2"
    assert agent.state.facts["bathrooms"] == "5"
    assert "расстояние" in reply.lower()


def test_distance_question_remembers_phases_and_asks_only_distance():
    agent = PumpQualifier()
    agent.start()
    agent.reply("колодец")
    agent.reply("полный")
    agent.reply("5 человек 4 точки")
    reply = agent.reply("3фазы")
    assert agent.state.facts["power_phase"] == "3 фазы"
    assert "расстояние" in reply.lower()
    assert "220/380" not in reply


def test_distance_question_understands_one_two_three_phases_with_spaces():
    for message, expected in [("1 фаза", "1 фаза"), ("2 фазы", "2 фазы"), ("3фазы", "3 фазы")]:
        agent = PumpQualifier()
        agent.start()
        agent.reply("колодец")
        agent.reply("полный")
        agent.reply("5 человек 4 точки")
        agent.reply(message)
        assert agent.state.facts["power_phase"] == expected


def test_pressure_boost_understands_object_usage_words_and_point_range():
    agent = PumpQualifier()
    agent.start()
    agent.reply("повысить давление в центральной воде")
    agent.reply("насосная станция")

    reply = agent.reply("дом на полив")
    assert agent.state.facts["object_type"] == "Дом/дача"
    assert agent.state.facts["usage_points"] == "Полив"
    assert "точек" in reply.lower()

    reply = agent.reply("3 -5")
    assert agent.state.facts["bathrooms"] == "3-5"
    assert "расстояние" in reply.lower()


def test_pressure_boost_accepts_whole_house_as_usage_context():
    agent = PumpQualifier()
    agent.start()
    agent.reply("центральное водоснабжение")
    agent.reply("насосная станция")
    reply = agent.reply("для всего дома")
    assert agent.state.facts["object_type"] == "Дом/дача"
    assert agent.state.facts["usage_points"] == "Весь дом"
    assert "точек" in reply.lower()


def test_pressure_boost_flow_understands_central_water_and_pump_station():
    agent = PumpQualifier()
    agent.start()
    agent.reply("для бани")
    agent.reply("центральное водоснабжения")
    reply = agent.reply("повысеть давление в центральное воде на даче")
    assert agent.state.facts["task"] == "Повышение давления"
    assert "только насос" in reply.lower() or "насосная станция" in reply.lower()

    reply = agent.reply("насосная станция с защитой от холостого ходя")
    low = reply.lower()
    assert agent.state.facts["scope"] == "Насосная станция с защитой"
    assert "скважин" not in low
    assert "зеркало" not in low
    assert "сануз" in low or "точек" in low or "пользоваться" in low


def test_pressure_boost_flow_does_not_ask_water_treatment_before_usage_details():
    agent = PumpQualifier()
    agent.start()
    agent.reply("повысить давление в центральной воде")
    reply = agent.reply("нужна насосная станция")
    assert agent.state.facts["scope"] == "Насосная станция"
    assert "водоочист" not in reply.lower()
    assert "анализ" not in reply.lower()


def test_drainage_flow_asks_drainage_questions_not_house_water_points():
    agent = PumpQualifier()
    agent.start()
    agent.reply("привет")
    agent.reply("насос")
    reply = agent.reply("дренажный")
    low = reply.lower()
    assert agent.state.facts["task"] == "Дренажный насос"
    assert "сануз" not in low
    assert "сколько человек" not in low
    assert "подвал" in low or "откач" in low or "вода" in low


def test_drainage_flow_understands_basement_and_rainwater_with_typos():
    agent = PumpQualifier()
    agent.start()
    agent.reply("дренажный")
    reply = agent.reply("для добвала уберать воду от лявня")
    low = reply.lower()
    assert agent.state.facts["task"] == "Дренажный насос"
    assert agent.state.facts["drainage_place"] == "Подвал"
    assert agent.state.facts["drainage_water"] == "Дождевая/ливневая вода"
    assert "сануз" not in low
    assert "сколько человек" not in low


def test_drainage_flow_can_handoff_without_water_treatment_question():
    agent = PumpQualifier()
    agent.start()
    for message in [
        "дренажный",
        "для добвала уберать воду от лявня",
        "глубина приямка 1 метр, отводить в канаву",
        "Иван, город Казань, телефон 89991234567",
    ]:
        reply = agent.reply(message)
    assert agent.is_ready_for_handoff() is True
    assert "передаю заявку" in reply.lower()
    assert "водоочист" not in reply.lower()
    assert "анализ" not in reply.lower()


def test_drainage_depth_does_not_create_well_depth():
    agent = PumpQualifier()
    agent.start()
    agent.reply("дренажный")
    agent.reply("для добвала уберать воду от лявня")
    agent.reply("глубина приямка 1 метр, отводить в канаву")
    assert agent.state.facts["drainage_depth"] == "1"
    assert "well_depth_m" not in agent.state.facts
    lead = extract_lead_summary(agent.state)
    assert "Глубина воды/приямка" in lead
    assert "Глубина скважины" not in lead


def test_agent_understands_short_answer_pump_as_only_pump():
    agent = PumpQualifier()
    agent.start()
    agent.reply("Здравствуйте, нужен насос для скважины на дачу")
    reply = agent.reply("насос")
    assert agent.state.facts["scope"] == "Только насос"
    assert "глубина" in reply.lower()
    assert "зеркало" in reply.lower()
    assert "водоочист" not in reply.lower()
    assert "анализ" not in reply.lower()


def test_agent_understands_natural_well_depth_water_level_and_diameter_phrase():
    agent = PumpQualifier()
    agent.start()
    agent.reply("скважина")
    agent.reply("насос")
    reply = agent.reply("скважина 30 метров воды на 10 метрах диаметр 89")
    assert agent.state.facts["well_depth_m"] == "30"
    assert agent.state.facts["water_level_m"] == "10"
    assert agent.state.facts["casing_diameter_mm"] == "89"
    assert "глубина" not in reply.lower()
    assert "зеркало" not in reply.lower()
    assert "диаметр" not in reply.lower()


def test_agent_understands_well_numbers_with_labels_after_numbers_and_typo():
    agent = PumpQualifier()
    agent.start()
    agent.reply("скважина")
    agent.reply("насос")
    reply = agent.reply("50 метров 20 зеркало 110 диамент")
    assert agent.state.facts["well_depth_m"] == "50"
    assert agent.state.facts["water_level_m"] == "20"
    assert agent.state.facts["casing_diameter_mm"] == "110"
    assert "глубина" not in reply.lower()
    assert "зеркало" not in reply.lower()
    assert "диаметр" not in reply.lower()


def test_agent_understands_well_numbers_with_dots_and_labels_after_numbers():
    agent = PumpQualifier()
    agent.start()
    agent.reply("скважина")
    agent.reply("насос")
    reply = agent.reply("50 метров . 20 зеркало. 110 диаметр")
    assert agent.state.facts["well_depth_m"] == "50"
    assert agent.state.facts["water_level_m"] == "20"
    assert agent.state.facts["casing_diameter_mm"] == "110"
    assert "глубина" not in reply.lower()
    assert "зеркало" not in reply.lower()
    assert "диаметр" not in reply.lower()


def test_agent_asks_to_clarify_impossible_water_level_deeper_than_well():
    agent = PumpQualifier()
    agent.start()
    agent.reply("скважина")
    agent.reply("насос")
    reply = agent.reply("скважина 30 метров воды на 110 метрах диаметр 89")
    assert agent.state.facts["well_depth_m"] == "30"
    assert agent.state.facts["water_level_m"] == "110"
    assert "уточн" in reply.lower()
    assert "зеркал" in reply.lower() or "вод" in reply.lower()


def test_agent_after_full_kit_asks_well_details_before_water_treatment():
    agent = PumpQualifier()
    agent.start()
    agent.reply("Здравствуйте, нужен насос для скважины на дачу")
    reply = agent.reply("Нужен полный комплект с автоматикой и баком")
    assert agent.state.facts["scope"] == "Полный комплект"
    assert "глубина" in reply.lower()
    assert "зеркало" in reply.lower()
    assert "водоочист" not in reply.lower()
    assert "анализ воды" not in reply.lower()


def test_agent_does_not_repeat_scope_question_after_scope_is_known():
    agent = PumpQualifier()
    agent.start()
    agent.reply("Здравствуйте, нужен насос для скважины на дачу")
    agent.reply("Нужен полный комплект с автоматикой и баком")
    reply = agent.reply("Дом 4 человека, 2 санузла, кухня, душ")
    assert agent.state.facts["scope"] == "Полный комплект"
    assert "только насос" not in reply.lower()
    assert "комплект" not in reply.lower()


def test_agent_asks_water_treatment_near_end_after_pump_details():
    agent = PumpQualifier()
    agent.start()
    agent.reply("Здравствуйте, нужен насос для скважины на дачу")
    agent.reply("Нужен полный комплект с автоматикой и баком")
    agent.reply("Скважина глубина 45 метров, зеркало воды 18 метров, диаметр трубы 110")
    agent.reply("Дом 4 человека, 2 санузла, кухня, душ")
    reply = agent.reply("Расстояние до дома 20 метров")
    assert "водоочист" in reply.lower() or "анализ воды" in reply.lower()
    assert "контакт" not in reply.lower()


def test_agent_does_not_handoff_before_water_treatment_answer():
    agent = PumpQualifier()
    agent.start()
    for message in [
        "Здравствуйте, нужен насос для скважины на дачу",
        "Нужен полный комплект с автоматикой и баком",
        "Скважина глубина 45 метров, зеркало воды 18 метров, диаметр трубы 110",
        "Дом 4 человека, 2 санузла, кухня, душ",
        "Расстояние до дома 20 метров",
        "Меня зовут Иван, город Казань, телефон 89991234567",
    ]:
        reply = agent.reply(message)
    assert agent.is_ready_for_handoff() is False
    assert "водоочист" in reply.lower() or "анализ воды" in reply.lower()


def test_agent_understands_negative_water_treatment_answer_without_drainage_pollution():
    agent = PumpQualifier()
    agent.start()
    for message in [
        "Здравствуйте, нужен насос для скважины на дачу",
        "Нужен полный комплект с автоматикой и баком",
        "Скважина глубина 45 метров, зеркало воды 18 метров, диаметр трубы 110",
        "Дом 4 человека, 2 санузла, кухня, душ",
        "Расстояние до дома 20 метров",
    ]:
        agent.reply(message)

    reply = agent.reply("Водоочистка не нужна, анализа нет")

    assert agent.state.facts["water_treatment"] == "Не нужна, анализа нет"
    assert "drainage_water" not in agent.state.facts
    assert "контакт" in reply.lower()


def test_agent_understands_positive_water_treatment_answer():
    agent = PumpQualifier()
    agent.start()
    agent.reply("скважина глубина 50 зеркало 30 диаметр 110")
    agent.reply("полный комплект")
    agent.reply("дом 4 человека, 2 санузла")
    agent.reply("расстояние 20 метров")
    agent.reply("Да, нужна водоочистка, анализ воды есть")

    assert agent.state.facts["water_treatment"] == "Нужна, анализ есть"


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
