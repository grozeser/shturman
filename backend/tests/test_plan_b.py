"""План Б: симуляция сбоя после покупки — агент сам собирает замену, ничего не меняется до подтверждения."""

import json
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

HEADERS = {"X-User-Id": "test-user-plan-b"}


def book(client: TestClient, text: str) -> dict:
    conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
    for message in (text, "оформляй"):
        client.post(f"/api/conversations/{conv}/turn", json={"text": message}, headers=HEADERS)
    return client.post(f"/api/conversations/{conv}/checkout", json={"name": "Иван", "email": "ivan@example.com"}, headers=HEADERS).json()[
        "booking"
    ]


def act(client: TestClient, booking_id: str, **post) -> dict:
    return client.post(f"/api/bookings/{booking_id}/actions", json={"post": post}, headers=HEADERS).json()


def test_flight_cancelled_is_rebooked_for_free():
    with TestClient(app) as client:
        booking = book(client, "Анталья в мае вдвоём")
        cancelled = booking["bundle"]["outbound"]["number"]
        result = act(client, booking["id"], type="disruption", what="flight_cancelled")
        assert "План Б" in result["text"] and cancelled in result["text"]
        new = result["booking"]["pending"]["bundle"]
        assert new["outbound"]["number"] != cancelled
        assert new["outbound"]["arrive"][:10] in (booking["bundle"]["outbound"]["arrive"][:10],)  # тот же день прилёта
        assert result["booking"]["bundle"]["outbound"]["number"] == cancelled, "до подтверждения ничего не меняется"
        applied = act(client, booking["id"], type="confirm")["booking"]
        assert applied["bundle"]["outbound"]["number"] == new["outbound"]["number"]
        assert applied["payment"]["amount"] == booking["payment"]["amount"] + result["booking"]["pending"]["extra"]


def test_hotel_overbooked_moves_to_hotel_not_worse():
    with TestClient(app) as client:
        booking = book(client, "Хургада в ноябре с ребёнком 4 года")
        old = booking["bundle"]["hotel"]
        result = act(client, booking["id"], type="disruption", what="hotel_overbooked")
        new = result["booking"]["pending"]["bundle"]["hotel"]
        assert new["id"] != old["id"] and new["stars"] >= old["stars"]
        assert result["booking"]["pending"]["extra"] == 0, "переселение при овербукинге — за счёт поставщика"
        assert act(client, booking["id"], type="decline")["booking"]["bundle"]["hotel"]["id"] == old["id"]


def test_disruption_from_chat_text():
    from datetime import date

    from app.travel.brief import new_brief, parse_rules

    for text, what in (("у нас рейс отменили!", "flight_cancelled"), ("отель не может нас заселить", "hotel_overbooked")):
        result = parse_rules(text, new_brief(), date(2026, 10, 24), "booked")
        assert result["intent"] == "post" and result["post"] == {"type": "disruption", "what": what}, json.dumps(result["post"])
