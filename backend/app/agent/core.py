"""Оркестратор агента: решает, когда спросить, когда предложить направления, когда собрать поездку и когда пересобрать.

Политика:
- уточняем максимум один раз и только блокирующее: «когда» (и «кто», если тоже неизвестно) — одним сообщением с кнопками;
- всё остальное допускаем сами и показываем допущения в карточке «Я понял так»;
- направление известно — сразу собираем поездку; неизвестно — предлагаем 3–4 с объяснением;
- изменение условий при готовом плане — пересборка от текущего плана с diff, а не поиск с нуля.
"""

import copy
import re
import time
import uuid
from collections.abc import Iterator
from datetime import date, timedelta

from app.agent import booking as bk
from app.agent import llm, replies, savings
from app.agent.interpret import interpret, looks_like_place
from app.travel import catalog, forecast, geo, hotel_view, planner
from app.travel.brief import apply_patch, chips, derive, knows_when, knows_who, new_brief, new_sources, remove_chip
from app.travel.catalog import MONTHS, MONTHS_IN, destination
from app.travel.compare import build_comparison, comparison_quick, comparison_text


def new_state(conv_id: str, user_id: str, profile: dict) -> dict:
    brief, sources = new_brief(), new_sources()
    used = bk.apply_memory(brief, sources, profile)
    state = {
        "id": conv_id,
        "user_id": user_id,
        "brief": brief,
        "sources": sources,
        "stage": "start",
        "asked": [],
        "suggestions": None,
        "plan": None,
        "selected": 0,
        "diff": None,
        "booking_id": None,
        "memory_used": used,
        "messages": [],
        "metrics": {
            "started": None,
            "first_rec_s": None,
            "first_rec_turn": None,
            "clarifications": 0,
            "turns": 0,
            "replans": 0,
            "llm_calls": 0,
            "llm_fallbacks": 0,
            "number_violations": 0,
            "booked": False,
        },
    }
    add_message(state, "agent", replies.greeting(profile), kind="greeting")
    return state


def add_message(state: dict, role: str, text: str, **extra) -> dict:
    message = {"id": uuid.uuid4().hex[:10], "role": role, "text": text, "ts": time.time()} | extra
    state["messages"].append(message)
    return message


def public_state(state: dict) -> dict:
    view = copy.copy(state)
    if state["stage"] == "checkout" and state.get("plan"):  # корзина: полис одной галочкой и проверка паспорта
        view["documents"] = bk.documents(state["plan"]["bundles"][state["selected"]], state["brief"], state.get("passport_until"))
    view["chips"] = chips(state["brief"], state["sources"])
    view["llm"] = llm.status()
    view["savings"] = savings.summary(state) if state["stage"] in ("checkout", "booked") else None
    return view


class Turn:
    """Один ход агента: шаги (видны пользователю как «след агента»), текст ответа и быстрые ответы."""

    def __init__(self, state: dict, today: date, profile: dict):
        self.state, self.today, self.profile = state, today, profile
        self.steps: list[dict] = []
        self.text = ""
        self.quick: list[dict] = []
        self.kind = "info"
        self.started = time.perf_counter()
        self.narrate = True

    def step(self, tool: str, title: str, detail: str = "") -> dict:
        item = {"tool": tool, "title": title, "detail": detail, "ms": round((time.perf_counter() - self.started) * 1000)}
        self.steps.append(item)
        return {"type": "step", "step": item}

    def say(self, text: str, kind: str = "info", quick: list[dict] | None = None, narrate: bool = True) -> None:
        self.text, self.kind, self.quick, self.narrate = text, kind, quick or [], narrate

    def recommended(self) -> None:
        m = self.state["metrics"]
        if m["first_rec_s"] is None and m["started"]:
            m["first_rec_s"] = round(time.time() - m["started"], 2)
            m["first_rec_turn"] = m["turns"]


def run_turn(
    state: dict, *, text: str | None = None, action: dict | None = None, today: date | None = None, profile: dict | None = None
) -> Iterator[dict]:
    """Генератор событий для SSE: step / thinking / message / state."""
    today = today or date.today()
    profile = profile if profile is not None else {}
    for key, value in new_brief().items():  # диалог начат до появления поля — добавляем его с пустым значением
        state["brief"].setdefault(key, value)
    turn = Turn(state, today, profile)
    metrics = state["metrics"]
    if metrics["started"] is None:
        metrics["started"] = time.time()
    metrics["turns"] += 1
    if with_human(state) and (action or {}).get("type") != "handoff_cancel":
        # диалог у менеджера: агент молчит, сообщение ждёт ответа человека — иначе они говорили бы наперебой
        if text:
            add_message(state, "user", text)
            state["handoff"]["unread"] += 1
            state["handoff"]["updated"] = time.time()
        yield {"type": "state", "state": public_state(state)}
        return
    if text:
        add_message(state, "user", text)
        yield from handle_text(turn, text)
    elif action:
        label = action.get("label")
        if label:
            add_message(state, "user", label, action=True)
        yield from handle_action(turn, action)
    if turn.narrate and turn.text and llm.enabled():
        yield {"type": "thinking", "title": "Формулирую ответ"}
        turn.text = replies.narrate(turn.text, metrics)
    message = add_message(state, "agent", turn.text, kind=turn.kind, quick=turn.quick, steps=turn.steps)
    yield {"type": "message", "message": message}
    yield {"type": "state", "state": public_state(state)}


# ── Текст ───────────────────────────────────────────────────────────────────


