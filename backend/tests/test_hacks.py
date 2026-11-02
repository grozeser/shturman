"""Лайфхаки из расписаний: ночь в поезде вместо отеля, город на длинной пересадке, полдня на месте за рейс попозже."""

import json
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

HEADERS = {"X-User-Id": "test-user-hacks"}


def turn(client: TestClient, conv: str, **body) -> tuple[dict, dict]:
    response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=HEADERS)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return next(e["message"] for e in events if e["type"] == "message"), next(e["state"] for e in events if e["type"] == "state")


def start(client: TestClient, text: str) -> tuple[str, dict, dict]:
    conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
    message, state = turn(client, conv, text=text)
    return conv, message, state


def hack(state: dict, kind: str) -> dict | None:
    bundle = state["plan"]["bundles"][state["selected"]]
    return next((h for h in bundle["hacks"] if h["kind"] == kind), None)


def test_night_train_instead_of_hotel_night():
    with TestClient(app) as client:
        conv, message, state = start(client, "Петербург на 3 ночи в ноябре вдвоём")
        found = hack(state, "night_train")
        assert found and found["title"].startswith("Ночной поезд обратно — минус")
        assert any(s["tool"] == "find_hacks" for s in message["steps"])
        assert "Лайфхак: ночной поезд" in message["text"]
        before = state["plan"]["bundles"][0]

        message, state = turn(client, conv, action=found["action"] | {"label": found["label"]})
        after = state["plan"]["bundles"][0]
        assert after["nights"] == before["nights"] - 1 and state["brief"]["nights"] == after["nights"]
        assert after["inbound"]["mode"] == "train" and after["inbound"]["overnight"]
        assert after["inbound"]["depart"][:10] == after["checkout"], "поезд уходит вечером в день выезда из отеля"
        assert "06:30" <= after["inbound"]["arrive"][11:16] <= "10:00", "ночной поезд приходит утром"
        assert before["total"] - after["total"] == found["saving"], "обещанная экономия — ровно та, что в плане"
        assert {c["part"] for c in state["diff"]["changes"]} >= {"Даты", "Обратно"}
        assert hack(state, "night_train") is None or hack(state, "night_train")["saving"] < found["saving"]


def test_later_flight_home_for_half_a_day():
    with TestClient(app) as client:
        conv, _, state = start(client, "Казань на выходные в декабре")
        found = hack(state, "later_return")
        assert found and found["action"]["type"] == "swap" and found["action"]["part"] == "inbound_id"
        early = state["plan"]["bundles"][0]["inbound"]["depart"]
        _, state = turn(client, conv, action=found["action"] | {"label": found["label"]})
        late = state["plan"]["bundles"][state["selected"]]["inbound"]["depart"]
        assert late[:10] == early[:10] and late[11:13] >= "15"


def test_layover_city_walk_without_visa():
    with TestClient(app) as client:
        conv, _, state = start(client, "Париж в мае вдвоём")
        found = hack(state, "layover_city")
        assert found and "Стамбуле" in found["title"] and "виза для граждан РФ не нужна" in found["detail"]
        _, state = turn(client, conv, action=found["action"])
        out = state["plan"]["bundles"][state["selected"]]["outbound"]
        assert out["via"] == "Стамбуле" and out["layover_min"] >= 300
        tip = hack(state, "layover_city")
        assert tip and tip["action"] is None, "рейс уже в плане — остаётся подсказка без кнопки"


def test_no_hacks_against_explicit_wishes():
    with TestClient(app) as client:
        _, _, state = start(client, "Петербург на 3 ночи в ноябре вдвоём, только самолётом")
        assert hack(state, "night_train") is None, "просили самолёт — поезд не предлагаем"
        _, _, state = start(client, "Париж в мае вдвоём, без пересадок")
        assert hack(state, "layover_city") is None
