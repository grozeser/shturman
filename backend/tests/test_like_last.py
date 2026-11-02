"""«Как в прошлый раз, но…» и память, которая не мешает названному городу."""

import json
import os
import tempfile
from datetime import date

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.travel.brief import new_brief, parse_rules  # noqa: E402

HEADERS = {"X-User-Id": "test-user-like-last"}


def say(client: TestClient, conv: str, text: str) -> tuple[dict, dict]:
    response = client.post(f"/api/conversations/{conv}/turn", json={"text": text}, headers=HEADERS)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return next(e["message"] for e in events if e["type"] == "message"), next(e["state"] for e in events if e["type"] == "state")


def test_like_last_is_not_a_question():
    result = parse_rules("как в прошлый раз, но в горы", new_brief(), date(2026, 10, 24))
    assert result["like_last"] and result["intent"] != "question"


def test_like_last_time_repeats_and_changes_only_what_was_said():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        message, state = say(client, conv, "как в прошлый раз")
        assert any(step["title"] == "Прошлых поездок пока не помню" for step in message["steps"])
        for text in ("Анталья в мае вдвоём на 10 ночей, всё включено", "оформляй"):
            say(client, conv, text)
        client.post(f"/api/conversations/{conv}/checkout", json={"name": "Иван", "email": "ivan@example.com"}, headers=HEADERS)

        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        _, state = say(client, conv, "хочу как в прошлый раз")
        brief, sources = state["brief"], {c["key"]: c["kind"] for c in state["chips"]}
        assert state["stage"] == "plan" and brief["destination"] == "antalya" and brief["nights"] == 10 and brief["month"] == 5
        assert sources["destination"] == "memory"

        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        _, state = say(client, conv, "как в прошлый раз, но в горы")
        assert state["brief"]["destination"] is None and "mountains" in state["brief"]["kinds"] and state["brief"]["nights"] == 10

        # «всё включено» из памяти не отменяет названный город, где его не бывает
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        message, state = say(client, conv, "Стамбул в апреле")
        assert state["stage"] == "plan" and state["brief"]["destination"] == "istanbul"
        assert any(step["title"] == "Снял условие из памяти" for step in message["steps"])
