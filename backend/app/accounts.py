"""Аккаунты для демо: регистрация и вход по почте и паролю, тестовые пользователи с готовыми поездками.

Аккаунт — это имя, почта и пароль поверх user_id. Вход возвращает user_id, браузер подставляет его в X-User-Id,
и дальше всё работает как раньше: поездки, память, диалоги. При регистрации аккаунт привязывается к текущему
user_id браузера, поэтому уже оформленные поездки и память переезжают в аккаунт.

Тестовые пользователи создаются на старте: их поездки собирает тот же агент (на правилах, без LLM), как живой
пользователь в чате. Пароли тестовых пользователей показаны на экране входа — это демо.
"""

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import date

from app import store
from app.agent import booking as bk
from app.agent import llm
from app.agent.core import finish_checkout, new_state, run_turn

log = logging.getLogger("accounts")

DEMO_USERS = [
    {
        "user_id": "demo-anna",
        "name": "Анна Смирнова",
        "email": "anna@demo.shturman",
        "password": "demo123",
        "about": "Семья с ребёнком: тёплое море, всё включено, без ночных рейсов",
        "trips": [
            {"text": "Хочу к тёплому морю в ноябре, недорого, с ребёнком 5 лет, без долгих перелётов"},
            {"text": "Анталья в июле на неделю, всё включено, двое взрослых и ребёнок 6 лет", "after": [{"type": "early_checkin"}]},
            {"text": "Сочи на майские с ребёнком 6 лет, вдвоём с мужем"},
        ],
    },
    {
        "user_id": "demo-ilya",
        "name": "Илья Петров",
        "email": "ilya@demo.shturman",
        "password": "demo123",
        "about": "Горнолыжник: компания друзей, склоны и сноуборд",
        "trips": [
            {"text": "Красная Поляна на новый год, компанией из 4 человек"},
            {"text": "Шерегеш в феврале на неделю, вдвоём, покататься на сноуборде"},
            {"text": "Гудаури в марте вдвоём на лыжах", "after": [{"type": "cancel"}, {"type": "confirm"}]},
        ],
    },
    {
        "user_id": "demo-marina",
        "name": "Марина Ковалёва",
        "email": "marina@demo.shturman",
        "password": "demo123",
        "about": "Пара: города, гастрономия, романтические выходные",
        "trips": [
            {"text": "Стамбул в апреле вдвоём на 5 ночей"},
            {"text": "Тбилиси в мае вдвоём на неделю, хорошая еда и вино", "after": [{"type": "late_checkout"}]},
            {"text": "Санкт-Петербург на выходные в декабре вдвоём, на поезде"},
            {"text": "Ереван в июне вдвоём на 5 ночей"},
        ],
    },
]


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    salt, _, digest = stored.partition("$")
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(candidate.hex(), digest)


def public(account: dict) -> dict:
    return {key: account[key] for key in ("user_id", "name", "email", "demo")}


def demo_list() -> list[dict]:
    """Тестовые пользователи для экрана входа: с паролем и поездками, чтобы войти в один клик."""
    result = []
    for user in DEMO_USERS:
        if not store.get_account(user["user_id"]):
            continue
        trips = store.list_bookings(user["user_id"])
        result.append(
            {
                "user_id": user["user_id"],
                "name": user["name"],
                "email": user["email"],
                "password": user["password"],
                "about": user["about"],
                "trips": [b["bundle"]["dest_name"] for b in trips],
            }
        )
    return result


def _book(user: dict, trip: dict, profile: dict, today: date) -> dict | None:
    """Проводит запрос через агента до оплаты (имитация), как живой пользователь: запрос → направление → оформление."""
    state = new_state(f"demo-{uuid.uuid4().hex[:12]}", user["user_id"], profile)

    def turn(**body) -> None:
        for _ in run_turn(state, today=today, profile=profile, **body):
            pass

    turn(text=trip["text"])
    for _ in range(2):
        if state["stage"] in ("inspire", "plan"):
            break
        turn(text=trip.get("answer", "вдвоём"))
    if state["stage"] == "inspire" and state["suggestions"]["items"]:
        turn(action={"type": "select_destination", "id": state["suggestions"]["items"][0]["id"]})
    if state["stage"] != "plan" or not state["plan"].get("bundles"):
        log.warning("Тестовая поездка не собралась (%s): %s", state["stage"], trip["text"])
        return None
    booking = finish_checkout(state, {"name": user["name"], "email": user["email"]}, profile)
    for post in trip.get("after", []):
        bk.booking_action(booking, post, today)
    store.save_booking(booking)
    store.save_events(state.pop("events_out", []))
    store.save_conversation(state)
    return booking


def seed_demo_users(today: date) -> None:
    """Создаёт тестовых пользователей с поездками, если их ещё нет. Ошибка засева не мешает запуску сервиса."""
    with llm.rules_only():
        for user in DEMO_USERS:
            if store.get_account(user["user_id"]):
                continue
            try:
                profile = store.get_profile(user["user_id"])
                booked = [b for trip in user["trips"] if (b := _book(user, trip, profile, today))]
                store.save_profile(user["user_id"], profile)
                store.create_account(user["user_id"], user["email"], user["name"], hash_password(user["password"]), demo=True)
                log.info("Тестовый пользователь %s: %s поездки", user["email"], len(booked))
            except Exception:  # noqa: BLE001 — демо-данные не должны ронять старт
                log.exception("Не удалось создать тестового пользователя %s", user["email"])
