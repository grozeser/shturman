"""Планировщик: направления, варианты поездки, проверка состыковок, пересборка и diff.

Здесь считаются все цифры, которые видит пользователь. LLM их не придумывает — только пересказывает.
"""

import calendar
import copy
import hashlib
import json
import math
import statistics
from datetime import date, datetime, timedelta

from app.travel import inventory as inv
from app.travel.brief import MEAL_LABELS, REGION_MEMBERS, diet_label, money, plural
from app.travel.catalog import (
    KIND_LABELS,
    MONTHS_GEN,
    MONTHS_IN,
    RAIL_COUNTRIES,
    climate,
    destination,
    destinations,
    distance_km,
    origin,
    season_factor,
)

HARD_KINDS = {"sea", "ski"}


def hours_label(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    if not h:
        return f"{m} мин"
    return f"{h} ч {m:02d} мин" if m else f"{h} ч"


def time_of(stamp: str) -> str:
    return stamp[11:16]


def day_label(day: date) -> str:
    return f"{day.day} {MONTHS_GEN[day.month - 1]}"


def people(brief: dict) -> int:
    return brief["adults"] + len(brief["children"])


def transport_cost(option: dict, brief: dict) -> int:
    if option.get("per_vehicle"):  # машина с водителем — цена за машину на 4 мест, а не за человека
        return inv.round_price(option["price"] * math.ceil(people(brief) / 4), 50)
    flight = option["mode"] == "flight"
    factor = brief["adults"]
    for age in brief["children"]:
        factor += (0.1 if flight else 0.0) if age < 2 else (0.75 if flight else 0.6) if age < 12 else 1.0
    pet_fee = (4500 if flight else 1500) if brief["pets"] else 0
    return inv.round_price(option["price"] * factor + pet_fee, 50)


# ── Фильтры и оценки транспорта ─────────────────────────────────────────────


def transport_violations(option: dict, brief: dict) -> list[str]:
    problems = []
    if brief["transport"] == "train" and option["mode"] != "train":
        problems.append("хотели поездом")
    if brief["transport"] == "flight" and option["mode"] != "flight":
        problems.append("хотели самолётом")
    if brief["direct_only"] and option["stops"]:
        problems.append("с пересадкой")
    if brief["avoid_night"] and option["night"]:
        problems.append("ночной рейс")
    if brief["max_hours"] and option["duration_min"] > brief["max_hours"] * 60 and option["mode"] == "flight":
        problems.append(f"в пути {hours_label(option['duration_min'])}")
    if brief["pets"] and not option["pets_cabin"]:
        problems.append("нельзя с животным")
    if brief["children"] and option["mode"] == "train" and option["class"] == "Сидячий" and option["duration_min"] > 8 * 60:
        problems.append("сидячий вагон надолго")
    return problems


def eligible(options: list[dict], brief: dict) -> tuple[list[dict], list[str]]:
    """Опции без нарушений. Если таких нет — ослабляем ограничения и честно говорим, что ослабили."""
    clean = [o for o in options if not transport_violations(o, brief)]
    if clean or not options:
        return clean, []
    relaxed = min(options, key=lambda o: len(transport_violations(o, brief)))
    worst = len(transport_violations(relaxed, brief))
    return [o for o in options if len(transport_violations(o, brief)) == worst], transport_violations(relaxed, brief)


def transport_score(option: dict, brief: dict, cheapest: int) -> float:
    p = brief["priorities"]
    hours = option["duration_min"] / 60
    score = -hours * (0.5 + p["speed"])
    score -= option["stops"] * 2.5
    if option["night"]:
        score -= 4 if brief["avoid_night"] else 1.5
    depart_hour = int(option["depart"][11:13])
    if depart_hour < 7 and option["mode"] == "flight":
        score -= 1.0
    if not option["baggage"]:
        score -= 2.5 if brief["children"] else 0.8
    if option["mode"] == "train" and option.get("overnight") and brief["transport"] != "train":
        score -= 1.0
    score -= (option["price"] - cheapest) / max(cheapest, 1) * 6 * (0.3 + p["price"])
    score -= 6 * len(transport_violations(option, brief))
    return score


def transport_pros(option: dict) -> str:
    if option["mode"] == "train":
        return f"{option['carrier'].lower()} {option['number']}, {option['class'].lower()}, {hours_label(option['duration_min'])}"
    if option["mode"] in ("bus", "car"):
        return f"{option['carrier'].lower()}, {hours_label(option['duration_min'])}, отправление в {time_of(option['depart'])}"
    kind = "прямой рейс" if not option["stops"] else f"с пересадкой в {option['via']}"
    return f"{kind}, {hours_label(option['duration_min'])}, вылет в {time_of(option['depart'])}"


# ── Отели ───────────────────────────────────────────────────────────────────


def default_meal(h: dict, brief: dict, style: str) -> str:
    meals = h["meals"]
    if brief["meal"] and brief["meal"] in meals:
        return brief["meal"]
    if brief["meal"]:  # просили лучше, чем есть: берём лучшее доступное
        return max(meals, key=lambda m: inv.MEAL_RANK[m])
    if style == "cheap":
        return min(meals, key=lambda m: inv.MEAL_RANK[m])
    if style == "comfort":
        return max(meals, key=lambda m: inv.MEAL_RANK[m])
    return "BB" if "BB" in meals else meals[0]


def hotel_exclusion(h: dict, brief: dict, quote: dict) -> str | None:
    f = h["features"]
    if not quote["available"]:
        return "нет мест на ваши даты"
    if brief["pets"] and not f["pets"]:
        return "нельзя с животными"
    if brief.get("accessible") and not f["accessible"]:
        return "нет номеров с доступной средой"
    if brief["children"] and f["adults_only"]:
        return "только для взрослых 16+"
    if brief["min_stars"] and h["stars"] < brief["min_stars"]:
        return f"{h['stars']}★ — ниже, чем вы хотели"
    if brief["meal"] == "AI" and "AI" not in h["meals"]:
        return "нет «всё включено»"
    missing = [d for d in brief.get("diet") or [] if not h["diets"].get(d)]
    if missing:
        return f"кухня не готовит: {diet_label(missing)}"
    return None


def hotel_fit(h: dict, brief: dict, dest: dict, quote: dict) -> dict:
    """Насколько отель подходит именно этим гостям (без учёта цены): балл 0–100, плюсы, минусы, кому не подойдёт."""
    p = brief["priorities"]
    f = h["features"]
    sea = "sea" in dest["kinds"] and (not brief["kinds"] or "sea" in brief["kinds"])
    city = "city" in brief["kinds"] or "culture" in brief["kinds"] or ("city" in dest["kinds"] and not sea)
    kids = bool(brief["children"])
    quiet_wanted = "quiet" in brief["hotel_prefs"] or brief["seniors"] or any(a < 6 for a in brief["children"])
    parts: list[tuple[float, float]] = []  # (значение 0..1, вес)
    pros, cons = [], []

    parts.append(((h["rating"] - 6.4) / 3.4, 1.0 + p["comfort"]))
    parts.append(((h["stars"] - 2) / 3, 0.4 + p["comfort"]))
    if h["rating"] >= 8.8:
        pros.append(f"рейтинг {h['rating']} по {h['reviews']:,} отзывам".replace(",", " "))
    elif h["rating"] < 7.6:
        cons.append(f"рейтинг {h['rating']} — отзывы средние")
    if sea and h["beach_m"] is not None:
        beach = h["beach_m"]
        value = 1 if beach <= 200 else 0.75 if beach <= 500 else 0.45 if beach <= 1000 else 0.15
        parts.append((value, 0.5 + 1.5 * p["beach"]))
        if beach <= 200:
            pros.append(f"{beach} м до пляжа")
        elif beach > 900:
            cons.append(f"{beach / 1000:.1f} км до моря — пешком {round(beach / 80)} мин".replace(".", ","))
    if kids:
        value = 0.5 * f["kids_club"] + 0.3 * f["kids_pool"] + 0.2 * f["family_rooms"]
        parts.append((value, 1.4))
        if f["kids_club"]:
            pros.append("детский клуб" + (" и детский бассейн" if f["kids_pool"] else ""))
        elif "kids_club" in brief["hotel_prefs"]:
            cons.append("нет детского клуба")
        if f["family_rooms"]:
            pros.append("семейные номера")
    if quiet_wanted:
        parts.append((1.0 if f["quiet"] else 0.0 if f["party"] else 0.5, 0.9))
        if f["quiet"]:
            pros.append("тихий, без ночной анимации")
        elif f["party"]:
            cons.append("анимация и вечеринки — может быть шумно")
    if "party" in brief["mood"]:
        parts.append((1.0 if f["party"] else 0.3, 0.8))
        if f["party"]:
            pros.append("вечеринки и бары рядом")
    meal = quote["meal"]
    if brief["meal"]:
        parts.append((1.0 if inv.MEAL_RANK[meal] >= inv.MEAL_RANK[brief["meal"]] else 0.2, 1.0))
    if meal == "AI":
        pros.append("всё включено")
    if city:
        parts.append((1 if h["center_km"] <= 2 else 0.6 if h["center_km"] <= 5 else 0.2, 0.9))
        if h["center_km"] <= 1.5:
            pros.append(f"{h['center_km']:g} км до центра".replace(".", ","))
        elif h["center_km"] > 6:
            cons.append(f"{h['center_km']:g} км до центра".replace(".", ","))
    if "pool" in brief["hotel_prefs"]:
        parts.append((1.0 if f["pool"] else 0.0, 0.6))
    if "spa" in brief["hotel_prefs"] or "spa" in brief["kinds"]:
        parts.append((1.0 if f["spa"] else 0.0, 0.7))
        if f["spa"]:
            pros.append("спа")
    if brief["seniors"]:
        parts.append((1.0 if f["accessible"] else 0.3, 0.6))
    if brief.get("accessible"):  # явное требование — первым, его должно быть видно в карточке варианта
        pros.insert(0, "доступная среда: номер без порогов, лифт, пандус")
    if h["stars"] <= 2 and (kids or brief["seniors"] or "romantic" in brief["mood"]):
        parts.append((0.0, 3.0))  # семье, старшим и паре в романтической поездке 2★ почти всегда хуже, даже если дёшево
        cons.append("2★ — скромный сервис" + (" для семейного отдыха" if kids else ""))
    parts.append((1 - min(h["airport_km"], 120) / 120, 0.2 + 0.5 * p["speed"]))
    if h["airport_km"] >= 70:
        cons.append(f"{h['airport_km']} км от аэропорта")
    if brief["pets"]:
        pros.append("можно с собакой" if brief["pets"] == "dog" else "можно с кошкой")
    if quote["refundable"] and quote["free_cancel_until"]:
        pros.append(f"бесплатная отмена до {day_label(date.fromisoformat(quote['free_cancel_until']))}")
    if brief.get("diet"):  # явное требование — первым, его должно быть видно в карточке варианта
        pros.insert(0, f"кухня: {diet_label(brief['diet'])}")

    total_weight = sum(w for _, w in parts)
    score = round(100 * sum(max(0.0, min(1.0, v)) * w for v, w in parts) / total_weight)
    not_for = []
    if f["adults_only"]:
        not_for.append("семьям с детьми")
    if f["party"]:
        not_for.append("тем, кто ищет тишину")
    if sea and h["beach_m"] and h["beach_m"] > 900:
        not_for.append("тем, кто хочет к морю пешком")
    if not f["pets"]:
        not_for.append("путешествующим с животными")
    if h["stars"] <= 2:
        not_for.append("тем, кому важен сервис")
    if h["center_km"] > 6:
        not_for.append("любителям гулять по городу")
    return {"score": score, "pros": pros, "cons": cons, "not_for": not_for}


def hotel_card(h: dict, quote: dict, fit: dict, nights: int) -> dict:
    return {
        "id": h["id"],
        "name": h["name"],
        "stars": h["stars"],
        "rating": h["rating"],
        "reviews": h["reviews"],
        "area": h["area"],
        "beach_m": h["beach_m"],
        "center_km": h["center_km"],
        "airport_km": h["airport_km"],
        "checkin": h["checkin"],
        "checkout": h["checkout"],
        "features": h["features"],
        "meals": h["meals"],
        "diets": [d for d, ok in h["diets"].items() if ok],
        "meal": quote["meal"],
        "meal_label": MEAL_LABELS[quote["meal"]],
        "refundable": quote["refundable"],
        "free_cancel_until": quote["free_cancel_until"],
        "price_total": quote["total"],
        "price_night": round(quote["total"] / nights),
        "rooms": quote["rooms"],
        "fit": fit["score"],
        "pros": fit["pros"],
        "cons": fit["cons"],
        "not_for": fit["not_for"],
        "lat": h["lat"],
        "lon": h["lon"],
    }


PREF_CHECKS = {
    "near_beach": lambda e: e["beach_m"] is not None and e["beach_m"] <= 300,
    "pool": lambda e: e["features"]["pool"],
    "spa": lambda e: e["features"]["spa"],
    "quiet": lambda e: not e["features"]["party"],
    "kids_club": lambda e: e["features"]["kids_club"],
}


def meets_prefs(entry: dict, brief: dict) -> bool:
    return all(PREF_CHECKS[p](entry) for p in brief["hotel_prefs"] if p in PREF_CHECKS)


def accessible_share(dest_id: str) -> float:
    """Доля отелей направления с номерами для гостей на коляске."""
    hotels = inv.hotels(dest_id)
    return sum(h["features"]["accessible"] for h in hotels) / len(hotels)


def rank_hotels(brief: dict, dest: dict, checkin: date, nights: int) -> tuple[list[dict], list[dict]]:
    """Отели по пригодности для этих гостей + отсеянные с причиной («почему не другие»)."""
    entries, rejected = [], []
    quotes = []
    for h in inv.hotels(dest["id"]):
        meal = default_meal(h, brief, "best")
        refundable = brief["refundable"] is not False
        quote = inv.quote_hotel(h, checkin, nights, brief["adults"], brief["children"], meal, refundable)
        quotes.append((h, quote))
    for h, quote in quotes:
        reason = hotel_exclusion(h, brief, quote)
        if reason:
            rejected.append({"id": h["id"], "name": h["name"], "stars": h["stars"], "rating": h["rating"], "reason": reason})
            continue
        fit = hotel_fit(h, brief, dest, quote)
        entries.append(hotel_card(h, quote, fit, nights))
    if entries:
        cheapest = min(e["price_total"] for e in entries)
        weight = 8 + 26 * brief["priorities"]["price"]  # баллы пригодности за каждые +100% к цене самого дешёвого
        for e in entries:
            e["value"] = round(e["fit"] - weight * (e["price_total"] - cheapest) / cheapest, 1)
            e["meets_prefs"] = meets_prefs(e, brief)
    # явно названные пожелания («с бассейном», «поближе к пляжу») — требование: такие отели всегда выше
    entries.sort(key=lambda e: (not e["meets_prefs"], -e["value"]))
    return entries, rejected


# ── Даты ────────────────────────────────────────────────────────────────────


def choose_dates(brief: dict, dest: dict, orig: dict, today: date) -> tuple[date, str, list[dict]]:
    """Явные даты — как есть. Только месяц — сравниваем заезды внутри месяца и берём самый выгодный."""
    nights = brief["nights"]
    if brief["date_from"]:
        return date.fromisoformat(brief["date_from"]), "explicit", []
    month = brief["month"] or (today + timedelta(days=30)).month
    year = brief.get("year") or (today.year if month >= today.month else today.year + 1)
    first = max(date(year, month, 1), today + timedelta(days=5))
    end_of_month = date(year, month, calendar.monthrange(year, month)[1])
    if (end_of_month - first).days < 7:  # от месяца почти ничего не осталось — значит, имеют в виду следующий год
        year += 1
        first = date(year, month, 1)
        end_of_month = date(year, month, calendar.monthrange(year, month)[1])
    # заезд не позже середины поездки до конца месяца: «в августе на 2 недели» — не с 31 августа
    last = max(first, end_of_month - timedelta(days=nights // 2))
    hotel_prices = sorted(h["price_night"] for h in inv.hotels(dest["id"]))
    median_hotel = hotel_prices[len(hotel_prices) // 2]
    scan = []
    day = first
    while day <= last and len(scan) < 16:
        out, _ = eligible(inv.transport_out(orig, dest, day), brief)
        back, _ = eligible(inv.transport_back(orig, dest, day + timedelta(days=nights)), brief)
        if out and back:
            transport = min(transport_cost(o, brief) for o in out) + min(transport_cost(o, brief) for o in back)
            hotel_total = sum(
                median_hotel * season_factor(dest, (day + timedelta(days=i)).month) * inv.holiday_factor(day + timedelta(days=i))
                for i in range(nights)
            ) * inv.rooms_for(brief["adults"], brief["children"])
            scan.append({"date": day.isoformat(), "estimate": inv.round_price(transport + hotel_total, 100)})
        day += timedelta(days=2)
    if not scan:
        return first, "fallback", []
    best = min(scan, key=lambda s: s["estimate"])
    return date.fromisoformat(best["date"]), "best_in_month", scan


# ── Сборка варианта поездки ─────────────────────────────────────────────────


def pick_transfer(options: list[dict], brief: dict, style: str) -> dict:
    if brief.get("accessible"):  # на коляске — только машина с подъёмником, даже в «Экономном»
        lift = [o for o in options if o["kind"] == "accessible"]
        if lift:
            return lift[0]
    allowed = [o for o in options if (not brief["pets"] or o["pets"])] or options
    if style == "cheap":
        return min(allowed, key=lambda o: o["price"])
    if style == "comfort" or (brief["children"] and any(a < 7 for a in brief["children"])):
        return next((o for o in allowed if o["kind"] == "private"), allowed[-1])
    return next((o for o in allowed if o["kind"] == "taxi"), allowed[0])


def assemble(brief: dict, dest: dict, checkin: date, out: dict, back: dict, hotel_entry: dict, style: str, label: str) -> dict:
    h = inv.hotel(hotel_entry["id"])
    nights = brief["nights"]
    meal = default_meal(h, brief, style)
    refundable = brief["refundable"] is not False and not (style == "cheap" and brief["refundable"] is None)
    quote = inv.quote_hotel(h, checkin, nights, brief["adults"], brief["children"], meal, refundable)
    fit = hotel_fit(h, brief, dest, quote)
    card = hotel_card(h, quote, fit | {"score": hotel_entry["fit"]}, nights)
    arrive = datetime.fromisoformat(out["arrive"])
    depart = datetime.fromisoformat(back["depart"])
    lift = bool(brief.get("accessible"))
    t_in = pick_transfer(inv.transfers(h, out["mode"], arrive, people(brief), bool(brief["pets"]), lift), brief, style)
    t_out_options = inv.transfers(h, back["mode"], depart - timedelta(hours=3), people(brief), bool(brief["pets"]), lift)
    t_out = next((o for o in t_out_options if o["kind"] == t_in["kind"]), pick_transfer(t_out_options, brief, style))
    costs = {
        "transport": transport_cost(out, brief) + transport_cost(back, brief),
        "hotel": quote["room_total"],
        "meals": quote["meal_total"],
        "transfers": t_in["price"] + t_out["price"],
        "extras": 0,
    }
    bundle = {
        "label": label,
        "style": style,
        "dest": dest["id"],
        "dest_name": dest["name"],
        "dest_info": {
            "country": dest["country"],
            "kinds": dest["kinds"],
            "weather": climate(dest, checkin.month),
            "visa": dest["visa"],
            "dynamic": bool(dest.get("dynamic")),
            "lat": dest["lat"],
            "lon": dest["lon"],
            "origin": {
                "name": origin(brief["origin"])["name"],
                "lat": origin(brief["origin"])["lat"],
                "lon": origin(brief["origin"])["lon"],
            },
        },
        "checkin": checkin.isoformat(),
        "checkout": (checkin + timedelta(days=nights)).isoformat(),
        "nights": nights,
        "outbound": out | {"cost": transport_cost(out, brief)},
        "inbound": back | {"cost": transport_cost(back, brief)},
        "hotel": card,
        "transfer_in": t_in,
        "transfer_out": t_out,
        "extras": [],
        "costs": costs,
    }
    recount(bundle, brief)
    return bundle


def recount(bundle: dict, brief: dict) -> None:
    costs = bundle["costs"]
    costs["extras"] = sum(e["price"] for e in bundle["extras"])
    bundle["total"] = sum(costs.values())
    bundle["per_person"] = inv.round_price(bundle["total"] / people(brief), 100)
    signature = json.dumps(
        [
            bundle["outbound"]["id"],
            bundle["inbound"]["id"],
            bundle["hotel"]["id"],
            bundle["hotel"]["meal"],
            bundle["hotel"]["refundable"],
            bundle["transfer_in"]["kind"],
        ]
    )
    bundle["id"] = hashlib.sha1(signature.encode()).hexdigest()[:10]


def similar(option: dict, previous: dict | None) -> float:
    """Похожесть рейса на прежний: тот же номер — 0, иначе разница во времени вылета в часах."""
    if not previous:
        return 0.0
    if option["number"] == previous["number"] and option["class"] == previous["class"]:
        return 0.0
    minutes = lambda s: int(s[11:13]) * 60 + int(s[14:16])  # noqa: E731
    return abs(minutes(option["depart"]) - minutes(previous["depart"])) / 60 + (0 if option["mode"] == previous["mode"] else 3)


def build_plan(brief: dict, dest_id: str, today: date, previous: dict | None = None, hotel_focus: bool = False) -> dict:
    """Три собранные поездки (оптимальная, экономная, комфорт) + все отели с причинами и проверка состыковок."""
    dest = destination(dest_id)
    orig = origin(brief["origin"])
    trace = []
    if distance_km(orig, dest) < 60:
        return {"error": f"Вы уже {dest['loc']} — выберите другое направление или город вылета.", "trace": trace}
    checkin, how, scan = choose_dates(brief, dest, orig, today)
    if previous and not brief["date_from"] and date.fromisoformat(previous["checkin"]).month == (brief["month"] or checkin.month):
        # даты не просили менять — оставляем прежний заезд, иначе «ребёнку 2 года» сдвигало бы поездку
        checkin, how, scan = date.fromisoformat(previous["checkin"]), "kept", []
    nights = brief["nights"]
    checkout = checkin + timedelta(days=nights)
    out_all = inv.transport_out(orig, dest, checkin)
    back_all = inv.transport_back(orig, dest, checkout)
    out_ok, relaxed_out = eligible(out_all, brief)
    back_ok, relaxed_back = eligible(back_all, brief)
    trace.append(
        {
            "tool": "search_transport",
            "title": f"Транспорт {orig['from']}",
            # после ослабления условий «подходят» — ноль: иначе след агента противоречил бы ответу
            "detail": f"туда {len(out_all)} {plural(len(out_all), 'вариант', 'варианта', 'вариантов')}, "
            f"подходят {0 if relaxed_out else len(out_ok)}; обратно {len(back_all)}, подходят {0 if relaxed_back else len(back_ok)}"
            + (f" — ослабил: {', '.join(sorted(set(relaxed_out + relaxed_back)))}" if relaxed_out or relaxed_back else ""),
        }
    )
    if not out_ok or not back_ok:
        reason = dest.get("note") or "на эти даты нет рейсов и поездов"
        return {"error": f"Не нашёл, как добраться {orig['from']} — {dest['name']}: {reason}.", "trace": trace}
    if how == "best_in_month":
        trace.append(
            {
                "tool": "pick_dates",
                "title": "Подобрал даты",
                "detail": f"сравнил {len(scan)} {plural(len(scan), 'дату', 'даты', 'дат')} заезда в {MONTHS_IN[checkin.month - 1]} — "
                f"выгоднее всего с {day_label(checkin)}",
            }
        )
    hotels_ranked, hotels_rejected = rank_hotels(brief, dest, checkin, nights)
    trace.append(
        {
            "tool": "search_hotels",
            "title": f"Отели {dest['loc']}",
            "detail": f"{len(hotels_ranked) + len(hotels_rejected)} в базе → {len(hotels_ranked)} {plural(len(hotels_ranked), 'подходит', 'подходят', 'подходят')}"
            + (
                f" (отсеял {len(hotels_rejected)}: {', '.join(sorted({r['reason'] for r in hotels_rejected})[:3])})"
                if hotels_rejected
                else ""
            ),
        }
    )
    if brief.get("diet"):
        kitchen_out = sum(1 for r in hotels_rejected if r["reason"].startswith("кухня"))
        trace.append(
            {
                "tool": "check_kitchen",
                "title": "Проверил кухню отелей",
                "detail": f"{diet_label(brief['diet'])}: подходят {len(hotels_ranked)}, не умеют {kitchen_out}",
            }
        )
    if not hotels_ranked:
        reasons = ", ".join(sorted({r["reason"] for r in hotels_rejected}))
        return {
            "error": f"{dest['loc'][0].upper()}{dest['loc'][1:]} нет отелей под ваши условия: {reasons}.",
            "error_kind": "hotels",
            "trace": trace,
        }

    cheapest_out = min(o["price"] for o in out_ok)
    cheapest_back = min(o["price"] for o in back_ok)
    by_score_out = sorted(out_ok, key=lambda o: -transport_score(o, brief, cheapest_out))
    by_score_back = sorted(back_ok, key=lambda o: -transport_score(o, brief, cheapest_back))
    prev_out = previous["outbound"] if previous else None
    prev_back = previous["inbound"] if previous else None
    # пересборка от выбранного варианта: «Экономный» и «Комфорт» остаются собой — тот же стиль, отель, питание и тариф,
    # иначе «на 2 дня позже» молча превращало выбранный план в оптимальный с другой ценой
    style = previous.get("style") if previous and previous.get("style") in ("cheap", "comfort") else "best"

    def best_transport(ranked: list[dict], prev: dict | None) -> dict:
        if not prev:
            return ranked[0]
        # из приличных — самый похожий на прежний; у «Эконома» и «Комфорта» прежний мог быть и не в верхней половине
        top = ranked if style != "best" else ranked[: max(3, len(ranked) // 2)]
        return min(top, key=lambda o: similar(o, prev))

    out_best = best_transport(by_score_out, prev_out)
    back_best = best_transport(by_score_back, prev_back)

    budget = brief["budget"]
    kept_hotel = None
    if previous:
        kept_hotel = next((e for e in hotels_ranked if e["id"] == previous["hotel"]["id"]), None)
        # прежний отель держим, пока он подходит под пожелания; если менялись именно пожелания к отелю —
        # меняем на заметно лучший (у «Оптимального» и без этого — на намного лучший)
        margin = 4 if hotel_focus else (15 if style == "best" else None)
        if kept_hotel and (
            (margin is not None and kept_hotel["value"] < hotels_ranked[0]["value"] - margin)
            or (hotels_ranked[0]["meets_prefs"] and not kept_hotel["meets_prefs"])
        ):
            kept_hotel = None
    hotel_best = kept_hotel or hotels_ranked[0]
    if previous and not kept_hotel and style == "comfort":  # прежний отель занят — замена того же уровня, а не «самый выгодный»
        hotel_best = max(hotels_ranked, key=lambda e: (e["meets_prefs"], e["fit"] + 6 * e["stars"] + 4 * e["rating"]))
    elif previous and not kept_hotel and style == "cheap":
        hotel_best = min(
            [e for e in hotels_ranked if e["fit"] >= 40 and e["rating"] >= 7.4] or hotels_ranked, key=lambda e: e["price_total"]
        )
    if budget and not kept_hotel:
        fixed = transport_cost(out_best, brief) + transport_cost(back_best, brief)
        within = [e for e in hotels_ranked if fixed + e["price_total"] <= budget * 0.97]
        if within:  # в бюджете важнее пригодность отеля, цена влияет слабее
            hotel_best = max(
                within, key=lambda e: (e["meets_prefs"], e["fit"] - 12 * brief["priorities"]["price"] * e["price_total"] / budget)
            )

    best_brief = brief
    if previous:
        best_brief = brief | {
            "meal": brief["meal"] or previous["hotel"]["meal"],
            "refundable": previous["hotel"]["refundable"] if brief["refundable"] is None else brief["refundable"],
        }
    best = assemble(best_brief, dest, checkin, out_best, back_best, hotel_best, style, "Оптимальный")
    downgrade_steps = []
    if budget and best["total"] > budget:
        best, downgrade_steps = fit_budget(best, brief, dest, checkin, by_score_out, by_score_back, hotels_ranked, budget)

    out_cheap = min(out_ok, key=lambda o: (transport_cost(o, brief), -transport_score(o, brief, cheapest_out)))
    back_cheap = min(back_ok, key=lambda o: (transport_cost(o, brief), -transport_score(o, brief, cheapest_back)))
    decent = [e for e in hotels_ranked if e["fit"] >= 40 and e["rating"] >= 7.4] or hotels_ranked
    hotel_cheap = min(decent, key=lambda e: e["price_total"])
    cheap = assemble(brief, dest, checkin, out_cheap, back_cheap, hotel_cheap, "cheap", "Экономный")

    comfort_out = max(out_ok, key=lambda o: transport_score(o, brief | {"priorities": brief["priorities"] | {"price": 0.0}}, cheapest_out))
    comfort_back = max(
        back_ok, key=lambda o: transport_score(o, brief | {"priorities": brief["priorities"] | {"price": 0.0}}, cheapest_back)
    )
    cap = budget * 1.35 if budget else None
    premium = sorted(hotels_ranked, key=lambda e: -(e["fit"] + 6 * e["stars"] + 4 * e["rating"]))
    premium = [e for e in premium if not cap or e["price_total"] <= cap] or premium
    hotel_comfort = next((e for e in premium if e["id"] != best["hotel"]["id"]), premium[0])
    comfort = assemble(brief, dest, checkin, comfort_out, comfort_back, hotel_comfort, "comfort", "Комфорт")

    bundles = [best]
    for candidate in (cheap, comfort):
        if candidate is cheap and cheap["total"] >= best["total"]:
            continue  # «экономный» не дешевле — значит, оптимальный и есть самый выгодный
        if all(candidate["id"] != b["id"] for b in bundles):
            bundles.append(candidate)
    if previous:
        best["label"] = "Ваш план"
    for bundle in bundles:
        validate(bundle, brief, dest, today)
    explain(bundles, brief, dest)
    for bundle in bundles:
        bundle["caught"] = caught(bundle, brief, out_all + back_all, hotels_ranked, hotels_rejected)
        bundle["hacks"] = find_hacks(bundle, brief, out_all, back_all, today)
    checks_fixed = sum(1 for b in bundles for c in b["checks"] if c["status"] == "fixed")
    checks_warn = sum(1 for c in bundles[0]["checks"] if c["status"] in ("warn", "error"))
    trace.append(
        {
            "tool": "assemble_trip",
            "title": f"Собрал {len(bundles)} {plural(len(bundles), 'вариант', 'варианта', 'вариантов')} поездки",
            "detail": "перелёт/поезд + отель + трансфер + питание, цена «от двери до двери»",
        }
    )
    trace.append(
        {
            "tool": "validate_itinerary",
            "title": "Проверил состыковки",
            "detail": f"прилёт → трансфер → заселение и выезд → вылет; исправил сам: {checks_fixed}, требуют внимания: {checks_warn}",
        }
    )
    hacks = list(dict.fromkeys(hack["title"] for bundle in bundles for hack in bundle["hacks"]))
    if hacks:
        trace.append({"tool": "find_hacks", "title": "Поискал неочевидное в расписаниях", "detail": "; ".join(hacks[:3])})
    return {
        "dest": dest_id,
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "nights": nights,
        "dates_how": how,
        "date_scan": scan,
        "bundles": bundles,
        "hotels": hotels_ranked[:14],
        "hotels_rejected": hotels_rejected,
        "outbound": sorted(out_all, key=lambda o: o["depart"]),
        "inbound": sorted(back_all, key=lambda o: o["depart"]),
        "relaxed": sorted(set(relaxed_out + relaxed_back)),
        "kept_hotel": bool(kept_hotel),
        "downgrade": downgrade_steps,
        "trace": trace,
    }


def date_options(brief: dict, plan: dict, selected: dict, today: date, spread: int = 3) -> list[dict]:
    """Календарь «а если сдвинуть заезд на ±3 дня»: цена от двери до двери той же поездки на каждый день.
    Считаем тем же build_plan с прежним вариантом, что и пересборка по клику, — цифры в календаре и в плане совпадут."""
    if plan.get("multi"):
        return []  # shortcut: для маршрута из нескольких мест календарь не строим — сдвиг переставил бы все части
    base = date.fromisoformat(plan["checkin"])
    days = []
    for offset in range(-spread, spread + 1):
        day = base + timedelta(days=offset)
        entry = {"date": day.isoformat(), "offset": offset, "available": False, "total": None, "delta": None, "same_hotel": None}
        if day > today:
            shifted = build_plan(brief | {"date_from": day.isoformat(), "month": day.month}, plan["dest"], today, selected)
            if shifted.get("bundles"):
                bundle = shifted["bundles"][0]
                entry |= {
                    "available": True,
                    "total": bundle["total"],
                    "delta": bundle["total"] - selected["total"],
                    "same_hotel": bundle["hotel"]["id"] == selected["hotel"]["id"],
                }
        days.append(entry)
    totals = [d["total"] for d in days if d["available"]]
    for d in days:
        d["cheapest"] = bool(totals) and d["total"] == min(totals)
    return days


def rebuild_bundle(
    brief: dict,
    plan: dict,
    bundle: dict,
    today: date,
    *,
    hotel_id: str | None = None,
    outbound_id: str | None = None,
    inbound_id: str | None = None,
    meal: str | None = None,
    refundable: bool | None = None,
    transfer_kind: str | None = None,
) -> dict:
    """Меняет одну часть поездки, остальное оставляет как было, и заново проверяет стыковки."""
    dest = destination(plan["dest"])
    checkin = date.fromisoformat(bundle["checkin"])
    out = next(o for o in plan["outbound"] if o["id"] == (outbound_id or bundle["outbound"]["id"]))
    back = next(o for o in plan["inbound"] if o["id"] == (inbound_id or bundle["inbound"]["id"]))
    target = hotel_id or bundle["hotel"]["id"]
    entry = next((e for e in plan["hotels"] if e["id"] == target), None)
    if entry is None:
        entry = next(e for e in rank_hotels(brief, dest, checkin, bundle["nights"])[0] if e["id"] == target)
    h = inv.hotel(target)
    chosen_meal = meal or (bundle["hotel"]["meal"] if bundle["hotel"]["meal"] in h["meals"] else None)
    overrides = {"meal": chosen_meal, "refundable": bundle["hotel"]["refundable"] if refundable is None else refundable}
    new = assemble(brief | overrides, dest, checkin, out, back, entry, bundle["style"], "Ваш вариант")
    kind = transfer_kind or (bundle["transfer_in"]["kind"] if not hotel_id else None)
    if kind:
        people_count, lift = people(brief), bool(brief.get("accessible"))
        options_in = inv.transfers(h, out["mode"], datetime.fromisoformat(out["arrive"]), people_count, bool(brief["pets"]), lift)
        options_out = inv.transfers(
            h, back["mode"], datetime.fromisoformat(back["depart"]) - timedelta(hours=3), people_count, bool(brief["pets"]), lift
        )
        t_in = next((o for o in options_in if o["kind"] == kind), None)
        t_out = next((o for o in options_out if o["kind"] == kind), None)
        if t_in and t_out:
            new["transfer_in"], new["transfer_out"] = t_in, t_out
            new["costs"]["transfers"] = t_in["price"] + t_out["price"]
    validate(new, brief, dest, today)
    new["hacks"] = find_hacks(new, brief, plan["outbound"], plan["inbound"], today)
    return new


def fit_budget(bundle, brief, dest, checkin, outs, backs, hotels_ranked, budget) -> tuple[dict, list[dict]]:
    """Пересборка под бюджет: сначала дешёвые уступки (тариф, трансфер, рейс), отель меняем в последнюю очередь."""
    steps = []
    current = bundle

    def attempt(candidate: dict, text: str) -> None:
        nonlocal current
        saving = current["total"] - candidate["total"]
        if saving > 0:
            steps.append({"text": text, "saving": saving})
            current = candidate

    h = inv.hotel(current["hotel"]["id"])
    out, back = current["outbound"], current["inbound"]
    entry = next(e for e in hotels_ranked if e["id"] == h["id"])
    if current["hotel"]["refundable"] and current["total"] > budget and brief["refundable"] is not True:
        candidate = assemble(brief | {"refundable": False}, dest, checkin, out, back, entry, "best", current["label"])
        attempt(candidate, "невозвратный тариф отеля")
    if current["total"] > budget and current["transfer_in"]["kind"] != "shuttle":
        candidate = assemble(
            brief | {"refundable": current["hotel"]["refundable"]}, dest, checkin, out, back, entry, "cheap", current["label"]
        )
        candidate["hotel"] = current["hotel"]
        candidate["costs"]["hotel"], candidate["costs"]["meals"] = current["costs"]["hotel"], current["costs"]["meals"]
        recount(candidate, brief)
        attempt(candidate, f"трансфер: {candidate['transfer_in']['title'].lower()}")
    if current["total"] > budget:
        out_c = min(outs, key=lambda o: transport_cost(o, brief))
        back_c = min(backs, key=lambda o: transport_cost(o, brief))
        if out_c["id"] != out["id"] or back_c["id"] != back["id"]:
            candidate = assemble(
                brief | {"refundable": current["hotel"]["refundable"]}, dest, checkin, out_c, back_c, entry, "best", current["label"]
            )
            attempt(candidate, "более дешёвые рейсы")
            out, back = current["outbound"], current["inbound"]
    if current["total"] > budget and brief["meal"] is None and inv.MEAL_RANK[current["hotel"]["meal"]] > 0:
        cheaper_meal = min(h["meals"], key=lambda m: inv.MEAL_RANK[m])
        candidate = assemble(
            brief | {"meal": cheaper_meal, "refundable": current["hotel"]["refundable"]},
            dest,
            checkin,
            out,
            back,
            entry,
            "best",
            current["label"],
        )
        attempt(candidate, f"питание: {MEAL_LABELS[cheaper_meal]}")
    if current["total"] > budget:
        transport = current["costs"]["transport"] + current["costs"]["transfers"]
        options = [e for e in hotels_ranked if transport + e["price_total"] <= budget]
        if options:
            new_entry = options[0]
            keep = {"refundable": current["hotel"]["refundable"]} | ({"meal": current["hotel"]["meal"]} if brief["meal"] is None else {})
            candidate = assemble(brief | keep, dest, checkin, out, back, new_entry, "best", current["label"])
            attempt(candidate, f"отель «{new_entry['name']}» вместо «{entry['name']}»")
    return current, steps


# ── Проверка состыковок ─────────────────────────────────────────────────────


def _at(day: str, clock: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{clock}")


def _add_extra(bundle: dict, extra: dict) -> None:
    # validate зовут повторно (финальная проверка перед оплатой) — та же доплата не должна попасть в итог дважды
    if all(e["type"] != extra["type"] for e in bundle["extras"]):
        bundle["extras"].append(extra)


def validate(bundle: dict, brief: dict, dest: dict, today: date) -> None:
    """Проверяет стыки поездки. Мелкое исправляет сам (ранний заезд, ночное такси), остальное — предлагает."""
    checks = []
    h = bundle["hotel"]
    hotel_raw = inv.hotel(h["id"])
    out, back = bundle["outbound"], bundle["inbound"]
    foreign = dest["country"] not in RAIL_COUNTRIES
    arrive = datetime.fromisoformat(out["arrive"])
    extra_min = (40 if foreign and out["mode"] == "flight" else 15) + (60 if dest["id"] == "abkhazia" else 0)
    at_hotel = arrive + timedelta(minutes=bundle["transfer_in"]["duration_min"] + extra_min)
    checkin_at = _at(bundle["checkin"], h["checkin"])
    night_price = h["price_total"] / bundle["nights"]

    if out["arrive"][:10] != bundle["checkin"] or back["depart"][:10] != bundle["checkout"]:
        checks.append(
            {"id": "dates", "status": "error", "title": "Даты не сходятся", "detail": "транспорт и отель на разные дни", "fix": None}
        )
    else:
        checks.append(
            {
                "id": "dates",
                "status": "ok",
                "title": "Даты сходятся",
                "detail": f"прибытие {day_label(arrive.date())}, выезд {day_label(date.fromisoformat(bundle['checkout']))}",
                "fix": None,
            }
        )

    wait = (checkin_at - at_hotel).total_seconds() / 3600
    route = f"прибытие в {time_of(out['arrive'])} → {bundle['transfer_in']['title'].lower()} {hours_label(bundle['transfer_in']['duration_min'])} → в отеле около {at_hotel:%H:%M}"
    if wait <= 0:
        checks.append({"id": "checkin", "status": "ok", "title": "Заселение сразу", "detail": route, "fix": None})
    elif wait <= 2.5:
        checks.append(
            {
                "id": "checkin",
                "status": "ok",
                "title": f"Заселение в {h['checkin']}",
                "detail": f"{route}; подождать {hours_label(wait * 60)}, багаж оставить на ресепшене",
                "fix": None,
            }
        )
    else:
        early_price = inv.round_price(night_price * 0.5, 50)
        prev_night_price = inv.round_price(night_price, 50)
        if at_hotel.hour < 8 or wait >= 6:
            # ночное или утреннее прибытие: агент сам решает, чтобы люди не сидели в лобби
            if at_hotel.hour >= 6 and hotel_raw["features"]["early_checkin"]:
                extra = {"type": "early_checkin", "title": f"Ранний заезд к {at_hotel:%H:%M}", "price": early_price}
            else:
                extra = {"type": "extra_night", "title": "Номер с ночи прилёта", "price": prev_night_price}
            _add_extra(bundle, extra)
            checks.append(
                {
                    "id": "checkin",
                    "status": "fixed",
                    "title": "Прибытие задолго до заселения — исправил",
                    "detail": f"{route}, а заселение в {h['checkin']} — пришлось бы ждать {hours_label(wait * 60)}. "
                    f"Добавил: {extra['title'].lower()} за {money(extra['price'])}",
                    "fix": None,
                }
            )
        else:
            checks.append(
                {
                    "id": "checkin",
                    "status": "warn",
                    "title": f"Ожидание заселения {hours_label(wait * 60)}",
                    "detail": f"{route}, заселение в {h['checkin']}",
                    "fix": {"type": "early_checkin", "label": f"Ранний заезд за {money(early_price)}", "price": early_price}
                    if hotel_raw["features"]["early_checkin"]
                    else None,
                }
            )

    if arrive.hour >= 22 or arrive.hour < 7:
        checks.append(
            {
                "id": "night_transfer",
                "status": "ok",
                "title": "Ночной трансфер учтён",
                "detail": "групповые трансферы ночью не ходят — заложил " + bundle["transfer_in"]["title"].lower(),
                "fix": None,
            }
        )

    depart = datetime.fromisoformat(back["depart"])
    buffer = 120 if back["mode"] == "flight" and foreign else 90 if back["mode"] == "flight" else 40
    leave = depart - timedelta(minutes=buffer + bundle["transfer_out"]["duration_min"] + (60 if dest["id"] == "abkhazia" else 0))
    checkout_at = _at(bundle["checkout"], h["checkout"])
    idle = (leave - checkout_at).total_seconds() / 3600
    leave_text = f"выезд из отеля в {leave:%H:%M}, {('рейс' if back['mode'] == 'flight' else 'поезд')} в {time_of(back['depart'])}"
    if leave < _at(bundle["checkout"], "05:00"):
        lost = leave < _at(bundle["checkout"], "00:00")
        checks.append(
            {
                "id": "checkout",
                "status": "warn",
                "title": "Ночной выезд",
                "detail": leave_text
                + (" — уезжать накануне вечером, последняя оплаченная ночь пропадает" if lost else " — придётся встать ночью")
                + (", с ребёнком тяжело" if brief["children"] else ""),
                "fix": {"type": "swap_inbound", "label": "Подобрать рейс позже", "price": 0},
            }
        )
    elif idle > 4:
        late_price = inv.round_price(night_price * 0.5, 50)
        if brief["children"] and hotel_raw["features"]["late_checkout"]:
            _add_extra(bundle, {"type": "late_checkout", "title": f"Поздний выезд до {min(leave.hour, 20)}:00", "price": late_price})
            checks.append(
                {
                    "id": "checkout",
                    "status": "fixed",
                    "title": "Долго ждать вылета — исправил",
                    "detail": f"выселение в {h['checkout']}, а {leave_text}. С ребёнком добавил поздний выезд за {money(late_price)}",
                    "fix": None,
                }
            )
        else:
            checks.append(
                {
                    "id": "checkout",
                    "status": "warn",
                    "title": f"После выселения {hours_label(idle * 60)} до выезда",
                    "detail": f"выселение в {h['checkout']}, {leave_text}",
                    "fix": {"type": "late_checkout", "label": f"Поздний выезд за {money(late_price)}", "price": late_price}
                    if hotel_raw["features"]["late_checkout"]
                    else None,
                }
            )
    else:
        checks.append({"id": "checkout", "status": "ok", "title": "Выезд без спешки", "detail": leave_text, "fix": None})

    if brief["children"] and (out["night"] or back["night"]):
        checks.append(
            {
                "id": "night_kids",
                "status": "warn",
                "title": "Ночной рейс с ребёнком",
                "detail": "дневных рейсов на эти даты нет",
                "fix": None,
            }
        )
    if brief["pets"]:
        ok = h["features"]["pets"] and out["pets_cabin"] and back["pets_cabin"]
        checks.append(
            {
                "id": "pets",
                "status": "ok" if ok else "error",
                "title": "Питомец" + (" — всё можно" if ok else " — проблема"),
                "detail": "отель принимает животных, перевозка в салоне до 8 кг" if ok else "отель или перевозчик не принимает животных",
                "fix": None,
            }
        )
    if brief.get("accessible"):
        checks += access_checks(bundle)
    visa = dest["visa"]
    days_left = (date.fromisoformat(bundle["checkin"]) - today).days
    if "шенген" in visa:
        checks.append(
            {
                "id": "visa",
                "status": "error" if days_left < 45 else "warn",
                "title": "Нужна шенгенская виза",
                "detail": f"до поездки {days_left} {plural(days_left, 'день', 'дня', 'дней')}"
                + (" — можно не успеть" if days_left < 45 else " — подавайте документы сейчас"),
                "fix": None,
            }
        )
    elif "нужна виза" in visa or "уточните" in visa:
        checks.append({"id": "visa", "status": "warn", "title": "Виза", "detail": visa, "fix": None})
    elif "электрон" in visa or "прибыт" in visa:
        checks.append({"id": "visa", "status": "ok", "title": "Виза", "detail": visa, "fix": None})
    if brief["budget"]:
        recount(bundle, brief)
        over = bundle["total"] - brief["budget"]
        checks.append(
            {
                "id": "budget",
                "status": "ok" if over <= 0 else "warn",
                "title": "В бюджете" if over <= 0 else f"Дороже бюджета на {money(over)}",
                "detail": f"{money(bundle['total'])} из {money(brief['budget'])}",
                "fix": None if over <= 0 else {"type": "cheaper", "label": "Уложиться в бюджет", "price": 0},
            }
        )
    if brief["max_hours"] and out["mode"] == "flight" and out["duration_min"] > brief["max_hours"] * 60:
        checks.append(
            {
                "id": "hours",
                "status": "warn",
                "title": f"В пути {hours_label(out['duration_min'])}",
                "detail": f"хотели до {brief['max_hours']:g} ч — быстрее вариантов нет",
                "fix": None,
            }
        )
    if dest.get("note"):
        checks.append({"id": "route_note", "status": "ok", "title": "Маршрут", "detail": dest["note"], "fix": None})
    month = date.fromisoformat(bundle["checkin"]).month
    weather = climate(dest, month)
    if weather["rain"] is not None and weather["rain"] >= 10:
        checks.append(
            {
                "id": "rain",
                "status": "warn",
                "title": "Дождливо",
                "detail": f"в {MONTHS_IN[month - 1]} около {weather['rain']} дней с ливнями — закладывайте планы под крышей",
                "fix": None,
            }
        )
    if (
        "sea" in dest["kinds"]
        and weather["water"] is not None
        and weather["water"] < 21
        and ("sea" in brief["kinds"] or not brief["kinds"])
    ):
        checks.append(
            {"id": "water", "status": "warn", "title": f"Вода +{weather['water']}°", "detail": "для купания прохладно", "fix": None}
        )
    bundle["checks"] = checks
    recount(bundle, brief)


def access_checks(bundle: dict) -> list[dict]:
    """Гость на коляске: перевозчика предупреждаем заранее, пересадку и трансфер без подъёмника — показываем."""
    out = bundle["outbound"]
    flight = out["mode"] == "flight"
    who = f"авиакомпанию «{out['carrier']}»" if flight else f"перевозчика поезда {out['number']}"
    service = "кресло-коляска до борта и помощь при посадке" if flight else "место для коляски и помощь при посадке"
    checks = []
    hop = next((t for t in (out, bundle["inbound"]) if t["stops"]), None)
    if hop:
        checks.append(
            {
                "id": "assist",
                "status": "warn",
                "title": "Пересадка с коляской",
                "detail": f"прямых рейсов на эти даты нет: пересадка в {hop['via']}, {hours_label(hop['layover_min'])} — помощь на пересадке тоже закажу",
                "fix": None,
            }
        )
    else:
        checks.append(
            {
                "id": "assist",
                "status": "ok",
                "title": "Помощь в пути",
                "detail": f"при оформлении предупрежу {who}: {service} — бесплатно, своё кресло сдаётся в багаж бесплатно",
                "fix": None,
            }
        )
    lift = bundle["transfer_in"]["kind"] == "accessible"
    checks.append(
        {
            "id": "lift",
            "status": "ok" if lift else "warn",
            "title": "Трансфер с подъёмником" if lift else "Трансфер без подъёмника",
            "detail": "минивэн с подъёмником и креплением для коляски, туда и обратно"
            if lift
            else f"{bundle['transfer_in']['title'].lower()}: коляска поместится не во всякую машину",
            "fix": None,
        }
    )
    return checks


# ── Объяснения ──────────────────────────────────────────────────────────────


VIOLATION_LABELS = {
    "ночной рейс": "ночные рейсы",
    "с пересадкой": "с пересадками",
    "нельзя с животным": "питомца не берут в салон",
    "хотели поездом": "не поезд",
    "хотели самолётом": "не самолёт",
    "сидячий вагон надолго": "долго в сидячем вагоне",
}


def caught(bundle: dict, brief: dict, transport: list[dict], hotels_ranked: list[dict], hotels_rejected: list[dict]) -> list[dict]:
    """«Что агент поймал за вас»: то, что пользователь заметил бы только в дороге или не заметил бы вовсе.
    Всё из уже посчитанного: исправленные стыковки, отсеянная дорога и отели, ловушка «дешёвый отель дороже»."""
    items = [
        {"kind": "fixed", "title": check["title"], "detail": check["detail"]} for check in bundle["checks"] if check["status"] == "fixed"
    ]
    trap = _cheap_hotel_trap(bundle, brief, hotels_ranked)
    if trap:
        items.append(trap)

    def label(reason: str) -> str:  # «в пути 10 ч 11 мин» у каждого рейса своё — сводим к условию пользователя
        return f"дольше {brief['max_hours']:g} ч в пути" if reason.startswith("в пути") else VIOLATION_LABELS.get(reason, reason)

    # условие, которое в выбранном варианте пришлось уступить, «пойманным» не называем — это было бы неправдой
    relaxed = {label(r) for t in (bundle["outbound"], bundle["inbound"]) for r in transport_violations(t, brief)}
    reasons: dict[str, int] = {}
    for option in transport:
        for reason in map(label, transport_violations(option, brief)):
            if reason not in relaxed:
                reasons[reason] = reasons.get(reason, 0) + 1
    for reason, count in sorted(reasons.items(), key=lambda r: -r[1])[:2]:
        items.append(
            {"kind": "filtered", "title": f"Отсеял {count} {plural(count, 'вариант', 'варианта', 'вариантов')} дороги", "detail": reason}
        )
    by_reason: dict[str, int] = {}
    for hotel in hotels_rejected:
        if hotel["reason"] != "нет мест на ваши даты":  # занятость — не забота о вас, а наличие
            by_reason[hotel["reason"]] = by_reason.get(hotel["reason"], 0) + 1
    for reason, count in sorted(by_reason.items(), key=lambda r: -r[1])[:2]:
        items.append({"kind": "filtered", "title": f"Убрал {count} {plural(count, 'отель', 'отеля', 'отелей')}", "detail": reason})
    return items[:5]


def _cheap_hotel_trap(bundle: dict, brief: dict, hotels_ranked: list[dict]) -> dict | None:
    """Отель дешевле нашего, но дальше от аэропорта: с трансферами туда и обратно выходит дороже. Пример из ТЗ."""
    if bundle["outbound"]["mode"] != "flight" or bundle["transfer_in"]["kind"] == "shuttle":
        return None  # к вокзалу и с групповым трансфером разница по расстоянию почти не видна
    ours = bundle["hotel"]["price_total"] + bundle["costs"]["transfers"]
    arrive = datetime.fromisoformat(bundle["outbound"]["arrive"])
    worst = None
    for entry in hotels_ranked:
        if entry["id"] == bundle["hotel"]["id"] or entry["price_total"] >= bundle["hotel"]["price_total"]:
            continue
        options = inv.transfers(inv.hotel(entry["id"]), "flight", arrive, people(brief), bool(brief["pets"]), bool(brief.get("accessible")))
        same = next((o for o in options if o["kind"] == bundle["transfer_in"]["kind"]), None)
        if not same:
            continue
        theirs = entry["price_total"] + 2 * same["price"]
        if theirs > ours and (worst is None or theirs - ours > worst[1]):
            worst = (entry, theirs - ours, 2 * same["price"] - bundle["costs"]["transfers"])
    if not worst:
        return None
    entry, extra, transfer_extra = worst
    saving = bundle["hotel"]["price_total"] - entry["price_total"]
    return {
        "kind": "trap",
        "title": f"«{entry['name']}» дешевле на {money(saving)}, но в итоге дороже",
        "detail": f"до аэропорта {inv.hotel(entry['id'])['airport_km']} км: трансферы +{money(transfer_extra)} — переплата {money(extra)}",
    }


def explain(bundles: list[dict], brief: dict, dest: dict) -> None:
    """Почему этот вариант, чем пожертвовали и какие риски — относительно соседних вариантов."""
    cheapest = min(b["total"] for b in bundles)
    best = bundles[0]
    for bundle in bundles:
        h = bundle["hotel"]
        why = [transport_pros(bundle["outbound"])] + h["pros"][:4]
        if brief["budget"] and bundle["total"] <= brief["budget"]:
            why.append(f"укладывается в бюджет: {money(bundle['total'])} из {money(brief['budget'])}")
        sacrifices = list(h["cons"][:3])
        if not h["refundable"]:
            sacrifices.append("невозвратный тариф — дешевле, но без бесплатной отмены")
        if bundle["outbound"]["stops"]:
            sacrifices.append(f"пересадка в {bundle['outbound']['via']}, ожидание {hours_label(bundle['outbound']['layover_min'])}")
        if bundle["outbound"]["mode"] == "flight" and not bundle["outbound"]["baggage"]:
            sacrifices.append("тариф без багажа — только ручная кладь")
        if bundle["transfer_in"]["kind"] == "shuttle":
            sacrifices.append("групповой трансфер — дольше, с остановками у других отелей")
        if bundle["total"] > cheapest:
            sacrifices.append(f"на {money(bundle['total'] - cheapest)} дороже самого экономного варианта")
        if bundle is not best and h["id"] != best["hotel"]["id"] and h["fit"] < best["hotel"]["fit"]:
            sacrifices.append(f"отель подходит хуже оптимального: {h['fit']} против {best['hotel']['fit']} баллов из 100")
        risks = [f"{c['title']}: {c['detail']}" for c in bundle["checks"] if c["status"] in ("warn", "error")]
        bundle["why"] = why
        bundle["sacrifices"] = sacrifices
        bundle["risks"] = risks
        bundle["fit"] = h["fit"]


# ── Направления ─────────────────────────────────────────────────────────────


def diet_share(dest_id: str, diets: list[str]) -> float:
    """Доля отелей направления, где кухня умеет всё нужное. Без особого питания — все."""
    if not diets:
        return 1.0
    hotels = inv.hotels(dest_id)
    return sum(all(h["diets"].get(d) for d in diets) for h in hotels) / len(hotels)


def region_ok(dest: dict, regions: list[str]) -> bool:
    if not regions:
        return True
    russian = dest["country"] in ("Россия", "Россия (Крым)")
    for region in regions:
        if region == "russia" and russian:
            return True
        if region == "abroad" and not russian:
            return True
        if dest["id"] in REGION_MEMBERS.get(region, ()):
            return True
    return False


def suggest_destinations(brief: dict, today: date, limit: int = 4) -> dict:
    """Вдохновение: какие направления подходят под месяц, состав, бюджет и ограничения — и почему."""
    month = brief["month"] or (date.fromisoformat(brief["date_from"]).month if brief["date_from"] else (today + timedelta(days=30)).month)
    orig = origin(brief["origin"])
    wanted = set(brief["kinds"]) - {"family", "allinclusive"}
    year = today.year if month >= today.month else today.year + 1
    probe = max(date(year, month, 15), today + timedelta(days=5))
    if probe.month != month:
        probe = date(year + 1, month, 15)
    scored, rejected = [], []
    for dest in destinations().values():
        if dest.get("dynamic") or dest["id"] in brief["exclude"] or distance_km(orig, dest) < 60:
            continue  # найденные на лету — только по прямому запросу, в подборку попадают проверенные
        if not region_ok(dest, brief["regions"]):
            continue
        c = climate(dest, month)
        reasons, cons = [], []
        reject = None
        hard = wanted & HARD_KINDS
        matched = wanted & set(dest["kinds"])
        if hard and not hard <= set(dest["kinds"]):
            reject = "нет " + " и ".join({"sea": "моря", "ski": "горнолыжных трасс"}[k] for k in hard - set(dest["kinds"]))
        sea = "sea" in dest["kinds"] and ("sea" in wanted or not wanted)
        if not reject and "ski" in wanted and month not in (12, 1, 2, 3, 4):
            reject = "не сезон для лыж"
        if not reject and sea and c["water"] is not None and ("sea" in wanted or brief["warm"]):
            if c["water"] < (23 if brief["warm"] else 21):
                reject = f"в {MONTHS_IN[month - 1]} вода +{c['water']}° — прохладно"
        if not reject and brief["warm"] and c["air"] is not None and c["air"] < 23:
            reject = f"в {MONTHS_IN[month - 1]} днём около +{c['air']}° — не тепло"
        if not reject and brief["visa_free"] and ("шенген" in dest["visa"] or "электрон" in dest["visa"]):
            reject = "нужна виза"
        if not reject and brief.get("accessible") and accessible_share(dest["id"]) < 0.15:
            reject = "почти нет отелей с доступной средой"
        if not reject and brief["pets"] and dest["pets"] < 0.15:
            reject = "почти нет отелей, куда можно с животными"
        diet_ok = diet_share(dest["id"], brief.get("diet") or [])
        if not reject and diet_ok < 0.15:
            reject = f"почти нет отелей, где кухня готовит: {diet_label(brief['diet'])}"
        if (
            not reject
            and brief["transport"] == "train"
            and not (orig.get("train") and dest.get("train") and dest["country"] in RAIL_COUNTRIES)
        ):
            reject = "поездом не добраться"
        if reject:
            # в «почему не туда» — только то, что могло подойти: нужный тип отдыха есть, но мешает погода, виза и т. п.
            if (matched and hard <= set(dest["kinds"])) or (not wanted and dest["direct"] == "all"):
                rejected.append({"id": dest["id"], "name": dest["name"], "reason": reject})
            continue
        options, relaxed = eligible(inv.transport_out(orig, dest, probe), brief)
        if not options:
            continue
        fastest = min(options, key=lambda o: o["duration_min"])
        if relaxed:
            if any("в пути" in r for r in relaxed):
                rejected.append(
                    {
                        "id": dest["id"],
                        "name": dest["name"],
                        "reason": f"дорога {hours_label(fastest['duration_min'])} — дольше, чем хотели",
                    }
                )
                continue
            if "хотели поездом" in relaxed:
                rejected.append({"id": dest["id"], "name": dest["name"], "reason": "поездом слишком далеко"})
                continue
            cons.append("транспорт: " + ", ".join(relaxed))
        back = eligible(inv.transport_back(orig, dest, probe + timedelta(days=brief["nights"])), brief)[0] or options
        transport = min(transport_cost(o, brief) for o in options) + min(transport_cost(o, brief) for o in back)
        hotel_prices = sorted(h["price_night"] for h in inv.hotels(dest["id"]))
        rooms = inv.rooms_for(brief["adults"], brief["children"])
        season = season_factor(dest, month)
        low = transport + hotel_prices[2] * season * brief["nights"] * rooms
        mid = transport * 1.15 + statistics.median(hotel_prices) * season * brief["nights"] * rooms
        estimate_low, estimate_mid = inv.round_price(low, 1000), inv.round_price(mid, 1000)
        if brief["budget"] and estimate_low > brief["budget"] * 1.1:
            rejected.append({"id": dest["id"], "name": dest["name"], "reason": f"от {money(estimate_low)} — дороже бюджета"})
            continue

        score = 3.0 * len(matched) - (2.0 if wanted and not matched else 0)
        if sea and c["water"] is not None:
            score += min(c["water"], 28) / 4 - 4
            reasons.append(f"вода +{c['water']}°, воздух +{c['air']}°")
        elif c["air"] is not None:
            comfy = 1.5 if 18 <= c["air"] <= 28 else 0 if 8 <= c["air"] <= 32 else -1
            if "ski" in wanted:
                comfy = 1.5 if c["air"] <= 2 else -1
            score += comfy
            reasons.append(f"днём около {'+' if c['air'] > 0 else ''}{c['air']}°")
        if c["rain"] is not None:
            if c["rain"] >= 10:
                score -= 2.5
                cons.append(f"около {c['rain']} дней с ливнями")
            elif c["rain"] <= 2:
                score += 0.5
                reasons[-1] += ", дождей почти нет"
        hours = fastest["duration_min"] / 60
        short_trip = 2.0 if brief["nights"] <= 3 else 1.0  # на выходные долгая дорога съедает отдых
        score -= hours * (0.25 + 0.4 * brief["priorities"]["speed"]) * short_trip
        travel = (
            "прямой рейс "
            if fastest["mode"] == "flight" and not fastest["stops"]
            else "поезд "
            if fastest["mode"] == "train"
            else "с пересадкой, "
        ) + hours_label(fastest["duration_min"])
        reasons.append(travel)
        if brief["children"]:
            score += 3 * dest["kids"]
            if dest["kids"] >= 0.8:
                reasons.append("много отелей с детскими клубами")
        if brief["budget_level"] == "low" or brief["priorities"]["price"] > 0.7:
            score -= estimate_low / 100000 * 2.5
        elif brief["budget"]:
            score -= max(0, estimate_mid - brief["budget"]) / brief["budget"] * 4
        if brief["budget_level"] == "high":
            score += dest["price"] / 5000
        if "не нужна" in dest["visa"]:
            reasons.append("без визы")
        elif "прибыт" in dest["visa"] or "бесплатно" in dest["visa"]:
            reasons.append(f"виза: {dest['visa']}")
        else:
            cons.append(f"виза: {dest['visa']}")
            score -= 1.5
        if dest.get("note"):
            cons.append(dest["note"])
        if brief.get("diet"):
            score += 2 * diet_ok
            if diet_ok >= 0.6:
                reasons.append(f"кухня: {diet_label(brief['diet'])} — в большинстве отелей")
        score += season - 1
        for kind in matched:
            reasons.append(KIND_LABELS[kind])
        scored.append(
            {
                "id": dest["id"],
                "name": dest["name"],
                "country": dest["country"],
                "loc": dest["loc"],
                "score": round(score, 2),
                "why": reasons[:5],
                "cons": cons,
                "highlights": dest["highlights"],
                "weather": c,
                "travel": {"mode": fastest["mode"], "minutes": fastest["duration_min"], "stops": fastest["stops"]},
                "visa": dest["visa"],
                "price_from": estimate_low,
                "price_mid": estimate_mid,
                "kinds": dest["kinds"],
            }
        )
    scored.sort(key=lambda s: -s["score"])
    shown_ids = {s["id"] for s in scored[:limit]}
    popular_rejected = [r for r in rejected if r["id"] not in shown_ids]
    # сначала места, подходящие по погоде и типу отдыха, но отсеянные другим условием — это самое полезное «почему не»
    weather = ("прохладно", "не тепло", "нет моря", "нет горнолыжных", "не сезон")
    popular_rejected.sort(key=lambda r: (any(w in r["reason"] for w in weather), destinations()[r["id"]]["direct"] != "all"))
    return {
        "month": month,
        "checked": sum(1 for d in destinations().values() if not d.get("dynamic")),
        "items": scored[:limit],
        "more": scored[limit : limit + 4],
        "rejected": popular_rejected[:4],
    }


# ── Diff ────────────────────────────────────────────────────────────────────


def describe_transport(option: dict) -> str:
    return f"{option['number']}, {time_of(option['depart'])} → {time_of(option['arrive'])}, {money(option['cost'])}"


def split_nights(total: int, count: int, given: list[int | None]) -> list[int]:
    """Ночи по городам: что названо — как названо, остальное делим поровну, минимум 2 ночи на город."""
    given = (list(given) + [None] * count)[:count]
    named = sum(n for n in given if n)
    free = [i for i, n in enumerate(given) if not n]
    rest = max(total - named, 2 * len(free))
    result = list(given)
    for position, index in enumerate(free):
        result[index] = rest // len(free) + (1 if position < rest % len(free) else 0)
    return [max(1, int(n)) for n in result]


def build_route(brief: dict, route: list[str], today: date, given_nights: list[int | None] | None = None) -> dict:
    """Поездка в несколько мест: каждая часть — полноценный вариант (отель, трансферы, проверка стыковок),
    между городами — переезд. Цена переезда считается один раз — в той части, откуда уезжаем."""
    dests = [destination(d) for d in route]
    orig = origin(brief["origin"])
    nights = split_nights(max(brief["nights"], 2 * len(route)), len(route), given_nights or [])
    trace = []
    checkin, how, scan = choose_dates(brief | {"nights": sum(nights)}, dests[0], orig, today)
    legs: list[dict] = []
    cursor = checkin
    arrival = None
    for index, dest in enumerate(dests):
        leg_brief = brief | {"nights": nights[index], "destination": dest["id"]}
        checkout = cursor + timedelta(days=nights[index])
        if index == 0:
            arrivals, _ = eligible(inv.transport_out(orig, dest, cursor), leg_brief)
            if not arrivals:
                return {"error": f"Не нашёл, как добраться {orig['from']} — {dest['name']}.", "trace": trace}
            cheapest = min(o["price"] for o in arrivals)
            arrival = max(arrivals, key=lambda o: transport_score(o, leg_brief, cheapest))
        last = index == len(dests) - 1
        options = inv.transport_back(orig, dest, checkout) if last else inv.connections(dest, dests[index + 1], checkout)
        departures, _ = eligible(options, leg_brief)
        if not departures:
            where = f"обратно {orig['from'][3:]}" if last else f"{dest['name']} → {dests[index + 1]['name']}"
            return {"error": f"Не нашёл переезд {where} на {day_label(checkout)}.", "trace": trace}
        cheapest = min(o["price"] for o in departures)
        departure = max(departures, key=lambda o: transport_score(o, leg_brief, cheapest))
        hotels_ranked, _ = rank_hotels(leg_brief, dest, cursor, nights[index])
        if not hotels_ranked:
            return {"error": f"{dest['loc'][0].upper()}{dest['loc'][1:]} нет отелей под ваши условия.", "trace": trace}
        leg = assemble(leg_brief, dest, cursor, arrival, departure, hotels_ranked[0], "best", dest["name"])
        if index > 0:  # переезд сюда уже оплачен в предыдущей части
            leg["costs"]["transport"] -= leg["outbound"]["cost"]
            leg["outbound"] = leg["outbound"] | {"cost": 0, "included": True}
            recount(leg, leg_brief)
        validate(leg, leg_brief, dest, today)
        explain([leg], leg_brief, dest)
        legs.append(leg)
        hop = departure if not last else None
        trace.append(
            {
                "tool": "assemble_trip",
                "title": f"Часть {index + 1}: {dest['name']}, {nights[index]} {plural(nights[index], 'ночь', 'ночи', 'ночей')}",
                "detail": f"{leg['hotel']['name']} {leg['hotel']['stars']}★"
                + (f"; дальше: {transport_pros(hop)}" if hop else f"; домой: {transport_pros(departure)}"),
            }
        )
        arrival, cursor = departure, checkout
    combined = combine_route(legs, brief)
    fixed = sum(1 for c in combined["checks"] if c["status"] == "fixed")
    warn = sum(1 for c in combined["checks"] if c["status"] in ("warn", "error"))
    trace.append(
        {
            "tool": "validate_itinerary",
            "title": "Проверил стыковки всего маршрута",
            "detail": f"исправил сам: {fixed}, требуют внимания: {warn}",
        }
    )
    return {
        "multi": True,
        "route": route,
        "dest": route[0],
        "checkin": checkin.isoformat(),
        "checkout": cursor.isoformat(),
        "nights": sum(nights),
        "dates_how": how,
        "date_scan": scan,
        "bundles": [combined],
        "hotels": [],
        "hotels_rejected": [],
        "outbound": [],
        "inbound": [],
        "relaxed": [],
        "downgrade": [],
        "kept_hotel": False,
        "trace": trace,
    }


def combine_route(legs: list[dict], brief: dict) -> dict:
    """Части маршрута → одна поездка для корзины, сравнения и брони; сами части лежат в legs."""
    first, last = legs[0], legs[-1]
    combined = copy.deepcopy(first)
    combined.update(
        label="Маршрут",
        style="route",
        dest_name=" → ".join(leg["dest_name"] for leg in legs),
        checkout=last["checkout"],
        nights=sum(leg["nights"] for leg in legs),
        inbound=last["inbound"],
        transfer_out=last["transfer_out"],
        legs=legs,
        extras=[extra for leg in legs for extra in leg["extras"]],
        costs={key: sum(leg["costs"][key] for leg in legs) for key in first["costs"]},
        checks=[
            check | {"id": f"{i}-{check['id']}", "title": f"{leg['dest_name']}: {check['title']}"}
            for i, leg in enumerate(legs)
            for check in leg["checks"]
        ],
        why=[
            f"{leg['dest_name']}, {leg['nights']} ноч.: {leg['hotel']['name']} {leg['hotel']['stars']}★, {leg['hotel']['meal_label']}"
            for leg in legs
        ],
        sacrifices=[s for leg in legs for s in leg["sacrifices"][:2]],
        risks=[r for leg in legs for r in leg["risks"]],
        fit=round(sum(leg["fit"] for leg in legs) / len(legs)),
    )
    combined["dest_info"] = first["dest_info"] | {"route": [leg["dest_name"] for leg in legs]}
    recount(combined, brief)
    return combined


def diff(old: dict, new: dict) -> dict:
    """Что изменилось после пересборки: по частям поездки и в итоге."""
    changes, kept = [], []

    def compare(part: str, before: str, after: str, delta: int | None) -> None:
        if before == after:
            kept.append(part)
        else:
            changes.append({"part": part, "before": before, "after": after, "delta": delta})

    period = lambda b: f"{day_label(date.fromisoformat(b['checkin']))} – {day_label(date.fromisoformat(b['checkout']))}"  # noqa: E731
    compare("Даты", period(old), period(new), None)
    compare(
        "Туда", describe_transport(old["outbound"]), describe_transport(new["outbound"]), new["outbound"]["cost"] - old["outbound"]["cost"]
    )
    old_h, new_h = old["hotel"], new["hotel"]
    hotel_text = lambda h: f"«{h['name']}» {h['stars']}★, {h['meal_label']}" + ("" if h["refundable"] else ", невозвратный")  # noqa: E731
    compare(
        "Отель",
        hotel_text(old_h),
        hotel_text(new_h),
        (new["costs"]["hotel"] + new["costs"]["meals"]) - (old["costs"]["hotel"] + old["costs"]["meals"]),
    )
    compare("Трансфер", old["transfer_in"]["title"], new["transfer_in"]["title"], new["costs"]["transfers"] - old["costs"]["transfers"])
    compare(
        "Обратно", describe_transport(old["inbound"]), describe_transport(new["inbound"]), new["inbound"]["cost"] - old["inbound"]["cost"]
    )
    extras = lambda b: ", ".join(e["title"] for e in b["extras"]) or "нет"  # noqa: E731
    compare("Доплаты", extras(old), extras(new), new["costs"]["extras"] - old["costs"]["extras"])
    return {
        "changes": changes,
        "kept": kept,
        "total_before": old["total"],
        "total_after": new["total"],
        "delta": new["total"] - old["total"],
        "same_hotel": old_h["id"] == new_h["id"],
    }


# ── Лайфхаки ────────────────────────────────────────────────────────────────

# транзитные хабы, куда гражданам РФ виза не нужна: город и дорога от аэропорта до центра, мин
TRANSIT_CITIES = {"Стамбуле": 60, "Дубае": 20, "Дохе": 20, "Бангкоке": 45, "Белграде": 25}


def find_hacks(bundle: dict, brief: dict, outbound: list[dict], inbound: list[dict], today: date) -> list[dict]:
    """Неочевидное, что агент нашёл в расписаниях, которые уже собрал: ночь в поезде вместо отеля,
    город на длинной пересадке, полдня на месте за рейс попозже. У каждого — что сделать одной кнопкой."""
    if bundle.get("legs"):
        return []  # shortcut: у маршрута из нескольких мест лайфхаки не ищем
    found = [_night_train_hack(bundle, brief, today), _layover_hack(bundle, brief, outbound), _later_return_hack(bundle, brief, inbound)]
    return [hack for hack in found if hack]


def night_train(orig: dict, dest: dict, day: date) -> dict | None:
    """Ночной поезд обратно: уходит около 23:00, приходит утром. Только для ночных расстояний по рельсам."""
    if not (orig.get("train") and dest.get("train") and dest["country"] in RAIL_COUNTRIES):
        return None
    km = distance_km(orig, dest) * 1.3
    if not 450 <= km <= 1000:
        return None
    r = inv.rng("night-train", orig["id"], dest["id"], day.isoformat())
    depart = datetime.combine(day, datetime.min.time()) + timedelta(hours=22, minutes=r.choice([20, 35, 50, 65, 85]))
    minutes = min(max(round(km / 95 * 60), 420), 570)  # ночной идёт медленнее дневного — чтобы прийти утром, а не в 4 часа
    arrive = depart + timedelta(minutes=minutes, hours=orig["tz"] - dest["tz"])
    early = datetime.combine(day + timedelta(days=1), datetime.min.time()) + timedelta(hours=6, minutes=30) - arrive
    if early.total_seconds() > 0:  # короткое плечо: отправляемся позже, но до полуночи — приезд не раньше 6:30
        shift = min(early, datetime.combine(day, datetime.min.time()) + timedelta(hours=23, minutes=55) - depart)
        depart, arrive = depart + shift, arrive + shift
    return {
        "id": f"N-{orig['id']}-{dest['id']}-{day:%Y%m%d}-back",
        "mode": "train",
        "carrier": "Ночной экспресс",
        "number": f"№ {r.randint(1, 60):03d}{r.choice('АМЧ')}",
        "from": dest["name"],
        "to": orig["name"],
        "depart": inv.iso(depart),
        "arrive": inv.iso(arrive),
        "duration_min": minutes,
        "stops": 0,
        "via": None,
        "layover_min": 0,
        "night": False,
        "overnight": True,
        "baggage": True,
        "pets_cabin": True,
        "class": "Купе",
        "price": inv.round_price((300 + km * 2.3) * season_factor(dest, day.month) * r.uniform(0.9, 1.15), 10),
    }


def night_train_bundle(brief: dict, bundle: dict, today: date) -> dict | None:
    """Та же поездка, но последняя ночь — в поезде: на ночь меньше в отеле, домой утром."""
    if bundle["nights"] < 2 or brief["transport"] == "flight" or bundle.get("legs"):
        return None
    dest, orig = destination(bundle["dest"]), origin(brief["origin"])
    option = night_train(orig, dest, date.fromisoformat(bundle["checkout"]) - timedelta(days=1))
    if not option or transport_violations(option, brief):
        return None
    shorter = brief | {"nights": bundle["nights"] - 1, "meal": bundle["hotel"]["meal"], "refundable": bundle["hotel"]["refundable"]}
    entry = {"id": bundle["hotel"]["id"], "fit": bundle["hotel"]["fit"]}
    new = assemble(
        shorter, dest, date.fromisoformat(bundle["checkin"]), bundle["outbound"], option, entry, bundle["style"], bundle["label"]
    )
    validate(new, shorter, dest, today)
    return new


def _night_train_hack(bundle: dict, brief: dict, today: date) -> dict | None:
    new = night_train_bundle(brief, bundle, today)
    if not new:
        return None
    saving = bundle["total"] - new["total"]
    if saving < 1000:
        return None
    train = new["inbound"]
    loc = destination(bundle["dest"])["loc"]
    nights = new["nights"]
    return {
        "kind": "night_train",
        "title": f"Ночной поезд обратно — минус {money(saving)}",
        "detail": f"ночь в поезде вместо ночи в отеле: выезд из отеля {day_label(date.fromisoformat(new['checkout']))} в {new['hotel']['checkout']}, "
        f"вечер {loc}, поезд {train['number']} в {time_of(train['depart'])} — дома в {time_of(train['arrive'])}; "
        f"{nights} {plural(nights, 'ночь', 'ночи', 'ночей')} в отеле вместо {bundle['nights']}, багаж — в камеру хранения",
        "saving": saving,
        "action": {"type": "apply_hack", "kind": "night_train"},
        "label": "Ехать ночным поездом",
    }


def _layover_hack(bundle: dict, brief: dict, outbound: list[dict]) -> dict | None:
    """Длинная пересадка в хабе без визы: если после паспортного контроля, досмотра и дороги до центра остаётся хотя бы час."""
    current = bundle["outbound"]
    best = None
    for option in outbound:
        if not option["stops"] or option["via"] not in TRANSIT_CITIES or transport_violations(option, brief):
            continue
        free = option["layover_min"] - 120 - 2 * TRANSIT_CITIES[option["via"]]  # выход в город и обратный досмотр — 2 часа
        if free < 60:
            continue
        delta = transport_cost(option, brief) - current["cost"]
        if option["id"] != current["id"] and delta > 0:
            continue  # менять рейс ради прогулки предлагаем, только если он не дороже
        if best is None or delta < best[1]:
            best = (option, delta, free)
    if not best:
        return None
    option, delta, free = best
    same = option["id"] == current["id"]
    price = "" if same else (f"; и этот рейс дешевле на {money(-delta)}" if delta < 0 else "; цена та же")
    return {
        "kind": "layover_city",
        "title": f"Пересадка {hours_label(option['layover_min'])} в {option['via']} — можно выйти в город",
        "detail": f"{option['number']}: виза для граждан РФ не нужна, до центра около {TRANSIT_CITIES[option['via']]} мин — "
        f"на прогулку останется {hours_label(free)}{price}",
        "saving": -delta if not same and delta < 0 else None,
        "action": None if same else {"type": "swap", "part": "outbound_id", "value": option["id"]},
        "label": None if same else "Взять этот рейс",
    }


def _later_return_hack(bundle: dict, brief: dict, inbound: list[dict]) -> dict | None:
    """Обратно утром, а в тот же день есть рейс после обеда почти за те же деньги — ещё полдня на месте."""
    current = bundle["inbound"]
    if int(current["depart"][11:13]) >= 13:
        return None
    best = None
    for option in inbound:
        hour = int(option["depart"][11:13])
        if option["depart"][:10] != current["depart"][:10] or option["mode"] != current["mode"] or not 15 <= hour <= 21:
            continue
        if transport_violations(option, brief):
            continue
        delta = transport_cost(option, brief) - current["cost"]
        if delta <= max(1500, current["cost"] * 0.1) and (best is None or delta < best[1]):
            best = (option, delta)
    if not best:
        return None
    option, delta = best
    gain = (datetime.fromisoformat(option["depart"]) - datetime.fromisoformat(current["depart"])).total_seconds() / 60
    price = "та же цена" if abs(delta) < 100 else (f"+{money(delta)}" if delta > 0 else f"даже дешевле на {money(-delta)}")
    return {
        "kind": "later_return",
        "title": f"Ещё полдня {destination(bundle['dest'])['loc']} — {price}",
        "detail": f"обратно {option['number']} в {time_of(option['depart'])} вместо {time_of(current['depart'])}: "
        f"+{hours_label(gain)} на месте; после выселения в {bundle['hotel']['checkout']} багаж оставите на ресепшене",
        "saving": -delta if delta < 0 else None,
        "action": {"type": "swap", "part": "inbound_id", "value": option["id"]},
        "label": "Вернуться позже",
    }
