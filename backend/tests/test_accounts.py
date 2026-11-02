"""Аккаунты: тестовые пользователи с поездками, вход по паролю, регистрация с переносом поездок браузера."""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/accounts.db"
os.environ["TODAY"] = "2026-10-24"
os.environ.pop("LLM_BASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import accounts  # noqa: E402
from app.main import app  # noqa: E402


def test_demo_users_have_trips():
    with TestClient(app) as client:
        demo = client.get("/api/accounts/demo").json()
        assert [d["email"] for d in demo] == [u["email"] for u in accounts.DEMO_USERS]
        for user in demo:
            assert len(user["trips"]) >= 3
            bookings = client.get("/api/bookings", headers={"X-User-Id": user["user_id"]}).json()
            assert len(bookings) == len(user["trips"])
            memory = client.get("/api/profile", headers={"X-User-Id": user["user_id"]}).json()
            assert memory.get("facts"), "агент запомнил предпочтения после покупок"


def test_login_with_demo_password():
    with TestClient(app) as client:
        account = client.post("/api/accounts/login", json={"email": "Anna@demo.shturman ", "password": "demo123"}).json()
        assert account == {"user_id": "demo-anna", "name": "Анна Смирнова", "email": "anna@demo.shturman", "demo": True}
        assert client.get("/api/accounts/me", headers={"X-User-Id": "demo-anna"}).json()["name"] == "Анна Смирнова"
        assert client.post("/api/accounts/login", json={"email": "anna@demo.shturman", "password": "wrong"}).status_code == 401
        assert client.post("/api/accounts/login", json={"email": "nobody@demo.shturman", "password": "demo123"}).status_code == 401


def test_register_keeps_browser_trips():
    browser = {"X-User-Id": "u-browser-before-signup"}
    with TestClient(app) as client:
        assert client.get("/api/accounts/me", headers=browser).json() is None
        body = {"name": "Пётр", "email": "petr@example.com", "password": "secret1"}
        account = client.post("/api/accounts/register", json=body, headers=browser).json()
        assert account["user_id"] == "u-browser-before-signup" and not account["demo"]
        assert client.post("/api/accounts/login", json={"email": "petr@example.com", "password": "secret1"}).json() == account

        again = client.post("/api/accounts/register", json=body | {"email": "other@example.com"}, headers=browser)
        assert again.status_code == 409
        taken = client.post("/api/accounts/register", json=body, headers={"X-User-Id": "u-another-browser"})
        assert taken.status_code == 409
        short = client.post("/api/accounts/register", json=body | {"password": "123"}, headers={"X-User-Id": "u-third"})
        assert short.status_code == 422


def test_password_is_hashed():
    stored = accounts.hash_password("demo123")
    assert "demo123" not in stored and accounts.check_password("demo123", stored)
    assert not accounts.check_password("demo124", stored)
