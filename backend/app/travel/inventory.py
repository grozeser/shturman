"""Синтетический инвентарь: отели, рейсы, поезда, трансферы.

Всё детерминированно от seed (направление, дата, маршрут): одинаковый запрос даёт одинаковую выдачу,
поэтому пересборка плана честно показывает, что изменилось. Названия отелей и перевозчиков вымышлены.
Реальные здесь только география (координаты, расстояния, часовые пояса), климат и закрытые аэропорты.
"""

import hashlib
import math
import random
from datetime import date, datetime, timedelta
from functools import cache

from app.travel.catalog import RAIL_COUNTRIES, destination, distance_km, haversine, season_factor
from app.travel.clock import today


def cancel_until(h: dict, checkin: date) -> date:
    """Бесплатная отмена до N дней до заезда; при поздней брони — хотя бы до дня перед заездом, но не в прошлом."""
    until = checkin - timedelta(days=h["refund_days"])
    return max(until, min(today(), checkin - timedelta(days=1)))


HUBS = {
    "MOW": {"name": "Москве", "lat": 55.97, "lon": 37.41, "tz": 3},
    "IST": {"name": "Стамбуле", "lat": 41.26, "lon": 28.74, "tz": 3},
    "DXB": {"name": "Дубае", "lat": 25.25, "lon": 55.36, "tz": 4},
    "BKK": {"name": "Бангкоке", "lat": 13.69, "lon": 100.75, "tz": 7},
    "BEG": {"name": "Белграде", "lat": 44.82, "lon": 20.31, "tz": 1},
    "DOH": {"name": "Дохе", "lat": 25.27, "lon": 51.61, "tz": 3},
}

CARRIERS = {
    "domestic": [("Борей", "БР"), ("Аэроград", "АГ"), ("Лазурь Авиа", "ЛА"), ("Крыло", "КЛ")],
    "intl": [("Лазурь Авиа", "ЛА"), ("Борей", "БР"), ("Anatolia Wings", "AW"), ("Gulf Breeze", "GB"), ("Siam Sky", "SY")],
}

MEALS = {"RO": "без питания", "BB": "завтраки", "HB": "завтраки и ужины", "AI": "всё включено"}
MEAL_RANK = {"RO": 0, "BB": 1, "HB": 2, "AI": 3}


def rng(*parts) -> random.Random:
    seed = int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def round_price(value: float, step: int = 10) -> int:
    return int(round(value / step) * step)


def price_index(dest: dict) -> float:
    return dest["price"] / 5000


def is_night(moment: datetime) -> bool:
    return moment.hour >= 23 or moment.hour < 6


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


# ── Перелёты ────────────────────────────────────────────────────────────────


def _route_legs(orig: dict, dest: dict) -> list[dict] | None:
    """Плечи маршрута: прямой или с пересадкой в хабе. None — авиасообщения нет."""
    if not dest.get("iata") or distance_km(orig, dest) < 120:
        return None
    direct = dest["direct"] == "all" or (dest["direct"] == "hubs" and orig.get("big"))
    if direct:
        return [{"from": orig, "to": dest}]
    hub_code = dest.get("hub") or "MOW"
    if dest["direct"] == "hubs" and hub_code != "MOW" and orig["id"] != "MOW":
        hub_code = "MOW"  # регион → Москва → направление с прямыми рейсами из Москвы
    if hub_code == orig["id"]:
        return [{"from": orig, "to": dest}]
    return [{"from": orig, "to": HUBS[hub_code] | {"code": hub_code}}, {"from": HUBS[hub_code] | {"code": hub_code}, "to": dest}]


