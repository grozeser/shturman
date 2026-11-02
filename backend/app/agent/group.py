"""Поездка компанией: ссылка для попутчиков, голосование за вариант и доля каждого в сумме."""

from datetime import date

from app.travel.brief import party_label
from app.travel.planner import day_label, transport_pros


def snapshot(state: dict) -> dict:
    """Что увидят попутчики: варианты на момент «позвать» — без чата, брифа и личных данных организатора."""
    plan, brief = state["plan"], state["brief"]
    first = plan["bundles"][0]
    people = brief["adults"] + len(brief["children"])
    return {
        "title": first["dest_name"],
        "dates": f"{day_label(date.fromisoformat(first['checkin']))} – {day_label(date.fromisoformat(first['checkout']))}",
        "nights": first["nights"],
        "party": party_label(brief),
        "people": people,
        "options": [
            {
                "id": bundle["id"],
                "label": bundle["label"],
                "total": bundle["total"],
                "per_person": bundle["per_person"],
                "hotel": f"{bundle['hotel']['name']} {bundle['hotel']['stars']}★, {bundle['hotel']['meal_label']}",
                "road": transport_pros(bundle["outbound"]),
                "why": bundle["why"][:3],
            }
            for bundle in plan["bundles"]
        ],
    }


def summary(data: dict, votes: list[dict], viewer: str | None) -> dict:
    """Голоса по вариантам, лидер (при ничьей — нет) и голоса этого браузера."""
    counts = [0] * len(data["options"])
    for vote in votes:
        if 0 <= vote["choice"] < len(counts):
            counts[vote["choice"]] += 1
    top = max(counts) if counts else 0
    leader = counts.index(top) if top and counts.count(top) == 1 else None
    return {
        "counts": counts,
        "voters": [{"name": v["name"], "choice": v["choice"]} for v in votes],
        "leader": leader,
        "mine": [{"name": v["name"], "choice": v["choice"]} for v in votes if viewer and v["voter_id"] == viewer],
    }
