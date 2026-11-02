"""Пересборка от выбранного варианта: «Экономный» и «Комфорт» остаются собой, календарь обещает ту цену, что выйдет."""

import json
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def say(client: TestClient, conv: str, headers: dict, **body) -> dict:
    response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=headers)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return next(e["state"] for e in events if e["type"] == "state")


@pytest.mark.parametrize(("text", "style"), [("Анталья в мае вдвоём", "comfort"), ("Хургада в ноябре с ребёнком 4 года", "cheap")])
def test_replan_keeps_selected_variant(text, style):
    headers = {"X-User-Id": f"test-replan-{style}"}
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=headers).json()["id"]
        state = say(client, conv, headers, text=text)
        index = next(i for i, b in enumerate(state["plan"]["bundles"]) if b["style"] == style)
        state = say(client, conv, headers, action={"type": "select_bundle", "index": index})
        selected = state["plan"]["bundles"][state["selected"]]

        days = client.get(f"/api/conversations/{conv}/dates", headers=headers).json()
        assert next(d for d in days if d["offset"] == 0)["total"] == selected["total"], "сегодня в календаре — цена выбранного варианта"

        state = say(client, conv, headers, text="а если на 2 дня позже?")
        after = state["plan"]["bundles"][state["selected"]]
        assert after["style"] == style, "пересборка не превращает выбранный вариант в «Оптимальный»"
        assert after["total"] == next(d for d in days if d["offset"] == 2)["total"], "вышла та цена, что обещал календарь"
