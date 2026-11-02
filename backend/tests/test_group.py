"""Поездка компанией: ссылка со снимком вариантов, голоса попутчиков, лидер и доля каждого."""

import json
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

OWNER = {"X-User-Id": "test-group-owner"}


def test_group_vote_flow():
    with TestClient(app) as client:
        conv = client.post("/api/conversations", headers=OWNER).json()["id"]
        assert client.post(f"/api/conversations/{conv}/share", headers=OWNER).status_code == 409  # плана ещё нет
        response = client.post(f"/api/conversations/{conv}/turn", json={"text": "Анталья в мае вчетвером"}, headers=OWNER)
        state = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")][-1]["state"]
        token = client.post(f"/api/conversations/{conv}/share", headers=OWNER).json()["token"]

        shared = client.get(f"/api/shared/{token}").json()
        assert shared["people"] == 4 and len(shared["options"]) == len(state["plan"]["bundles"])
        assert shared["options"][0]["per_person"] * 4 >= shared["options"][0]["total"] * 0.95
        assert "messages" not in shared and "brief" not in shared, "попутчикам — только варианты, без чата организатора"

        friend = {"X-User-Id": "test-group-friend"}
        client.post(f"/api/shared/{token}/vote", json={"name": "Оля", "choice": 1}, headers=friend)
        client.post(f"/api/shared/{token}/vote", json={"name": "Петя", "choice": 1}, headers=friend)  # двое в одном браузере
        after = client.post(f"/api/shared/{token}/vote", json={"name": "Оля", "choice": 0}, headers=friend).json()  # передумала
        assert after["counts"][:2] == [1, 1] and after["leader"] is None, "ничья — лидера нет"
        assert {v["name"] for v in after["mine"]} == {"Оля", "Петя"}

        client.post(f"/api/shared/{token}/vote", json={"name": "Иван", "choice": 1}, headers=OWNER)
        owner_view = client.get(f"/api/conversations/{conv}/share", headers=OWNER).json()
        assert owner_view["token"] == token and owner_view["leader"] == 1 and sum(owner_view["counts"]) == 3

        assert client.post(f"/api/shared/{token}/vote", json={"name": "Оля", "choice": 7}, headers=friend).status_code == 400
        assert client.post(f"/api/shared/{token}/vote", json={"name": "Оля", "choice": 0}).status_code == 400  # без X-User-Id
        assert client.get("/api/shared/nope").status_code == 404
        assert client.get(f"/api/conversations/{conv}/share", headers=friend).status_code == 404  # чужой диалог
