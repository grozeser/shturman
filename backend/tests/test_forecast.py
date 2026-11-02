"""Настоящий прогноз Open-Meteo для поездок в ближайшие 16 дней: в плане, в ответе на «какая погода», в боте за 3 дня."""

import json
import os
import tempfile
from datetime import date, datetime, timedelta

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bot, store  # noqa: E402
from app.agent import booking as bk  # noqa: E402
from app.main import app  # noqa: E402
from app.travel import forecast  # noqa: E402

HEADERS = {"X-User-Id": "test-user-forecast"}
# во вторник 3 ноября ливень, дальше сухо — как в ТЗ: «во вторник ливень — экскурсию лучше на среду»
WEATHER = {
    "2026-11-03": (31, 22, 18.0, 81),
    "2026-11-04": (29, 21, 0.0, 1),
    "2026-11-05": (28, 20, 0.4, 2),
    "2026-11-06": (27, 20, 0.0, 0),
    "2026-11-07": (28, 21, 0.0, 1),
    "2026-11-08": (29, 21, 0.0, 0),
}


@pytest.fixture
def online(monkeypatch):
    """Open-Meteo «отвечает» заготовкой, а «сегодня» для прогноза — 1 ноября: поездка 3–8 ноября в горизонте 16 дней."""
    calls = []

    def fake_get(params: dict) -> dict:
        calls.append(params)
        start, end = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
        days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
        pick = lambda i: [WEATHER.get(d, (25, 18, 0.0, 0))[i] for d in days]  # noqa: E731
        return {
            "daily": {
                "time": days,
                "temperature_2m_max": pick(0),
                "temperature_2m_min": pick(1),
                "precipitation_sum": pick(2),
                "precipitation_probability_max": [90 if r else 10 for r in pick(2)],
                "weather_code": pick(3),
            }
        }

    monkeypatch.delenv("FORECAST_OFFLINE", raising=False)
    monkeypatch.delenv("GEO_OFFLINE", raising=False)
    monkeypatch.setattr(forecast, "_get", fake_get)
    monkeypatch.setattr(forecast, "real_today", lambda: date(2026, 11, 1))
    forecast._cache.clear()
    return calls


def test_window_follows_real_calendar():
    now = date(2026, 11, 1)
    assert forecast.window(date(2026, 11, 3), date(2026, 11, 8), now) == (date(2026, 11, 3), date(2026, 11, 8))
    assert forecast.window(date(2026, 11, 10), date(2026, 11, 24), now) == (date(2026, 11, 10), date(2026, 11, 16)), "часть поездки"
    assert forecast.window(date(2026, 12, 1), date(2026, 12, 8), now) is None, "дальше 16 дней — только норма"
    assert forecast.fetch(36.9, 30.7, date.today(), date.today()) is None, "в тестах сеть выключена"


def test_summary_gives_advice_like_a_person():
    days = [
        {"date": d, "tmax": t, "tmin": n, "rain_mm": r, "rain_prob": 50, "code": c, "sky": "", "rainy": r >= 5}
        for d, (t, n, r, c) in WEATHER.items()
    ]
    result = forecast.summary(days, date(2026, 11, 3), date(2026, 11, 8), "в Анталье")
    assert result["line"] == "В Анталье обещают днём +27°…+31°, во вторник 3 ноября ливень — экскурсию лучше на среду"
    assert result["rainy"] == ["2026-11-03"] and (result["covered"], result["total"]) == (6, 6)


def turn(client: TestClient, conv: str, **body) -> tuple[dict, dict]:
    response = client.post(f"/api/conversations/{conv}/turn", json=body, headers=HEADERS)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    return next(e["message"] for e in events if e["type"] == "message"), next(e["state"] for e in events if e["type"] == "state")


def test_plan_shows_real_forecast_instead_of_norm(online):
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=HEADERS).json()["id"]
        message, state = turn(client, conv, text="Анталья с 3 по 8 ноября вдвоём")
        assert state["plan"]["forecast"]["line"].endswith("экскурсию лучше на среду")
        assert any(s["tool"] == "weather_forecast" and "6 дней из 6" in s["detail"] for s in message["steps"])
        assert "во вторник 3 ноября ливень" in message["text"]
        assert len(online) == 1

        message, _ = turn(client, conv, text="а какая там погода?")
        assert "настоящий прогноз Open-Meteo" in message["text"] and "+31°" in message["text"]
        assert len(online) == 1, "повторный вопрос — из кэша, без нового запроса"

        turn(client, conv, text="оформляй")
        booking = client.post(
            f"/api/conversations/{conv}/checkout", json={"name": "Анна", "email": "anna@example.com"}, headers=HEADERS
        ).json()["booking"]
        view = client.get(f"/api/bookings/{booking['id']}", headers=HEADERS).json()
        assert view["forecast"]["rainy"] == ["2026-11-03"]
        clothes = next(g for g in view["checklist"] if g["title"] == "Одежда по погоде")
        assert any(item["text"] == "Зонт или дождевик" and "3 ноября" in item["why"] for item in clothes["items"])


def test_bot_sends_fresh_forecast_three_days_before(online, monkeypatch):
    class FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 24, 12, 0)

    # прошедшие напоминания отбрасываются по настоящим часам — фиксируем «сейчас» до поездки 3–8 ноября
    monkeypatch.setattr(bk, "datetime", FrozenNow)

    class FakeTelegram:
        def __init__(self):
            self.sent: list[str] = []

        def send(self, chat_id, text, quick=None):
            self.sent.append(text)

        def call(self, method, **params):
            return {"ok": True}

    store.init_db()
    tg = FakeTelegram()
    bot.handle(tg, 4242, text="/start")
    bot.handle(tg, 4242, text="Анталья с 3 по 8 ноября вдвоём")
    bot.handle(tg, 4242, text="оформляй")
    bot.handle(tg, 4242, text="Анна, anna@example.com")
    booking = store.list_bookings("tg-4242")[0]
    reminder = next(r for r in booking["reminders"] if r.get("kind") == "forecast")
    depart = datetime.fromisoformat(booking["bundle"]["outbound"]["depart"])
    assert datetime.fromisoformat(reminder["at"]) == depart - timedelta(days=3)

    bot.send_due(tg, now=datetime.fromisoformat(reminder["at"]))
    forecast_messages = [t for t in tg.sent if "обещают" in t]
    assert (
        forecast_messages
        and "В Анталье обещают днём +27°…+31°, во вторник 3 ноября ливень — экскурсию лучше на среду" in forecast_messages[0]
    )
