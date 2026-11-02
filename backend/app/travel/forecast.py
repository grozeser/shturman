"""Настоящий прогноз погоды Open-Meteo, если поездка в ближайшие 16 дней, — вместо многолетней нормы.

Прогноз считается от настоящей даты, а не от TODAY демо-стенда: погода бывает только в реальном календаре.
Нет сети или поездка дальше 16 дней — агент честно показывает норму. FORECAST_OFFLINE=1 (или GEO_OFFLINE)
отключает запросы: тесты, эталонный прогон, стенд без интернета.
"""

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

from app.travel.brief import plural
from app.travel.catalog import MONTHS_GEN, destination

log = logging.getLogger("forecast")

URL = "https://api.open-meteo.com/v1/forecast"
HORIZON = 16  # дней вперёд, включая сегодня
TTL = 3 * 3600  # прогноз обновляется несколько раз в сутки — чаще спрашивать незачем
TIMEOUT = float(os.getenv("FORECAST_TIMEOUT_SECONDS", "5"))
_cache: dict[tuple, tuple[float, list[dict]]] = {}

WEEKDAY_ON = ["в понедельник", "во вторник", "в среду", "в четверг", "в пятницу", "в субботу", "в воскресенье"]
WEEKDAY_TO = ["на понедельник", "на вторник", "на среду", "на четверг", "на пятницу", "на субботу", "на воскресенье"]
# коды погоды WMO, которые отдаёт Open-Meteo
SKY = [
    ((0,), "ясно"),
    ((1, 2), "переменная облачность"),
    ((3,), "пасмурно"),
    ((45, 48), "туман"),
    ((51, 53, 55, 56, 57), "морось"),
    ((61, 63, 66), "дождь"),
    ((65, 67), "сильный дождь"),
    ((71, 73, 75, 77, 85, 86), "снег"),
    ((80, 81), "ливни"),
    ((82,), "сильные ливни"),
    ((95, 96, 99), "гроза"),
]


def real_today() -> date:
    return date.today()


def offline() -> bool:
    return bool(os.getenv("FORECAST_OFFLINE") or os.getenv("GEO_OFFLINE"))


def window(start: date, end: date, now: date | None = None) -> tuple[date, date] | None:
    """Часть поездки, на которую уже есть прогноз. None — поездка целиком дальше горизонта или в прошлом."""
    now = now or real_today()
    first, last = max(start, now), min(end, now + timedelta(days=HORIZON - 1))
    return (first, last) if first <= last else None


def sky(code: int | None) -> str:
    return next((label for codes, label in SKY if code in codes), "")


def _get(params: dict) -> dict:
    with urllib.request.urlopen(f"{URL}?{urllib.parse.urlencode(params)}", timeout=TIMEOUT) as response:
        return json.load(response)


def fetch(lat: float, lon: float, start: date, end: date) -> list[dict] | None:
    """Дни прогноза между start и end (включительно). None — прогноза нет: далеко, офлайн или сервис не ответил."""
    span = window(start, end)
    if not span or offline():
        return None
    key = (round(lat, 2), round(lon, 2), span)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < TTL:
        return cached[1]
    try:
        data = _get(
            {
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code",
                "timezone": "auto",
                "start_date": span[0].isoformat(),
                "end_date": span[1].isoformat(),
            }
        )
        daily = data["daily"]
        days = []
        for index, stamp in enumerate(daily["time"]):
            high, low = daily["temperature_2m_max"][index], daily["temperature_2m_min"][index]
            if high is None or low is None:
                continue
            rain = daily["precipitation_sum"][index] or 0.0
            code = daily["weather_code"][index]
            days.append(
                {
                    "date": stamp,
                    "tmax": round(high),
                    "tmin": round(low),
                    "rain_mm": round(rain, 1),
                    "rain_prob": daily["precipitation_probability_max"][index],
                    "code": code,
                    "sky": sky(code),
                    # день, когда планы на улице лучше перенести: от 5 мм за день или гроза
                    "rainy": rain >= 5 or code in (95, 96, 99),
                }
            )
    except (OSError, ValueError, KeyError, TypeError) as error:
        log.info("Прогноз не получен: %s", error.__class__.__name__)
        return None
    _cache[key] = (time.time(), days)
    return days


