"""Сквозной сценарий через API в режиме без LLM: от первого сообщения до покупки и действий после неё."""

import json
import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import store  # noqa: E402
from app.main import app  # noqa: E402

HEADERS = {"X-User-Id": "test-user-1"}


def turn(client: TestClient, conv_id: str, **body) -> tuple[dict, dict, list[dict]]:
    response = client.post(f"/api/conversations/{conv_id}/turn", json=body, headers=HEADERS)
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    message = next(e["message"] for e in events if e["type"] == "message")
    state = next(e["state"] for e in events if e["type"] == "state")
    return message, state, [e["step"] for e in events if e["type"] == "step"]


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_full_journey():
    with TestClient(app) as client:
        state = client.post("/api/conversations", headers=HEADERS).json()
        conv = state["id"]

        message, state, _ = turn(client, conv, text="хочу на море")
        assert state["stage"] == "clarify" and message["quick"]

        message, state, steps = turn(client, conv, text="в ноябре с ребёнком 5 лет, недорого, без долгих перелётов")
        assert state["stage"] == "inspire", message["text"]
        assert state["metrics"]["clarifications"] == 1
        assert any(s["tool"] == "search_destinations" for s in steps)
        first = state["suggestions"]["items"][0]

        message, state, steps = turn(client, conv, action={"type": "select_destination", "id": first["id"]})
        assert state["stage"] == "plan", message["text"]
        best = state["plan"]["bundles"][0]
        assert best["total"] > 0 and best["checks"]
        assert not best["outbound"]["night"], "с ребёнком агент не должен брать ночной рейс"
        assert any(s["tool"] == "validate_itinerary" for s in steps)

        message, state, steps = turn(client, conv, text="а если на два дня позже?")
        assert state["diff"] and any(c["part"] == "Даты" for c in state["diff"]["changes"]), message["text"]
        assert any(s["tool"] == "replan" for s in steps)

        message, state, _ = turn(client, conv, text="с нами едет собака")
        if state["stage"] == "inspire":  # там, где были, с собакой нельзя — агент сам предложил замену
            assert state["suggestions"]["items"], message["text"]
            message, state, _ = turn(client, conv, action={"type": "select_destination", "id": state["suggestions"]["items"][0]["id"]})
        hotel = state["plan"]["bundles"][0]["hotel"]
        assert hotel["features"]["pets"], "после «с нами едет собака» отель должен принимать животных"

        message, state, _ = turn(client, conv, text="оформляй")
        assert state["stage"] == "checkout"
        response = client.post(f"/api/conversations/{conv}/checkout", json={"name": "Иван", "email": "ivan@example.com"}, headers=HEADERS)
        assert response.status_code == 200
        booking = response.json()["booking"]
        assert booking["status"] == "confirmed" and booking["reminders"]

        message, state, _ = turn(client, conv, text="можно заселиться пораньше?")
        assert "заезд" in message["text"].lower()

        message, state, _ = turn(client, conv, text="перенеси поездку на два дня позже")
        assert message["quick"] and message["quick"][0]["action"]["post"]["type"] == "confirm", message["text"]
        message, state, _ = turn(client, conv, action={"type": "post", "post": {"type": "confirm"}})
        assert "Перенёс" in message["text"]

        profile = client.get("/api/profile", headers=HEADERS).json()
        assert "party" in profile["facts"] and "pets" in profile["facts"]
        fresh = client.post("/api/conversations", headers=HEADERS).json()
        assert fresh["sources"]["children"]["kind"] == "memory"
        assert "помню" in fresh["messages"][0]["text"].lower()

        metrics = client.get("/api/metrics").json()
        assert metrics["live"]["booked"] >= 1
        funnel = {row["step"]: row["count"] for row in metrics["business"]["funnel"]}
        assert funnel["Написали запрос"] >= funnel["Собрали поездку"] >= funnel["Оформили"] >= 1
        assert metrics["business"]["avg_check"] > 0 and metrics["business"]["post_purchase_actions"] >= 1

        # взгляд отеля: забронированный отель видит рекомендацию и бронь, а также кому он подходит
        hotel_id = booking["bundle"]["hotel"]["id"]
        report = client.get(f"/api/hotels/{hotel_id}").json()
        # в базе есть и брони тестовых пользователей — сверяем со всеми бронями этого отеля, наша среди них
        booked_here = [b["id"] for b in store.all_bookings() if b["bundle"]["hotel"]["id"] == hotel_id]
        assert booking["id"] in booked_here
        assert report["stats"]["recommended"] >= 1 and report["stats"]["booked"] == len(booked_here)
        assert set(report["segments"]) == {"family", "couple", "solo", "pets", "seniors", "party", "accessible"}
        rows = client.get(f"/api/hotels?dest={booking['bundle']['dest']}").json()
        assert any(row["id"] == hotel_id and row["booked"] == len(booked_here) for row in rows)


