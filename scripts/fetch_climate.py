"""Запекает климатические нормы в backend/app/data/climate.json по данным Open-Meteo (CC BY 4.0).

    python scripts/fetch_climate.py            # только направления без климата
    python scripts/fetch_climate.py --all      # пересчитать всё

Воздух — средний дневной максимум за 2015–2024, дожди — среднее число дней с заметным дождём ≥ 5 мм,
вода — средняя температура поверхности моря за 2022–2024 (marine API). Запускать вручную, рантайм в сеть не ходит.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "backend" / "app" / "data"


def get(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(full, timeout=60) as response:
                return json.load(response)
        except Exception as error:  # noqa: BLE001 — сеть: повторяем с паузой
            print("  retry", attempt + 1, error)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"не удалось получить {full}")


def monthly(times: list[str], values: list, reducer) -> list:
    buckets: dict[int, list] = defaultdict(list)
    for stamp, value in zip(times, values, strict=True):
        if value is not None:
            buckets[int(stamp[5:7])].append(value)
    return [reducer(buckets[m]) if buckets[m] else None for m in range(1, 13)]


def air_and_rain(lat: float, lon: float) -> tuple[list, list]:
    data = get(
        "https://archive-api.open-meteo.com/v1/archive",
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": "2015-01-01",
            "end_date": "2024-12-31",
            "daily": "temperature_2m_max,precipitation_sum",
            "timezone": "auto",
        },
    )
    daily = data["daily"]
    air = monthly(daily["time"], daily["temperature_2m_max"], lambda v: round(sum(v) / len(v)))
    years = 10
    rain = monthly(daily["time"], daily["precipitation_sum"], lambda v: round(sum(x >= 5 for x in v) / years))
    return air, rain


def water(lat: float, lon: float) -> list:
    data = get(
        "https://marine-api.open-meteo.com/v1/marine",
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": "2022-01-01",
            "end_date": "2024-12-31",
            "hourly": "sea_surface_temperature",
        },
    )
    hourly = data["hourly"]
    return monthly(hourly["time"], hourly["sea_surface_temperature"], lambda v: round(sum(v) / len(v)))


def main() -> None:
    destinations = json.loads((DATA / "destinations.json").read_text(encoding="utf-8"))
    path = DATA / "climate.json"
    climate = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for dest in destinations:
        if dest["id"] in climate and "--all" not in sys.argv:
            continue
        print(dest["id"])
        air, rain = air_and_rain(dest["lat"], dest["lon"])
        entry = {"air": air, "rain": rain, "water": None}
        if dest["sea"]:
            entry["water"] = water(*dest["sea"])
        climate[dest["id"]] = entry
        path.write_text(json.dumps(climate, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(1)
    print("готово:", len(climate))


if __name__ == "__main__":
    main()
