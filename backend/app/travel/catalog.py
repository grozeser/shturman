"""Справочники: направления, города вылета, климат. Всё грузится один раз из app/data."""

import json
import math
import os
import re
from functools import cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

MONTHS = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]  # fmt: skip
MONTHS_IN = [
    "январе", "феврале", "марте", "апреле", "мае", "июне",
    "июле", "августе", "сентябре", "октябре", "ноябре", "декабре",
]  # fmt: skip
MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]  # fmt: skip

KIND_LABELS = {
    "sea": "море",
    "mountains": "горы",
    "city": "город",
    "culture": "экскурсии",
    "food": "гастрономия",
    "nature": "природа",
    "spa": "оздоровление",
    "party": "ночная жизнь",
    "romantic": "романтика",
    "exotic": "экзотика",
    "active": "активный отдых",
    "allinclusive": "всё включено",
    "family": "с детьми",
    "ski": "горные лыжи",
}

RAIL_COUNTRIES = {"Россия", "Россия (Крым)", "Беларусь", "Абхазия"}


def _load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@cache
def destinations() -> dict[str, dict]:
    climate = _load("climate.json") if (DATA / "climate.json").exists() else {}
    result = {}
    for dest in _load("destinations.json"):
        dest["climate"] = climate.get(dest["id"])
        result[dest["id"]] = dest
    dynamic = Path(os.getenv("GEO_CACHE", DATA / "dynamic_destinations.json"))  # найденные на лету (app.travel.geo)
    if dynamic.exists():
        try:
            for dest in json.loads(dynamic.read_text(encoding="utf-8")):
                result.setdefault(dest["id"], dest)
        except (OSError, ValueError):
            pass
    return result


@cache
def origins() -> dict[str, dict]:
    return {o["id"]: o for o in _load("origins.json")}


def destination(dest_id: str) -> dict:
    return destinations()[dest_id]


def origin(origin_id: str) -> dict:
    return origins()[origin_id]


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_km(orig: dict, dest: dict) -> float:
    return haversine(orig["lat"], orig["lon"], dest["lat"], dest["lon"])


def climate(dest: dict, month: int) -> dict:
    """Климат в месяце: воздух (дневной максимум), вода, дождливые дни. None — данных нет."""
    data = dest.get("climate") or {}
    pick = lambda key: (data.get(key) or [None] * 12)[month - 1]  # noqa: E731
    return {"air": pick("air"), "water": pick("water"), "rain": pick("rain")}


def season_factor(dest: dict, month: int) -> float:
    """Спрос в месяце из климата: тёплое море и приятная погода — дороже. 0.75…1.3."""
    c = climate(dest, month)
    air, water = c["air"], c["water"]
    kinds = dest["kinds"]
    factor = 1.0
    if "ski" in kinds and month in (12, 1, 2, 3):
        factor = 1.3
    elif "sea" in kinds and water is not None:
        factor = 1.25 if water >= 25 else 1.12 if water >= 23 else 0.98 if water >= 21 else 0.78
    elif air is not None:
        factor = 1.12 if 18 <= air <= 28 else 0.95 if 10 <= air <= 33 else 0.82
    return factor


def find_destination(text: str) -> dict | None:
    """Самое длинное совпадение алиаса в тексте: «Красная Поляна» важнее «Сочи»."""
    # «из Москвы в Сочи»: город вылета не должен стать направлением
    # «недалеко от Москвы», «под Питером» — ориентир, а не цель поездки
    lowered = re.sub(r"\b(из|от|около|возле|под)\s+[\w-]+(\s+новгорода)?", " ", text.lower().replace("ё", "е"))
    best, best_len = None, 0
    for dest in destinations().values():
        for alias in dest["aliases"] + [dest["name"].lower()] + EN_ALIASES.get(dest["id"], []):
            alias = alias.replace("ё", "е")
            if _contains_word(lowered, alias) and len(alias) > best_len:
                best, best_len = dest, len(alias)
    if best is None and re.search(r"(?<![\w-])тай(?![\w-])", lowered):  # разговорное «в тай»
        return destinations()["phuket"]
    return best or _find_typo(lowered)


# латиницей пишут чаще всего страны и самые известные курорты
EN_ALIASES = {
    "antalya": ["turkey", "antalya"],
    "hurghada": ["egypt", "hurghada"],
    "sharm": ["sharm"],
    "phuket": ["thailand", "phuket"],
    "dubai": ["dubai", "uae", "emirates"],
    "bali": ["bali", "indonesia"],
    "maldives": ["maldives"],
    "istanbul": ["istanbul"],
    "sochi": ["sochi"],
    "nha_trang": ["vietnam"],
    "tbilisi": ["georgia", "tbilisi"],
    "yerevan": ["armenia", "yerevan"],
    "paris": ["paris", "france"],
    "rome": ["rome", "italy"],
    "barcelona": ["barcelona", "spain"],
    "sri_lanka": ["sri lanka"],
    "sanya": ["china", "hainan"],
    "varadero": ["cuba"],
}


def _find_typo(text: str) -> dict | None:
    """Опечатка в одну букву в названии после «в/на/до»: «в сочм», «на бпли».
    Сверяем с целыми названиями, а не с основами: основы ловили «каталог» → Катар, «турист» → Тунис."""
    words = re.findall(r"(?:^|\s)(?:в|во|на|до)\s+([а-я-]{4,})", text)
    for dest in destinations().values():
        if dest.get("dynamic"):
            continue
        name = dest["name"].lower().replace("ё", "е")
        for word in words:
            # первые две буквы совпадают — иначе «были» стали бы «Бали»
            if len(name) >= 4 and word[:2] == name[:2] and _one_edit(word, name):
                return dest
    return None


def _one_edit(a: str, b: str) -> bool:
    """Ровно одна правка: замена, вставка или удаление буквы."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1 :] == short for i in range(len(long_)))


def find_origin(text: str) -> dict | None:
    lowered = text.lower().replace("ё", "е")
    for marker in ("из ", "вылет ", "вылетаем ", "летим из ", "живу в ", "живем в ", "я из ", "мы из "):
        start = lowered.find(marker)
        while start >= 0:
            tail = lowered[start + len(marker) : start + len(marker) + 30]
            for orig in origins().values():
                if any(tail.startswith(alias) for alias in orig["aliases"]):
                    return orig
            start = lowered.find(marker, start + 1)
    return None


def _contains_word(text: str, alias: str) -> bool:
    """Алиас — начало слова (основа): «турци» найдётся в «в Турцию», но «рак» не найдётся в «прак»."""
    index = text.find(alias)
    while index >= 0:
        if index == 0 or not text[index - 1].isalpha():
            # короткие алиасы (≤4) — целое слово или с окончанием в одну букву: «кубу», но не «Кубань»
            end = index + len(alias)
            rest = 0
            while end + rest < len(text) and text[end + rest].isalpha():
                rest += 1
            if len(alias) > 4 or rest <= 1:
                return True
        index = text.find(alias, index + 1)
    return False
