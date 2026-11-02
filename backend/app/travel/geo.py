"""Направления вне базы: город находим геокодером Open-Meteo, климат и море — по реальным данным, отели и рейсы моделируем.

Так незнакомый запрос («хочу в Берген на фьорды») превращается в собранную поездку, а не в «нет в базе».
Найденное направление сохраняется в data/dynamic_destinations.json и живёт дальше как обычное (но в подборках
«куда поехать» не участвует — туда попадают только проверенные направления каталога).
"""

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

from app.travel import catalog

log = logging.getLogger("geo")

DATA = Path(__file__).resolve().parents[1] / "data"
STORE = Path(os.getenv("GEO_CACHE", DATA / "dynamic_destinations.json"))
TIMEOUT = float(os.getenv("GEO_TIMEOUT_SECONDS", "8"))

# страна в запросе → город, с которого логично начать (для фьордов — Берген, для моря — курорт)
COUNTRY_HINTS = {
    "норвег": "Берген", "япон": "Токио", "мексик": "Канкун", "финлянд": "Хельсинки", "исланд": "Рейкьявик",
    "португал": "Лиссабон", "греци": "Ираклион", "кипр": "Ларнака", "израил": "Тель-Авив", "иордани": "Акаба",
    "марокко": "Марракеш", "южн африк": "Кейптаун", "юар": "Кейптаун", "аргентин": "Буэнос-Айрес",
    "бразили": "Рио-де-Жанейро", "сша": "Нью-Йорк", "америк": "Нью-Йорк", "канад": "Торонто", "австрали": "Сидней",
    "новую зеланд": "Окленд", "новой зеланд": "Окленд", "коре": "Сеул", "филиппин": "Себу", "германи": "Берлин",
    "чехи": "Прага", "австри": "Вена", "швейцари": "Цюрих", "венгри": "Будапешт", "хорвати": "Дубровник",
    "англи": "Лондон", "великобритан": "Лондон", "шотланди": "Эдинбург", "ирланди": "Дублин", "голланди": "Амстердам",
    "нидерланд": "Амстердам", "бельги": "Брюссель", "польш": "Краков", "швеци": "Стокгольм", "дани": "Копенгаген",
    "эстони": "Таллин", "латви": "Рига", "литв": "Вильнюс", "монголи": "Улан-Батор", "непал": "Катманду",
    "перу": "Куско", "танзани": "Занзибар", "кени": "Момбаса", "оман": "Маскат", "мадейр": "Фуншал",
    "сицили": "Палермо", "сардини": "Кальяри", "тенериф": "Санта-Крус-де-Тенерифе", "канар": "Санта-Крус-де-Тенерифе",
    "майорк": "Пальма", "ибиц": "Ибица", "крит": "Ираклион", "родос": "Родос", "мальт": "Валлетта",
    "сингапур": "Сингапур", "гонконг": "Гонконг", "камбодж": "Сиемреап", "лаос": "Луангпхабанг", "мьянм": "Янгон",
    "доминикан": "Пунта-Кана", "ямайк": "Монтего-Бей", "колумби": "Картахена", "чили": "Сантьяго", "эквадор": "Кито",
    "фиджи": "Нади", "таити": "Папеэте", "занзибар": "Занзибар", "азербайджан": "Баку", "таджикистан": "Душанбе",
}  # fmt: skip

# уровень цен: базовая цена ночи в 3★ на двоих, ₽
COST = {
    "NO": 13000, "IS": 14000, "CH": 14000, "DK": 12000, "SE": 11000, "FI": 10000, "GB": 12000, "IE": 11000,
    "FR": 11000, "NL": 11000, "BE": 10000, "DE": 9500, "AT": 9500, "IT": 9500, "ES": 8500, "PT": 7500, "GR": 7500,
    "CY": 8000, "MT": 8000, "HR": 8000, "CZ": 7000, "HU": 6500, "PL": 6000, "EE": 6500, "LV": 6000, "LT": 6000,
    "US": 13000, "CA": 11000, "AU": 12000, "NZ": 11000, "JP": 9000, "KR": 8000, "SG": 12000, "HK": 11000,
    "IL": 11000, "JO": 7000, "OM": 8000, "MX": 6500, "DO": 7000, "JM": 8000, "BR": 6000, "AR": 5500, "CL": 6500,
    "PE": 5000, "CO": 5000, "EC": 5000, "MA": 5000, "ZA": 6000, "TZ": 6000, "KE": 6000, "NP": 3000, "MN": 4000,
    "KH": 3500, "LA": 3500, "MM": 3500, "PH": 4000, "FJ": 9000, "PF": 15000, "AZ": 4500, "TJ": 3500, "RU": 4500,
}  # fmt: skip

