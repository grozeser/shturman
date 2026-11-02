"""HTTP API Штурмана и раздача собранного фронтенда. Всё на одном порту (8080 в контейнере)."""

import json
import logging
import mimetypes
import os
import re
import secrets
import statistics
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import accounts, store
from app.agent import booking as bk
from app.agent import group, llm, operator, replies
from app.agent.core import add_message, finish_checkout, new_state, public_state, run_turn
from app.travel import catalog, forecast, hotel_view, inventory, planner
from app.travel.clock import today

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

STATIC_DIR = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
# В slim-образе нет /etc/mime.types: без этого фото направлений уходят как text/plain
mimetypes.add_type("image/webp", ".webp")
EVAL_REPORT = Path(__file__).resolve().parent / "data" / "eval_report.json"
USER_RE = re.compile(r"^[A-Za-z0-9_:-]{4,64}$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.init_db()
    accounts.seed_demo_users(today())
    log.info("Штурман запущен. LLM: %s", llm.status())
    yield


app = FastAPI(title="Штурман — AI-агент поездок", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")


def user_of(x_user_id: str | None) -> str:
    if not x_user_id or not USER_RE.match(x_user_id):
        raise HTTPException(400, "Нужен заголовок X-User-Id (4–64 символа: буквы, цифры, _ : -)")
    return x_user_id


def conversation_for(conv_id: str, user_id: str) -> dict:
    state = store.get_conversation(conv_id)
    if not state or state["user_id"] != user_id:
        raise HTTPException(404, "Диалог не найден")
    return state


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def status():
    return {"llm": llm.status(), "db": store.ping(), "data": "synthetic", "today": today().isoformat()}


@app.post("/api/conversations")
def create_conversation(x_user_id: str | None = Header(default=None)):
    user_id = user_of(x_user_id)
    state = new_state(uuid.uuid4().hex[:16], user_id, store.get_profile(user_id))
    store.save_conversation(state)
    return public_state(state)


@app.get("/api/conversations/{conv_id}")
def read_conversation(conv_id: str, x_user_id: str | None = Header(default=None)):
    return public_state(conversation_for(conv_id, user_of(x_user_id)))


@app.get("/api/conversations/{conv_id}/dates")
def date_calendar(conv_id: str, x_user_id: str | None = Header(default=None)):
    """Цена той же поездки при заезде на ±3 дня — считается по запросу, чтобы не замедлять каждый ход."""
    state = conversation_for(conv_id, user_of(x_user_id))
    plan = state.get("plan")
    if not plan or not plan.get("bundles"):
        return []
    return planner.date_options(state["brief"], plan, plan["bundles"][state["selected"]], today())


class TurnIn(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    action: dict | None = None


@app.post("/api/conversations/{conv_id}/turn")
def turn(conv_id: str, body: TurnIn, x_user_id: str | None = Header(default=None)):
    user_id = user_of(x_user_id)
    state = conversation_for(conv_id, user_id)
    text = (body.text or "").strip() or None
    if not text and not body.action:
        raise HTTPException(400, "Пустое сообщение")
    profile = store.get_profile(user_id)

    def events():
        try:
            for event in run_turn(state, text=text, action=body.action, today=today(), profile=profile):
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception:  # noqa: BLE001 — пользователь должен получить ответ, а не оборванный поток
            log.exception("Ошибка хода агента")
            message = add_message(
                state,
                "agent",
                "Что-то пошло не так на моей стороне. Попробуйте переформулировать — бриф и план сохранены. "
                "Или позову менеджера: он увидит всё, что мы уже обсудили.",
                kind="error",
                quick=[replies.HANDOFF_QUICK],
            )
            yield f"data: {json.dumps({'type': 'message', 'message': message}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'state', 'state': public_state(state)}, ensure_ascii=False, default=str)}\n\n"
        finally:
            store.save_events(state.pop("events_out", []))
            store.save_conversation(state)
            store.save_profile(user_id, profile)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class CheckoutIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120, pattern=EMAIL)
    insurance: bool | None = None  # галочка в корзине; None — как решили в чате («со страховкой»)


@app.post("/api/conversations/{conv_id}/checkout")
def checkout(conv_id: str, body: CheckoutIn, x_user_id: str | None = Header(default=None)):
    user_id = user_of(x_user_id)
    state = conversation_for(conv_id, user_id)
    if not state.get("plan") or not state["plan"].get("bundles"):
        raise HTTPException(409, "Сначала соберите поездку")
    profile = store.get_profile(user_id)
    if body.insurance is not None:
        state.setdefault("checkout_options", {})["insurance"] = body.insurance
    booking = finish_checkout(state, {"name": body.name.strip(), "email": body.email.strip()}, profile)
    store.save_booking(booking)
    store.save_events(state.pop("events_out", []))
    store.save_profile(user_id, profile)
    store.save_conversation(state)
    return {"booking": booking, "state": public_state(state)}


class PassportIn(BaseModel):
    until: date


@app.post("/api/conversations/{conv_id}/passport")
def check_passport(conv_id: str, body: PassportIn, x_user_id: str | None = Header(default=None)):
    """Поле «загранпаспорт действует до» в корзине: проверка по правилам страны, дата запоминается."""
    user_id = user_of(x_user_id)
    state = conversation_for(conv_id, user_id)
    if not state.get("plan") or not state["plan"].get("bundles"):
        raise HTTPException(409, "Сначала соберите поездку")
    state["passport_until"] = body.until.isoformat()
    profile = store.get_profile(user_id)
    profile.setdefault("facts", {})["passport_until"] = {
        "value": body.until.isoformat(),
        "label": f"загранпаспорт действует до {bk.full_date(body.until)}",
    }
    store.save_profile(user_id, profile)
    store.save_conversation(state)
    return bk.passport_check(state["plan"]["bundles"][state["selected"]], body.until)


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120, pattern=EMAIL)
    password: str = Field(min_length=6, max_length=100)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=100)


