"""Данные для карты поездки: реальные координаты города вылета и городов поездки."""

from datetime import date

from app.travel import planner
from app.travel.brief import new_brief
from app.travel.catalog import destination, origin


def test_bundle_has_real_coordinates_for_map():
    bundle = planner.build_plan(new_brief() | {"month": 5, "origin": "LED"}, "antalya", date(2026, 10, 24))["bundles"][0]
    info = bundle["dest_info"]
    assert (info["lat"], info["lon"]) == (destination("antalya")["lat"], destination("antalya")["lon"])
    assert info["origin"] == {"name": origin("LED")["name"], "lat": origin("LED")["lat"], "lon": origin("LED")["lon"]}


def test_route_parts_keep_their_own_coordinates():
    plan = planner.build_route(new_brief() | {"month": 5, "nights": 7}, ["istanbul", "cappadocia"], date(2026, 10, 24), [3, 4])
    legs = plan["bundles"][0]["legs"]
    assert [round(leg["dest_info"]["lat"], 1) for leg in legs] == [round(destination(d)["lat"], 1) for d in ("istanbul", "cappadocia")]