def handle_text(turn: Turn, text: str) -> Iterator[dict]:
    state, today = turn.state, turn.today
    brief, sources = state["brief"], state["sources"]
    stage = state["stage"]
    # «паспорт до 10.03.2027» — проверка документа, а не новые даты поездки; «со страховкой» у корзины — галочка полиса
    until = bk.passport_date(text, today)
    if until:
        yield from check_passport(turn, until)
        return
    if stage == "checkout" and re.search(r"страхов", text.lower()):
        yield from set_insurance(turn, not re.search(r"(без|не\s+нужн\w*|убер\w*|не\s+надо)\W+(?:\w+\W+)?страхов", text.lower()))
        return
    if llm.enabled():
        yield {"type": "thinking", "title": "Разбираю запрос"}
    result = interpret(text, brief, stage, today)
    if result["source"] == "llm":
        state["metrics"]["llm_calls"] += 1
    if result.get("fallback"):
        state["metrics"]["llm_fallbacks"] += 1
    intent = result["intent"]
    patch = result["patch"]

    if intent == "reset":
        reset(state, turn.profile)
        turn.say(replies.greeting(turn.profile), "greeting", narrate=False)
        yield turn.step("reset", "Начал заново", "бриф очищен, память о вас сохранена")
        return
    if intent == "handoff":
        yield from start_handoff(turn, "попросили живого менеджера")
        return
    if intent == "chat" and result.get("chat") == "about":
        turn.say(replies.ABOUT, "info", replies.EXAMPLES_QUICK, narrate=False)
        return
    if intent == "chat" and not patch:
        quick = replies.plan_quick(state["plan"]) if state["stage"] == "plan" and state["plan"] else []
        follow = {
            "plan": "Когда будете готовы — оформлю, а если что-то поменять, просто скажите.",
            "inspire": "Выберите направление — соберу поездку целиком.",
            "compare": "Выберите поездку из сравнения — соберу её целиком.",
            "booked": "Я рядом: ранний заезд, перенос дат, трансфер — пишите.",
        }.get(state["stage"], "Расскажите, куда и когда хочется поехать.")
        low = text.lower()
        if re.search(r"(спасибо|благодар|спс)", low):
            head = "Пожалуйста! "
        elif re.search(r"(привет|здравств|добр\w* (день|вечер|утро))", low):
            head = "Здравствуйте! "
        else:  # «расскажи анекдот» — модель сочла это болтовнёй; «Здравствуйте!» посреди разговора звучит странно
            head = "Я помогаю только с поездками. "
            if state["stage"] == "start":
                follow, quick = replies.ABOUT, replies.EXAMPLES_QUICK
        turn.say(head + follow, "info", quick, narrate=False)
        return
    chosen = compared_choice(state, result)
    if chosen:  # «беру Хургаду», «давай второй» после сравнения — собираем выбранную поездку целиком
        yield from choose_destination(turn, chosen)
        return
    if result.get("remember"):
        bk.remember_note(turn.profile, result["remember"])
        yield turn.step("remember_preference", "Запомнил на будущее", result["remember"][:80])

    if intent == "post":
        if state["booking_id"]:
            yield from post_purchase(turn, result["post"])
            return
        if result["post"] and result["post"]["type"] in ("early_checkin", "late_checkout") and state["plan"]:
            yield from apply_fix(turn, {"type": result["post"]["type"]})
            return
        intent = "plan"
    if intent == "book":
        if state["plan"] and state["plan"].get("bundles"):
            if result.get("select") and result["select"] <= len(state["plan"]["bundles"]):
                state["selected"] = result["select"] - 1
            yield from start_checkout(turn)
            cart_documents(turn)
        else:
            turn.say("Сначала соберём поездку — расскажите, куда и когда хотите.", "info")
        return
    meaningful = {k: v for k, v in patch.items() if k not in ("kinds",) or v}
    if intent == "question" and not meaningful:
        topic = result.get("question") if result.get("question") in QUESTION_TOPICS else "other"
        month = result.get("question_month")
        if topic == "other" and llm.enabled():
            yield {"type": "thinking", "title": "Ищу ответ в данных поездки"}
        answer = replies.answer_question(topic, brief, state["plan"], text, month, state["metrics"])
        yield turn.step("answer_question", "Ответил по данным поездки" if topic == "other" else "Ответил по справочнику", topic)
        quick = replies.plan_quick(state["plan"]) if state["plan"] and state["stage"] == "plan" else []
        if month and month != (brief["month"] or 0) and state["plan"]:
            quick = [{"label": f"Пересобрать на {MONTHS[month - 1]}", "text": f"давай в {MONTHS_IN[month - 1]}"}] + quick[:3]
        turn.say(answer, "answer", quick, narrate=False)
        return
    if result.get("select") and not meaningful and not result.get("shift_days") and not result.get("budget_change"):
        yield from select(turn, result["select"])
        return

    unknown = result.get("unknown_destination") or (None if "destination" in patch or patch.get("regions") else looks_like_place(text))
    changed = apply_patch(brief, sources, patch, "explicit")
    for key, reason in (result.get("inferred_reasons") or {}).items():
        if key in sources and key in changed:
            sources[key] = {"kind": "inferred", "reason": reason}
    if result.get("romantic_pair") and sources.get("adults", {}).get("kind") == "default":
        sources["adults"] = {"kind": "inferred", "reason": "романтическая поездка — считаю, что вас двое"}
    if result.get("ages_guessed") and "children" in changed:
        sources["children"] = {"kind": "default", "reason": "возраст не назван — считаю 6 лет, поправьте"}
    if result.get("family_guess") and "children" in changed:
        sources["children"] = {"kind": "default", "reason": "«семьёй» — предположил одного ребёнка, поправьте"}
    if result.get("like_last"):
        yield from like_last_time(turn, patch, changed)
        unknown = None if brief["destination"] else unknown
    reason_bits = []
    if result.get("shift_days"):
        base = (
            date.fromisoformat(brief["date_from"])
            if brief["date_from"]
            else (date.fromisoformat(state["plan"]["checkin"]) if state["plan"] and state["plan"].get("checkin") else None)
        )
        if base:
            shifted = base + timedelta(days=result["shift_days"])
            if shifted > today:
                brief["date_from"], brief["month"] = shifted.isoformat(), shifted.month
                sources["date_from"] = {"kind": "explicit", "reason": f"сдвиг на {result['shift_days']:+d} дн."}
                changed.append("date_from")
                reason_bits.append(
                    f"даты {'позже' if result['shift_days'] > 0 else 'раньше'} на {abs(result['shift_days'])} {replies.plural(abs(result['shift_days']), 'день', 'дня', 'дней')}"
                )
    if result.get("budget_change") == "down" and state["plan"] and state["plan"].get("bundles"):
        current = state["plan"]["bundles"][state["selected"]]["total"]
        floor = min(b["total"] for b in state["plan"]["bundles"])
        # цель на 15% дешевле, но не ниже самого дешёвого варианта на эти даты — иначе обещание невыполнимо
        target = int(max(current * 0.85, floor) // 1000 * 1000 + (1000 if floor > current * 0.85 else 0))
        if not brief["budget"] or brief["budget"] > target:
            brief["budget"] = target
            sources["budget"] = {"kind": "inferred", "reason": "«подешевле» — цель на 15% дешевле текущего плана"}
            changed.append("budget")
            reason_bits.append(f"цель — до {replies.money(target)}")
    if result.get("budget_change") == "up":
        brief["priorities"] = brief["priorities"] | {"comfort": 0.9, "price": 0.2}
        sources["priorities"] = {"kind": "explicit", "reason": "«получше»"}
        changed.append("priorities")
    # маршрут распознаём до шага «Обновил бриф», иначе в нём мелькнёт «Каппадокия, 3 ночи» вместо маршрута
    stops = geo.find_route(text)
    if stops:
        ids, given = [], []
        for stop in stops:
            dest = catalog.destination(stop["id"]) if "id" in stop else geo.resolve(stop["name"])
            if dest and dest["id"] not in ids:
                ids.append(dest["id"])
                given.append(stop["nights"])
        if len(ids) >= 2:
            brief["route"], brief["route_nights"], brief["destination"] = ids, given, ids[0]
            sources["destination"] = {"kind": "explicit", "reason": ""}
            brief["nights"] = sum(given) if all(given) else max(brief["nights"], 2 * len(ids))
            sources["nights"] = {
                "kind": "explicit" if all(given) else "default",
                "reason": "" if all(given) else "делю ночи между городами поровну",
            }
            changed.append("route")
            unknown = None
            names = [catalog.destination(i)["name"] for i in ids]
            split = ", ".join(f"{name} — {n} ноч." for name, n in zip(names, given, strict=True) if n) or "поровну"
            yield turn.step("plan_route", f"Маршрут из {len(ids)} мест: {' → '.join(names)}", f"ночи по городам: {split}")
    elif "destination" in patch and brief["route"]:
        brief["route"], brief["route_nights"] = [], []  # назвали одно новое место — маршрут больше не нужен
    inferred = derive(brief, sources, changed)
    if changed:
        keys = {CHIP_OF.get(k, k) for k in changed}
        labels = [c["label"] for c in chips(brief, sources) if c["key"].split(":")[0] in keys or c["key"] in keys]
        yield turn.step("update_brief", "Обновил бриф «Я понял так»", ", ".join(labels[:8]) or describe_change(changed))
    if inferred:
        yield turn.step("infer_requirements", "Вывел скрытые требования", "; ".join(item["reason"] for item in inferred[:4]))
    to_compare = result.get("compare") or picked_suggestions(state, result.get("compare_picks"))
    if not to_compare and state.get("compare_pending") and knows_when(brief):
        to_compare = state.pop("compare_pending")  # ответили, когда едут, — возвращаемся к сравнению
    if to_compare:
        yield from compare_destinations(turn, to_compare)
        return
    if not reason_bits:
        reason_bits = [describe_change(changed)]
    nothing = (
        not changed and not result.get("shift_days") and not result.get("budget_change") and not unknown and not result.get("like_last")
    )
    if nothing and state["stage"] in ("plan", "inspire") and result["source"] == "rules":
        hint = "даты («на 2 дня позже»), бюджет («подешевле»), состав («с нами едет собака»), отель («поближе к морю»)"
        quick = replies.plan_quick(state["plan"]) if state["stage"] == "plan" else replies.inspire_quick(state["suggestions"])
        state["metrics"]["misses"] = state["metrics"].get("misses", 0) + 1
        if state["metrics"]["misses"] >= 2:  # второй раз не понял — не мучаем человека, предлагаем живого менеджера
            quick = [replies.HANDOFF_QUICK] + quick[:3]
        turn.say(
            f"Не до конца понял, что поменять. Могу пересобрать по любому условию: {hint} — или выберите вариант на экране.", "info", quick
        )
        return
    if nothing and state["stage"] == "start" and not TRAVEL_HINT.search(text.lower()):
        # «расскажи анекдот», «asdfgh» — не анкета «когда и кто едет», а честное «я про поездки»
        turn.say("Я помогаю только с поездками. " + replies.ABOUT, "info", replies.EXAMPLES_QUICK, narrate=False)
        return
    if unknown and not brief["destination"]:
        yield {"type": "thinking", "title": f"Ищу «{unknown}» на карте"}
        found = geo.resolve(unknown, text)
        if found:
            brief["destination"] = found["id"]
            reason = "нет в базе — нашёл на карте, отели и рейсы смоделировал" if found.get("dynamic") else ""
            sources["destination"] = {"kind": "explicit", "reason": reason}
            changed.append("destination")
            if found.get("dynamic"):
                c = found["climate"]
                sea = ", море рядом" if c["water"] else ""
                yield turn.step(
                    "geocode",
                    f"Нашёл на карте: {found['name']}, {found['country']}",
                    f"{found['lat']:.1f}°, {found['lon']:.1f}° · климат за 6 лет — Open-Meteo{sea} · виза: {found['visa']}",
                )
            unknown = None
        else:
            yield turn.step("search_catalog", f"Ищу «{unknown}» в базе", "не нашёл даже на карте — подберу похожие")
    yield from decide(turn, reason=", ".join(b for b in reason_bits if b), unknown=unknown, changed=changed)


def like_last_time(turn: Turn, patch: dict, changed: list[str]) -> Iterator[dict]:
    """«Как в прошлый раз, но в горы»: берём из последней поездки всё, что не назвали заново. Помечаем «из памяти»."""
    brief, sources = turn.state["brief"], turn.state["sources"]
    trips = turn.profile.get("trips") or []
    if not trips:
        yield turn.step("remember_preference", "Прошлых поездок пока не помню", "соберу с нуля и запомню эту")
        return
    last = trips[-1]
    memory = {"kind": "memory", "reason": f"как в прошлый раз ({last['dest']})"}
    taken, keep = [], []

    def take(key: str, value, label: str) -> None:
        brief[key], sources[key] = value, memory
        changed.append(key)
        taken.append(label)

    # «но в горы», «но к морю», «но в Стамбул» — меняют место; остальное берём из прошлой поездки
    new_place = "destination" in patch or bool(patch.get("kinds") or patch.get("regions") or patch.get("warm"))
    dest_id = last.get("dest_id") or (catalog.find_destination(last["dest"]) or {}).get("id")
    if new_place:
        keep.append("место — новое")
    elif dest_id and dest_id in catalog.destinations():
        take("destination", dest_id, last["dest"])
    if "nights" not in patch:
        take("nights", last["nights"], f"{last['nights']} {replies.plural(last['nights'], 'ночь', 'ночи', 'ночей')}")
    if "month" not in patch and "date_from" not in patch:
        month = int(last["checkin"][5:7])
        take("month", month, f"в {MONTHS_IN[month - 1]}")
    if last.get("meal") in ("HB", "AI") and "meal" not in patch and not new_place:  # «всё включено» в Стамбуле не бывает
        take("meal", last["meal"], "всё включено" if last["meal"] == "AI" else "полупансион")
    detail = "взял: " + ", ".join(taken) + (f"; {', '.join(keep)}" if keep else "") + "; состав и город вылета — из памяти"
    yield turn.step("remember_preference", "Как в прошлый раз", detail)


CHIP_OF = {
    "date_from": "dates",
    "month": "dates",
    "nights": "dates",
    "adults": "party",
    "children": "party",
    "kinds": "kind",
    "hotel_prefs": "pref",
    "exclude": "exclude",
    "route": "destination",
}


def describe_change(changed: list[str]) -> str:
    names = {
        "pets": "питомец",
        "children": "состав",
        "adults": "состав",
        "budget": "бюджет",
        "date_from": "даты",
        "month": "месяц",
        "nights": "длительность",
        "meal": "питание",
        "refundable": "отмена",
        "max_hours": "время в пути",
        "avoid_night": "ночные рейсы",
        "direct_only": "пересадки",
        "transport": "транспорт",
        "hotel_prefs": "пожелания к отелю",
        "origin": "город вылета",
        "priorities": "приоритеты",
        "min_stars": "звёздность",
        "kinds": "тип отдыха",
        "diet": "особое питание",
        "accessible": "доступная среда",
    }
    labels = sorted({names[c] for c in changed if c in names})
    return "учёл: " + ", ".join(labels) if labels else ""


def reset(state: dict, profile: dict) -> None:
    fresh = new_state(state["id"], state["user_id"], profile)
    keep = {"messages": state["messages"], "metrics": state["metrics"], "booking_id": state["booking_id"]}
    if "tally" in state:  # сообщения остаются — и сделанная агентом работа тоже, иначе итог «сэкономили» не сойдётся
        keep["tally"] = state["tally"]
    state.clear()
    state.update(fresh | keep)


# ── Решение о следующем шаге ────────────────────────────────────────────────


QUESTION_TOPICS = {"visa", "weather", "todo", "travel_time", "why", "other"}
# «отель получше» меняет приоритеты — значит, и отель должен смениться, а не остаться прежним
HOTEL_FIELDS = {
    "hotel_prefs",
    "min_stars",
    "meal",
    "pets",
    "children",
    "adults",
    "seniors",
    "kinds",
    "mood",
    "refundable",
    "priorities",
    "diet",
    "accessible",
}
TRAVEL_HINT = re.compile(
    r"(отдох|отпуск|поех|поезд|съезд|слета|лет[еа]т|путеш|\bтур|куда|отел|гостиниц|билет|мор|гор|каникул|выходн|уикенд|погулять|"
    r"посмотреть|виз|рейс|перел[её]т|пляж|курорт|страну|город)"
)


def decide(
    turn: Turn, reason: str = "", unknown: str | None = None, rerank: bool = False, prefix: str = "", changed: list[str] | None = None
) -> Iterator[dict]:
    state, today = turn.state, turn.today
    brief, sources = state["brief"], state["sources"]
    if brief["destination"]:
        previous = None
        plan_before = state["plan"]
        if (
            plan_before
            and plan_before.get("dest") == brief["destination"]
            and plan_before.get("bundles")
            and state["stage"] in ("plan", "checkout")
        ):
            previous = plan_before["bundles"][state["selected"]]
        multi = len(brief["route"]) >= 2
        if previous and bool(previous.get("legs")) != multi:
            previous = None  # маршрут и одиночную поездку между собой не сравниваем
        if multi:
            plan = planner.build_route(brief, brief["route"], today, brief["route_nights"])
        else:
            hotel_focus = bool(set(changed or []) & HOTEL_FIELDS)
            plan = planner.build_plan(brief, brief["destination"], today, None if rerank else previous, hotel_focus=hotel_focus)
        if "error" in plan and not multi and brief["meal"] and sources.get("meal", {}).get("kind") == "memory":
            # «всё включено» из прошлой поездки не должно отменять названный город: в Стамбуле его просто не бывает
            loc = catalog.destination(brief["destination"])["loc"]
            brief["meal"] = None
            sources["meal"] = {"kind": "default", "reason": f"питание из прошлой поездки {loc} не найти — подберу лучшее из доступного"}
            yield turn.step("update_brief", "Снял условие из памяти", f"питание из прошлой поездки {loc} не найти")
            plan = planner.build_plan(brief, brief["destination"], today, None if rerank else previous)
        for item in plan["trace"]:
            yield turn.step(item["tool"], item["title"], item["detail"])
        if "error" in plan:
            # не тупик: сразу подбираем направления, где эти условия выполнимы
            failed = brief["destination"]
            brief["destination"] = None
            brief["exclude"] = sorted(set(brief["exclude"] + [failed]))
            sources["exclude"] = {"kind": "inferred", "reason": "там не нашлось вариантов под условия"}
            yield turn.step("replan", "Ищу замену направлению", plan["error"])
            state["plan"] = None
            yield from decide(turn, prefix=plan["error"] + " Ищу, куда можно с этими условиями.\n")
            return
        state["plan"], state["selected"], state["stage"] = plan, 0, "plan"
        state["metrics"]["planned"] = True
        savings.track_plan(state, plan)
        log_hotel_events(state, plan)
        turn.recommended()
        weather = forecast.for_bundle(plan["bundles"][0])
        if weather:  # поездка в ближайшие 16 дней — показываем настоящий прогноз, а не многолетнюю норму
            plan["forecast"] = weather
            yield turn.step("weather_forecast", "Посмотрел настоящий прогноз погоды", weather["detail"])
        if previous:
            change = planner.diff(previous, plan["bundles"][0])
            state["diff"] = change
            state["metrics"]["replans"] += 1
            yield turn.step(
                "replan",
                "Пересобрал от текущего плана",
                f"сохранил: {', '.join(change['kept']).lower() or '—'}; изменилось: {', '.join(c['part'] for c in change['changes']).lower() or 'ничего'}",
            )
            turn.say(replies.replan_text(state, change, plan, reason or "новые условия"), "replan", replies.plan_quick(plan))
        else:
            state["diff"] = None
            turn.say(replies.plan_text(plan, brief), "plan", replies.plan_quick(plan))
        if weather:
            turn.text += f"\n{weather['line']} — это настоящий прогноз на ваши даты."
        return

    if not knows_when(brief):
        if "when" not in state["asked"]:
            ask_who = not knows_who(sources)
            state["asked"] += ["when"] + (["who"] if ask_who else [])
            state["metrics"]["clarifications"] += 1
            state["stage"] = "clarify"
            yield turn.step("clarify", "Решил уточнить", "без месяца не проверить погоду и цены — спрашиваю один раз")
            turn.say(
                replies.clarify(brief, sources, chips(brief, sources), ask_who), "clarify", replies.clarify_quick(today, ask_who, brief)
            )
            return
        month = (today + timedelta(days=30)).month
        brief["month"] = month
        sources["month"] = {"kind": "default", "reason": f"месяц не назван — беру {MONTHS_IN[month - 1]}"}
    sugg = planner.suggest_destinations(brief, today)
    savings.track_suggestions(state, sugg)
    criteria = [f"погода в {MONTHS_IN[sugg['month'] - 1]}", "время в пути", "визы", "цены на ваш состав"]
    yield turn.step(
        "search_destinations",
        f"Проверил {sugg['checked']} {replies.plural(sugg['checked'], 'направление', 'направления', 'направлений')}",
        f"по критериям: {', '.join(criteria)} → подходят {len(sugg['items']) + len(sugg['more'])}",
    )
    if not sugg["items"]:
        relax = []
        if brief["max_hours"]:
            relax.append({"label": "Можно лететь дольше", "action": {"type": "remove_chip", "key": "max_hours"}})
        if brief["warm"]:
            relax.append({"label": "Не обязательно жарко", "action": {"type": "remove_chip", "key": "warm"}})
        if brief["budget"]:
            relax.append({"label": "Бюджет можно больше", "action": {"type": "remove_chip", "key": "budget"}})
        relax.append({"label": "Другой месяц", "text": f"а если в {MONTHS_IN[sugg['month'] % 12]}?"})
        if brief["pets"]:
            relax.insert(0, {"label": "Поедем без питомца", "text": "собака не едет"})
        reasons = "; ".join(f"{r['name']} — {r['reason']}" for r in sugg["rejected"][:3])
        state["stage"] = "clarify"
        turn.say(
            prefix + f"Под все условия сразу ничего не подходит{': ' + reasons if reasons else ''}. Что можно ослабить?", "clarify", relax
        )
        return
    state["suggestions"], state["stage"] = sugg, "inspire"
    turn.recommended()
    text = prefix + replies.inspire(sugg, brief)
    if unknown:
        text = replies.unknown_destination(unknown) + "\n" + text
    turn.say(text, "inspire", replies.inspire_quick(sugg))


def select(turn: Turn, index: int) -> Iterator[dict]:
    state = turn.state
    if state["stage"] in ("inspire", "clarify") and state["suggestions"]:
        items = state["suggestions"]["items"] + state["suggestions"].get("more", [])
        if index <= len(items):
            yield from choose_destination(turn, items[index - 1]["id"])
            return
    if state["plan"] and state["plan"].get("bundles") and index <= len(state["plan"]["bundles"]):
        state["selected"] = index - 1
        bundle = state["plan"]["bundles"][index - 1]
        yield turn.step("select_option", f"Выбран вариант «{bundle['label']}»", replies.money(bundle["total"]))
        turn.say(replies.bundle_selected(bundle), "plan", [{"label": "Оформить", "action": {"type": "checkout"}}])
        return
    turn.say("Не понял, какой вариант выбрать — нажмите на карточку или назовите номер.", "info")


def picked_suggestions(state: dict, picks: list[int] | None) -> list[str]:
    """«Сравни первые два», «сравни 1 и 3» — номера из подборки направлений."""
    if not picks or not state.get("suggestions") or state["stage"] not in ("inspire", "clarify"):
        return []
    items = state["suggestions"]["items"] + state["suggestions"].get("more", [])
    ids = [items[p - 1]["id"] for p in picks if 1 <= p <= len(items)]
    return ids if len(ids) >= 2 else []


def compared_choice(state: dict, result: dict) -> str | None:
    if state["stage"] != "compare" or not state.get("comparison") or result.get("compare"):
        return None
    items = state["comparison"]["items"]
    ready = [item["id"] for item in items if not item["error"]]
    if result["patch"].get("destination") in ready:
        return result["patch"]["destination"]
    pick = result.get("select")
    if pick and pick <= len(items) and not items[pick - 1]["error"]:
        return items[pick - 1]["id"]
    return None


def compare_destinations(turn: Turn, ids: list[str]) -> Iterator[dict]:
    """Две-три поездки рядом. Когда едут, не знаем — спрашиваем один раз и потом возвращаемся к сравнению."""
    state, brief, sources = turn.state, turn.state["brief"], turn.state["sources"]
    brief["destination"], brief["route"], brief["route_nights"] = None, [], []
    if not knows_when(brief):
        if "when" not in state["asked"]:
            state["compare_pending"] = ids
            yield from decide(turn)
            return
        month = (turn.today + timedelta(days=30)).month
        brief["month"] = month
        sources["month"] = {"kind": "default", "reason": f"месяц не назван — беру {MONTHS_IN[month - 1]}"}
    names = [destination(i)["name"] for i in ids]
    yield turn.step(
        "compare_destinations",
        f"Сравниваю: {' или '.join(names)}",
        "собираю каждую поездку целиком: дорога, отель, трансфер, цена от двери до двери",
    )
    comparison = build_comparison(brief, ids, turn.today)
    ready = [item for item in comparison["items"] if not item["error"]]
    yield turn.step(
        "assemble_trip",
        f"Собрал {len(ready)} {replies.plural(len(ready), 'поездку', 'поездки', 'поездок')} рядом",
        "; ".join(f"{item['name']} — {replies.money(item['total'])}" for item in ready) or "ни одну не собрать",
    )
    state["comparison"], state["stage"], state["plan"], state["diff"] = comparison, "compare", None, None
    turn.recommended()
    turn.say(comparison_text(comparison, brief), "compare", comparison_quick(comparison))


def choose_destination(turn: Turn, dest_id: str) -> Iterator[dict]:
    state = turn.state
    state["brief"]["destination"] = dest_id
    state["sources"]["destination"] = {"kind": "explicit", "reason": ""}
    state["plan"] = None
    yield turn.step("select_destination", f"Направление: {destination(dest_id)['name']}", "собираю поездку целиком")
    yield from decide(turn)


# ── Действия из интерфейса ──────────────────────────────────────────────────


def handle_action(turn: Turn, action: dict) -> Iterator[dict]:
    state = turn.state
    brief, sources = state["brief"], state["sources"]
    kind = action.get("type")
    if kind in ("select_destination", "choose_compared"):  # из подборки или «беру эту» из сравнения
        yield from choose_destination(turn, action["id"])
    elif kind == "more_destinations" and state["suggestions"]:
        sugg = state["suggestions"]
        sugg["items"], sugg["more"] = sugg["more"] + sugg["items"], []
        turn.say(replies.inspire(sugg, brief), "inspire", replies.inspire_quick(sugg))
    elif kind == "select_bundle":
        yield from select(turn, int(action["index"]) + 1)
    elif kind == "swap":
        yield from swap(turn, action)
    elif kind == "apply_fix":
        yield from apply_fix(turn, action["fix"])
    elif kind == "apply_hack":
        yield from apply_hack(turn, action)
    elif kind == "set_priorities":
        values = {k: max(0.0, min(1.0, float(v))) for k, v in (action.get("priorities") or {}).items() if k in brief["priorities"]}
        brief["priorities"] = brief["priorities"] | values
        sources["priorities"] = {"kind": "explicit", "reason": "ползунки приоритетов"}
        yield turn.step("update_brief", "Новые приоритеты", ", ".join(f"{k} {v:.0%}" for k, v in values.items()))
        yield from replan_after(turn, "новые приоритеты", rerank=True)
    elif kind == "remove_chip":
        remove_chip(brief, sources, action["key"])
        derive(brief, sources)
        yield turn.step("update_brief", "Убрал условие", action.get("label") or action["key"])
        yield from replan_after(turn, "убрали условие")
    elif kind == "edit_brief":
        changed = apply_patch(brief, sources, action.get("patch") or {}, "explicit")
        derive(brief, sources)
        yield turn.step("update_brief", "Поправил бриф", describe_change(changed))
        yield from replan_after(turn, describe_change(changed) or "новые условия")
    elif kind == "checkout":
        yield from start_checkout(turn)
        cart_documents(turn)
    elif kind == "post" and state["booking_id"]:
        yield from post_purchase(turn, action["post"])
    elif kind == "handoff":
        yield from start_handoff(turn, "нажали «Позвать менеджера»")
    elif kind == "handoff_cancel" and state.get("handoff"):
        state["handoff"] |= {"status": "closed", "updated": time.time()}
        yield turn.step("handoff", "Вернул диалог агенту", "менеджер больше не нужен")
        turn.say(
            "Хорошо, продолжаем вдвоём. " + replies.ABOUT if not state["plan"] else "Хорошо, продолжаем вдвоём — план на месте.", "info"
        )
    elif kind == "reset":
        reset(state, turn.profile)
        turn.say(replies.greeting(turn.profile), "greeting", narrate=False)
    else:
        turn.say("Это действие сейчас недоступно.", "info", narrate=False)


def replan_after(turn: Turn, reason: str, rerank: bool = False) -> Iterator[dict]:
    state = turn.state
    if state["stage"] in ("plan", "checkout") or state["brief"]["destination"]:
        previous = state["plan"]["bundles"][state["selected"]] if state["plan"] and state["plan"].get("bundles") else None
        yield from decide(turn, reason=reason, rerank=rerank)
        if rerank and previous and state["plan"] and state["plan"].get("bundles"):
            change = planner.diff(previous, state["plan"]["bundles"][0])
            state["diff"] = change
            turn.say(replies.replan_text(state, change, state["plan"], reason), "replan", replies.plan_quick(state["plan"]))
    else:
        yield from decide(turn, reason=reason)


SWAP_PARTS = {"hotel_id", "outbound_id", "inbound_id", "meal", "refundable", "transfer_kind"}


def swap(turn: Turn, action: dict) -> Iterator[dict]:
    """Ручная замена части поездки: отель, рейс, питание, тариф, трансфер. Остальное остаётся."""
    state, today = turn.state, turn.today
    plan = state["plan"]
    if not plan or not plan.get("bundles"):
        turn.say("Сначала соберём поездку.", "info")
        return
    if action.get("part") not in SWAP_PARTS:
        turn.say("Эту часть поездки заменить нельзя.", "info", narrate=False)
        return
    old = plan["bundles"][state["selected"]]
    try:
        new = planner.rebuild_bundle(state["brief"], plan, old, today, **{action["part"]: action["value"]})
    except StopIteration:  # вариант из устаревшего списка — на эти даты его уже нет
        turn.say("Этот вариант уже недоступен — выберите другой.", "info", narrate=False)
        return
    yield turn.step("swap_component", "Заменил часть поездки", action.get("label") or action["part"])
    yield turn.step(
        "validate_itinerary",
        "Перепроверил состыковки",
        f"{sum(1 for c in new['checks'] if c['status'] in ('ok', 'fixed'))} из {len(new['checks'])} в порядке",
    )
    plan["bundles"][state["selected"]] = new
    planner.explain(plan["bundles"], state["brief"], destination(plan["dest"]))
    change = planner.diff(old, new)
    state["diff"] = change
    state["metrics"]["replans"] += 1
    turn.say(
        replies.replan_text(state, change, plan | {"bundles": [new], "downgrade": []}, "заменили часть поездки"),
        "replan",
        replies.plan_quick(plan),
    )


def apply_fix(turn: Turn, fix: dict) -> Iterator[dict]:
    state = turn.state
    plan = state["plan"]
    if not plan or not plan.get("bundles"):
        turn.say("Сначала соберём поездку.", "info")
        return
    kind = fix["type"]
    if kind == "cheaper":
        current = plan["bundles"][state["selected"]]["total"]
        state["brief"]["budget"] = int(current * 0.85 // 1000 * 1000)
        state["sources"]["budget"] = {"kind": "inferred", "reason": "«уложиться в бюджет» — на 15% дешевле"}
        yield from decide(turn, reason="ищу дешевле")
        return
    if kind == "swap_inbound":
        old = plan["bundles"][state["selected"]]
        later = [
            o for o in plan["inbound"] if o["depart"] > old["inbound"]["depart"] and not planner.transport_violations(o, state["brief"])
        ]
        if not later:
            turn.say("Более поздних рейсов в этот день нет. Могу продлить поездку на ночь — скажите «продли на ночь».", "info")
            return
        yield from swap(
            turn, {"part": "inbound_id", "value": later[0]["id"], "label": f"обратно {later[0]['number']} в {later[0]['depart'][11:16]}"}
        )
        return
    old = plan["bundles"][state["selected"]]
    new = copy.deepcopy(old)
    hotel_night = new["hotel"]["price_total"] / new["nights"]
    price = int(round(hotel_night * 0.5 / 50) * 50)
    title = "Ранний заезд" if kind == "early_checkin" else "Поздний выезд до 18:00"
    if any(e["type"] == kind for e in new["extras"]):
        turn.say(f"{title} уже в плане.", "info")
        return
    new["extras"].append({"type": kind, "title": title, "price": price})
    for check in new["checks"]:
        if check.get("fix") and check["fix"]["type"] == kind:
            check["status"], check["fix"] = "fixed", None
            check["detail"] += f" — добавил: {title.lower()} за {replies.money(price)}"
    planner.recount(new, state["brief"])
    plan["bundles"][state["selected"]] = new
    planner.explain(plan["bundles"], state["brief"], destination(plan["dest"]))
    state["diff"] = planner.diff(old, new)
    yield turn.step("apply_fix", f"Добавил: {title.lower()}", replies.money(price))
    turn.say(
        f"Добавил в план: {title.lower()} за {replies.money(price)}. Итог {replies.money(new['total'])}.",
        "replan",
        replies.plan_quick(plan),
    )


def apply_hack(turn: Turn, action: dict) -> Iterator[dict]:
    """Лайфхак «ночь в поезде вместо отеля»: последняя ночь — в купе, поездка на ночь короче, домой утром."""
    state = turn.state
    plan = state["plan"]
    if not plan or not plan.get("bundles") or action.get("kind") != "night_train":
        turn.say("Этот лайфхак сейчас не применить.", "info", narrate=False)
        return
    old = plan["bundles"][state["selected"]]
    new = planner.night_train_bundle(state["brief"], old, turn.today)
    if not new:
        turn.say("Ночной поезд на эти даты уже не подходит — оставил план как был.", "info", narrate=False)
        return
    state["brief"]["nights"] = new["nights"]
    state["sources"]["nights"] = {"kind": "inferred", "reason": "последняя ночь — в поезде вместо отеля"}
    plan["inbound"] = plan["inbound"] + [new["inbound"]]  # чтобы и потом можно было поменять обратный поезд
    plan["checkout"], plan["nights"] = new["checkout"], new["nights"]
    new["hacks"] = planner.find_hacks(new, state["brief"], plan["outbound"], plan["inbound"], turn.today)
    plan["bundles"][state["selected"]] = new
    planner.explain(plan["bundles"], state["brief"], destination(plan["dest"]))
    change = planner.diff(old, new)
    state["diff"] = change
    state["metrics"]["replans"] += 1
    yield turn.step(
        "apply_hack", "Применил лайфхак: ночной поезд", f"{new['inbound']['number']}, −{replies.money(old['total'] - new['total'])}"
    )
    turn.say(
        replies.replan_text(state, change, plan | {"bundles": [new], "downgrade": []}, "ночь в поезде вместо ночи в отеле"),
        "replan",
        replies.plan_quick(plan),
    )


def start_checkout(turn: Turn) -> Iterator[dict]:
    state = turn.state
    bundle = state["plan"]["bundles"][state["selected"]]
    if not bundle.get("legs"):  # у маршрута проверки уже собраны по частям — не пересчитываем как поездку в один город
        planner.validate(bundle, state["brief"], destination(bundle["dest"]), turn.today)
    yield turn.step(
        "validate_itinerary",
        "Финальная проверка перед оплатой",
        f"{len(bundle['checks'])} проверок, ошибок: {sum(1 for c in bundle['checks'] if c['status'] == 'error')}",
    )
    yield turn.step("add_to_cart", "Собрал корзину", f"{replies.money(bundle['total'])}: транспорт, отель, питание, трансферы, доплаты")
    state["stage"] = "checkout"
    state["metrics"]["checkout"] = True
    saved = savings.summary(state, bundle)
    yield turn.step("time_saved", f"Сэкономил вам около {savings.duration_label(saved['minutes'])}", saved["line"])
    turn.say(replies.checkout_text(bundle) + f"\nИтог: {saved['line']}.", "checkout", [], narrate=False)


def cart_documents(turn: Turn) -> None:
    """У корзины — полис одной галочкой и вопрос про загранпаспорт; срок из памяти проверяем сразу."""
    state = turn.state
    if state["stage"] != "checkout":
        return
    passport = state.get("passport_until") or (turn.profile.get("facts") or {}).get("passport_until", {}).get("value")
    if passport:  # из памяти — чтобы корзина сразу показала проверку
        state["passport_until"] = passport
    turn.text += bk.documents_note(state["plan"]["bundles"][state["selected"]], state["brief"], passport)


def check_passport(turn: Turn, until: date) -> Iterator[dict]:
    """Срок загранпаспорта против правил страны поездки. Дату помним и в следующих поездках."""
    state = turn.state
    state["passport_until"] = until.isoformat()
    turn.profile.setdefault("facts", {})["passport_until"] = {
        "value": until.isoformat(),
        "label": f"загранпаспорт действует до {bk.full_date(until)}",
    }
    plan = state["plan"]
    if not plan or not plan.get("bundles"):
        turn.say(f"Запомнил: загранпаспорт действует до {bk.full_date(until)}. Проверю, как только выберем страну.", "info", narrate=False)
        return
    check = bk.passport_check(plan["bundles"][state["selected"]], until)
    yield turn.step("check_passport", "Проверил срок загранпаспорта", check["rule"])
    quick = [{"label": "Поездка по России", "text": "давай куда-нибудь по России"}] if not check["ok"] else []
    turn.say(check["text"], "answer", quick + (replies.plan_quick(plan)[:2] if state["stage"] == "plan" else []), narrate=False)


def set_insurance(turn: Turn, wanted: bool) -> Iterator[dict]:
    state = turn.state
    bundle = state["plan"]["bundles"][state["selected"]]
    item = bk.policy(bundle, state["brief"])
    state.setdefault("checkout_options", {})["insurance"] = wanted
    yield turn.step(
        "add_to_cart", "Страховка в корзине" if wanted else "Страховку убрал", f"{item['title']}, {replies.money(item['price'])}"
    )
    if wanted:
        text = (
            f"Добавил страховку: {item['title'].lower()}, покрытие {item['coverage']}, на {item['people']} чел. и {item['days']} дн. — "
            f"{replies.money(item['price'])}. К оплате {replies.money(bundle['total'] + item['price'])}."
        )
    else:
        text = f"Убрал страховку. К оплате {replies.money(bundle['total'])}."
    turn.say(text, "checkout", [], narrate=False)


def post_purchase(turn: Turn, post: dict | None) -> Iterator[dict]:
    from app import store  # локальный импорт: core не зависит от БД, кроме этого шага

    booking = store.get_booking(turn.state["booking_id"])
    if not booking or not post:
        turn.say("Не нашёл оформленную поездку.", "info")
        return
    yield turn.step("post_purchase", "Работаю с бронью " + booking["id"], post["type"])
    text, quick = bk.booking_action(booking, post, turn.today)
    store.save_booking(booking)
    turn.say(text, "post", quick or replies.booked_quick(), narrate=False)


# ── Живой менеджер ──────────────────────────────────────────────────────────


def with_human(state: dict) -> bool:
    return (state.get("handoff") or {}).get("status") in ("waiting", "active")


def start_handoff(turn: Turn, reason: str) -> Iterator[dict]:
    """Диалог — в очередь менеджеров. Менеджер увидит бриф, план и след агента: человеку не придётся повторять."""
    state = turn.state
    if with_human(state):
        turn.say("Менеджер уже подключается — ответ придёт сюда же.", "handoff", narrate=False)
        return
    now = time.time()
    state["handoff"] = {"status": "waiting", "reason": reason, "since": now, "updated": now, "operator": None, "unread": 0}
    state["metrics"]["handoff"] = True
    done = sum(len(m.get("steps") or []) for m in state["messages"])
    yield turn.step("handoff", "Передал диалог менеджеру", f"{reason}; менеджер увидит бриф, план и мои шаги ({done})")
    turn.say(
        "Передаю менеджеру. Он увидит, что вы хотите, собранный план и всё, что я уже сделал, — повторять не придётся. "
        "Ответ придёт сюда же; пока ждёте, можно писать — сообщения увидит менеджер.",
        "handoff",
        [{"label": "Вернуться к агенту", "action": {"type": "handoff_cancel"}}],
        narrate=False,
    )


def log_hotel_events(state: dict, plan: dict) -> None:
    """Для экрана «Для отеля»: какие отели агент рекомендовал этим гостям и какие отсеял — с причиной.
    События копятся в state["events_out"], сохраняет их вызывающий (API или бот) — ядро не зависит от БД."""
    segment = hotel_view.segment_of(state["brief"])
    events = state.setdefault("events_out", [])
    for bundle in plan["bundles"]:
        events.append({"hotel_id": bundle["hotel"]["id"], "event": "recommended", "segment": segment, "reason": ""})
    for rejected in plan["hotels_rejected"]:
        events.append({"hotel_id": rejected["id"], "event": "rejected", "segment": segment, "reason": rejected["reason"][:120]})


def finish_checkout(state: dict, traveller: dict, profile: dict) -> dict:
    """Имитация оплаты: бронь, память о предпочтениях, сообщение агента. Сохраняет вызывающий (API или бот)."""
    booking = bk.create_booking(state, traveller)
    booking["savings"] = savings.summary(state, booking["bundle"])
    state.setdefault("events_out", []).append(
        {"hotel_id": booking["bundle"]["hotel"]["id"], "event": "booked", "segment": hotel_view.segment_of(state["brief"]), "reason": ""}
    )
    if (state.get("checkout_options") or {}).get("insurance"):
        bk.add_insurance(booking)
    passport = state.get("passport_until") or (profile.get("facts") or {}).get("passport_until", {}).get("value")
    if passport and bk.passport_need(booking["bundle"]):
        booking["passport"] = bk.passport_check(booking["bundle"], date.fromisoformat(passport))
    bk.remember_trip(profile, state["brief"], state["sources"], booking["bundle"])
    state["stage"], state["booking_id"] = "booked", booking["id"]
    state["metrics"]["booked"] = True
    add_message(
        state,
        "agent",
        replies.booked_text(booking),
        kind="booked",
        quick=replies.booked_quick(),
        steps=[
            {"tool": "checkout", "title": "Оплата (имитация)", "detail": replies.money(booking["payment"]["amount"]), "ms": 0},
            {
                "tool": "remember_preference",
                "title": "Запомнил ваши предпочтения",
                "detail": "город вылета, состав, пожелания — пригодятся в следующий раз",
                "ms": 0,
            },
        ],
    )
    return booking