def degrees(value: int) -> str:
    return f"{'+' if value > 0 else ''}{value}°"


def day_label(stamp: str) -> str:
    day = date.fromisoformat(stamp)
    return f"{day.day} {MONTHS_GEN[day.month - 1]}"


def summary(days: list[dict], start: date, end: date, loc: str) -> dict:
    """Итог прогноза для ответа агента, карточки и напоминания: диапазон температуры, дождливые дни и совет."""
    highs = [d["tmax"] for d in days]
    low, high = min(highs), max(highs)
    heat = f"днём {degrees(low)}…{degrees(high)}" if low != high else f"днём {degrees(high)}"
    rainy = [d for d in days if d["rainy"]]
    advice = None
    if rainy:
        wet = rainy[0]
        wet_day = date.fromisoformat(wet["date"])
        dry = [d for d in days if not d["rainy"]]
        # сухой день ближе всего к дождливому, лучше — после него: экскурсию переносят, а не отменяют
        nearest = min(dry, key=lambda d: (abs((date.fromisoformat(d["date"]) - wet_day).days), d["date"] < wet["date"]), default=None)
        what = "гроза" if wet["code"] in (95, 96, 99) else "ливень"
        advice = f"{WEEKDAY_ON[wet_day.weekday()]} {day_label(wet['date'])} {what}"
        if nearest:
            advice += f" — экскурсию лучше {WEEKDAY_TO[date.fromisoformat(nearest['date']).weekday()]}"
        if len(rainy) > 1:
            advice += f" (дождливых дней в прогнозе: {len(rainy)})"
    elif high >= 32:
        advice = "жарко — экскурсии лучше утром и вечером"
    total = (end - start).days + 1
    covered = len(days)
    return {
        "source": "Open-Meteo",
        "days": days,
        "covered": covered,
        "total": total,
        "tmax": [low, high],
        "rainy": [d["date"] for d in rainy],
        "advice": advice,
        # «В Анталье обещают +31°, во вторник ливень — экскурсию лучше на среду»
        "line": f"{loc[0].upper()}{loc[1:]} обещают {heat}" + (f", {advice}" if advice else ", дождей не ждут"),
        "detail": f"Open-Meteo: {covered} {plural(covered, 'день', 'дня', 'дней')} из {total}, {heat}"
        + (f", дождливых дней: {len(rainy)}" if rainy else ", без дождей"),
    }


def for_bundle(bundle: dict) -> dict | None:
    """Прогноз на даты поездки. Маршрут из нескольких мест — shortcut: прогноз только для одиночных поездок."""
    if bundle.get("legs"):
        return None
    info = bundle.get("dest_info") or {}
    if info.get("lat") is None:
        return None
    start, end = date.fromisoformat(bundle["checkin"]), date.fromisoformat(bundle["checkout"])
    days = fetch(info["lat"], info["lon"], start, end)
    if not days:
        return None
    return summary(days, start, end, destination(bundle["dest"])["loc"])


def pack(groups: list[dict], weather: dict | None) -> list[dict]:
    """Памятка «что взять» по прогнозу: обещают дождь — зонт, даже если по норме месяц сухой."""
    if not weather or not weather["rainy"]:
        return groups
    clothes = next((g for g in groups if g["title"] == "Одежда по погоде"), None)
    if clothes is None or any("Зонт" in item["text"] for item in clothes["items"]):
        return groups
    when = ", ".join(day_label(stamp) for stamp in weather["rainy"][:3])
    clothes["items"].append({"text": "Зонт или дождевик", "why": f"прогноз Open-Meteo: дождь {when}"})
    return groups


def reminder_text(booking: dict) -> str:
    """Напоминание за 3 дня до выезда: свежий прогноз и совет, что перенести."""
    bundle = booking["bundle"]
    forecast = for_bundle(bundle)
    if forecast:
        return f"{forecast['line']}. Прогноз Open-Meteo на ваши даты, обновлю, если поменяется."
    weather = (bundle.get("dest_info") or {}).get("weather") or {}
    norm = f": по норме днём около {degrees(weather['air'])}" if weather.get("air") is not None else ""
    return f"Прогноз на {bundle['dest_name']} пока недоступен{norm}. Загляну ещё раз ближе к поездке."