def _flights_on(orig: dict, dest: dict, day: date, direction: str) -> list[dict]:
    legs = _route_legs(orig, dest)
    if not legs:
        return []
    if direction == "back":  # обратно тем же маршрутом: нет прямого туда — нет и обратно
        legs = [{"from": leg["to"], "to": leg["from"]} for leg in reversed(legs)]
    r = rng("flights", orig["id"], dest["id"], day.isoformat(), direction)
    foreign = dest["country"] not in RAIL_COUNTRIES
    pool = CARRIERS["intl" if foreign else "domestic"]
    count = r.randint(3, 6) if (orig.get("big") or dest["direct"] == "all") else r.randint(1, 3)
    if len(legs) > 1:
        count = min(count, 3)
    slots = sorted(r.sample(range(0, 24 * 4), count))
    season = season_factor(dest, day.month)
    names = (orig["name"], dest["name"]) if direction == "out" else (dest["name"], orig["name"])
    total_km = sum(haversine(leg["from"]["lat"], leg["from"]["lon"], leg["to"]["lat"], leg["to"]["lon"]) for leg in legs)
    result = []
    for index, slot in enumerate(slots):
        carrier, code = pool[r.randrange(len(pool))]
        depart = datetime.combine(day, datetime.min.time()) + timedelta(minutes=slot * 15 + 5)
        if len(legs) == 1 and r.random() < 0.6 and is_night(depart):
            depart = depart.replace(hour=r.choice([7, 9, 12, 15, 18]))  # ночных рейсов меньше дневных
        minutes = 0
        tz_shift = legs[-1]["to"]["tz"] - legs[0]["from"]["tz"]
        layover = 0
        for leg_index, leg in enumerate(legs):
            km = haversine(leg["from"]["lat"], leg["from"]["lon"], leg["to"]["lat"], leg["to"]["lon"])
            minutes += round(km / 780 * 60 + 35)
            if leg_index < len(legs) - 1:
                layover = r.choice([95, 130, 180, 240, 320])
                minutes += layover
        arrive = depart + timedelta(minutes=minutes, hours=tz_shift)
        base = 2200 + total_km * (2.6 if len(legs) == 1 else 2.2) + (1500 if len(legs) > 1 else 0)
        factor = season * r.uniform(0.82, 1.3)
        if is_night(depart) or is_night(arrive):
            factor *= 0.86
        if depart.weekday() in (4, 5) and direction == "out":
            factor *= 1.1
        baggage = r.random() < 0.7
        price = round_price(base * factor * (1 if baggage else 0.86), 50)
        result.append(
            {
                "id": f"F-{orig['id']}-{dest['id']}-{day:%Y%m%d}-{direction}-{index}",
                "mode": "flight",
                "carrier": carrier,
                "number": f"{code} {r.randint(100, 999)}",
                "from": names[0],
                "to": names[1],
                "depart": iso(depart),
                "arrive": iso(arrive),
                "duration_min": minutes,
                "stops": len(legs) - 1,
                "via": legs[0]["to"]["name"] if len(legs) > 1 else None,
                "layover_min": layover if len(legs) > 1 else 0,
                "night": is_night(depart) or is_night(arrive),
                "baggage": baggage,
                "pets_cabin": r.random() < 0.8,
                "class": "Эконом",
                "price": price,
            }
        )
    return result


# ── Поезда ──────────────────────────────────────────────────────────────────

TRAIN_CLASSES = [("Плацкарт", 1.25), ("Купе", 2.3), ("СВ", 4.6)]
FAST_CLASS = [("Сидячий", 2.0), ("Бизнес", 4.2)]


def _rail_ok(orig: dict, dest: dict) -> bool:
    return bool(orig.get("train") and dest.get("train")) and dest.get("country", "Россия") in RAIL_COUNTRIES


