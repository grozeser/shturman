"""Бот на фейковом Telegram: тот же путь, что в вебе, — от запроса до оформления."""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/bot.db"
os.environ["TODAY"] = "2026-10-24"

from app import bot, store  # noqa: E402


class FakeTelegram:
    def __init__(self):
        self.sent: list[tuple[str, list | None]] = []

    def send(self, chat_id, text, quick=None):
        self.sent.append((text, quick))

    def call(self, method, **params):
        return {"ok": True}


def test_bot_journey():
    store.init_db()
    tg = FakeTelegram()
    bot.handle(tg, 42, text="/start")
    assert "Штурман" in tg.sent[-1][0]
    bot.handle(tg, 42, text="Сочи с 10 по 17 ноября вдвоём, бюджет 80 тысяч")
    text, quick = tg.sent[-1]
    assert "Варианты:" in text and quick
    checkout = next(i for i, q in enumerate(quick) if q["label"] == "Оформить")
    bot.handle(tg, 42, quick_index=checkout)
    assert "почту" in tg.sent[-1][0]
    bot.handle(tg, 42, text="Анна, anna@example.com")
    assert "номер брони" in tg.sent[-1][0]
    assert store.list_bookings("tg-42")


def test_bot_reminders():
    from datetime import datetime

    store.init_db()
    tg = FakeTelegram()
    bot.handle(tg, 77, text="/start")
    bot.handle(tg, 77, text="Сочи с 10 по 17 ноября вдвоём")
    checkout = next(i for i, q in enumerate(tg.sent[-1][1]) if q["label"] == "Оформить")
    bot.handle(tg, 77, quick_index=checkout)
    bot.handle(tg, 77, text="Анна, anna@example.com")
    assert "Напомню сюда" in tg.sent[-1][0]

    before = len(tg.sent)
    bot.handle(tg, 77, text="/remind")  # демо: ближайшее напоминание сразу
    assert len(tg.sent) == before + 1 and tg.sent[-1][0].startswith("⏰")

    sent = bot.send_due(tg, now=datetime(2100, 1, 1))  # наступили все остальные
    assert sent >= 2
    assert bot.send_due(tg, now=datetime(2100, 1, 1)) == 0, "каждое напоминание приходит один раз"


def test_bot_token_never_reaches_logs(caplog):
    """httpx на INFO пишет адрес запроса, а в адресе Bot API — токен; бот обязан это глушить."""
    import logging

    import app.bot  # noqa: F401 — настройка логгеров происходит при импорте

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_send_never_passes_null_reply_markup():
    """Найдено на живом боте: reply_markup: null → «Bad Request: object expected as reply markup», ответ не доходил."""
    from app.bot import Telegram

    sent = []
    tg = Telegram("123:test")
    tg.call = lambda method, **params: sent.append(params) or {"ok": True}
    tg.send(1, "Привет")  # без кнопок, как ответ на /start
    tg.send(1, "x" * 9000, [{"label": "Оформить"}])  # длинный ответ: кнопки только у последней части
    assert "reply_markup" not in sent[0]
    assert [("reply_markup" in p) for p in sent[1:]] == [False, False, True]
    assert all(p.get("reply_markup") is not None for p in sent if "reply_markup" in p)