SCHENGEN = set(
    [
        "AT",
        "BE",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IS",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "SK",
        "SI",
        "ES",
        "SE",
        "CH",
        "LI",
        "HR",
    ]
)
VISA_FREE = set(
    [
        "RU",
        "BY",
        "AM",
        "GE",
        "AZ",
        "KZ",
        "KG",
        "UZ",
        "TJ",
        "TR",
        "AE",
        "EG",
        "TH",
        "VN",
        "ID",
        "MV",
        "LK",
        "CN",
        "TN",
        "ME",
        "RS",
        "CU",
        "SC",
        "MU",
        "QA",
        "MY",
        "IL",
        "AR",
        "BR",
        "CL",
        "PE",
        "CO",
        "EC",
        "MA",
        "ZA",
        "PH",
        "KR",
        "JO",
    ]
)
VISA_REQUIRED = set(["JP", "US", "GB", "CA", "AU", "NZ", "IE"])
VISA_ON_ARRIVAL = {
    "KH": "по прибытии, около $30",
    "LA": "по прибытии, около $40",
    "NP": "по прибытии, около $30",
    "TZ": "электронная, около $50",
}

ISLAND_WORDS = ("остров", "крит", "родос", "мальт", "кипр", "бали", "занзибар", "фиджи", "таити", "мадейр", "сицили", "сардини")


# слова с заглавной в начале фразы, которые не названия мест
SENTENCE_STARTS = {
    "хочу", "хотим", "хотелось", "хочется", "едем", "летим", "поедем", "полетим", "поехали", "планируем", "думаем",
    "ищу", "ищем", "нужно", "нужна", "нужен", "надо", "можно", "давай", "давайте", "подскажи", "подскажите",
    "посоветуй", "посоветуйте", "куда", "где", "когда", "отпуск", "поездка", "поездку", "путешествие", "привет",
    "здравствуйте", "добрый", "доброе", "семья", "семьёй", "семьей", "вдвоём", "вдвоем", "мечтаем", "мечтаю",
    "очень", "просто", "только", "сколько", "отдых", "отдохнуть", "собери", "собираемся", "выходные", "новогодние",
    "майские", "летом", "зимой", "осенью", "весной", "недорого", "бюджет", "дешево", "дёшево", "горнолыжка",
}  # fmt: skip


NOT_A_NAME = ("ие", "ые", "ая", "яя", "ое", "ее", "ий", "ый", "ой", "ть", "ться", "тся", "лось", "лся", "ем", "ют", "ят", "ешь", "ишь")

# обычные слова после «в/на», которые не названия мест: «на море», «в горы», «на неделю», «в отеле»
COMMON_STEMS = (
    "мор", "гор", "нед", "выход", "отпуск", "отдых", "поезд", "самол", "машин", "авто", "каникул", "майск", "нов", "пляж",
    "курорт", "лыж", "природ", "дач", "двоих", "трои", "четвер", "пару", "сут", "ноч", "тепл", "жар", "холод", "солн",
    "север", "остров", "озер", "реку", "океан", "экскурс", "работ", "свадьб", "концерт", "фестивал", "матч", "город",
    "стран", "деревн", "санатор", "баз", "лагер", "кемпинг", "дом", "отел", "гостиниц", "хостел", "апартам", "тур",
    "круиз", "поход", "сафари", "рыбалк", "охот", "бан", "парк", "музе", "театр", "ресторан", "магазин", "шопинг",
    "праздн", "день", "дня", "месяц", "год", "уикенд", "ближ", "недалек", "далек", "учеб", "командировк", "границ",
    "зарубеж", "европ", "ази", "кавказ", "росси", "сибир", "урал", "лето", "зиму", "весну", "осень", "рождеств", "пасх",
    "семь", "дет", "ребен", "собак", "кошк", "жен", "муж", "друз", "подруг", "родител", "бабушк", "дедушк", "маму",
    "папу", "сына", "доч", "начал", "конц", "середин", "понедел", "вторн", "сред", "четверг", "пятниц", "суббот",
    "воскрес", "пут", "человек", "всех", "сумм", "район", "предел", "течени", "связ", "выбор", "свой", "свое", "этот",
    "это", "такс", "трансфер", "рейс", "пересадк", "вылет", "завтрак", "ужин", "питани", "номер", "бассейн", "кровать",
)  # fmt: skip


