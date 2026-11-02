"""«Что агент поймал за вас»: исправленные стыковки, отсеянное и ловушка «дешёвый отель дороже»."""

from datetime import date

from app.travel import planner
from app.travel.brief import new_brief

TODAY = date(2026, 10, 24)


def test_cheap_hotel_trap_is_real_money():
    plan = planner.build_plan(new_brief() | {"month": 12}, "dubai", TODAY)
    bundle = plan["bundles"][0]
    trap = next(item for item in bundle["caught"] if item["kind"] == "trap")
    name = trap["title"].split("»")[0].lstrip("«")
    cheaper = next(h for h in plan["hotels"] if h["name"] == name)
    assert cheaper["price_total"] < bundle["hotel"]["price_total"], "отель в ловушке действительно дешевле"
    assert "переплата" in trap["detail"]


def test_relaxed_condition_is_not_called_caught():
    # с младенцем до Пхукета короче 5 ч не долететь: это условие уступлено — значит, «отсеял» про него не пишем
    brief = new_brief() | {"month": 1, "children": [1], "max_hours": 5, "avoid_night": True}
    plan = planner.build_plan(brief, "phuket", TODAY)
    bundle = plan["bundles"][0]
    assert plan["relaxed"]
    assert not any("ч в пути" in item["detail"] for item in bundle["caught"])


def test_filtered_reasons_for_family():
    brief = new_brief() | {"month": 11, "children": [4], "avoid_night": True, "max_hours": 6, "hotel_prefs": ["kids_club"]}
    caught = planner.build_plan(brief, "hurghada", TODAY)["bundles"][0]["caught"]
    assert any(item["detail"] == "ночные рейсы" for item in caught)
    assert any(item["detail"] == "только для взрослых 16+" for item in caught)


def test_revalidate_does_not_double_fixes():
    # перед оплатой агент проверяет стыковки ещё раз: доплата «номер с ночи прилёта» не должна попасть в итог дважды
    plan = planner.build_plan(new_brief() | {"month": 12}, "dubai", TODAY)
    bundle = plan["bundles"][0]
    assert bundle["extras"], "у Дубая в декабре прилёт задолго до заселения — есть авто-исправление"
    extras, total = list(bundle["extras"]), bundle["total"]
    planner.validate(bundle, new_brief() | {"month": 12}, planner.destination("dubai"), TODAY)
    assert bundle["extras"] == extras
    assert bundle["total"] == total
