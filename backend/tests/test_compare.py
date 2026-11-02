"""Сравнение направлений: «Турция или Египет в мае?» → две собранные поездки рядом, «беру эту» → тот же план до рубля."""

import json
import os
import tempfile
from datetime import date

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.travel.brief import find_compare, new_brief, parse_rules  # noqa: E402

HEADERS = {"X-User-Id": "test-user-compare"}


def test_rules_tell_choice_from_route():
    assert find_compare("турция или египет в мае?") == ["antalya", "hurghada"]
    assert find_compare("что лучше: сочи или абхазия") == ["sochi", "abkhazia"]
    assert find_compare("сравни анталью и хургаду") == ["antalya", "hurghada"]
    assert find_compare("стамбул и каппадокия в мае") == [], "без «или» и «сравни» — это маршрут, а не выбор"
    assert find_compare("в мае или в июне в сочи") == [], "одно место — сравнивать нечего"
    result = parse_rules("сравни первые два", new_brief(), date(2026, 10, 24), "inspire")
    assert result["compare_picks"] == [1, 2] and not result["select"], "«первые два» — не выбор первого варианта"


def turn(client: TestClient, conv: str, **body) -> tuple[dict, dict]:
    response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=HEADERS)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return next(e["message"] for e in events if e["type"] == "message"), next(e["state"] for e in events if e["type"] == "state")


def test_two_trips_side_by_side_and_take_one():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        message, state = turn(client, conv, text="Турция или Египет в мае вдвоём?")
        assert state["stage"] == "compare", message["text"]
        items = state["comparison"]["items"]
        assert [i["id"] for i in items] == ["antalya", "hurghada"]
        assert all(i["total"] > 0 and i["weather"]["water"] and i["hotel"]["name"] for i in items)
        assert any(pro.startswith("дешевле на") for i in items for pro in i["pros"])
        assert any(con.startswith("дороже на") for i in items for con in i["cons"])
        assert state["comparison"]["winner"] in ("antalya", "hurghada")
        assert "Мой выбор — " in message["text"]
        assert [q["action"]["type"] for q in message["quick"]] == ["choose_compared", "choose_compared"]
        assert any(s["tool"] == "compare_destinations" for s in message["steps"])

        hurghada = next(i for i in items if i["id"] == "hurghada")
        _, state = turn(client, conv, action={"type": "choose_compared", "id": "hurghada", "label": "Беру: Хургада"})
        assert state["stage"] == "plan" and state["plan"]["dest"] == "hurghada"
        assert state["plan"]["bundles"][0]["total"] == hurghada["total"], "в плане та же цена, что в сравнении"


def test_choice_by_text_and_question_without_dates():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        message, state = turn(client, conv, text="сравни Сочи и Абхазию")
        assert state["stage"] == "clarify", "без месяца не сравнить погоду и цены — спрашиваем один раз"
        message, state = turn(client, conv, text="в июле вдвоём")
        assert state["stage"] == "compare", message["text"]
        assert {i["id"] for i in state["comparison"]["items"]} == {"sochi", "abkhazia"}
        _, state = turn(client, conv, text="беру абхазию")
        assert state["stage"] == "plan" and state["plan"]["dest"] == "abkhazia"


def test_compare_two_from_suggestions():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        _, state = turn(client, conv, text="хочу к морю в мае вдвоём")
        first, second = state["suggestions"]["items"][:2]
        _, state = turn(client, conv, text="сравни первые два")
        assert [i["id"] for i in state["comparison"]["items"]] == [first["id"], second["id"]]