def test_concrete_request_goes_straight_to_plan():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers={"X-User-Id": "test-user-2"}).json()["id"]
        response = client.post(
            f"/api/conversations/{conv}/turn",
            json={"text": "Сочи с 10 по 17 ноября вдвоём, бюджет 80 тысяч"},
            headers={"X-User-Id": "test-user-2"},
        )
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        state = next(e["state"] for e in events if e["type"] == "state")
        assert state["stage"] == "plan" and state["metrics"]["clarifications"] == 0
        assert state["plan"]["checkin"] == "2026-11-10"
        assert state["plan"]["bundles"][0]["total"] <= 80000


def test_route_of_two_places():
    headers = {"X-User-Id": "test-user-route"}
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=headers).json()["id"]

        def say(**body):
            response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=headers)
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            return next(e["state"] for e in events if e["type"] == "state")

        state = say(text="3 ночи в Стамбуле и 4 в Каппадокии в мае вдвоём")
        assert state["stage"] == "plan" and state["plan"]["multi"]
        trip = state["plan"]["bundles"][0]
        legs = trip["legs"]
        assert [leg["dest"] for leg in legs] == ["istanbul", "cappadocia"] and [leg["nights"] for leg in legs] == [3, 4]
        assert legs[0]["checkout"] == legs[1]["checkin"], "переезд в день выезда из первого города"
        assert legs[1]["outbound"]["id"] == legs[0]["inbound"]["id"] and legs[1]["outbound"]["included"]
        assert trip["total"] == sum(leg["total"] for leg in legs), "переезд оплачен один раз"
        assert any(c["label"] == "Стамбул → Каппадокия" for c in state["chips"])

        state = say(text="а если на два дня позже?")
        assert state["plan"]["multi"] and state["plan"]["checkin"] > trip["checkin"]

        state = say(text="оформляй")
        booking = client.post(
            f"/api/conversations/{conv}/checkout", json={"name": "Иван", "email": "ivan@example.com"}, headers=headers
        ).json()["booking"]
        assert len(booking["bundle"]["legs"]) == 2
        moved = client.post(
            f"/api/bookings/{booking['id']}/actions", json={"post": {"type": "change_dates", "shift_days": 3}}, headers=headers
        ).json()
        assert "Перенос" in moved["text"] and moved["booking"]["pending"]["bundle"]["legs"]


def test_price_calendar_matches_rebuild():
    headers = {"X-User-Id": "test-user-dates"}
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=headers).json()["id"]
        assert client.get(f"/api/conversations/{conv}/dates", headers=headers).json() == []  # плана ещё нет

        def say(**body):
            response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=headers)
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            return next(e["state"] for e in events if e["type"] == "state")

        state = say(text="Анталья в мае вдвоём")
        days = client.get(f"/api/conversations/{conv}/dates", headers=headers).json()
        assert [d["offset"] for d in days] == [-3, -2, -1, 0, 1, 2, 3]
        current = next(d for d in days if d["offset"] == 0)
        assert current["date"] == state["plan"]["checkin"] and current["delta"] == 0
        assert current["total"] == state["plan"]["bundles"][state["selected"]]["total"]
        assert sum(d["cheapest"] for d in days) >= 1
        # клик по другому дню — та же цена, что обещал календарь
        other = min((d for d in days if d["available"] and d["offset"]), key=lambda d: d["total"])
        state = say(action={"type": "edit_brief", "patch": {"date_from": other["date"], "month": int(other["date"][5:7])}})
        assert state["plan"]["checkin"] == other["date"]
        assert state["plan"]["bundles"][0]["total"] == other["total"]
