"""Разбор живых формулировок на правилах — регрессия на ошибки, найденные прогоном реальных запросов."""

from datetime import date

import pytest

from app.travel.brief import new_brief, parse_rules

TODAY = date(2026, 10, 25)


def parse(text: str, **brief_overrides) -> dict:
    return parse_rules(text, new_brief() | brief_overrides, TODAY, "plan" if brief_overrides else "start")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Хочу в Турцию в июле с мужем и тремя детьми", {"children": [6, 6, 6], "adults": 2}),
        ("Хургада, 2+2 (дети 5 и 10)", {"children": [5, 10], "adults": 2}),
        ("хочу на море в сентябре, ребёнку 3", {"children": [3]}),
        ("погреться на новогодние, нас 2 взрослых и малыш 1.5 года", {"adults": 2, "children": [1], "month": 12}),
        ("мы с мужем и двумя пацанами 4 и 9 лет, денег тысяч на 250", {"children": [4, 9], "budget": 250000}),
        ("Тайланд в феврале, 2 недели", {"nights": 14, "month": 2}),
        ("в отпуск на 2 недели в августе, куда-нибудь в Европу без визы", {"regions": ["europe"], "visa_free": True, "nights": 14}),
        ("семья 2+1, хотим на Черное море в августе, без самолетов", {"regions": ["black_sea"], "transport": "train"}),
        ("поездка с пожилыми родителями на воды в октябре следующего года", {"destination": "kmv", "adults": 3, "year": 2027}),
        ("что-нибудь романтичное, недалеко от Москвы, в ноябре", {"destination": None, "adults": 2}),
        ("хочу куда-то где нет туристов и красивая природа, лето", {"month": 7}),
        ("летом на Алтай на машине", {"destination": "altai", "own_car": True}),
    ],
)
def test_first_message(text, expected):
    patch = parse(text)["patch"]
    for key, value in expected.items():
        assert patch.get(key) == value, f"{key}: ждали {value}, получили {patch.get(key)} для «{text}»"


@pytest.mark.parametrize(
    ("text", "expected", "forbidden"),
    [
        ("без завтраков", {"meal": "RO"}, ["date_from"]),  # «завтраки» не «завтра»
        ("добавь завтраки", {"meal": "BB"}, ["date_from"]),
        ("лучше самолётом", {"transport": "flight"}, ["month"]),  # «самолЁТОМ» не «летом»
        ("на 2 дня меньше", {"nights": 5}, []),
        ("а давай на 10 ночей", {"nights": 10}, []),
        ("с нами ещё мама поедет", {"adults": 3}, []),
        ("хочу отель поближе к пляжу и с бассейном", {"hotel_prefs": ["near_beach", "pool"]}, []),
        ("спасибо!", {}, ["kinds"]),  # «спасибо» не «спа»
        ("отпуск в феврале, хочу горы, я не катаюсь", {"month": 2}, ["exclude"]),  # «не катаюсь» не исключает Пхукет
    ],
)
def test_plan_edits(text, expected, forbidden):
    patch = parse(text, destination="antalya", month=9, nights=7)["patch"]
    for key, value in expected.items():
        assert patch.get(key) == value, f"{key}: ждали {value}, получили {patch.get(key)} для «{text}»"
    for key in forbidden:
        assert key not in patch, f"«{text}» не должно менять {key}, а дало {patch.get(key)}"


@pytest.mark.parametrize(
    ("text", "intent"),
    [("спасибо!", "chat"), ("начнём сначала", "reset"), ("что там посмотреть?", "question"), ("окей, бронируем", "book")],
)
def test_intents(text, intent):
    assert parse(text, destination="antalya", month=9)["intent"] == intent


def test_other_destinations_excludes_current():
    patch = parse("а покажи другие направления", destination="antalya", month=9)["patch"]
    assert patch["destination"] is None and "antalya" in patch["exclude"]


@pytest.mark.parametrize(
    ("text", "topic", "month"),
    [
        ("а в январе там тепло?", "weather", 1),
        ("можно ли там купаться в декабре?", "weather", 12),
        ("нужна ли виза?", "visa", None),
        ("какая там валюта?", "other", None),
        ("безопасно ли там с детьми?", "other", None),  # вопрос, а не «добавь детей»
    ],
)
def test_questions_do_not_change_brief(text, topic, month):
    result = parse(text, destination="hurghada", month=12)
    assert result["intent"] == "question" and result["question"] == topic and not result["patch"]
    assert result.get("question_month") == month


def test_route_phrase_is_not_reset():
    assert parse("сначала Рим, потом Флоренция, 6 ночей в июне")["intent"] != "reset"
    assert parse("сначала")["intent"] == "reset"