def name_ok(word: str) -> bool:
    """Похоже ли слово на название места, а не на обычное слово или начало фразы."""
    low = word.lower().replace("ё", "е")
    return not (low in SENTENCE_STARTS or low.endswith(NOT_A_NAME) or low.startswith(MONTH_STEMS + COMMON_STEMS))


def lower_place(text: str) -> str | None:
    """«в лиссабон», «пекин в сентябре» — название строчными: люди редко пишут города с заглавной."""
    low = text.lower().replace("ё", "е")
    candidates = re.findall(r"(?:^|\s)(?:в|во|на)\s+([а-я][а-я-]{3,})", low)
    first = re.match(r"^\s*([а-я][а-я-]{3,})(?=\s+(?:в|во|на|с|до|\d)\b|\s*[,.!?]?\s*$)", low)
    if first:
        candidates.append(first.group(1))
    return next((word for word in candidates if name_ok(word)), None)


ROUTE_SPLIT = re.compile(r"\s*(?:,|\+|→|->|\bи\b|\bпотом\b|\bзатем\b|\bпосле этого\b|\bа после\b)\s*", re.IGNORECASE)
MONTH_STEMS = ("январ", "феврал", "март", "апрел", "май", "мая", "мае", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр")


def find_route(text: str) -> list[dict]:
    """Несколько мест в одном запросе («Стамбул и Каппадокия», «сначала Рим, потом Флоренция») по порядку упоминания.
    Каждый пункт — {"id": ...} из каталога или {"name": ...} для геокодера, с ночами, если они названы рядом («3 ночи в Стамбуле»)."""
    clean = re.sub(r"\b(из|от|около|возле|под)\s+[\w-]+", " ", text)  # город вылета и ориентиры — не точки маршрута
    each = re.search(r"по\s+(\d{1,2})\s*(ноч|дн)", clean.lower())
    stops: list[dict] = []
    for part in ROUTE_SPLIT.split(clean):
        if not part.strip():
            continue
        nights_match = re.search(r"(\d{1,2})\s*(ноч|дн)", part.lower())
        nights = None
        if nights_match:
            value = int(nights_match.group(1))
            nights = value if nights_match.group(2) == "ноч" else max(2, value - 1)
        elif bare := re.match(r"^\s*(\d{1,2})\s+(?:в|во|на)\b", part):  # «…и 4 в Каппадокии» — единица названа раньше
            nights = int(bare.group(1))
        dest = catalog.find_destination(part)
        if dest:
            if all(stop.get("id") != dest["id"] for stop in stops):
                stops.append({"id": dest["id"], "nights": nights})
            continue
        # строчными — после предлога или сразу за уже найденным местом («в рим и флоренцию»);
        # иначе любое слово через запятую уходило бы в геокодер
        lower = r"[а-яё][а-яё-]{3,}" if stops else r"(?!)"
        match = re.match(rf"^\s*(?:сначала\s+)?(?:(?:в|во|на)\s+([а-яё][а-яё-]{{3,}})|(?:в|во|на)?\s*([А-ЯЁ][а-яё-]{{3,}}|{lower}))", part)
        name = match and (match.group(1) or match.group(2))
        if name and name_ok(name):
            stops.append({"name": name, "nights": nights})
    if each:
        value = int(each.group(1))
        for stop in stops:
            stop["nights"] = value if each.group(2) == "ноч" else max(2, value - 1)
    sequence = each or any(s["nights"] for s in stops) or re.search(r"(сначала|потом|затем|после этого|а после|→|->)", text.lower())
    countries = {catalog.destination(s["id"])["country"] for s in stops if "id" in s}
    if not sequence and len(countries) > 1 and all("id" in s for s in stops):
        return []  # «Турция и Египет в мае» — выбирают между странами, а не едут по маршруту
    return stops if len(stops) >= 2 else []


def _get(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):  # у бесплатного API бывают разовые обрывы TLS — повторяем
        try:
            with urllib.request.urlopen(full, timeout=TIMEOUT) as response:
                return json.load(response)
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.4 * (attempt + 1))
    raise OSError("недостижимо")


