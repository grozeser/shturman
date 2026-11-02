"""«Передать человеку»: очередь, консоль оператора с брифом, планом и следом агента, ответ прямо в чат и в Telegram."""

import json
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)
os.environ.pop("OPERATOR_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import bot, store  # noqa: E402
from app.main import app  # noqa: E402

HEADERS = {"X-User-Id": "test-user-handoff"}
OPERATOR = {"X-Operator-Key": "operator-demo"}


def turn(client: TestClient, conv: str, **body) -> tuple[dict | None, dict]:
    response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=HEADERS)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    message = next((e["message"] for e in events if e["type"] == "message"), None)
    return message, next(e["state"] for e in events if e["type"] == "state")


def test_handoff_with_full_context_and_back_to_agent():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        turn(client, conv, text="Анталья в мае вдвоём")
        message, state = turn(client, conv, text="позовите живого менеджера")
        assert message["kind"] == "handoff" and state["handoff"]["status"] == "waiting"
        assert state["stage"] == "plan", "план никуда не делся"
        assert any(s["tool"] == "handoff" for s in message["steps"])

        message, state = turn(client, conv, text="у мамы день рождения 12 мая, хотим успеть")
        assert message is None, "пока диалог у менеджера, агент молчит"
        assert state["messages"][-1]["role"] == "user" and state["handoff"]["unread"] == 1

        assert client.get("/api/operator/queue").status_code == 403, "без ключа оператора очередь не видна"
        queue = client.get("/api/operator/queue", headers=OPERATOR).json()
        row = next(r for r in queue if r["id"] == conv)
        assert row["status"] == "waiting" and row["reason"] == "попросили живого менеджера"
        assert row["last_message"].startswith("у мамы день рождения") and row["trip"].startswith("Анталья")

        seen = client.get(f"/api/operator/conversations/{conv}", headers=OPERATOR).json()
        assert seen["chips"] and seen["plan"]["bundles"], "оператор видит бриф «Я понял так» и план"
        assert sum(len(m.get("steps") or []) for m in seen["messages"]) > 3, "и след агента"

        reply = client.post(
            f"/api/operator/conversations/{conv}/reply",
            json={"text": "Здравствуйте! Подберу даты к 12 мая.", "operator": "Мария"},
            headers=OPERATOR,
        ).json()
        assert reply["handoff"]["status"] == "active" and reply["handoff"]["unread"] == 0
        mine = client.get(f"/api/conversations/{conv}", headers=HEADERS).json()
        operator_message = mine["messages"][-1]
        assert (operator_message["role"], operator_message["author"]) == ("operator", "Мария")

        closed = client.post(f"/api/operator/conversations/{conv}/close", json={"operator": "Мария"}, headers=OPERATOR).json()
        assert closed["handoff"]["status"] == "closed" and "я снова на связи" in closed["messages"][-1]["text"]
        assert all(r["id"] != conv for r in client.get("/api/operator/queue", headers=OPERATOR).json())

        message, state = turn(client, conv, text="а если на два дня позже?")
        assert message and state["diff"], "после менеджера снова отвечает агент"
        live = client.get("/api/metrics").json()["live"]
        assert live["handoffs"] >= 1 and 0 < live["handoff_share"] <= 1


def test_cancel_and_offer_after_misunderstanding():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        turn(client, conv, text="Сочи в мае вдвоём")
        message, _ = turn(client, conv, text="ну такое")
        assert all(q["label"] != "Позвать менеджера" for q in message["quick"])
        message, _ = turn(client, conv, text="хм, не то")
        assert message["quick"][0] == {"label": "Позвать менеджера", "action": {"type": "handoff"}}, (
            "второй раз не понял — предлагает человека"
        )

        message, state = turn(client, conv, action={"type": "handoff", "label": "Позвать менеджера"})
        assert state["handoff"]["reason"] == "нажали «Позвать менеджера»"
        message, state = turn(client, conv, action={"type": "handoff_cancel", "label": "Вернуться к агенту"})
        assert state["handoff"]["status"] == "closed" and message["text"].startswith("Хорошо, продолжаем вдвоём")


class FakeTelegram:
    def __init__(self):
        self.sent: list[str] = []

    def send(self, chat_id, text, quick=None):
        self.sent.append(text)

    def call(self, method, **params):
        return {"ok": True}


def test_operator_reply_reaches_telegram_once():
    store.init_db()
    tg = FakeTelegram()
    bot.handle(tg, 5151, text="/start")
    bot.handle(tg, 5151, text="хочу поговорить с человеком")
    assert "Передаю менеджеру" in tg.sent[-1]
    with TestClient(app) as client:
        client.post("/api/operator/conversations/tg5151/reply", json={"text": "Я на связи!", "operator": "Олег"}, headers=OPERATOR)
    assert bot.send_operator_messages(tg) == 1 and tg.sent[-1] == "👤 Олег, менеджер:\nЯ на связи!"
    assert bot.send_operator_messages(tg) == 0, "каждый ответ приходит один раз"