# находки прогона scripts/redteam.py: опечатки, валюта, разговорные даты, «без ребёнка»
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("хочу в сочм в декабре вдвоем", {"destination": "sochi"}),
        ("turkey в июле, 2 взрослых", {"destination": "antalya"}),
        ("хочу в тай в декабре", {"destination": "phuket"}),
        ("дубай нг 2 взрослых", {"date_from": "2026-12-30", "month": 12}),
        ("в начале марта в египет на неделю", {"date_from": "2027-03-02", "nights": 7}),
        ("$1500 на двоих в египет в феврале", {"budget": 120000}),
        ("до 50 на человека, море, ноябрь", {"budget": 100000}),
        ("без перелётов на мальдивы", {"transport": "train"}),
        ("хочу отдохнуть от работы, чтобы никого вокруг", {"hotel_prefs": ["quiet"]}),
    ],
)
def test_redteam_findings(text, expected):
    patch = parse(text)["patch"]
    for key, value in expected.items():
        assert patch.get(key) == value, (key, patch.get(key))


@pytest.mark.parametrize(
    "text", ["весной куда-нибудь недалеко", "отель недалеко от пляжа", "до 25 мая", "не больше 4 часов в пути", "до 18 лет"]
)
def test_no_false_positives(text):
    patch = parse(text)["patch"]
    assert "food" not in patch.get("kinds", []) and "budget" not in patch


def test_without_child_drops_inferred_limits():
    from app.travel.brief import derive, new_sources

    brief, sources = new_brief() | {"children": [6]}, new_sources()
    derive(brief, sources)
    assert brief["avoid_night"] and "kids_club" in brief["hotel_prefs"]
    brief["children"] = parse("а если без ребёнка", destination="sochi")["patch"]["children"]
    derive(brief, sources)
    assert brief["children"] == [] and not brief["avoid_night"] and brief["max_hours"] is None and "kids_club" not in brief["hotel_prefs"]


@pytest.mark.parametrize("text", ["кто ты?", "что ты умеешь?", "как дела?"])
def test_about_is_chat(text):
    result = parse(text)
    assert result["intent"] == "chat" and result["chat"] == "about"


def test_places_in_lowercase():
    from app.travel import geo

    assert geo.lower_place("лиссабон на 5 дней в октябре") == "лиссабон"
    assert geo.lower_place("в нью-йорк на новый год") == "нью-йорк"
    for text in ("хочу на море в июле", "на неделю в горы", "в отпуск в августе с семьёй", "в пути не больше 4 часов"):
        assert geo.lower_place(text) is None, text
    assert geo.find_route("турция и египет в мае") == []  # выбор между странами, а не маршрут
    assert [s.get("id") for s in geo.find_route("в рим и флоренцию")] == ["rome", None]


def test_llm_budget_in_dollars_uses_rules_rate(monkeypatch):
    """Модель на «$1500» сама пересчитала в 300 000 ₽ (живой прогон qwen3) — правила с помеченным курсом главнее."""
    from app.agent import interpret as interpret_module
    from app.agent import llm

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(
        llm, "chat", lambda *args, **kwargs: '{"intent": "plan", "destination": "Египет", "budget_rub": 300000, "adults": 2}'
    )
    result = interpret_module.interpret("$1500 на двоих в египет в феврале", new_brief(), "start", TODAY)
    assert not result.get("fallback")
    assert result["patch"]["budget"] == 120000 and "курсу" in result["inferred_reasons"]["budget"]


@pytest.mark.parametrize("text", ["нужна ли виза?", "кто ты?", "спасибо"])
def test_llm_is_skipped_when_rules_are_sure(monkeypatch, text):
    """Визу, погоду, «кто ты» и приветствие отвечаем шаблоном по данным — модель не вызываем вовсе."""
    from app.agent import interpret as interpret_module
    from app.agent import llm

    def fail(*args, **kwargs):
        raise AssertionError("модель не должна вызываться")

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "chat", fail)
    result = interpret_module.interpret(text, new_brief() | {"destination": "antalya"}, "plan", TODAY)
    assert result["source"] == "rules" and result["intent"] in ("question", "chat")


def test_offtopic_chat_from_llm_is_not_a_greeting(monkeypatch):
    from app.agent import llm
    from app.agent.core import new_state, run_turn

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda *args, **kwargs: '{"intent": "chat"}')
    state = new_state("t-offtopic", "t-offtopic", {})
    for _ in run_turn(state, text="расскажи анекдот", today=TODAY, profile={}):
        pass
    answer = state["messages"][-1]["text"]
    assert answer.startswith("Я помогаю только с поездками") and "Здравствуйте" not in answer