def name_variants(name: str) -> list[str]:
    """«Прагу» → «Прага», «Лондоне» → «Лондон»: геокодер понимает только именительный падеж."""
    name = name.strip()
    variants = [name]
    lowered = name.lower()
    for ending, replacements in (("ю", ["я"]), ("у", ["а"]), ("е", ["", "а", "ь"]), ("и", ["ь", "я"]), ("ой", ["ая"])):
        if lowered.endswith(ending) and len(name) > 4:
            stem = name[: -len(ending)]
            variants += [stem + r for r in replacements]
    return list(dict.fromkeys(variants))


def hint_for(text: str) -> str | None:
    lowered = text.lower().replace("ё", "е")
    for stem, city in COUNTRY_HINTS.items():
        # только с начала слова: «романтические» не Оман, «свидание» не Дания, «скорее» не Корея
        if re.search(rf"(?<![а-я]){re.escape(stem)}", lowered):
            return city
    return None


def geocode(name: str) -> dict | None:
    for variant in name_variants(name):
        data = _get("https://geocoding-api.open-meteo.com/v1/search", {"name": variant, "count": 5, "language": "ru", "format": "json"})
        # только заметные населённые пункты: случайное слово не должно превратиться в деревню на 200 жителей
        places = [
            p
            for p in data.get("results") or []
            if str(p.get("feature_code", "")).startswith("PPL")
            and ((p.get("population") or 0) >= 10000 or p.get("feature_code") in ("PPLC", "PPLA"))
        ]
        if places:
            # из одноимённых берём самый крупный: «Берген» в Норвегии, а не в Нидерландах
            return max(places[:5], key=lambda p: (p.get("population") or 0))
    return None


def monthly(times: list[str], values: list, reducer) -> list:
    buckets: dict[int, list] = defaultdict(list)
    for stamp, value in zip(times, values, strict=True):
        if value is not None:
            buckets[int(stamp[5:7])].append(value)
    return [reducer(buckets[m]) if buckets[m] else None for m in range(1, 13)]


def climate_at(lat: float, lon: float) -> tuple[dict, float]:
    """Климатические нормы как у каталога: дневной максимум, дни с ливнями ≥ 5 мм, вода (если рядом море)."""
    years = 6
    data = _get(
        "https://archive-api.open-meteo.com/v1/archive",
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": "2019-01-01",
            "end_date": "2024-12-31",
            "daily": "temperature_2m_max,precipitation_sum",
            "timezone": "auto",
        },
    )
    daily = data["daily"]
    air = monthly(daily["time"], daily["temperature_2m_max"], lambda v: round(sum(v) / len(v)))
    rain = monthly(daily["time"], daily["precipitation_sum"], lambda v: round(sum(x >= 5 for x in v) / years))
    water = None
    try:
        marine = _get(
            "https://marine-api.open-meteo.com/v1/marine",
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": "2022-01-01",
                "end_date": "2024-12-31",
                "daily": "sea_surface_temperature_mean",
            },
        )
        values = marine.get("daily", {}).get("sea_surface_temperature_mean") or []
        if sum(v is not None for v in values) > 300:
            water = monthly(marine["daily"]["time"], values, lambda v: round(sum(v) / len(v)))
    except (OSError, ValueError, KeyError):
        water = None  # моря рядом нет или сервис недоступен — направление просто без моря
    return {"air": air, "rain": rain, "water": water}, data.get("utc_offset_seconds", 0) / 3600