def _trains_on(orig: dict, dest: dict, day: date, direction: str) -> list[dict]:
    a, b = (orig, dest) if direction == "out" else (dest, orig)
    if not _rail_ok(orig, dest):
        return []
    km = distance_km(a, b) * 1.3
    if km < 150 or km > 6000:
        return []
    r = rng("trains", orig["id"], dest["id"], day.isoformat(), direction)
    fast = km < 950  # Москва — Петербург по рельсам ~830 км: скоростной, а не ночной
    speed = 105 if fast else 62
    minutes = round(km / speed * 60)
    tz_shift = b["tz"] - a["tz"]
    count = r.randint(2, 4) if fast else r.randint(1, 2)
    season = season_factor(destination(dest["id"]), day.month)
    hours = sorted(r.sample([6, 7, 9, 12, 14, 17, 19, 21, 22, 23], count))
    result = []
    for index, hour in enumerate(hours):
        depart = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=r.choice([0, 15, 30, 45]))
        arrive = depart + timedelta(minutes=minutes, hours=tz_shift)
        number = f"{r.randint(1, 180):03d}{r.choice('АСМЧЭ')}"
        for class_name, per_km in FAST_CLASS if fast else TRAIN_CLASSES:
            price = round_price((300 + km * per_km) * season * r.uniform(0.9, 1.2), 10)
            result.append(
                {
                    "id": f"T-{orig['id']}-{dest['id']}-{day:%Y%m%d}-{direction}-{index}-{class_name}",
                    "mode": "train",
                    "carrier": "Скоростной поезд" if fast else "Фирменный поезд",
                    "number": f"№ {number}",
                    "from": a["name"],
                    "to": b["name"],
                    "depart": iso(depart),
                    "arrive": iso(arrive),
                    "duration_min": minutes,
                    "stops": 0,
                    "via": None,
                    "layover_min": 0,
                    "night": False,  # в поезде ночь проходит в постели — не штрафуем как ночной рейс
                    "overnight": not fast and minutes > 8 * 60,
                    "baggage": True,
                    "pets_cabin": class_name != "Сидячий",
                    "class": class_name,
                    "price": price,
                }
            )
    return result


def transport_out(orig: dict, dest: dict, arrive_on: date) -> list[dict]:
    """Рейсы и поезда туда, которые прибывают в день заезда."""
    options = []
    for back_days in range(0, 4):
        day = arrive_on - timedelta(days=back_days)
        if back_days <= 1:
            options += _flights_on(orig, dest, day, "out")
        options += _trains_on(orig, dest, day, "out")
    return [o for o in options if o["arrive"][:10] == arrive_on.isoformat()]


def transport_back(orig: dict, dest: dict, depart_on: date) -> list[dict]:
    """Рейсы и поезда обратно в день выезда."""
    return _flights_on(orig, dest, depart_on, "back") + _trains_on(orig, dest, depart_on, "back")


def connections(a: dict, b: dict, day: date) -> list[dict]:
    """Переезд между городами маршрута в один день: автобус и машина — рядом, поезд и прямой рейс — подальше."""
    km = distance_km(a, b)
    r = rng("hop", a["id"], b["id"], day.isoformat())
    season = season_factor(b, day.month)
    tz_shift = b["tz"] - a["tz"]
    options = []

    def add(mode: str, carrier: str, number: str, hour: int, minutes: int, price: float, **extra) -> None:
        depart = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=r.choice([0, 15, 30, 45]))
        arrive = depart + timedelta(minutes=minutes, hours=tz_shift)
        if arrive.date() != day:
            return  # переезд должен уложиться в день — иначе сломаются даты отеля
        options.append(
            {
                "id": f"H-{a['id']}-{b['id']}-{day:%Y%m%d}-{mode}-{hour}",
                "mode": mode,
                "carrier": carrier,
                "number": number,
                "from": a["name"],
                "to": b["name"],
                "depart": iso(depart),
                "arrive": iso(arrive),
                "duration_min": minutes,
                "stops": 0,
                "via": None,
                "layover_min": 0,
                "night": is_night(depart) or is_night(arrive),
                "baggage": True,
                "pets_cabin": mode != "flight" or r.random() < 0.8,
                "class": {"bus": "Автобус", "car": "Машина с водителем", "train": "Купе", "flight": "Эконом"}[mode],
                "price": round_price(price * season, 50),
            }
            | extra
        )

    if km <= 900:
        hours = round(km / 65 * 60 + 20)
        for hour in (8, 13):
            add("bus", "Междугородний автобус", f"Рейс {r.randint(100, 999)}", hour, hours, 400 + km * 3.2)
        add("car", "Трансфер на машине", "Индивидуально", 10, round(km / 80 * 60 + 15), 1500 + km * 22, per_vehicle=True)
    if a.get("train") and b.get("train") and a["country"] in RAIL_COUNTRIES and b["country"] in RAIL_COUNTRIES and 150 < km * 1.3 < 1400:
        add("train", "Поезд", f"№ {r.randint(1, 180):03d}{r.choice('АСМ')}", 9, round(km * 1.3 / 90 * 60), 300 + km * 1.3 * 2.3)
    if km >= 350 and a.get("iata") and b.get("iata"):
        for hour in (7, 12, 18):
            add(
                "flight",
                r.choice(["Борей", "Лазурь Авиа", "Anatolia Wings", "Gulf Breeze"]),
                f"ЛА {r.randint(100, 999)}",
                hour,
                round(km / 780 * 60 + 35),
                2000 + km * 3.0,
            )
    return options