@app.get("/api/accounts/demo")
def demo_accounts():
    return accounts.demo_list()


@app.get("/api/accounts/me")
def me(x_user_id: str | None = Header(default=None)):
    account = store.get_account(user_of(x_user_id))
    return accounts.public(account) if account else None


@app.post("/api/accounts/register")
def register(body: RegisterIn, x_user_id: str | None = Header(default=None)):
    user_id = user_of(x_user_id)
    email = body.email.strip().lower()
    if store.get_account(user_id):
        raise HTTPException(409, "Вы уже вошли в аккаунт — выйдите, чтобы создать новый")
    if store.get_account_by_email(email):
        raise HTTPException(409, "Аккаунт с такой почтой уже есть — войдите")
    store.create_account(user_id, email, body.name.strip(), accounts.hash_password(body.password))
    return accounts.public(store.get_account(user_id))


@app.post("/api/accounts/login")
def login(body: LoginIn):
    account = store.get_account_by_email(body.email.strip().lower())
    if not account or not accounts.check_password(body.password, account["password"]):
        raise HTTPException(401, "Неверная почта или пароль")
    return accounts.public(account)


# ── Поездка компанией: ссылка для попутчиков и голосование ─────────────────

MAX_VOTES = 50  # на одну ссылку: защита от накрутки и мусора — компания столько не наберёт


@app.post("/api/conversations/{conv_id}/share")
def share_trip(conv_id: str, x_user_id: str | None = Header(default=None)):
    user_id = user_of(x_user_id)
    state = conversation_for(conv_id, user_id)
    if not state.get("plan") or not state["plan"].get("bundles"):
        raise HTTPException(409, "Сначала соберите поездку")
    token = secrets.token_urlsafe(9)
    store.create_share(token, conv_id, user_id, group.snapshot(state))
    return {"token": token}


@app.get("/api/conversations/{conv_id}/share")
def shared_for_owner(conv_id: str, x_user_id: str | None = Header(default=None)):
    """Последняя ссылка этого диалога с голосами — для карточки организатора."""
    conversation_for(conv_id, user_of(x_user_id))
    share = store.latest_share(conv_id)
    if not share:
        return None
    return {"token": share["token"], **share["data"], **group.summary(share["data"], store.votes(share["token"]), None)}


