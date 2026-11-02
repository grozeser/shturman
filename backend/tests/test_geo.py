"""Направления вне базы: геокодинг и климат подменены фикстурами — тест не ходит в сеть."""

import os
import tempfile
from datetime import date

os.environ["GEO_CACHE"] = f"{tempfile.mkdtemp()}/geo.json"

from app.agent.core import new_state, run_turn
from app.travel import catalog, geo


def fake_get(url: str, params: dict) -> dict:
    if "geocoding" in url:
        if params["name"] != "Прага":  # падежная форма «Прагу» геокодеру неизвестна — проверяем перебор вариантов
            return {}
        return {
            "results": [
                {"id": 3067696, "name": "Прага", "country": "Чехия", "country_code": "CZ", "feature_code": "PPLC", "population": 1165581,
                 "latitude": 50.088, "longitude": 14.421, "elevation": 202},
            ]
        }  # fmt: skip
    if "archive" in url:
        days = [f"2019-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]
        return {
            "utc_offset_seconds": 3600,
            "daily": {"time": days, "temperature_2m_max": [int(t[5:7]) * 2 for t in days], "precipitation_sum": [0.0] * len(days)},
        }
    return {"daily": {"time": [], "sea_surface_temperature_mean": []}}  # у Праги моря нет


def test_variants_and_preposition():
    assert "Прага" in geo.name_variants("Прагу")
    assert geo.prepositional("Прага") == "Праге" and geo.prepositional("Осло") == "Осло" and geo.prepositional("Лондон") == "Лондоне"
    assert geo.hint_for("хочу в норвегию на фьорды") == "Берген"
    for text in ("романтические выходные", "свидание в городе", "скорее бы отпуск"):  # страна не внутри слова
        assert geo.hint_for(text) is None, text


def test_unknown_city_becomes_a_trip(monkeypatch):
    monkeypatch.setattr(geo, "_get", fake_get)
    state = new_state("geo-test", "geo-user", {})
    for _ in run_turn(state, text="в Прагу на выходные в декабре вдвоём", today=date(2026, 10, 25), profile={}):
        pass
    assert state["stage"] == "plan", state["messages"][-1]["text"]
    dest = catalog.destination(state["plan"]["dest"])
    assert dest["dynamic"] and dest["name"] == "Прага" and "шенген" in dest["visa"] and dest["sea"] is None
    assert "смоделировал" in state["messages"][-1]["text"]
    bundle = state["plan"]["bundles"][0]
    assert bundle["outbound"]["stops"] == 1 and bundle["inbound"]["stops"] == 1, "в Европу без прямых рейсов — туда и обратно с пересадкой"
    assert any(step["tool"] == "geocode" for step in state["messages"][-1]["steps"])


def test_offline_falls_back_to_similar(monkeypatch):
    def offline(url, params):
        raise OSError("нет сети")

    monkeypatch.setattr(geo, "_get", offline)
    state = new_state("geo-offline", "geo-user", {})
    for _ in run_turn(state, text="хочу в Улан-Удэ в июле вдвоём", today=date(2026, 10, 25), profile={}):
        pass
    assert state["stage"] == "inspire" and state["suggestions"]["items"]