# ── Отели ───────────────────────────────────────────────────────────────────

NAME_PARTS = {
    "ru": (
        ["Гранд", "Парк", "Бутик-отель", "Апарт-отель", "Гостевой дом", "Курортный отель", "Отель", "Эко-отель"],
        ["Бриз", "Жемчужина", "Маяк", "Сосны", "Панорама", "Ривьера", "Лазурь", "Усадьба", "Причал", "Каскад", "Тишина", "Камея"],
    ),
    "resort": (
        ["Sun", "Blue", "Golden", "Royal", "Coral", "Palm", "Sea", "Crystal", "Amara", "Lagoon", "Aqua", "Silk"],
        ["Resort & Spa", "Beach Hotel", "Family Club", "Palace", "Garden Resort", "Bay Hotel", "Boutique", "Village"],
    ),
    "city": (
        ["Old Town", "Central", "Grand", "Park", "Riverside", "Urban", "Station", "Gallery", "Plaza", "Signature"],
        ["Hotel", "Suites", "Boutique Hotel", "Residence", "Inn", "Apartments"],
    ),
}

AREAS = {
    "sea": ["Первая линия", "Набережная", "Курортная зона", "Тихий залив", "Центр", "Холмы"],
    "city": ["Исторический центр", "Деловой район", "У парка", "Старый город", "Набережная", "Спальный район"],
    "nature": ["У озера", "В лесу", "Посёлок", "У подъёмника", "Панорамный склон", "Центр"],
}


def _name_style(dest: dict) -> str:
    if dest["country"] in RAIL_COUNTRIES:
        return "ru"
    return "resort" if "sea" in dest["kinds"] else "city"


# где халяль — норма кухни, а где редкость; вегетарианская кухня — в Индии и на Бали
HALAL_SHARE = {
    "Турция": 0.95, "ОАЭ": 0.98, "Египет": 0.95, "Тунис": 0.9, "Мальдивы": 0.95, "Катар": 0.98, "Малайзия": 0.9,
    "Узбекистан": 0.95, "Казахстан": 0.8, "Киргизия": 0.85, "Индонезия": 0.55, "Россия": 0.25, "Шри-Ланка": 0.35,
    "Маврикий": 0.4, "Индия": 0.4, "Таиланд": 0.3,
}  # fmt: skip
HALAL_DEST = {"dagestan": 0.95, "kazan": 0.65}
VEG_COUNTRIES = {"Индия": 0.98, "Индонезия": 0.9, "Шри-Ланка": 0.9, "Таиланд": 0.8, "Вьетнам": 0.75}
EUROPE = {"Франция", "Италия", "Испания", "Черногория", "Сербия"}


def _diets(dest: dict, hotel_id: str, stars: int) -> dict[str, bool]:
    """Что умеет кухня отеля. Своя последовательность случайных чисел — остальной инвентарь от неё не меняется."""
    r = rng("kitchen", hotel_id)
    level = (stars - 2) / 3  # 0 у 2★, 1 у 5★: в больших отелях кухня гибче
    halal = HALAL_DEST.get(dest["id"], HALAL_SHARE.get(dest["country"], 0.15 + 0.15 * level))
    veg = VEG_COUNTRIES.get(dest["country"], 0.5 + 0.4 * level)
    special = 0.1 + 0.5 * level + (0.15 if dest["country"] in EUROPE or "city" in dest["kinds"] else 0)
    vegetarian = r.random() < veg
    return {
        "halal": r.random() < halal,
        "vegetarian": vegetarian,
        "vegan": vegetarian and r.random() < 0.55 + 0.2 * level,
        "gluten_free": r.random() < special,
        "lactose_free": r.random() < special + 0.05,
        "nut_free": r.random() < special - 0.05,  # кухня с протоколом аллергенов: отдельные доски, маркировка блюд
    }