@app.get("/api/shared/{token}")
def shared_trip(token: str, x_user_id: str | None = Header(default=None)):
    share = store.get_share(token)
    if not share:
        raise HTTPException(404, "Ссылка не найдена или устарела")
    viewer = x_user_id if x_user_id and USER_RE.match(x_user_id) else None
    return {"token": token, **share["data"], **group.summary(share["data"], store.votes(token), viewer)}


class VoteIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    choice: int = Field(ge=0, le=9)


@app.post("/api/shared/{token}/vote")
def vote(token: str, body: VoteIn, x_user_id: str | None = Header(default=None)):
    voter = user_of(x_user_id)
    share = store.get_share(token)
    if not share:
        raise HTTPException(404, "Ссылка не найдена или устарела")
    name = " ".join(body.name.split())
    if not name or body.choice >= len(share["data"]["options"]):
        raise HTTPException(400, "Нужно имя и один из вариантов")
    existing = store.votes(token)
    if len(existing) >= MAX_VOTES and not any(v["voter_id"] == voter and v["name"] == name for v in existing):
        raise HTTPException(429, "Голосов по этой ссылке уже слишком много")
    store.save_vote(token, voter, name, body.choice)
    return {"token": token, **share["data"], **group.summary(share["data"], store.votes(token), voter)}


# ── Консоль оператора: агент закрывает основной поток, людям — сложное и уже с контекстом ──


def operator_of(x_operator_key: str | None) -> None:
    # демо-ключ по умолчанию открыт в README; на настоящем стенде задайте свой OPERATOR_KEY
    if not x_operator_key or not secrets.compare_digest(x_operator_key, os.getenv("OPERATOR_KEY") or "operator-demo"):
        raise HTTPException(403, "Нужен ключ оператора (заголовок X-Operator-Key)")


@app.get("/api/operator/queue")
def operator_queue(x_operator_key: str | None = Header(default=None)):
    """Ждут ответа — сверху, по времени ожидания; ниже — те, с кем менеджер уже говорит."""
    operator_of(x_operator_key)
    rows = [operator.queue_row(state) for state in store.handoffs() if state["handoff"]["status"] in ("waiting", "active")]
    return sorted(rows, key=lambda r: (r["status"] != "waiting", r["since"]))


@app.get("/api/operator/conversations/{conv_id}")
def operator_conversation(conv_id: str, x_operator_key: str | None = Header(default=None)):
    operator_of(x_operator_key)
    state = store.get_conversation(conv_id)
    if not state:
        raise HTTPException(404, "Диалог не найден")
    return public_state(state)


class OperatorReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    operator: str = Field(default="Менеджер", min_length=1, max_length=40)


@app.post("/api/operator/conversations/{conv_id}/reply")
def operator_answer(conv_id: str, body: OperatorReplyIn, x_operator_key: str | None = Header(default=None)):
    operator_of(x_operator_key)
    state = store.get_conversation(conv_id)
    if not state:
        raise HTTPException(404, "Диалог не найден")
    operator.operator_reply(state, body.text.strip(), " ".join(body.operator.split()))
    store.save_conversation(state)
    return public_state(state)


class OperatorCloseIn(BaseModel):
    operator: str = Field(default="Менеджер", min_length=1, max_length=40)


@app.post("/api/operator/conversations/{conv_id}/close")
def operator_close(conv_id: str, body: OperatorCloseIn, x_operator_key: str | None = Header(default=None)):
    operator_of(x_operator_key)
    state = store.get_conversation(conv_id)
    if not state or not state.get("handoff"):
        raise HTTPException(404, "Обращение не найдено")
    operator.close_handoff(state, " ".join(body.operator.split()))
    store.save_conversation(state)
    return public_state(state)


@app.get("/api/bookings")
def bookings(x_user_id: str | None = Header(default=None)):
    return store.list_bookings(user_of(x_user_id))


