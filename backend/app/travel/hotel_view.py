"""Взгляд отеля: кому агент его рекомендует, кому нет и почему, и что изменить, чтобы приходили «свои» гости.

Пользовательская история из ТЗ: «как отель, я хочу, чтобы меня рекомендовали тем гостям, которым я действительно подхожу».
Пригодность считается той же функцией, что и в подборе, — для типовых гостей.
"""

import copy
from datetime import date, timedelta

from app.travel import inventory as inv
from app.travel.brief import derive, new_brief, new_sources
from app.travel.catalog import destination
from app.travel.clock import today
from app.travel.planner import hotel_exclusion, hotel_fit

SEGMENTS = {
    "family": ("Семьи с детьми", {"children": [6], "kinds": ["sea"]}),
    "couple": ("Пары", {"mood": ["romantic"]}),
    "solo": ("Один путешественник", {"adults": 1}),
    "pets": ("С питомцем", {"pets": "dog"}),
    "seniors": ("Старшее поколение", {"seniors": True}),
    "party": ("Любители ночной жизни", {"adults": 3, "mood": ["party"]}),
    "accessible": ("Гости на коляске", {"accessible": True}),
}

# что отель может изменить у себя и как это называть
LEVERS = {
    "kids_club": "открыть детский клуб",
    "kids_pool": "сделать детский бассейн",
    "family_rooms": "добавить семейные номера",
    "pets": "разрешить проживание с животными",
    "quiet": "сделать тихие часы без ночной анимации",
    "spa": "открыть спа",
    "pool": "сделать бассейн",
    "accessible": "сделать номера с доступной средой",
    "early_checkin": "разрешить ранний заезд",
}


def segment_of(brief: dict) -> str:
    if brief.get("pets"):
        return "pets"
    if brief.get("accessible"):
        return "accessible"
    if brief.get("children"):
        return "family"
    if brief.get("seniors"):
        return "seniors"
    if brief.get("adults") == 1:
        return "solo"
    if "party" in brief.get("mood", []):
        return "party"
    return "couple"


def _brief_for(segment: str) -> dict:
    brief, sources = new_brief(), new_sources()
    brief.update(copy.deepcopy(SEGMENTS[segment][1]))
    derive(brief, sources)
    return brief


def fit_by_segment(h: dict, checkin: date | None = None) -> dict[str, dict]:
    """Балл пригодности отеля для каждого типа гостей; 0 и причина, если агент таким гостям его не покажет."""
    dest = destination(h["dest"])
    checkin = checkin or today() + timedelta(days=60)
    result = {}
    for key, (label, _) in SEGMENTS.items():
        brief = _brief_for(key)
        quote = inv.quote_hotel(h, checkin, 7, brief["adults"], brief["children"], h["meals"][0], True) | {"available": True}
        excluded = hotel_exclusion(h, brief, quote)
        if excluded:
            result[key] = {"label": label, "score": 0, "excluded": excluded, "pros": [], "cons": []}
            continue
        fit = hotel_fit(h, brief, dest, quote)
        result[key] = {"label": label, "score": fit["score"], "excluded": None, "pros": fit["pros"][:3], "cons": fit["cons"][:3]}
    return result


def improvements(h: dict) -> list[dict]:
    """Какие изменения сильнее всего расширят круг «своих» гостей: прирост баллов по сегментам."""
    base = fit_by_segment(h)
    ideas = []
    for feature, title in LEVERS.items():
        if h["features"].get(feature):
            continue
        changed = copy.deepcopy(h)
        changed["features"][feature] = True
        if feature == "quiet":
            changed["features"]["party"] = False
        after = fit_by_segment(changed)
        gains = {k: after[k]["score"] - base[k]["score"] for k in base if after[k]["score"] > base[k]["score"]}
        if gains:
            opened = [SEGMENTS[k][0] for k in gains if base[k]["excluded"]]
            ideas.append(
                {
                    "feature": feature,
                    "title": title,
                    "gains": {SEGMENTS[k][0]: v for k, v in sorted(gains.items(), key=lambda kv: -kv[1])},
                    "opens": opened,
                    "total": sum(gains.values()),
                }
            )
    return sorted(ideas, key=lambda idea: -idea["total"])[:4]


def hotel_report(hotel_id: str, stats: dict) -> dict:
    h = inv.hotel(hotel_id)
    segments = fit_by_segment(h)
    best = [s["label"] for s in sorted(segments.values(), key=lambda s: -s["score"]) if s["score"] >= 55][:3]
    return {
        "hotel": {
            "id": h["id"],
            "name": h["name"],
            "stars": h["stars"],
            "rating": h["rating"],
            "area": h["area"],
            "beach_m": h["beach_m"],
            "center_km": h["center_km"],
            "features": h["features"],
            "meals": h["meals"],
            "dest": h["dest"],
            "dest_name": destination(h["dest"])["name"],
        },
        "segments": segments,
        "best_for": best,
        "improvements": improvements(h),
        "stats": stats,
    }


def hotels_overview(dest_id: str, stats_by_hotel: dict[str, dict]) -> list[dict]:
    rows = []
    for h in inv.hotels(dest_id):
        segments = fit_by_segment(h)
        stats = stats_by_hotel.get(h["id"], {})
        rows.append(
            {
                "id": h["id"],
                "name": h["name"],
                "stars": h["stars"],
                "rating": h["rating"],
                "segments": {k: v["score"] for k, v in segments.items()},
                "recommended": stats.get("recommended", 0),
                "rejected": stats.get("rejected", 0),
                "booked": stats.get("booked", 0),
            }
        )
    return sorted(rows, key=lambda r: (-r["recommended"], -r["rating"]))
