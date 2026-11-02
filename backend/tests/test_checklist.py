"""Памятка «что взять с собой» и файл .ics для календаря — через API, в режиме без LLM."""

import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_checklist_and_calendar_file():
    from app.agent.booking import _ics_text

    assert _ics_text("Стамбул, Турция; бронь\nкод") == r"Стамбул\, Турция\; бронь\nкод"
    headers = {"X-User-Id": "test-user-checklist"}
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=headers).json()["id"]
        for text in ("Анталья в мае с ребёнком 2 года и собакой", "оформляй"):
            client.post(f"/api/conversations/{conv}/turn", json={"text": text}, headers=headers)
        booking = client.post(
            f"/api/conversations/{conv}/checkout", json={"name": "Иван", "email": "ivan@example.com"}, headers=headers
        ).json()["booking"]
        groups = client.get(f"/api/bookings/{booking['id']}", headers=headers).json()["checklist"]
        items = {item["text"] for group in groups for item in group["items"]}
        assert {"Загранпаспорт", "Свидетельство о рождении ребёнка", "Ветеринарный паспорт с прививками"} <= items
        assert any(text.startswith("Купальник") for text in items) and any(text.startswith("Подгузники") for text in items)
        assert all(item["why"] for group in groups for item in group["items"] if not item["text"].startswith("Паспорт РФ"))

        response = client.get(f"/api/bookings/{booking['id']}/calendar.ics", headers=headers)
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/calendar")
        assert response.text.startswith("BEGIN:VCALENDAR\r\n") and response.text.rstrip().endswith("END:VCALENDAR")
        assert response.text.count("BEGIN:VEVENT") == 3  # туда, проживание, обратно
        assert response.text.count("BEGIN:VALARM") == len(booking["reminders"])
        assert client.get(f"/api/bookings/{booking['id']}/calendar.ics", headers={"X-User-Id": "someone-else"}).status_code == 404