def prepositional(name: str) -> str:
    """«в Праге», «в Лондоне», «в Осло» — простое склонение для названий, которых нет в каталоге."""
    lowered = name.lower()
    if lowered.endswith("ия"):
        return name[:-1] + "и"
    if lowered.endswith(("а", "я")):
        return name[:-1] + "е"
    if lowered[-1] in "оиуюеэёы":
        return name
    if lowered.endswith("ь"):
        return name[:-1] + "и"
    if lowered.endswith("й"):
        return name[:-1] + "е"
    return name + "е"


def build(place: dict, climate: dict, tz: float, query: str) -> dict:
    code = place.get("country_code", "")
    russian = code == "RU"
    lat, lon = place["latitude"], place["longitude"]
    # пляжный отдых — только если море хоть в один месяц прогревается до +22°: Берген у моря, но не курорт
    sea = climate["water"] is not None and max((v for v in climate["water"] if v is not None), default=0) >= 22
    if not sea:
        climate = climate | {"water": None}
    kinds = ["city"]
    if sea:
        kinds.append("sea")
    if (place.get("elevation") or 0) > 900:
        kinds += ["mountains", "nature"]
    if place.get("feature_code") in ("PPLC", "PPLA"):
        kinds += ["culture", "food"]
    if code in SCHENGEN:
        visa = "шенгенская виза — оформлять за 1–2 месяца"
    elif code in VISA_FREE:
        visa = "не нужна"
    elif code in VISA_REQUIRED:
        visa = "нужна виза — оформлять заранее, сроки уточните в консульстве"
    else:
        visa = VISA_ON_ARRIVAL.get(code, "уточните визовый режим для граждан РФ")
    name = place["name"]
    island = any(w in query.lower() for w in ISLAND_WORDS)
    return {
        "id": f"geo-{place['id']}",
        "name": name,
        "loc": ("на " if island else "в ") + prepositional(name),
        "country": place.get("country", "") if not russian else "Россия",
        "lat": lat,
        "lon": lon,
        "sea": [lat, lon] if sea else None,
        "iata": "GEO",  # аэропорт не знаем — считаем, что он в получасе от города
        "airport_km": 25,
        "train": russian,
        "tz": round(tz * 2) / 2,
        "visa": visa,
        "kinds": sorted(set(kinds)),
        "price": COST.get(code, 6500),
        "kids": 0.6,
        "pets": 0.4,
        "direct": "hubs" if russian else "none",
        "hub": "MOW" if russian else ("DXB" if lon >= 45 else "IST"),
        "note": "направления нет в демо-базе: климат — реальный (Open-Meteo), отели и рейсы смоделированы, цены ориентировочные",
        "highlights": [
            f"{name}, {place.get('country', '')}",
            "погода по реальным нормам за 6 лет",
            "отели и рейсы смоделированы — цены ориентировочные",
        ],
        "aliases": sorted({name.lower(), query.lower()}),
        "dynamic": True,
        "climate": climate,
    }


def load() -> dict[str, dict]:
    if not STORE.exists():
        return {}
    try:
        return {d["id"]: d for d in json.loads(STORE.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {}


def register(dest: dict) -> None:
    catalog.destinations()[dest["id"]] = dest
    stored = load() | {dest["id"]: dest}
    try:
        STORE.write_text(json.dumps(list(stored.values()), ensure_ascii=False), encoding="utf-8")
    except OSError:
        log.warning("Не удалось сохранить %s — направление проживёт до перезапуска", STORE)


def resolve(query: str, text: str = "") -> dict | None:
    """Название из запроса → направление. None — не нашли или сеть недоступна (тогда агент предложит похожие)."""
    target = hint_for(f"{query} {text}") or query
    known = catalog.find_destination(target)
    if known:
        return known
    if os.getenv("GEO_OFFLINE"):
        return None
    try:
        place = geocode(target)
        if not place:
            return None
        existing = catalog.destinations().get(f"geo-{place['id']}")
        if existing:
            return existing
        climate, tz = climate_at(place["latitude"], place["longitude"])
    except (OSError, ValueError, KeyError) as error:
        log.info("Геокодинг «%s» не удался: %s", target, error.__class__.__name__)
        return None
    dest = build(place, climate, tz, target)
    register(dest)
    log.info("Новое направление: %s (%s)", dest["name"], dest["country"])
    return dest
