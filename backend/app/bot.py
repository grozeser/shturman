"""Telegram-бот на том же ядре агента: те же бриф, планировщик, проверки, оформление и действия после покупки.

TELEGRAM_BOT_TOKEN=... python -m app.bot      # long polling, вебхук не нужен
"""

import logging
import os
import re
import time
from datetime import date, datetime

import httpx

from app import store
from app.agent.core import finish_checkout, new_state, run_turn
from app.travel import forecast
from app.travel.brief import money
from app.travel.clock import today
from app.travel.planner import day_label, time_of

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")
# httpx на INFO пишет полный адрес запроса, а в адресе Bot API — токен: любой, кто видит логи, получил бы управление ботом
logging.getLogger("httpx").setLevel(logging.WARNING)
EMAIL = re.compile(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+")


class Telegram:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.http = httpx.Client(timeout=40)

    def call(self, method: str, **params) -> dict:
        response = self.http.post(f"{self.base}/{method}", json=params)
        data = response.json()
        if not data.get("ok"):
            log.warning("Telegram %s: %s", method, data.get("description"))
        return data

    def send(self, chat_id: int, text: str, quick: list[dict] | None = None) -> None:
        markup = None
        if quick:
            markup = {"inline_keyboard": [[{"text": q["label"][:60], "callback_data": f"q:{i}"}] for i, q in enumerate(quick[:6])]}
        for start in range(0, len(text), 4000):  # лимит Telegram — 4096 символов
            last = start + 4000 >= len(text)
            # без кнопок поле не передаём вовсе: на reply_markup: null Telegram отвечает 400 и сообщение не доходит
            extra = {"reply_markup": markup} if markup and last else {}
            self.call("sendMessage", chat_id=chat_id, text=text[start : start + 4000], **extra)


def plan_summary(state: dict) -> str:
    plan = state.get("plan")
    if state["stage"] not in ("plan", "checkout") or not plan or not plan.get("bundles"):
        return ""
    lines = ["", "Варианты:"]
    for index, b in enumerate(plan["bundles"], start=1):
        mark = "→ " if index - 1 == state["selected"] else ""
        lines.append(
            f"{mark}{index}. {b['label']} — {money(b['total'])}: {b['hotel']['name']} {b['hotel']['stars']}★, {b['hotel']['meal_label']}"
        )
    b = plan["bundles"][state["selected"]]
    out = b["outbound"]
    lines.append(
        f"План: {day_label_iso(b['checkin'])} — {out['number']} в {time_of(out['depart'])}, прибытие {time_of(out['arrive'])}, "
        f"{b['transfer_in']['title'].lower()}, заселение {b['hotel']['checkin']}."
    )
    warns = [c["title"] for c in b["checks"] if c["status"] in ("warn", "error")]
    if warns:
        lines.append("Внимание: " + "; ".join(warns))
    return "\n".join(lines)


def day_label_iso(stamp: str) -> str:
    return day_label(date.fromisoformat(stamp))


def handle(tg: Telegram, chat_id: int, text: str | None = None, quick_index: int | None = None) -> None:
    user_id = f"tg-{chat_id}"
    conv_id = f"tg{chat_id}"[:32]
    profile = store.get_profile(user_id)
    state = store.get_conversation(conv_id)
    if text == "/remind":
        sent = send_due(tg, chat_id=chat_id, force_next=True)
        if not sent:
            tg.send(chat_id, "Ближайших напоминаний нет: сначала оформите поездку здесь, в боте.")
        return
    if text in ("/start", "/new") or state is None:
        state = new_state(conv_id, user_id, profile)
        store.save_conversation(state)
        if text in ("/start", "/new"):
            tg.send(chat_id, state["messages"][-1]["text"])
            return

    if state["stage"] == "checkout" and text and EMAIL.search(text):
        email = EMAIL.search(text).group(0)
        name = text.replace(email, "").strip(" ,;") or "Путешественник"
        booking = finish_checkout(state, {"name": name[:80], "email": email}, profile)
        store.save_booking(booking)
        store.save_events(state.pop("events_out", []))
        store.save_profile(user_id, profile)
        store.save_conversation(state)
        message = state["messages"][-1]
        upcoming = "\n".join(f"• {r['at'][8:10]}.{r['at'][5:7]} {r['at'][11:16]} — {r['text']}" for r in booking["reminders"][:4])
        reminder_note = f"\n\nНапомню сюда, в Telegram:\n{upcoming}\n(команда /remind пришлёт ближайшее сейчас)" if upcoming else ""
        tg.send(chat_id, message["text"] + reminder_note, message.get("quick"))
        log.info("Оформлена бронь %s, напоминаний %s", booking["id"], len(booking["reminders"]))
        return

    body: dict = {"text": text}
    if quick_index is not None:
        last = next((m for m in reversed(state["messages"]) if m["role"] == "agent"), None)
        quick = (last or {}).get("quick") or []
        if quick_index >= len(quick):
            return
        chosen = quick[quick_index]
        body = (
            {"action": chosen["action"] | {"label": chosen["label"]}}
            if chosen.get("action")
            else {"text": chosen.get("text") or chosen["label"]}
        )
    tg.call("sendChatAction", chat_id=chat_id, action="typing")
    message = None
    for event in run_turn(state, today=today(), profile=profile, **body):
        if event["type"] == "message":
            message = event["message"]
    store.save_events(state.pop("events_out", []))
    store.save_conversation(state)
    store.save_profile(user_id, profile)
    if not message:
        return
    steps = message.get("steps") or []
    trace = ("Что я сделал: " + " → ".join(s["title"] for s in steps[:6]) + "\n\n") if len(steps) > 1 else ""
    reply = trace + message["text"] + plan_summary(state)
    if state["stage"] == "checkout":
        reply += "\n\nНапишите имя и почту одним сообщением, например: «Анна, anna@example.com» — оплата имитируется."
    tg.send(chat_id, reply, message.get("quick"))
    # ход без текста переписки: в логах не должно быть того, что человек написал боту
    log.info(
        "Ход: %s → стадия %s, шагов агента %s",
        "кнопка" if quick_index is not None else f"текст {len(text or '')} симв.",
        state["stage"],
        len(steps),
    )


def send_due(tg: Telegram, now: datetime | None = None, chat_id: int | None = None, force_next: bool = False) -> int:
    """Присылает наступившие напоминания по броням из бота. force_next — ближайшее сразу (для демо, команда /remind)."""
    now = now or datetime.now()
    sent = 0
    for booking in store.all_bookings():
        if booking["status"] != "confirmed" or not booking["user_id"].startswith("tg-"):
            continue
        chat = int(booking["user_id"][3:])
        if chat_id is not None and chat != chat_id:
            continue
        pending = [r for r in booking["reminders"] if not r.get("sent")]
        due = [r for r in pending if datetime.fromisoformat(r["at"]) <= now] or (pending[:1] if force_next else [])
        for reminder in due:
            when = datetime.fromisoformat(reminder["at"]).strftime("%d.%m %H:%M")
            text = forecast.reminder_text(booking) if reminder.get("kind") == "forecast" else reminder["text"]
            tg.send(chat, f"⏰ {text}\nБронь {booking['id']}, {booking['bundle']['dest_name']} · по плану {when}")
            reminder["sent"] = True
            sent += 1
        if due:
            store.save_booking(booking)
    return sent


def send_operator_messages(tg: Telegram) -> int:
    """Ответы менеджера (и сообщение «я снова на связи») из консоли оператора — в чат Telegram, каждое один раз."""
    sent = 0
    for state in store.handoffs():
        if not state["user_id"].startswith("tg-"):
            continue
        fresh = [m for m in state["messages"] if m.get("push") and not m.get("pushed")]
        for message in fresh:
            text = f"👤 {message['author']}, менеджер:\n{message['text']}" if message["role"] == "operator" else message["text"]
            tg.send(int(state["user_id"][3:]), text, message.get("quick"))
            message["pushed"] = True
            sent += 1
        if fresh:
            store.save_conversation(state)
    return sent


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        log.error("TELEGRAM_BOT_TOKEN не задан — бот не запущен. Добавьте токен в .env и перезапустите профиль telegram.")
        while True:  # не перезапускаемся в цикле restart: unless-stopped
            time.sleep(3600)
    store.init_db()
    tg = Telegram(token)
    tg.call(
        "setMyCommands",
        commands=[
            {"command": "new", "description": "Новая поездка"},
            {"command": "remind", "description": "Прислать ближайшее напоминание"},
        ],
    )
    offset = 0
    last_check = 0.0
    log.info("Бот запущен")
    while True:
        if time.time() - last_check > 60:  # раз в минуту — наступившие напоминания по броням
            last_check = time.time()
            try:
                send_due(tg)
            except Exception:  # noqa: BLE001 — сбой рассылки не должен останавливать диалоги
                log.exception("Ошибка рассылки напоминаний")
        try:  # ответы менеджеров — каждый круг, а не раз в минуту: человек ждёт
            send_operator_messages(tg)
        except Exception:  # noqa: BLE001
            log.exception("Ошибка доставки ответов менеджера")
        try:
            data = tg.call("getUpdates", offset=offset, timeout=30, allowed_updates=["message", "callback_query"])
        except httpx.HTTPError as error:
            log.warning("Нет связи с Telegram: %s", error.__class__.__name__)
            time.sleep(5)
            continue
        for update in data.get("result", []):
            offset = update["update_id"] + 1
            try:
                if "message" in update and update["message"].get("text"):
                    handle(tg, update["message"]["chat"]["id"], text=update["message"]["text"][:2000])
                elif "callback_query" in update:
                    query = update["callback_query"]
                    tg.call("answerCallbackQuery", callback_query_id=query["id"])
                    match = re.fullmatch(r"q:(\d)", query.get("data", ""))
                    if match:
                        handle(tg, query["message"]["chat"]["id"], quick_index=int(match.group(1)))
            except Exception:  # noqa: BLE001 — один сбойный апдейт не должен ронять бота
                log.exception("Ошибка обработки апдейта")


if __name__ == "__main__":
    main()