def booking_for(booking_id: str, user_id: str) -> dict:
    booking = store.get_booking(booking_id)
    if not booking or booking["user_id"] != user_id:
        raise HTTPException(404, "Бронь не найдена")
    return booking


def booking_view(booking: dict) -> dict:
    """Памятка и прогноз считаются при чтении: они есть и у старых броней, а прогноз всегда свежий."""
    weather = forecast.for_bundle(booking["bundle"]) if booking["status"] == "confirmed" else None
    return booking | {"checklist": forecast.pack(bk.checklist(booking), weather), "forecast": weather}


@app.get("/api/bookings/{booking_id}")
def read_booking(booking_id: str, x_user_id: str | None = Header(default=None)):
    return booking_view(booking_for(booking_id, user_of(x_user_id)))


@app.get("/api/bookings/{booking_id}/calendar.ics")
def booking_calendar(booking_id: str, x_user_id: str | None = Header(default=None)):
    booking = booking_for(booking_id, user_of(x_user_id))
    return Response(
        bk.ics(booking),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="trip-{booking_id.encode("ascii", "ignore").decode().strip("-")}.ics"'},
    )


class BookingActionIn(BaseModel):
    post: dict


@app.post("/api/bookings/{booking_id}/actions")
def booking_action(booking_id: str, body: BookingActionIn, x_user_id: str | None = Header(default=None)):
    booking = booking_for(booking_id, user_of(x_user_id))
    text, quick = bk.booking_action(booking, body.post, today())
    store.save_booking(booking)
    return {"booking": booking_view(booking), "text": text, "quick": quick}


@app.get("/api/profile")
def profile(x_user_id: str | None = Header(default=None)):
    return store.get_profile(user_of(x_user_id))


@app.delete("/api/profile/facts/{key}")
def forget_fact(key: str, x_user_id: str | None = Header(default=None)):
    user_id = user_of(x_user_id)
    data = store.get_profile(user_id)
    (data.get("facts") or {}).pop(key, None)
    store.save_profile(user_id, data)
    return data


@app.delete("/api/profile")
def forget_all(x_user_id: str | None = Header(default=None)):
    user_id = user_of(x_user_id)
    store.save_profile(user_id, {})
    return {}


@app.get("/api/destinations")
def destinations_list():
    return sorted(
        ({"id": d["id"], "name": d["name"], "country": d["country"]} for d in catalog.destinations().values() if not d.get("dynamic")),
        key=lambda d: d["name"],
    )


@app.get("/api/hotels")
def hotels_for(dest: str):
    if dest not in catalog.destinations():
        raise HTTPException(404, "Направление не найдено")
    return hotel_view.hotels_overview(dest, store.hotel_stats(dest_prefix=dest))


@app.get("/api/hotels/{hotel_id}")
def hotel_card(hotel_id: str):
    dest = hotel_id.rsplit("-", 1)[0]
    if dest not in catalog.destinations() or not any(h["id"] == hotel_id for h in inventory.hotels(dest)):
        raise HTTPException(404, "Отель не найден")
    stats = store.hotel_stats(hotel_id=hotel_id).get(
        hotel_id, {"recommended": 0, "rejected": 0, "booked": 0, "segments": {}, "reasons": {}}
    )
    return hotel_view.hotel_report(hotel_id, stats)


@app.get("/api/metrics")
def metrics():
    rows = store.conversation_metrics()
    active = [r for r in rows if r.get("turns")]
    recommended = [r for r in active if r.get("first_rec_turn")]
    live = {
        "conversations": len(active),
        "reached_recommendation": len(recommended),
        "booked": sum(1 for r in active if r.get("booked")),
        "avg_clarifications": round(statistics.mean(r.get("clarifications", 0) for r in active), 2) if active else 0,
        "median_turns_to_first_rec": statistics.median(r["first_rec_turn"] for r in recommended) if recommended else None,
        "replans": sum(r.get("replans", 0) for r in active),
        "llm_calls": sum(r.get("llm_calls", 0) for r in active),
        "llm_fallbacks": sum(r.get("llm_fallbacks", 0) for r in active),
        "number_violations_blocked": sum(r.get("number_violations", 0) for r in active),
        # сколько обращений агент передал людям: остальные закрыл сам
        "handoffs": sum(1 for r in active if r.get("handoff")),
        "handoff_share": round(sum(1 for r in active if r.get("handoff")) / len(active), 3) if active else None,
    }
    report = json.loads(EVAL_REPORT.read_text(encoding="utf-8")) if EVAL_REPORT.exists() else None
    return {"live": live, "business": business(active), "eval": report}


