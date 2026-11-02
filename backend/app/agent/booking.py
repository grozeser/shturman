"""Оформление поездки (оплата имитируется), действия после покупки и память о пользователе."""

import calendar
import copy
import hashlib
import re
from datetime import date, datetime, timedelta

from app.travel import inventory as inv
from app.travel.brief import diet_label, money, party_label
from app.travel.catalog import KIND_LABELS, destination, origin
from app.travel.planner import (
    assemble,
    build_plan,
    build_route,
    day_label,
    diff,
    eligible,
    people,
    pick_transfer,
    plural,
    rank_hotels,
    recount,
    time_of,
    transport_score,
    validate,
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def booking_code(seed: str) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    number = int(hashlib.sha1(seed.encode()).hexdigest(), 16)
    code = ""
    for _ in range(6):
        number, index = divmod(number, len(alphabet))
        code += alphabet[index]
    return f"ШТ-{code}"


def create_booking(state: dict, traveller: dict) -> dict:
    bundle = copy.deepcopy(state["plan"]["bundles"][state["selected"]])
    booking = {
        "id": booking_code(f"{state['id']}-{bundle['id']}-{now_iso()}"),
        "status": "confirmed",
        "created": now_iso(),
        "user_id": state["user_id"],
        "conversation_id": state["id"],
        "traveller": traveller,
        "brief": copy.deepcopy(state["brief"]),
        "bundle": bundle,
        "payment": {"amount": bundle["total"], "status": "paid", "method": "Имитация оплаты"},
        "services": [],
        "history": [{"ts": now_iso(), "text": f"Оформлено и оплачено {money(bundle['total'])} (имитация)"}],
        "pending": None,
    }
    if booking["brief"].get("accessible"):  # гость на коляске: перевозчик и отель узнают заранее, а не у трапа и на ресепшене
        out = bundle["outbound"]
        carrier = f"авиакомпания «{out['carrier']}»" if out["mode"] == "flight" else f"поезд {out['number']}"
        need = "кресло-коляска до борта и помощь при посадке" if out["mode"] == "flight" else "место для коляски и помощь при посадке"
        booking["requests"] = [
            {"type": "access", "who": carrier, "what": need, "status": "sent"},
            {
                "type": "access",
                "who": f"отель «{bundle['hotel']['name']}»",
                "what": "номер с доступной средой ближе к лифту",
                "status": "sent",
            },
        ]
        booking["history"].append(
            {"ts": now_iso(), "text": f"Предупредил: {carrier} — {need}; отель — номер с доступной средой (имитация)"}
        )
    booking["reminders"] = reminders(booking)
    diet = booking["brief"].get("diet") or []
    if diet:  # особое питание: отель узнаёт заранее, а не на завтраке
        hotel = bundle["hotel"]["name"]
        booking.setdefault("requests", []).append(
            {"type": "diet", "who": f"отель «{hotel}»", "what": f"кухня: {diet_label(diet)}", "status": "sent"}
        )
        booking["history"].append(
            {"ts": now_iso(), "text": f"Отелю «{hotel}» отправлены пожелания по питанию: {diet_label(diet)} (имитация)"}
        )
    return booking


def reminders(booking: dict) -> list[dict]:
    b = booking["bundle"]
    out, back = b["outbound"], b["inbound"]
    dest = destination(b["dest"])
    depart = datetime.fromisoformat(out["depart"])
    flight = out["mode"] == "flight"
    items = []
    if "шенген" in dest["visa"]:
        items.append({"at": (depart - timedelta(days=60)).isoformat(timespec="minutes"), "text": "Подать документы на шенгенскую визу"})
    elif "не нужна" not in dest["visa"]:
        items.append({"at": (depart - timedelta(days=10)).isoformat(timespec="minutes"), "text": f"Виза: {dest['visa']}"})
    hotel = b["hotel"]
    if hotel["refundable"] and hotel["free_cancel_until"]:
        last = datetime.fromisoformat(hotel["free_cancel_until"] + "T10:00") - timedelta(days=1)
        items.append({"at": last.isoformat(timespec="minutes"), "text": "Завтра последний день бесплатной отмены отеля"})
    if flight:
        items.append(
            {"at": (depart - timedelta(hours=24)).isoformat(timespec="minutes"), "text": f"Онлайн-регистрация на рейс {out['number']}"}
        )
    items.append(
        {
            "at": (depart - timedelta(hours=3 if flight else 1.5)).isoformat(timespec="minutes"),
            "text": f"Пора выезжать {'в аэропорт' if flight else 'на вокзал'}: {out['number']} в {time_of(out['depart'])}",
        }
    )
    items.append({"at": out["arrive"], "text": f"{b['transfer_in']['title']} встречает по прибытии в {time_of(out['arrive'])}"})
    # за 3 дня до выезда бот пришлёт свежий прогноз: текст собирается в момент отправки, а не при покупке
    items.append(
        {"at": (depart - timedelta(days=3)).isoformat(timespec="minutes"), "text": "Прогноз погоды на поездку", "kind": "forecast"}
    )
    if back["mode"] == "flight":
        back_at = datetime.fromisoformat(back["depart"]) - timedelta(hours=24)
        items.append({"at": back_at.isoformat(timespec="minutes"), "text": f"Регистрация на обратный рейс {back['number']}"})
    now = datetime.now().isoformat(timespec="minutes")
    # прошедшие напоминания не нужны: иначе бот прислал бы их все разом сразу после покупки
    return sorted((item for item in items if item["at"] > now), key=lambda item: item["at"])


def _night_price(bundle: dict) -> int:
    return inv.round_price(bundle["hotel"]["price_total"] / bundle["nights"], 50)


def _has_extra(booking: dict, *types: str) -> dict | None:
    for item in booking["bundle"]["extras"] + booking["services"]:
        if item["type"] in types:
            return item
    return None


def _charge(booking: dict, amount: int, text: str) -> None:
    booking["payment"]["amount"] += amount
    booking["history"].append({"ts": now_iso(), "text": text})


CONFIRM_QUICK = [
    {"label": "Подтвердить", "action": {"type": "post", "post": {"type": "confirm"}}},
    {"label": "Оставить как есть", "action": {"type": "post", "post": {"type": "decline"}}},
]


def booking_action(booking: dict, post: dict, today: date) -> tuple[str, list[dict]]:
    """Действия с купленной поездкой. Всё, что меняет деньги, — в два шага: расчёт, затем подтверждение."""
    kind = post.get("type")
    bundle = booking["bundle"]
    h = inv.hotel(bundle["hotel"]["id"])
    if booking["status"] == "cancelled" and kind not in ("reminders",):
        return "Эта поездка отменена. Соберём новую?", [{"label": "Новая поездка", "action": {"type": "reset"}}]

    if kind == "early_checkin":
        existing = _has_extra(booking, "early_checkin", "extra_night")
        if existing:
            return f"Уже включено: {existing['title'].lower()}. Номер будет готов к вашему приезду.", []
        price = inv.round_price(_night_price(bundle) * 0.5, 50)
        arrive = datetime.fromisoformat(bundle["outbound"]["arrive"])
        if h["features"]["early_checkin"]:
            hour = max(8, min(12, arrive.hour + 1))
            booking["services"].append(
                {"type": "early_checkin", "title": f"Ранний заезд с {hour}:00", "price": price, "status": "confirmed"}
            )
            _charge(booking, price, f"Ранний заезд с {hour}:00 — доплата {money(price)} (имитация)")
            return (
                f"Запросил у отеля «{h['name']}» ранний заезд — подтвердили: заселение с {hour}:00, доплата {money(price)} (оплачено, имитация).",
                [],
            )
        booking["services"].append({"type": "early_checkin", "title": "Ранний заезд — лист ожидания", "price": 0, "status": "waitlist"})
        booking["history"].append({"ts": now_iso(), "text": "Запрос раннего заезда — лист ожидания"})
        return (
            f"«{h['name']}» не гарантирует ранний заезд. Поставил запрос в лист ожидания: ответ придёт за сутки до заезда. "
            "Багаж можно оставить на ресепшене, а если номер не дадут — подберу дневной номер рядом.",
            [],
        )

    if kind == "late_checkout":
        if _has_extra(booking, "late_checkout"):
            return "Поздний выезд уже включён.", []
        price = inv.round_price(_night_price(bundle) * 0.5, 50)
        if h["features"]["late_checkout"]:
            booking["services"].append({"type": "late_checkout", "title": "Поздний выезд до 18:00", "price": price, "status": "confirmed"})
            _charge(booking, price, f"Поздний выезд до 18:00 — доплата {money(price)} (имитация)")
            return f"Договорился: выезд до 18:00, доплата {money(price)} (имитация).", []
        return "Отель не продлевает номер в день выезда. Могу добавить ещё одну ночь — скажите «продли на ночь».", []

    if kind == "add_transfer":
        current = bundle["transfer_in"]
        arrive = datetime.fromisoformat(bundle["outbound"]["arrive"])
        options = inv.transfers(h, bundle["outbound"]["mode"], arrive, people(booking["brief"]), bool(booking["brief"]["pets"]))
        private = next(o for o in options if o["kind"] == "private")
        if current["kind"] in ("private", "accessible"):
            return f"У вас уже {current['title'].lower()}: водитель встретит с табличкой в {time_of(bundle['outbound']['arrive'])}.", []
        back_options = inv.transfers(
            h, bundle["inbound"]["mode"], datetime.fromisoformat(bundle["inbound"]["depart"]), people(booking["brief"]), False
        )
        private_back = next(o for o in back_options if o["kind"] == "private")
        extra = private["price"] + private_back["price"] - current["price"] - bundle["transfer_out"]["price"]
        booking["pending"] = {"type": "transfer", "transfer_in": private, "transfer_out": private_back, "extra": extra}
        seat = ", детское кресло" if booking["brief"]["children"] else ""
        return (
            f"Сейчас у вас {current['title'].lower()}. Могу заменить на индивидуальный трансфер туда и обратно: водитель с табличкой{seat}, "
            f"без ожидания других туристов. Доплата {money(extra)}. Подтвердить?",
            CONFIRM_QUICK,
        )

    if kind == "change_dates":
        old_start = date.fromisoformat(bundle["checkin"])
        if post.get("date_from"):
            new_start = date.fromisoformat(post["date_from"])
        elif post.get("shift_days"):
            new_start = old_start + timedelta(days=post["shift_days"])
        else:
            return "На какие даты перенести? Например: «на 2 дня позже» или «с 20 ноября».", []
        if new_start <= today:
            return "Эта дата уже прошла — выберите другую.", []
        brief = booking["brief"] | {"date_from": new_start.isoformat(), "month": new_start.month}
        if bundle.get("legs"):  # маршрут из нескольких мест сдвигаем целиком, с теми же ночами по городам
            plan = build_route(brief, brief["route"], today, [leg["nights"] for leg in bundle["legs"]])
        else:
            plan = build_plan(brief, bundle["dest"], today, previous=bundle)
        if "error" in plan:
            return plan["error"], []
        new = plan["bundles"][0]
        change = diff(bundle, new)
        hotel_fee = 0
        if not bundle["hotel"]["refundable"] or (
            bundle["hotel"]["free_cancel_until"] and today.isoformat() > bundle["hotel"]["free_cancel_until"]
        ):
            hotel_fee = inv.round_price(bundle["costs"]["hotel"] * 0.25, 50)
        transport_fee = 2500 * people(booking["brief"]) if bundle["outbound"]["mode"] == "flight" else 300 * people(booking["brief"])
        extra = new["total"] - bundle["total"] + hotel_fee + transport_fee
        booking["pending"] = {"type": "change_dates", "bundle": new, "diff": change, "extra": extra, "fees": hotel_fee + transport_fee}
        lines = [f"• {c['part']}: {c['after']}" for c in change["changes"]]
        fee_text = f"сборы за изменение {money(hotel_fee + transport_fee)}" + (" (тариф отеля невозвратный)" if hotel_fee else "")
        sign = "доплата" if extra >= 0 else "возврат"
        return (
            f"Перенос на {day_label(new_start)} – {day_label(new_start + timedelta(days=bundle['nights']))}:\n"
            + "\n".join(lines)
            + f"\nНовая цена поездки {money(new['total'])}, {fee_text}. Итого {sign} {money(abs(extra))}. Подтвердить?",
            CONFIRM_QUICK,
        )

    if kind == "disruption":
        return _plan_b(booking, post.get("what", "flight_cancelled"), today)

    if kind == "cancel":
        hotel = bundle["hotel"]
        hotel_refund = 0
        if hotel["refundable"] and hotel["free_cancel_until"] and today.isoformat() <= hotel["free_cancel_until"]:
            hotel_refund = bundle["costs"]["hotel"] + bundle["costs"]["meals"]
        transport_refund = inv.round_price(bundle["costs"]["transport"] * (0.3 if bundle["outbound"]["mode"] == "flight" else 0.85), 50)
        refund = hotel_refund + transport_refund + bundle["costs"]["transfers"]
        booking["pending"] = {"type": "cancel", "refund": refund}
        return (
            f"Если отменить сейчас, вернём {money(refund)} из {money(booking['payment']['amount'])}: "
            f"отель — {money(hotel_refund)}{' (бесплатная отмена ещё действует)' if hotel_refund else ' (срок бесплатной отмены прошёл или тариф невозвратный)'}, "
            f"транспорт — {money(transport_refund)}, трансферы — полностью. Отменить поездку?",
            CONFIRM_QUICK,
        )

    if kind == "confirm":
        pending = booking.get("pending")
        if not pending:
            return "Нечего подтверждать — все изменения уже применены.", []
        booking["pending"] = None
        if pending["type"] == "plan_b":
            booking["bundle"] = pending["bundle"]
            _charge(
                booking,
                pending["extra"],
                f"План Б: {pending['title']}" + (f", доплата {money(pending['extra'])}" if pending["extra"] else ", без доплаты"),
            )
            booking["reminders"] = reminders(booking)
            return "Готово: план Б применён, ваучер и напоминания обновил.", []
        if pending["type"] == "change_dates":
            booking["bundle"] = pending["bundle"]
            booking["brief"]["date_from"] = pending["bundle"]["checkin"]
            _charge(
                booking,
                pending["extra"],
                f"Даты перенесены на {pending['bundle']['checkin']}, {'доплата' if pending['extra'] >= 0 else 'возврат'} {money(abs(pending['extra']))}",
            )
            booking["reminders"] = reminders(booking)
            return f"Перенёс поездку: теперь с {day_label(date.fromisoformat(pending['bundle']['checkin']))}. Напоминания обновил.", []
        if pending["type"] == "transfer":
            bundle["transfer_in"], bundle["transfer_out"] = pending["transfer_in"], pending["transfer_out"]
            bundle["costs"]["transfers"] = pending["transfer_in"]["price"] + pending["transfer_out"]["price"]
            recount(bundle, booking["brief"])
            _charge(booking, pending["extra"], f"Трансфер заменён на индивидуальный, доплата {money(pending['extra'])}")
            booking["reminders"] = reminders(booking)
            return "Готово: индивидуальный трансфер туда и обратно, водитель встретит с табличкой.", []
        if pending["type"] == "cancel":
            booking["status"] = "cancelled"
            booking["payment"]["refund"] = pending["refund"]
            booking["history"].append({"ts": now_iso(), "text": f"Поездка отменена, возврат {money(pending['refund'])} (имитация)"})
            return f"Поездка отменена. Возврат {money(pending['refund'])} придёт на карту (имитация).", []
    if kind == "decline":
        booking["pending"] = None
        return "Хорошо, оставляю всё как было.", []
    if kind == "reminders":
        lines = [f"• {datetime.fromisoformat(r['at']):%d.%m %H:%M} — {r['text']}" for r in booking["reminders"]]
        return "Напоминания по поездке:\n" + "\n".join(lines), []
    return "Это я пока не умею. Могу: ранний заезд, поздний выезд, перенос дат, трансфер, отмена, напоминания.", []


# ── План Б: сбой после покупки ──────────────────────────────────────────────


def _plan_b(booking: dict, what: str, today: date) -> tuple[str, list[dict]]:
    """Симуляция сбоя: отменили рейс туда или отель не может заселить. Агент сам собирает замену и считает разницу."""
    bundle, brief = booking["bundle"], booking["brief"]
    if bundle.get("legs"):
        return "Для маршрута из нескольких городов план Б пока собираю вручную — напишите, что случилось.", []  # shortcut: части маршрута
    dest = destination(bundle["dest"])
    new = copy.deepcopy(bundle)
    if what == "hotel_overbooked":
        checkin = date.fromisoformat(bundle["checkin"])
        ranked, _ = rank_hotels(brief, dest, checkin, bundle["nights"])
        current = bundle["hotel"]
        entry = next((e for e in ranked if e["id"] != current["id"] and e["stars"] >= current["stars"] and e["meets_prefs"]), None)
        entry = entry or next((e for e in ranked if e["id"] != current["id"]), None)
        if not entry:
            return "В этом направлении на ваши даты больше нет подходящих отелей — предложу вернуть деньги или сдвинуть даты.", []
        style_brief = brief | {"meal": current["meal"], "refundable": current["refundable"]}
        new = assemble(style_brief, dest, checkin, bundle["outbound"], bundle["inbound"], entry, bundle["style"], bundle["label"])
        validate(new, brief, dest, today)
        title = f"отель «{current['name']}» не смог заселить, переселение в «{new['hotel']['name']}»"
        lead = (
            f"Симуляция сбоя: «{current['name']}» сообщил, что не сможет заселить (овербукинг). "
            f"План Б: «{new['hotel']['name']}» {new['hotel']['stars']}★ — {', '.join(entry['pros'][:2]) or 'подходит под ваши условия'}."
        )
        extra = 0  # переселение при овербукинге — за счёт поставщика
    else:
        cancelled = bundle["outbound"]
        arrive_day = date.fromisoformat(cancelled["arrive"][:10])
        orig = origin(brief["origin"])
        options, shifted = [], False
        for day in (arrive_day, arrive_day + timedelta(days=1)):  # сначала тот же день, иначе — следующий
            same_mode = [o for o in inv.transport_out(orig, dest, day) if o["id"] != cancelled["id"] and o["mode"] == cancelled["mode"]]
            options, _ = eligible(same_mode, brief)
            if options:
                shifted = day != arrive_day
                break
        if not options:
            return "Других рейсов в ближайшие два дня нет — предложу перенести поездку или вернуть деньги за билеты.", []
        cheapest = min(o["price"] for o in options)
        replacement = max(options, key=lambda o: transport_score(o, brief, cheapest))
        # перевозчик пересаживает бесплатно: стоимость билета для вас та же
        new["outbound"] = replacement | {"cost": cancelled["cost"]}
        hotel = inv.hotel(bundle["hotel"]["id"])
        arrive = datetime.fromisoformat(replacement["arrive"])
        transfers = inv.transfers(hotel, replacement["mode"], arrive, people(brief), bool(brief["pets"]), bool(brief.get("accessible")))
        same = next((o for o in transfers if o["kind"] == bundle["transfer_in"]["kind"]), None)
        new["transfer_in"] = same or pick_transfer(transfers, brief, bundle["style"])
        new["costs"]["transfers"] = new["transfer_in"]["price"] + new["transfer_out"]["price"]
        new["extras"] = [e for e in new["extras"] if e["type"] not in ("extra_night", "early_checkin")]  # заново решит проверка стыковок
        validate(new, brief, dest, today)
        recount(new, brief)
        extra = new["total"] - bundle["total"]
        title = f"рейс {cancelled['number']} отменён, замена — {replacement['number']}"
        when = f"на следующий день, {day_label(arrive.date())}" if shifted else "в тот же день"
        lead = (
            f"Симуляция сбоя: рейс {cancelled['number']} в {time_of(cancelled['depart'])} отменили. "
            f"План Б: {replacement['number']} {when}, вылет в {time_of(replacement['depart'])}, прилёт в {time_of(replacement['arrive'])}. "
            "Билет перевозчик меняет бесплатно."
        )
        if shifted:
            lead += " Первая ночь в отеле пропадает — предупрежу отель, что заедете позже, чтобы бронь не аннулировали."
    change = diff(bundle, new)
    booking["pending"] = {"type": "plan_b", "bundle": new, "diff": change, "extra": extra, "title": title}
    # цена нового билета рядом с «меняет бесплатно» сбивает с толку — в плане Б её не показываем
    lines = [f"• {c['part']}: {c['after'].rsplit(', ', 1)[0] if c['part'] == 'Туда' else c['after']}" for c in change["changes"]]
    known = {(c["id"], c["detail"]) for c in bundle["checks"]}  # прежние замечания (дожди, ожидание вылета) — не про этот сбой
    fixes = [c for c in new["checks"] if c["status"] in ("fixed", "warn") and (c["id"], c["detail"]) not in known]
    tail = "".join(f"\n• Стыковка: {c['title'].lower()} — {c['detail']}" for c in fixes[:2])
    money_line = f"Доплата {money(extra)}." if extra > 0 else (f"Возврат {money(-extra)}." if extra < 0 else "Без доплаты.")
    return lead + ("\n" + "\n".join(lines) if lines else "") + tail + f"\n{money_line} Применить план Б?", CONFIRM_QUICK


# ── Память ──────────────────────────────────────────────────────────────────


def apply_memory(brief: dict, sources: dict, profile: dict) -> list[str]:
    """Подставляет в новый бриф то, что знаем о пользователе. Всё помечено как «из памяти» и правится в один клик."""
    facts = profile.get("facts") or {}
    used = []
    reason = "из прошлых поездок"
    if "origin" in facts:
        brief["origin"] = facts["origin"]["value"]
        sources["origin"] = {"kind": "memory", "reason": reason}
        used.append("origin")
    if "party" in facts:
        brief["adults"] = facts["party"]["value"]["adults"]
        brief["children"] = list(facts["party"]["value"]["children"])
        sources["adults"] = sources["children"] = {"kind": "memory", "reason": reason}
        used.append("party")
    if "avoid_night" in facts:
        brief["avoid_night"] = True
        sources["avoid_night"] = {"kind": "memory", "reason": reason}
        used.append("avoid_night")
    if "accessible" in facts:
        brief["accessible"] = True
        sources["accessible"] = {"kind": "memory", "reason": reason}
        used.append("accessible")
    if "meal" in facts:
        brief["meal"] = facts["meal"]["value"]
        sources["meal"] = {"kind": "memory", "reason": reason}
        used.append("meal")
    if "diet" in facts:
        brief["diet"] = list(facts["diet"]["value"])
        sources["diet"] = {"kind": "memory", "reason": reason}
        used.append("diet")
    return used


def remember_trip(profile: dict, brief: dict, sources: dict, bundle: dict) -> dict:
    facts = profile.setdefault("facts", {})
    facts["origin"] = {"value": brief["origin"], "label": f"вылетаете {origin(brief['origin'])['from']}"}
    facts["party"] = {"value": {"adults": brief["adults"], "children": brief["children"]}, "label": f"едете: {party_label(brief)}"}
    if brief["pets"]:
        facts["pets"] = {"value": brief["pets"], "label": "путешествуете с собакой" if brief["pets"] == "dog" else "путешествуете с кошкой"}
    if brief["avoid_night"] and sources.get("avoid_night", {}).get("kind") == "explicit":
        facts["avoid_night"] = {"value": True, "label": "не любите ночные рейсы"}
    if brief.get("accessible") and sources.get("accessible", {}).get("kind") == "explicit":
        facts["accessible"] = {"value": True, "label": "нужна доступная среда"}
    if brief["meal"] and sources.get("meal", {}).get("kind") == "explicit":
        facts["meal"] = {"value": brief["meal"], "label": f"питание: {bundle['hotel']['meal_label']}"}
    if brief.get("diet") and sources.get("diet", {}).get("kind") == "explicit":
        facts["diet"] = {"value": brief["diet"], "label": f"кухня: {diet_label(brief['diet'])}"}
    kinds = [k for k in brief["kinds"] if k in KIND_LABELS and k != "allinclusive"]
    if kinds:
        facts["kinds"] = {"value": kinds, "label": "любите: " + ", ".join(KIND_LABELS[k] for k in kinds)}
    profile.setdefault("trips", []).append(
        {
            "dest": bundle["dest_name"],
            "dest_id": bundle["dest"],  # для «как в прошлый раз»: название города не всегда однозначно
            "checkin": bundle["checkin"],
            "nights": bundle["nights"],
            "total": bundle["total"],
            "meal": bundle["hotel"]["meal"],
            "stars": bundle["hotel"]["stars"],
        }
    )
    return profile


def remember_note(profile: dict, text: str) -> None:
    notes = profile.setdefault("notes", [])
    if text not in notes:
        notes.append(text[:200])


# ── Памятка «что взять» и файл для календаря ────────────────────────────────

# граждане РФ въезжают по внутреннему паспорту (ЕАЭС и Абхазия) — загранпаспорт не нужен
INTERNAL_PASSPORT_OK = {"Россия", "Россия (Крым)", "Абхазия", "Беларусь", "Казахстан", "Киргизия", "Армения"}


def checklist(booking: dict) -> list[dict]:
    """Что взять с собой: по составу, погоде, типу места и визе. Каждый пункт с причиной — как и всё у агента."""
    brief, b = booking["brief"], booking["bundle"]
    info = b.get("dest_info") or {}
    weather = info.get("weather") or {}
    air, water, rain = weather.get("air"), weather.get("water"), weather.get("rain")
    kinds = set(info.get("kinds") or [])
    country = info.get("country", "")
    children, pets = brief.get("children") or [], brief.get("pets")
    flight = any(t["mode"] == "flight" for t in (b["outbound"], b["inbound"]))
    docs, clothes, extra = [], [], []

    def item(group: list, text: str, why: str = "") -> None:
        group.append({"text": text, "why": why})

    if country in INTERNAL_PASSPORT_OK:
        item(docs, "Паспорт РФ", "" if country.startswith("Россия") else f"{country}: загранпаспорт не нужен")
    else:
        need = passport_need(b)
        rule = f"{need['rule']}: должен действовать до {full_date(date.fromisoformat(need['required']))}" if need else ""
        item(docs, "Загранпаспорт", rule or "проверьте срок: многие страны требуют ещё 6 месяцев после выезда")
        insured = booking.get("insurance")
        item(
            docs,
            "Медицинская страховка для выезда",
            f"оформлена: полис {insured['number']}, покрытие {insured['coverage']}"
            if insured
            else "за границей лечение без полиса дорогое, а в ряде стран полис обязателен",
        )
    visa = info.get("visa") or ""
    if visa and "не нужна" not in visa:
        item(docs, "Виза", visa)
    if children:
        item(docs, "Свидетельство о рождении ребёнка", "спросят при посадке и заселении")
    if pets:
        item(docs, "Ветеринарный паспорт с прививками", "без него не пустят на рейс и в отель")
        item(docs, "Переноска для питомца", "в салоне — только в переноске")
    item(docs, f"Ваучер брони {booking['id']}", "есть в «Моих поездках», можно распечатать")

    if air is not None:
        if air >= 27:
            item(clothes, "Лёгкая одежда, головной убор, крем SPF 50", f"днём около +{air}°")
        elif air >= 18:
            item(clothes, "Лёгкая одежда и кофта на вечер", f"днём около +{air}°, вечером прохладнее")
        elif air >= 8:
            item(clothes, "Куртка и закрытая обувь", f"днём около {'+' if air > 0 else ''}{air}°")
        else:
            item(clothes, "Тёплая куртка, шапка, перчатки", f"днём около {'+' if air > 0 else ''}{air}°")
            if air <= -5:
                item(clothes, "Термобельё", "мороз")
    if rain and rain >= 6:
        item(clothes, "Зонт или дождевик", f"около {rain} дней с ливнями за месяц")
    if "sea" in kinds and water is not None and water >= 20:
        item(clothes, "Купальник и пляжные тапочки", f"вода около +{water}°")
    if "ski" in kinds:
        item(clothes, "Горнолыжная маска, перчатки, бальзам для губ", "склон и ветер")
    if "mountains" in kinds or "nature" in kinds:
        item(clothes, "Удобная треккинговая обувь", "прогулки по горам и природе")

    young = [age for age in children if age < 3]
    if young:
        item(extra, "Подгузники, питание и вода в ручную кладь", "в дороге детское питание пропускают сверх 100 мл")
    if brief.get("accessible"):
        item(
            docs,
            "Габариты и тип аккумулятора коляски",
            "перевозчик спросит при регистрации: электроколяски с литиевой батареей везут по особым правилам",
        )
    if children:
        item(extra, "Детская аптечка и игрушки в дорогу", f"дорога туда — около {max(1, round(b['outbound']['duration_min'] / 60))} ч")
    if brief.get("seniors"):
        item(extra, "Лекарства с запасом и рецепты", "в другой стране нужного препарата может не быть")
    diet = brief.get("diet") or []
    if set(diet) & {"gluten_free", "lactose_free", "nut_free"}:
        item(extra, "Карточка с ограничениями в еде на местном языке", f"для кафе вне отеля: {diet_label(diet)}")
    if "nut_free" in diet:
        item(extra, "Лекарства от аллергии и свой перекус — в ручную кладь", "в самолёте и поезде могут угощать орехами")
    if flight:
        item(extra, "Жидкости в ручной клади — до 100 мл", "правило досмотра в аэропорту")
    item(extra, "Зарядки и пауэрбанк в ручную кладь", "пауэрбанк в багаж сдавать нельзя" if flight else "в дороге пригодится")
    return [
        {"title": "Документы", "items": docs},
        {"title": "Одежда по погоде", "items": clothes},
        {"title": "В дорогу", "items": extra},
    ]


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_time(stamp: str) -> str:
    return datetime.fromisoformat(stamp).strftime("%Y%m%dT%H%M%S")  # «плавающее» местное время: как в билете


def ics(booking: dict) -> str:
    """Поездка в календарь: дорога туда и обратно, проживание и напоминания агента как будильники."""
    b = booking["bundle"]
    stays = b.get("legs") or [b]
    events = []

    def event(uid: str, summary: str, start: str, end: str, description: str = "", all_day: bool = False, alarms=()) -> None:
        kind = ";VALUE=DATE" if all_day else ""
        lines = [
            "BEGIN:VEVENT",
            f"UID:{booking['id']}-{uid}@shturman",
            f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%S')}",
            f"DTSTART{kind}:{start}",
            f"DTEND{kind}:{end}",
            f"SUMMARY:{_ics_text(summary)}",
        ]
        if description:
            lines.append(f"DESCRIPTION:{_ics_text(description)}")
        for at, text in alarms:
            lines += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{_ics_text(text)}",
                f"TRIGGER;VALUE=DATE-TIME:{_ics_time(at)}",
                "END:VALARM",
            ]
        events.append("\r\n".join(lines + ["END:VEVENT"]))

    def trip(uid: str, t: dict) -> None:
        what = "Рейс" if t["mode"] == "flight" else "Поезд" if t["mode"] == "train" else "Переезд"
        event(
            uid, f"{what} {t['number']}: {t['from']} → {t['to']}", _ics_time(t["depart"]), _ics_time(t["arrive"]), f"Бронь {booking['id']}"
        )

    out = b["outbound"]
    alarms = [(r["at"], r["text"]) for r in booking.get("reminders", [])]
    event("out", f"{'Рейс' if out['mode'] == 'flight' else 'Поезд'} {out['number']}: {out['from']} → {out['to']}",
          _ics_time(out["depart"]), _ics_time(out["arrive"]), f"Бронь {booking['id']}", alarms=alarms)  # fmt: skip
    for index, stay in enumerate(stays):
        hotel = stay["hotel"]
        event(
            f"stay-{index}",
            f"{stay['dest_name']}: {hotel['name']}",
            stay["checkin"].replace("-", ""),
            stay["checkout"].replace("-", ""),
            f"Заселение с {hotel['checkin']}, выезд до {hotel['checkout']}. Бронь {booking['id']}",
            all_day=True,
        )
        if index < len(stays) - 1:
            trip(f"move-{index}", stay["inbound"])
    trip("back", b["inbound"])
    head = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Shturman//Trip//RU",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_text(b['dest_name'])}",
    ]
    return "\r\n".join(head + events + ["END:VCALENDAR"]) + "\r\n"


