"""«Сколько времени вы сэкономили»: итог работы агента из его же следа, без придуманных цифр.

Что агент сравнил и проверил, копится по ходу диалога в state["tally"]. Ручной путь оценивается
прозрачной формулой: поиск на 5 сайтах + открыть каждый сравнённый вариант + сверить каждую стыковку.
"""

from app.travel import inventory as inv
from app.travel.brief import plural

# сайты, которые человек открыл бы сам: билеты, отели, трансферы, погода, визы
SITES = 5
ACTIONS_PER_SITE = 4  # открыть, ввести маршрут и даты, состав, найти и отсортировать
# сколько вариантов человек реально открыл бы руками — дальше не листают
CAPS = {"destinations": 8, "hotels": 15, "transport": 10, "dates": 8}


def empty() -> dict:
    return {"destinations": 0, "hotel_dests": [], "transport": [], "dates": []}


def tally(state: dict) -> dict:
    return state.setdefault("tally", empty())


def track_suggestions(state: dict, sugg: dict) -> None:
    t = tally(state)
    t["destinations"] = max(t["destinations"], sugg["checked"])


def track_plan(state: dict, plan: dict) -> None:
    """Отели считаем по направлениям (агент сравнивает все отели места), дорогу и даты — по уникальным вариантам."""
    t = tally(state)
    dests = plan["route"] if plan.get("multi") else [plan["dest"]]
    t["hotel_dests"] = sorted(set(t["hotel_dests"]) | set(dests))
    options = plan["outbound"] + plan["inbound"]
    for bundle in plan["bundles"]:
        for leg in bundle.get("legs") or []:  # у маршрута списков рейсов нет — берём выбранные переезды
            options += [leg["outbound"], leg["inbound"]]
    t["transport"] = sorted(set(t["transport"]) | {o["id"] for o in options})
    t["dates"] = sorted(set(t["dates"]) | {d["date"] for d in plan["date_scan"]})


def summary(state: dict, bundle: dict | None = None) -> dict | None:
    plan = state.get("plan")
    if bundle is None:
        if not plan or not plan.get("bundles"):
            return None
        bundle = plan["bundles"][state["selected"]]
    t = state.get("tally") or empty()
    user = [m for m in state["messages"] if m["role"] == "user"]
    messages = sum(1 for m in user if not m.get("action"))
    taps = len(user) - messages
    counts = {
        "destinations": t["destinations"],
        "hotels": sum(len(inv.hotels(d)) for d in t["hotel_dests"]),
        "transport": len(t["transport"]),
        "dates": len(t["dates"]),
    }
    checks = len(bundle["checks"])
    clicks = SITES * ACTIONS_PER_SITE + sum(min(value, CAPS[key]) * (2 if key == "destinations" else 1) for key, value in counts.items())
    clicks += checks  # каждую стыковку человек сверял бы сам: расписание трансфера, время заселения, визу
    minutes = round(clicks * 0.5 + checks * 3)  # полминуты на страницу, три — на ручную сверку
    return counts | {
        "messages": messages,
        "taps": taps,
        "clicks": clicks,
        "sites": SITES,
        "minutes": minutes,
        "checks": checks,
        "line": line(messages, taps, clicks, counts, checks),
    }


def line(messages: int, taps: int, clicks: int, counts: dict, checks: int) -> str:
    """«3 сообщения вместо 70+ кликов по 5 сайтам: сравнил 62 направления, 18 отелей и 24 варианта дороги, проверил 7 стыковок»."""
    said = f"{messages} {plural(messages, 'сообщение', 'сообщения', 'сообщений')}"
    if taps:
        said += f" и {taps} {plural(taps, 'нажатие', 'нажатия', 'нажатий')}"
    compared = [
        f"{n} {plural(n, one, few, many)}"
        for n, (one, few, many) in (
            (counts["destinations"], ("направление", "направления", "направлений")),
            (counts["hotels"], ("отель", "отеля", "отелей")),
            (counts["transport"], ("вариант дороги", "варианта дороги", "вариантов дороги")),
            (counts["dates"], ("дату заезда", "даты заезда", "дат заезда")),
        )
        if n
    ]
    work = ""
    if compared:
        work = "сравнил " + (", ".join(compared[:-1]) + " и " + compared[-1] if len(compared) > 1 else compared[0])
    if checks:
        work += (", " if work else "") + f"проверил {checks} {plural(checks, 'стыковку', 'стыковки', 'стыковок')}"
    return f"{said} вместо {clicks // 10 * 10}+ кликов по {SITES} сайтам" + (f": {work}" if work else "")


def duration_label(minutes: int) -> str:
    if minutes < 55:
        return f"{max(5, round(minutes / 5) * 5)} мин"
    hours = round(minutes / 30) / 2
    return f"{hours:g} ч".replace(".", ",")
