"""Печатает диалог с агентом по шагам — быстро посмотреть качество ответов без интерфейса.

    cd backend && python ../scripts/demo_dialogue.py "хочу к морю в ноябре с ребёнком" "1" "а если на два дня позже?"

Сообщение «1», «2» — выбор направления или варианта по номеру. Пишет во временную SQLite.
"""

import json
import os
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/demo.db")
os.environ.setdefault("TODAY", "2026-10-24")
sys.path.insert(0, os.getcwd())

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

HEADERS = {"X-User-Id": "demo-dialogue"}


def main(messages: list[str]) -> None:
    with TestClient(app) as client:
        state = client.post("/api/conversations", headers=HEADERS).json()
        print(state["messages"][0]["text"])
        for text in messages:
            body = {"text": text}
            if text.isdigit() and state.get("stage") == "inspire":
                body = {"action": {"type": "select_destination", "id": state["suggestions"]["items"][int(text) - 1]["id"]}}
            response = client.post(f"/api/conversations/{state['id']}/turn", json=body, headers=HEADERS)
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            message = next(e["message"] for e in events if e["type"] == "message")
            state = next(e["state"] for e in events if e["type"] == "state")
            print(f"\n>> {text}")
            for step in message.get("steps", []):
                print(f"   · {step['title']} — {step['detail']}")
            print(message["text"])
            print("   [кнопки]", [q["label"] for q in message.get("quick", [])])
        print("\nБРИФ:", [(c["label"], c["kind"]) for c in state["chips"]])


if __name__ == "__main__":
    main(
        sys.argv[1:]
        or [
            "хочу куда-нибудь к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов",
            "1",
            "а если на два дня позже?",
            "подешевле",
            "с нами едет собака",
        ]
    )