@cache
def hotels(dest_id: str) -> tuple[dict, ...]:
    dest = destination(dest_id)
    r = rng("hotels", dest_id)
    style = _name_style(dest)
    first, second = NAME_PARTS[style]
    sea = "sea" in dest["kinds"]
    area_kind = "sea" if sea else "city" if "city" in dest["kinds"] else "nature"
    resort_ai = "allinclusive" in dest["kinds"]
    idx = price_index(dest)
    stars_pool = [2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 5, 5, 5, 2, 3, 4, 5, 4]
    r.shuffle(stars_pool)
    used: set[str] = set()
    result = []
    for number, stars in enumerate(stars_pool, start=1):
        name = ""
        while not name or name in used:
            name = f"{r.choice(first)} {r.choice(second)}"
        used.add(name)
        rating = round(min(9.8, max(6.4, {2: 7.3, 3: 7.9, 4: 8.5, 5: 8.9}[stars] + r.uniform(-0.9, 0.6))), 1)
        resort = sea and stars >= 4 and r.random() < 0.8
        ai_included = resort_ai and resort
        adults_only = resort and r.random() < 0.08
        party = adults_only or ("party" in dest["kinds"] and r.random() < 0.3)
        beach_m = None
        if sea:
            beach_m = r.randint(30, 200) if (resort or r.random() < 0.25) else r.randint(300, 2500)
        price = dest["price"] * {2: 0.6, 3: 1.0, 4: 1.7, 5: 2.9}[stars] * r.uniform(0.85, 1.2) * (1 + (rating - 8.2) * 0.08)
        if ai_included:
            price *= 1.45
        if beach_m is not None and beach_m < 250:
            price *= 1.12
        meals = ["AI"] if ai_included else ["RO", "BB"] + (["HB"] if stars >= 3 and r.random() < 0.6 else [])
        if resort and not ai_included and r.random() < 0.5:
            meals.append("AI")
        kids_club = not adults_only and ((resort and r.random() < 0.75) or r.random() < 0.08)
        pets = (not adults_only) and r.random() < dest["pets"] * (0.6 if stars == 5 else 1.0)
        center_km = round(r.uniform(0.2, 3.0) if r.random() < 0.6 else r.uniform(3, 14), 1)
        airport_km = round(max(3, (dest["airport_km"] or dest.get("station_km", 6)) * r.uniform(0.6, 1.5)))
        result.append(
            {
                "id": f"{dest_id}-{number:02d}",
                "dest": dest_id,
                "name": name,
                "stars": stars,
                "rating": rating,
                "reviews": r.randint(40, 3500),
                "area": r.choice(AREAS[area_kind]),
                "beach_m": beach_m,
                "center_km": center_km,
                "airport_km": airport_km,
                "meals": meals,
                "price_night": round_price(price, 50),
                "checkin": r.choice(["14:00", "14:00", "15:00"]),
                "checkout": r.choice(["12:00", "12:00", "11:00"]),
                "refund_days": r.choice([1, 3, 3, 7, 14]),
                "features": {
                    "kids_club": kids_club,
                    "kids_pool": kids_club or (resort and r.random() < 0.5),
                    "family_rooms": not adults_only and r.random() < (0.7 if resort else 0.35),
                    "pets": pets,
                    "pool": resort or r.random() < 0.35,
                    "spa": stars >= 4 and r.random() < 0.6,
                    "adults_only": adults_only,
                    "party": party,
                    "quiet": not party and r.random() < 0.55,
                    "early_checkin": r.random() < 0.65,
                    "late_checkout": r.random() < 0.55,
                    "accessible": stars >= 4 and r.random() < 0.6,
                },
                "diets": _diets(dest, f"{dest_id}-{number:02d}", stars),
                "lat": dest["lat"] + r.uniform(-0.05, 0.05),
                "lon": dest["lon"] + r.uniform(-0.05, 0.05),
                "idx": idx,
            }
        )
    return tuple(result)


def hotel(hotel_id: str) -> dict:
    dest_id = hotel_id.rsplit("-", 1)[0]
    return next(h for h in hotels(dest_id) if h["id"] == hotel_id)


def holiday_factor(day: date) -> float:
    if (day.month == 12 and day.day >= 28) or (day.month == 1 and day.day <= 8):
        return 1.35
    if day.month == 5 and day.day <= 10:
        return 1.2
    return 1.0