def business(active: list[dict]) -> dict:
    """Метрики для бизнеса: воронка от запроса до брони, средний чек и допродажи."""
    bookings = [b for b in store.all_bookings() if b["status"] == "confirmed"]
    funnel = [
        {"step": "Написали запрос", "count": len(active)},
        {"step": "Получили рекомендацию", "count": sum(1 for r in active if r.get("first_rec_turn"))},
        # бронь подразумевает пройденные шаги — так воронка не ломается на диалогах, начатых до появления отметок
        {"step": "Собрали поездку", "count": sum(1 for r in active if r.get("planned") or r.get("checkout") or r.get("booked"))},
        {"step": "Дошли до корзины", "count": sum(1 for r in active if r.get("checkout") or r.get("booked"))},
        {"step": "Оформили", "count": sum(1 for r in active if r.get("booked"))},
    ]
    checks = [b["payment"]["amount"] for b in bookings]
    saved = [b["savings"] for b in bookings if b.get("savings")]  # у броней до появления итога его нет

    def upsold(b: dict) -> bool:  # к брони добавили что-то сверх отеля и дороги
        bundle = b["bundle"]
        return bool(
            b["services"]
            or bundle["extras"]
            or bundle["transfer_in"]["kind"] == "private"
            or bundle["hotel"]["meal"] in ("HB", "AI")
            or b.get("insurance")
        )

    return {
        "funnel": funnel,
        "bookings": len(bookings),
        "avg_check": round(statistics.mean(checks)) if checks else None,
        "gmv": sum(checks),
        "package_share": round(sum(1 for b in bookings if b["bundle"]["costs"]["transport"] > 0) / len(bookings), 3) if bookings else None,
        "upsell_share": round(sum(1 for b in bookings if upsold(b)) / len(bookings), 3) if bookings else None,
        "insurance_share": round(sum(1 for b in bookings if b.get("insurance")) / len(bookings), 3) if bookings else None,
        "post_purchase_actions": sum(len(b["services"]) for b in bookings),
        "avg_minutes_saved": round(statistics.mean(s["minutes"] for s in saved)) if saved else None,
        "avg_clicks_saved": round(statistics.mean(s["clicks"] for s in saved)) if saved else None,
        "avg_messages": round(statistics.mean(s["messages"] + s["taps"] for s in saved), 1) if saved else None,
    }


# Без Cache-Control браузер сам решает, сколько держать страницу, и после обновления может часами
# показывать старую сборку. index.html и файлы без хеша — no-cache (каждый раз сверка по ETag),
# assets/ с хешем в имени — на год: новая сборка даёт новые имена.
NO_CACHE = {"Cache-Control": "no-cache"}


class CachedStaticFiles(StaticFiles):
    def __init__(self, *args, cache_control: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache_control = cache_control

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = self.cache_control
        return response


if STATIC_DIR.exists():
    app.mount(
        "/assets", CachedStaticFiles(directory=STATIC_DIR / "assets", cache_control="public, max-age=31536000, immutable"), name="assets"
    )
    if (STATIC_DIR / "photos").is_dir():  # фото без хеша в имени: сверка по ETag, повтор — 304 без тела
        app.mount("/photos", CachedStaticFiles(directory=STATIC_DIR / "photos", cache_control="no-cache"), name="photos")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        file = STATIC_DIR / path
        if path and file.is_file() and STATIC_DIR.resolve() in file.resolve().parents:
            return FileResponse(file, headers=NO_CACHE)
        return FileResponse(STATIC_DIR / "index.html", headers=NO_CACHE)
