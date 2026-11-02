"""«Турция или Египет в мае?» — две-три собранные поездки рядом: цена от двери до двери, погода, дорога, виза,
отель, плюсы и минусы друг относительно друга и рекомендация. Каждую поездку собирает тот же планировщик,
поэтому после «беру эту» план совпадает с тем, что было в сравнении, до рубля.
"""

from datetime import date

from app.travel import planner
from app.travel.brief import money, party_label, plural
from app.travel.catalog import MONTHS_IN, destination
from app.travel.planner import day_label, hours_label


def build_comparison(brief: dict, ids: list[str], today: date) -> dict:
    items = []
    for dest_id in ids:
        dest = destination(dest_id)
        plan = planner.build_plan(brief | {"destination": dest_id, "route": [], "route_nights": []}, dest_id, today)
        base = {"id": dest_id, "name": dest["name"], "country": dest["country"], "kinds": dest["kinds"], "visa": dest["visa"]}
        if "error" in plan:
            items.append(base | {"error": plan["error"], "pros": [], "cons": [plan["error"]]})
            continue
        b = plan["bundles"][0]
        out = b["outbound"]
        items.append(
            base
            | {
                "error": None,
                "checkin": b["checkin"],
                "checkout": b["checkout"],
                "nights": b["nights"],
                "total": b["total"],
                "per_person": b["per_person"],
                "weather": b["dest_info"]["weather"],
                "travel": {"mode": out["mode"], "minutes": out["duration_min"], "stops": out["stops"], "via": out["via"]},
                "hotel": {
                    "name": b["hotel"]["name"],
                    "stars": b["hotel"]["stars"],
                    "rating": b["hotel"]["rating"],
                    "meal_label": b["hotel"]["meal_label"],
                    "beach_m": b["hotel"]["beach_m"],
                    "fit": b["hotel"]["fit"],
                },
                "warnings": [c["title"] for c in b["checks"] if c["status"] in ("warn", "error")],
                "steps": len(plan["trace"]),
                "pros": [],
                "cons": [],
            }
        )
    ready = [item for item in items if not item["error"]]
    _pros_and_cons(ready, brief)
    winner = _winner(ready, brief)
    return {"items": items, "winner": winner, "month": brief["month"], "verdict": _verdict(ready, winner)}


def _pros_and_cons(items: list[dict], brief: dict) -> None:
    """Плюсы и минусы относительно соседей: «дешевле на 13 000 ₽», «вода теплее: +26° против +22°»."""
    if len(items) < 2:
        return
    sea = "sea" in brief["kinds"] or brief["warm"] or all("sea" in item["kinds"] for item in items)

    def best_and_rest(key, better):
        ranked = sorted(items, key=key, reverse=better == "max")
        return ranked[0], ranked[1:]

    cheap, others = best_and_rest(lambda i: i["total"], "min")
    gap = others[0]["total"] - cheap["total"]
    if gap >= 1000:
        cheap["pros"].append(f"дешевле на {money(gap)}")
        for item in others:
            item["cons"].append(f"дороже на {money(item['total'] - cheap['total'])}")
    waters = [i for i in items if i["weather"]["water"] is not None and "sea" in i["kinds"]]
    if sea and len(waters) >= 2:
        warm, cold = best_and_rest(lambda i: i["weather"]["water"], "max")
        if warm["weather"]["water"] - cold[0]["weather"]["water"] >= 2:
            warm["pros"].append(f"вода теплее: +{warm['weather']['water']}° против +{cold[0]['weather']['water']}°")
    for item in waters:
        if item["weather"]["water"] < 21 and sea:
            item["cons"].append(f"вода +{item['weather']['water']}° — для купания прохладно")
    airs = [i for i in items if i["weather"]["air"] is not None]
    if len(airs) >= 2:
        hot, cool = best_and_rest(lambda i: i["weather"]["air"], "max")
        if hot["weather"]["air"] - cool[0]["weather"]["air"] >= 3 and (sea or brief["warm"]):
            hot["pros"].append(f"теплее днём: +{hot['weather']['air']}° против +{cool[0]['weather']['air']}°")
    for item in items:
        if (item["weather"]["rain"] or 0) >= 8:
            item["cons"].append(f"около {item['weather']['rain']} дней с ливнями")
    fast, slow = best_and_rest(lambda i: i["travel"]["minutes"], "min")
    if slow[0]["travel"]["minutes"] - fast["travel"]["minutes"] >= 45:
        fast["pros"].append(f"дорога короче на {hours_label(slow[0]['travel']['minutes'] - fast['travel']['minutes'])}")
    for item in items:
        if item["travel"]["stops"]:
            item["cons"].append(f"пересадка в {item['travel']['via']}")
        if "не нужна" in item["visa"]:
            if any("не нужна" not in other["visa"] for other in items):
                item["pros"].append("без визы")
        else:
            item["cons"].append(f"виза: {item['visa']}")
    fit, rest = best_and_rest(lambda i: i["hotel"]["fit"], "max")
    if fit["hotel"]["fit"] - rest[0]["hotel"]["fit"] >= 5:
        fit["pros"].append(f"отель подходит вам лучше: {fit['hotel']['fit']} против {rest[0]['hotel']['fit']} из 100")


