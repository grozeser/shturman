"""Страховка одной галочкой и проверка загранпаспорта: «Египет требует 6 месяцев после выезда, ваш истекает раньше — не пустят»."""

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

TODAY = date(2026, 10, 24)
HEADERS = {"X-User-Id": "test-user-insurance"}


def test_passport_date_from_words():
    assert bk.passport_date("мой загранпаспорт действует до 10.03.2027", TODAY) == date(2027, 3, 10)
    assert bk.passport_date("паспорт до 7 мая 2027 года", TODAY) == date(2027, 5, 7)
    assert bk.passport_date("загранпаспорт до марта 2027", TODAY) == date(2027, 3, 1), "без дня — первое число, так строже"
    assert bk.passport_date("нужен ли загранпаспорт в Турцию?", TODAY) is None
    assert bk.passport_date("Сочи с 10.03.2027 по 17.03.2027", TODAY) is None, "даты поездки без слова «паспорт» — не паспорт"


def test_rules_by_country():
    trip = {"checkin": "2026-11-10", "checkout": "2026-11-17", "nights": 7}
    egypt = bk.passport_need(trip | {"dest_info": {"country": "Египет"}})
    assert egypt["required"] == "2027-05-17" and egypt["rule"] == "Египет требует 6 месяцев после выезда"
    turkey = bk.passport_need(trip | {"dest_info": {"country": "Турция"}})
    assert turkey["required"] == "2027-04-09" and "150 дней с даты въезда" in turkey["rule"]
    assert bk.passport_need(trip | {"dest_info": {"country": "Абхазия"}}) is None, "по внутреннему паспорту"
    unknown = bk.passport_need(trip | {"dest_info": {"country": "Норвегия"}})
    assert "беру строгое" in unknown["rule"]


def turn(client: TestClient, conv: str, **body) -> tuple[dict, dict]:
    response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=HEADERS)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return next(e["message"] for e in events if e["type"] == "message"), next(e["state"] for e in events if e["type"] == "state")


def test_checkout_with_policy_and_passport_check():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        turn(client, conv, text="Хургада в мае вдвоём")
        message, state = turn(client, conv, text="оформляй")
        documents = state["documents"]
        assert documents["insurance"]["price"] > 0 and documents["insurance"]["people"] == 2
        assert "Страховка на всех" in message["text"]
        assert "До какого числа действует ваш загранпаспорт? Проверю: Египет требует 6 месяцев после выезда" in message["text"]

        message, state = turn(client, conv, text="мой загранпаспорт действует до 10.03.2027")
        assert "не пустят" in message["text"] and "Египет требует 6 месяцев после выезда" in message["text"]
        assert any(s["tool"] == "check_passport" for s in message["steps"])
        assert state["stage"] == "checkout" and state["brief"]["date_from"] is None, "дата паспорта — не даты поездки"
        assert state["documents"]["passport_check"]["ok"] is False

        message, state = turn(client, conv, text="давай со страховкой")
        assert message["text"].startswith("Добавил страховку") and state["checkout_options"]["insurance"]

        bundle = state["plan"]["bundles"][state["selected"]]
        result = client.post(
            f"/api/conversations/{conv}/checkout", json={"name": "Анна", "email": "anna@example.com"}, headers=HEADERS
        ).json()
        booking = result["booking"]
        assert booking["insurance"]["number"].startswith("ПС-")
        assert booking["payment"]["amount"] == bundle["total"] + booking["insurance"]["price"]
        assert booking["passport"]["ok"] is False
        docs = next(g for g in bk.checklist(booking) if g["title"] == "Документы")["items"]
        assert any(i["text"] == "Загранпаспорт" and i["why"].startswith("Египет требует 6 месяцев после выезда") for i in docs)
        assert any(i["why"].startswith("оформлена: полис ПС-") for i in docs)

        business = client.get("/api/metrics").json()["business"]
        assert business["insurance_share"] > 0

        profile = client.get("/api/profile", headers=HEADERS).json()
        assert profile["facts"]["passport_until"]["value"] == "2027-03-10", "срок паспорта помнится"


def test_passport_remembered_and_checked_in_cart():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        turn(client, conv, text="Анталья в мае вдвоём")
        message, state = turn(client, conv, text="оформляй")
        assert "Турция требует 150 дней с даты въезда" in message["text"], "дату паспорта агент взял из памяти и сразу проверил"
        ok = client.post(f"/api/conversations/{conv}/passport", json={"until": "2028-01-01"}, headers=HEADERS).json()
        assert ok["ok"] is True and ok["text"].startswith("Паспорт подходит")


def test_domestic_trip_needs_no_passport():
    headers = {"X-User-Id": "test-user-insurance-2"}
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=headers).json()["id"]
        client.post(f"/api/conversations/{conv}/turn", json={"text": "Сочи в мае вдвоём"}, headers=headers)
        response = client.post(f"/api/conversations/{conv}/turn", json={"text": "оформляй"}, headers=headers)
        state = next(json.loads(line[6:])["state"] for line in response.text.splitlines() if '"type": "state"' in line)
        assert state["documents"]["passport"] is None
        assert state["documents"]["insurance"]["title"].startswith("Страховка в поездке по России")
        result = client.post(
            f"/api/conversations/{conv}/checkout", json={"name": "Иван", "email": "ivan@example.com", "insurance": False}, headers=headers
        ).json()
        assert "insurance" not in result["booking"]
