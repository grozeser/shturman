"""Особое питание: халяль, вегетарианцы, без глютена, аллергия на орехи → фильтр отелей по кухне, «предупредил отель», память."""

import json
import os
import tempfile
from datetime import date

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.agent import booking as bk  # noqa: E402
from app.main import app  # noqa: E402
from app.travel import inventory, planner  # noqa: E402
from app.travel.brief import new_brief, parse_rules  # noqa: E402

TODAY = date(2026, 10, 24)
HEADERS = {"X-User-Id": "test-user-diet"}


def diet_of(text: str) -> list[str]:
    return parse_rules(text, new_brief(), TODAY)["patch"].get("diet", [])


def test_rules_understand_diets():
    assert diet_of("мы едим только халяль, у сына аллергия на арахис") == ["halal", "nut_free"]
    assert diet_of("мы веганы") == ["vegan"], "веганское меню — уже вегетарианское, второе условие лишнее"
    assert diet_of("жена не ест мясо") == ["vegetarian"]
    assert diet_of("без глютена и без лактозы") == ["gluten_free", "lactose_free"]
    assert diet_of("хочу к морю в мае") == []


def test_kitchen_does_not_shift_synthetic_inventory():
    """Умения кухни — своя последовательность случайных чисел: цены и состав отелей прежние."""
    hotels = inventory.hotels("antalya")
    assert all(set(h["diets"]) == {"halal", "vegetarian", "vegan", "gluten_free", "lactose_free", "nut_free"} for h in hotels)
    first = hotels[0]
    assert (first["name"], first["stars"], first["price_night"]) == ("Amara Village", 4, 16900), "как в main до появления кухни"
    halal = sum(h["diets"]["halal"] for h in hotels) / len(hotels)
    assert halal > 0.8, "в Турции халяль — норма кухни"
    assert planner.diet_share("paris", ["halal"]) < halal


def turn(client: TestClient, conv: str, **body) -> tuple[dict, dict]:
    response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=HEADERS)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return next(e["message"] for e in events if e["type"] == "message"), next(e["state"] for e in events if e["type"] == "state")


def test_hotels_filtered_and_hotel_warned():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        message, state = turn(client, conv, text="Анталья в мае вдвоём, едим только халяль, у жены аллергия на орехи")
        assert state["brief"]["diet"] == ["halal", "nut_free"]
        assert {"кухня: халяль", "кухня: без орехов"} <= {c["label"] for c in state["chips"]}
        plan = state["plan"]
        assert all({"halal", "nut_free"} <= set(h["diets"]) for h in plan["hotels"])
        assert any(r["reason"].startswith("кухня не готовит") for r in plan["hotels_rejected"])
        assert plan["bundles"][0]["why"][1] == "кухня: халяль, без орехов", "требование видно в карточке варианта"
        assert any(s["tool"] == "check_kitchen" for s in message["steps"])

        turn(client, conv, text="оформляй")
        booking = client.post(
            f"/api/conversations/{conv}/checkout", json={"name": "Анна", "email": "anna@example.com"}, headers=HEADERS
        ).json()
        assert booking["booking"]["requests"][0]["what"] == "кухня: халяль, без орехов"
        assert "Заранее предупредил: отель «" in booking["state"]["messages"][-1]["text"]
        checklist = bk.checklist(booking["booking"])
        assert any("аллерги" in item["text"].lower() for group in checklist for item in group["items"])

        conv = client.post("/api/conversations", headers=HEADERS).json()
        assert {c["label"]: c["kind"] for c in conv["chips"]}.get("кухня: халяль") == "memory", "особое питание помнится"


def test_destinations_without_suitable_kitchen_are_skipped():
    brief = new_brief() | {"month": 5, "kinds": ["city"], "diet": ["halal"]}
    sugg = planner.suggest_destinations(brief, TODAY, limit=8)
    assert all(planner.diet_share(item["id"], ["halal"]) >= 0.15 for item in sugg["items"] + sugg["more"])


def test_removing_diet_chip_brings_hotels_back():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers={"X-User-Id": "test-user-diet-2"}).json()["id"]
        headers = {"X-User-Id": "test-user-diet-2"}
        response = client.post(f"/api/conversations/{conv}/turn", json={"text": "Сочи в мае вдвоём, мы вегетарианцы"}, headers=headers)
        assert response.status_code == 200
        response = client.post(
            f"/api/conversations/{conv}/turn", json={"action": {"type": "remove_chip", "key": "diet:vegetarian"}}, headers=headers
        )
        state = next(json.loads(line[6:])["state"] for line in response.text.splitlines() if '"type": "state"' in line)
        assert state["brief"]["diet"] == []
        assert not any(r["reason"].startswith("кухня") for r in state["plan"]["hotels_rejected"])