def _winner(items: list[dict], brief: dict) -> str | None:
    """Кого рекомендовать: плюсы весят по приоритетам гостей (цена, время в пути, комфорт), минусы вычитаются."""
    if not items:
        return None
    if len(items) == 1:
        return items[0]["id"]
    p = brief["priorities"]
    weights = {"дешевле": 1 + 2 * p["price"], "дорога": 0.5 + p["speed"], "отель": 0.5 + p["comfort"], "вода": 1.5, "теплее": 1.0}

    def score(item: dict) -> float:
        plus = sum(next((w for key, w in weights.items() if pro.startswith(key)), 1.0) for pro in item["pros"])
        minus = sum(0.5 if con.startswith("дороже") else 1.0 for con in item["cons"])
        return plus - minus

    return max(items, key=score)["id"]


def _verdict(items: list[dict], winner: str | None) -> str:
    if not winner:
        return "Ни одну из поездок не удалось собрать под ваши условия."
    best = next(i for i in items if i["id"] == winner)
    text = f"Мой выбор — {best['name']}" + (f": {', '.join(best['pros'][:2])}" if best["pros"] else "")
    others = [i for i in items if i["id"] != winner and i["pros"]]
    for other in others:
        text += f". {other['name']} — если важнее, что там {other['pros'][0]}"
    return text + "."


def comparison_text(comparison: dict, brief: dict) -> str:
    items = comparison["items"]
    ready = [i for i in items if not i["error"]]
    month = f", в {MONTHS_IN[(comparison['month'] or date.fromisoformat(ready[0]['checkin']).month) - 1]}" if ready else ""
    lines = [f"Собрал {len(items)} {plural(len(items), 'поездку', 'поездки', 'поездок')} рядом — {party_label(brief)}{month}:"]
    for index, item in enumerate(items, start=1):
        if item["error"]:
            lines.append(f"{index}. {item['name']} — не собрать: {item['error']}")
            continue
        w = item["weather"]
        weather = ", ".join(
            part
            for part in (
                f"днём {'+' if (w['air'] or 0) > 0 else ''}{w['air']}°" if w["air"] is not None else "",
                f"вода +{w['water']}°" if w["water"] is not None and "sea" in item["kinds"] else "",
            )
            if part
        )
        road = (
            ("прямой рейс" if not item["travel"]["stops"] else f"с пересадкой в {item['travel']['via']}")
            if item["travel"]["mode"] == "flight"
            else "поезд"
        )
        h = item["hotel"]
        lines.append(
            f"{index}. {item['name']}, {day_label(date.fromisoformat(item['checkin']))} – {day_label(date.fromisoformat(item['checkout']))}: "
            f"{money(item['total'])} от двери до двери; {weather}; {road} {hours_label(item['travel']['minutes'])}; "
            f"виза — {item['visa']}; {h['name']} {h['stars']}★, {h['meal_label']}"
        )
    lines.append(comparison["verdict"])
    if len(ready) >= 1:
        lines.append("Какую берём? Соберу её целиком — с вариантами, стыковками и оформлением.")
    return "\n".join(lines)


def comparison_quick(comparison: dict) -> list[dict]:
    ready = [i for i in comparison["items"] if not i["error"]]
    ready.sort(key=lambda i: i["id"] != comparison["winner"])
    return [{"label": f"Беру: {i['name']}", "action": {"type": "choose_compared", "id": i["id"]}} for i in ready]