# ── Страховка и загранпаспорт ───────────────────────────────────────────────

# тариф полиса, ₽ на человека в день, и покрытие: по региону поездки
POLICY_RATES = [
    ({"Россия", "Россия (Крым)"}, 45, "500 000 ₽", "Страховка в поездке по России: несчастный случай и задержка рейса"),
    (
        {"Абхазия", "Беларусь", "Казахстан", "Киргизия", "Армения", "Грузия", "Узбекистан"},
        80,
        "$30 000",
        "Медицинская страховка для выезда",
    ),
    ({"Турция", "Египет", "ОАЭ", "Тунис", "Катар", "Черногория", "Сербия"}, 95, "$35 000", "Медицинская страховка для выезда"),
    ({"Франция", "Италия", "Испания"}, 120, "€30 000", "Медицинская страховка для шенгенской визы"),
]
EXOTIC_RATE = (140, "$50 000", "Медицинская страховка для выезда")

# сколько ещё должен действовать загранпаспорт: от даты въезда или выезда. Справка по открытым данным —
# правила меняются, поэтому агент всегда советует сверить с консульством. Неизвестная страна — строгое правило.
PASSPORT_RULES = {
    "Турция": ("entry", 150, "days"),
    "Египет": ("exit", 6, "months"),
    "ОАЭ": ("entry", 6, "months"),
    "Таиланд": ("entry", 6, "months"),
    "Вьетнам": ("entry", 6, "months"),
    "Индонезия": ("entry", 6, "months"),
    "Мальдивы": ("entry", 6, "months"),
    "Шри-Ланка": ("entry", 6, "months"),
    "Индия": ("entry", 6, "months"),
    "Китай": ("entry", 6, "months"),
    "Малайзия": ("entry", 6, "months"),
    "Катар": ("entry", 6, "months"),
    "Маврикий": ("entry", 6, "months"),
    "Тунис": ("exit", 6, "months"),
    "Черногория": ("exit", 3, "months"),
    "Сербия": ("exit", 3, "months"),
    "Узбекистан": ("exit", 3, "months"),
    "Франция": ("exit", 3, "months"),
    "Италия": ("exit", 3, "months"),
    "Испания": ("exit", 3, "months"),
    "Грузия": ("exit", 0, "months"),
    "Куба": ("exit", 0, "months"),
    "Сейшелы": ("exit", 0, "months"),
}
MONTH_STEMS = ["янв", "фев", "мар", "апр", "ма[йяе]", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def policy(bundle: dict, brief: dict) -> dict:
    """Полис на всех: тариф по стране, дни поездки, возраст (малыши и старшие дороже), горы и активный отдых — дороже."""
    info = bundle.get("dest_info") or {}
    country = info.get("country", "")
    rate, coverage, title = next(((r, c, t) for countries, r, c, t in POLICY_RATES if country in countries), EXOTIC_RATE)
    if "шенген" in (info.get("visa") or ""):  # найденные на карте страны Шенгена — с обязательным полисом
        rate, coverage, title = 120, "€30 000", "Медицинская страховка для шенгенской визы"
    days = bundle["nights"] + 1
    factor = brief["adults"] + sum(1.5 if age < 3 else 1.0 for age in brief["children"])
    if brief.get("seniors"):
        factor += 1.2  # одного из взрослых считаем старше 65 — для них тариф примерно вдвое выше
    sport = bool({"ski", "active"} & (set(info.get("kinds") or []) | set(brief["kinds"])))
    price = inv.round_price(rate * days * factor * (1.6 if sport else 1.0), 10)
    people = brief["adults"] + len(brief["children"])
    domestic = country in POLICY_RATES[0][0]
    includes = (
        ["несчастный случай", "задержка рейса от 4 ч", "потеря багажа"]
        if domestic
        else ["лечение и госпитализация", "скорая и эвакуация", "лекарства по назначению врача"]
    )
    if sport:
        includes.append("горные лыжи и активный отдых")
    return {
        "title": title,
        "coverage": coverage,
        "price": price,
        "per_person": inv.round_price(price / people, 10),
        "days": days,
        "people": people,
        "includes": includes,
        "required": "шенген" in title,
        "insurer": "Демо-страхование",
    }


def add_insurance(booking: dict) -> None:
    """Полис в брони: допродажа одной галочкой, видна в метриках. Оплата имитируется."""
    item = policy(booking["bundle"], booking["brief"])
    number = booking_code(f"policy-{booking['id']}").replace("ШТ-", "ПС-")
    booking["insurance"] = item | {"number": number}
    booking["payment"]["amount"] += item["price"]
    booking["history"].append(
        {
            "ts": now_iso(),
            "text": f"Полис {number}: {item['title'].lower()}, покрытие {item['coverage']} — {money(item['price'])} (имитация)",
        }
    )


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def full_date(day: date) -> str:
    return f"{day_label(day)} {day.year}"


def passport_date(text: str, today: date) -> date | None:
    """«Загранпаспорт действует до 10.03.2027», «паспорт до марта 2027» → дата. Без дня — первое число: так строже."""
    low = text.lower().replace("ё", "е")
    if "паспорт" not in low:
        return None
    found = None
    stems = "|".join(MONTH_STEMS)
    if match := re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", low):
        found = (int(match.group(3)), int(match.group(2)), int(match.group(1)))
    elif match := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", low):
        found = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    elif match := re.search(rf"(?:\b(\d{{1,2}})\s+)?\b({stems})\w*\.?\s+(\d{{4}})\b", low):
        month = next(i for i, stem in enumerate(MONTH_STEMS, start=1) if re.fullmatch(stem, match.group(2)))
        found = (int(match.group(3)), month, int(match.group(1) or 1))
    elif match := re.search(r"\b(\d{1,2})[./](\d{4})\b", low):
        found = (int(match.group(2)), int(match.group(1)), 1)
    if not found:
        return None
    try:
        until = date(*found)
    except ValueError:
        return None
    return until if today.year - 1 <= until.year <= today.year + 15 else None


def passport_need(bundle: dict) -> dict | None:
    """До какого числа должен действовать загранпаспорт в этой поездке и почему. None — хватит внутреннего паспорта."""
    country = (bundle.get("dest_info") or {}).get("country", "")
    if country in INTERNAL_PASSPORT_OK:
        return None
    basis, amount, unit = PASSPORT_RULES.get(country, ("exit", 6, "months"))
    start = date.fromisoformat(bundle["checkin"] if basis == "entry" else bundle["checkout"])
    required = start + timedelta(days=amount) if unit == "days" else add_months(start, amount)
    if amount == 0:
        why = f"{country} требует, чтобы загранпаспорт действовал весь срок поездки"
    else:
        span = (
            f"{amount} {plural(amount, 'день', 'дня', 'дней')}"
            if unit == "days"
            else f"{amount} {plural(amount, 'месяц', 'месяца', 'месяцев')}"
        )
        why = f"{country} требует {span} {'с даты въезда' if basis == 'entry' else 'после выезда'}"
    if country not in PASSPORT_RULES:
        why += " (точного правила для страны нет — беру строгое)"
    return {"country": country, "required": required.isoformat(), "rule": why}


def passport_check(bundle: dict, until: date) -> dict:
    need = passport_need(bundle)
    if not need:
        country = (bundle.get("dest_info") or {}).get("country", "")
        return {
            "ok": True,
            "rule": f"{country}: по внутреннему паспорту",
            "text": f"{country} — можно по внутреннему паспорту РФ, загранпаспорт не нужен.",
        }
    required = date.fromisoformat(need["required"])
    ok = until >= required
    if ok:
        text = f"Паспорт подходит: {need['rule']} — до {full_date(required)}, а ваш действует до {full_date(until)}."
    else:
        text = (
            f"{need['rule']} — паспорт должен действовать до {full_date(required)}, а ваш истекает {full_date(until)}: "
            "с таким не пустят на рейс. Продлите загранпаспорт заранее (новый делают около месяца) "
            "или выберем поездку, куда пускают по внутреннему паспорту: Россия, Абхазия, Беларусь, Армения, Казахстан."
        )
    return need | {
        "ok": ok,
        "until": until.isoformat(),
        "text": text + " Это справка по открытым данным — перед поездкой сверьтесь с консульством.",
    }


def documents(bundle: dict, brief: dict, passport_until: str | None) -> dict:
    """Что показать в корзине: полис одной галочкой и проверка паспорта (если дату уже знаем)."""
    need = passport_need(bundle)
    check = passport_check(bundle, date.fromisoformat(passport_until)) if passport_until and need else None
    return {"insurance": policy(bundle, brief), "passport": need, "passport_check": check}


def documents_note(bundle: dict, brief: dict, passport_until: str | None) -> str:
    """Строка в ответ агента у корзины: полис и вопрос про загранпаспорт — или уже готовая проверка."""
    item = policy(bundle, brief)
    note = f"\nСтраховка на всех — {money(item['price'])}, покрытие {item['coverage']}" + (
        ", для визы обязательна" if item["required"] else ""
    )
    note += ": добавить можно галочкой в корзине или словами «со страховкой»."
    need = passport_need(bundle)
    if need and passport_until:
        note += " " + passport_check(bundle, date.fromisoformat(passport_until))["text"]
    elif need:
        note += f" До какого числа действует ваш загранпаспорт? Проверю: {need['rule']}."
    return note
