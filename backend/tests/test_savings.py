"""«Сколько времени вы сэкономили»: итог собирается из следа агента — цифры совпадают с тем, что он реально сравнил."""

import json
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.agent import savings  # noqa: E402
from app.main import app  # noqa: E402
from app.travel import catalog, inventory  # noqa: E402

HEADERS = {"X-User-Id": "test-user-savings"}


def turn(client: TestClient, conv: str, **body) -> tuple[dict, dict]:
    response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=HEADERS)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    message = next(e["message"] for e in events if e["type"] == "message")
    return message, next(e["state"] for e in events if e["type"] == "state")


def test_full_path_counts_what_agent_compared():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        turn(client, conv, text="хочу на море")
        _, state = turn(client, conv, text="в ноябре вдвоём")
        first = state["suggestions"]["items"][0]
        _, state = turn(client, conv, action={"type": "select_destination", "id": first["id"], "label": f"Собрать: {first['name']}"})
        assert state["savings"] is None, "итог показываем в конце пути, а не на каждом шаге"
        plan = state["plan"]
        message, state = turn(client, conv, text="оформляй")

        saved = state["savings"]
        assert saved["destinations"] == sum(1 for d in catalog.destinations().values() if not d.get("dynamic"))
        assert saved["hotels"] == len(inventory.hotels(plan["dest"]))
        assert saved["transport"] == len({o["id"] for o in plan["outbound"] + plan["inbound"]})
        assert saved["dates"] == len(plan["date_scan"])
        assert (saved["messages"], saved["taps"]) == (3, 1)
        assert saved["checks"] == len(state["plan"]["bundles"][state["selected"]]["checks"])
        assert saved["clicks"] >= 40 and saved["minutes"] > 0
        assert saved["line"].startswith("3 сообщения и 1 нажатие вместо ")
        assert "направлени" in saved["line"] and "стыков" in saved["line"]
        assert saved["line"] in message["text"], "строка итога — в ответе агента (её же видит бот)"

        booking = client.post(
            f"/api/conversations/{conv}/checkout", json={"name": "Иван", "email": "ivan@example.com"}, headers=HEADERS
        ).json()["booking"]
        assert booking["savings"]["line"] == saved["line"]
        business = client.get("/api/metrics").json()["business"]
        assert business["avg_minutes_saved"] and business["avg_clicks_saved"] >= 40


def test_named_destination_does_not_claim_destinations():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        turn(client, conv, text="Сочи с 10 по 17 ноября вдвоём")
        _, state = turn(client, conv, text="оформляй")
        saved = state["savings"]
        assert saved["destinations"] == 0 and saved["dates"] == 0, "направление и даты назвали сами — их агент не перебирал"
        assert "направлени" not in saved["line"] and "дат" not in saved["line"]
        assert saved["line"].startswith("2 сообщения вместо ")


def test_duration_label():
    assert savings.duration_label(12) == "10 мин"
    assert savings.duration_label(59) == "1 ч"
    assert savings.duration_label(95) == "1,5 ч"
