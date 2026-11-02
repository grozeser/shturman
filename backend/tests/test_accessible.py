"""Доступная среда: «мама на коляске», «без лестниц» → доступные отели, трансфер с подъёмником, прямые рейсы, перевозчик предупреждён."""

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
from app.travel import hotel_view, inventory  # noqa: E402
from app.travel.brief import new_brief, parse_rules  # noqa: E402

TODAY = date(2026, 10, 24)
HEADERS = {"X-User-Id": "test-user-access"}


def accessible(text: str) -> bool:
    return bool(parse_rules(text, new_brief(), TODAY)["patch"].get("accessible"))


def test_rules_tell_wheelchair_from_stroller():
    assert accessible("мама на коляске")
    assert accessible("нужен отель без лестниц, папа плохо ходит")
    assert accessible("едем с колясочником")
    assert not accessible("едем с коляской и малышом 1 года"), "детская коляска — не доступная среда"
    assert not accessible("хочу в Сочи в мае")


def turn(client: TestClient, conv: str, **body) -> tuple[dict, dict]:
    response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=HEADERS)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return next(e["message"] for e in events if e["type"] == "message"), next(e["state"] for e in events if e["type"] == "state")


def test_plan_for_wheelchair_and_carrier_warned():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        _, state = turn(client, conv, text="Анталья в мае, мама на коляске, нас трое")
        chips = {c["key"]: c for c in state["chips"]}
        assert chips["accessible"]["kind"] == "explicit"
        assert chips["direct_only"]["kind"] == "inferred", "прямые рейсы — вывод агента, с причиной"
        plan = state["plan"]
        assert all(h["features"]["accessible"] for h in plan["hotels"])
        assert any(r["reason"] == "нет номеров с доступной средой" for r in plan["hotels_rejected"])
        for bundle in plan["bundles"]:
            assert bundle["transfer_in"]["kind"] == bundle["transfer_out"]["kind"] == "accessible", bundle["label"]
            assert not bundle["outbound"]["stops"]
            checks = {c["id"]: c for c in bundle["checks"]}
            assert checks["assist"]["status"] == "ok" and bundle["outbound"]["carrier"] in checks["assist"]["detail"]
            assert checks["lift"]["status"] == "ok"
        assert plan["bundles"][0]["why"][1].startswith("доступная среда")

        _, state = turn(client, conv, action={"type": "swap", "part": "transfer_kind", "value": "taxi"})
        lift = next(c for c in state["plan"]["bundles"][0]["checks"] if c["id"] == "lift")
        assert lift["status"] == "warn", "сами сменили трансфер на такси — агент предупреждает про коляску"

        turn(client, conv, text="оформляй")
        result = client.post(
            f"/api/conversations/{conv}/checkout", json={"name": "Анна", "email": "anna@example.com"}, headers=HEADERS
        ).json()
        booking = result["booking"]
        who = [r["who"] for r in booking["requests"]]
        assert who[0].startswith("авиакомпания «") and who[1].startswith("отель «")
        assert "Заранее предупредил: авиакомпания" in result["state"]["messages"][-1]["text"]
        assert any("коляски" in item["text"] for group in bk.checklist(booking) for item in group["items"])

        fresh = client.post("/api/conversations", headers=HEADERS).json()
        assert {c["key"]: c["kind"] for c in fresh["chips"]}.get("accessible") == "memory", "доступная среда помнится"


def test_removing_chip_drops_inferred_direct_flights():
    headers = {"X-User-Id": "test-user-access-2"}
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=headers).json()["id"]
        client.post(f"/api/conversations/{conv}/turn", json={"text": "Сочи в мае вдвоём, без лестниц"}, headers=headers)
        response = client.post(
            f"/api/conversations/{conv}/turn", json={"action": {"type": "remove_chip", "key": "accessible"}}, headers=headers
        )
        state = next(json.loads(line[6:])["state"] for line in response.text.splitlines() if '"type": "state"' in line)
        assert not state["brief"]["accessible"] and not state["brief"]["direct_only"]
        assert state["plan"]["bundles"][0]["transfer_in"]["kind"] != "accessible"


def test_hotel_view_has_wheelchair_segment():
    hotels = inventory.hotels("antalya")
    without = next(h for h in hotels if not h["features"]["accessible"])
    segments = hotel_view.fit_by_segment(without)
    assert segments["accessible"]["excluded"] == "нет номеров с доступной средой"
    ideas = hotel_view.improvements(without)
    lever = next((i for i in ideas if i["feature"] == "accessible"), None)
    assert lever is None or "Гости на коляске" in lever["opens"]