def meal_surcharge(h: dict, meal: str) -> int:
    """Доплата за питание на взрослого в ночь (ребёнку — половина)."""
    if meal in ("RO",) or (meal == "AI" and h["meals"] == ["AI"]):
        return 0
    base = destination(h["dest"])["price"]
    return round_price(base * {"BB": 0.12, "HB": 0.3, "AI": 0.55}[meal], 10)


def available(h: dict, checkin: date) -> bool:
    return rng("avail", h["id"], checkin.isoformat()).random() > 0.1


def rooms_for(adults: int, children: list[int]) -> int:
    return max(1, math.ceil(adults / 2), math.ceil((adults + len([c for c in children if c >= 2])) / 4))


def quote_hotel(h: dict, checkin: date, nights: int, adults: int, children: list[int], meal: str, refundable: bool) -> dict:
    dest = destination(h["dest"])
    rooms = rooms_for(adults, children)
    extra_adults = max(0, adults - 2 * rooms)
    paying_kids = [c for c in children if c >= 2]
    room_total = 0.0
    for offset in range(nights):
        day = checkin + timedelta(days=offset)
        night = h["price_night"] * season_factor(dest, day.month) * holiday_factor(day)
        if day.weekday() in (4, 5):
            night *= 1.08
        room_total += night
    room_total *= rooms * (1 + 0.4 * extra_adults / rooms + 0.15 * len(paying_kids) / rooms)
    if not refundable:
        room_total *= 0.88
    surcharge = meal_surcharge(h, meal)
    meal_total = surcharge * nights * (adults + 0.5 * len(paying_kids))
    total = round_price(room_total + meal_total, 50)
    return {
        "total": total,
        "room_total": round_price(room_total, 50),
        "meal_total": round_price(meal_total, 50),
        "per_night": round_price(total / nights, 50),
        "rooms": rooms,
        "meal": meal,
        "refundable": refundable,
        "free_cancel_until": cancel_until(h, checkin).isoformat() if refundable else None,
        "available": available(h, checkin),
    }


# ── Трансферы ───────────────────────────────────────────────────────────────


def transfers(h: dict, mode: str, arrive: datetime, people: int, pets: bool, accessible: bool = False) -> list[dict]:
    dest = destination(h["dest"])
    idx = price_index(dest)
    km = h["airport_km"] if mode == "flight" else dest.get("station_km", 5) + h["center_km"] * 0.5
    rate = 18 + 22 * min(idx, 2)
    cars = max(1, math.ceil(people / 4))
    taxi_price = round_price((200 + km * rate) * cars, 50)
    taxi_min = round(km / 50 * 60 + 10)
    options = [
        {
            "id": f"taxi-{h['id']}-{mode}",
            "kind": "taxi",
            "title": "Такси" if cars == 1 else f"Такси × {cars}",
            "price": taxi_price,
            "duration_min": taxi_min,
            "child_seat": False,
            "pets": False,
        },
        {
            "id": f"private-{h['id']}-{mode}",
            "kind": "private",
            "title": "Индивидуальный трансфер с табличкой",
            "price": round_price(taxi_price * 1.45 + 500, 50),
            "duration_min": taxi_min,
            "child_seat": True,
            "pets": True,
        },
    ]
    shuttle_hours = 7 <= arrive.hour < 22
    if mode == "flight" and km >= 8 and shuttle_hours and not pets:
        options.insert(
            0,
            {
                "id": f"shuttle-{h['id']}",
                "kind": "shuttle",
                "title": "Групповой трансфер",
                "price": round_price(max(400, km * 9 * idx) * people, 50),
                "duration_min": round(km / 38 * 60 + 40),
                "child_seat": False,
                "pets": False,
            },
        )
    if accessible:  # заказывается заранее: минивэн с подъёмником и креплением для коляски
        options.append(
            {
                "id": f"lift-{h['id']}-{mode}",
                "kind": "accessible",
                "title": "Минивэн с подъёмником для коляски",
                "price": round_price(taxi_price * 1.6 + 900, 50),
                "duration_min": taxi_min + 10,
                "child_seat": True,
                "pets": True,
            }
        )
    return options
