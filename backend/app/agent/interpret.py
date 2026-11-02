"""Понимание сообщения: LLM извлекает намерение и изменения брифа, правила подстраховывают.

Модель возвращает только структуру (JSON). Решения о том, что делать дальше, принимает оркестратор.
"""

import json
import logging
import re
from datetime import date

from app.agent import llm
from app.travel import geo
from app.travel.brief import DIET_LABELS, REGIONS, parse_rules
from app.travel.catalog import KIND_LABELS, destinations, find_destination, find_origin, origins

log = logging.getLogger("interpret")

INTENTS = {"plan", "modify", "select", "book", "question", "post", "reset", "chat"}
POST_TYPES = {"early_checkin", "late_checkout", "add_transfer", "change_dates", "cancel", "reminders"}
PREFS = {"near_beach", "pool", "spa", "quiet", "kids_club"}
MOODS = {"romantic", "party", "calm", "active"}

SYSTEM_PROMPT = f"""Ты — модуль понимания запросов тревел-агента. Пользователь пишет по-русски свободным текстом.
Верни ТОЛЬКО JSON без пояснений по схеме:
{{
 "intent": "plan|modify|select|book|question|post|reset|chat",
 "patch": {{
   "origin_city": "город вылета или null",
   "destination": "город/страна/курорт, куда хочет, или null",
   "destination_any": true если просит подобрать направление, иначе false,
   "exclude": ["направления, которые НЕ хочет"],
   "kinds": [типы отдыха из списка {sorted(KIND_LABELS)}],
   "warm": true|false|null,
   "month": 1-12 или null,
   "date_from": "YYYY-MM-DD" или null,
   "nights": число ночей или null,
   "adults": число взрослых или null,
   "children_ages": [возрасты детей] или null,
   "seniors": true если едут пожилые, иначе null,
   "accessible": true если кто-то на коляске, плохо ходит или просит «без лестниц», иначе null,
   "pets": "dog"|"cat"|"none"|null,
   "budget_rub": общий бюджет в рублях или null,
   "budget_per_person": true если бюджет указан на человека,
   "budget_level": "low"|"mid"|"high"|null,
   "max_hours": максимум часов в пути в одну сторону или null,
   "direct_only": true|null,
   "transport": "train"|"flight"|null,
   "avoid_night": true|null,
   "visa_free": true|null,
   "meal": "RO"|"BB"|"HB"|"AI"|null,
   "diet": [особое питание из {sorted(DIET_LABELS)}] или null,
   "refundable": true|false|null,
   "min_stars": 1-5 или null,
   "hotel_prefs": [из {sorted(PREFS)}] или null,
   "mood": [из {sorted(MOODS)}] или null,
   "regions": [из {sorted(REGIONS)}] — если назван регион, а не конкретное место («в Европу», «на Черное море», «по России»),
   "own_car": true если едут на своей машине
 }},
 "inferred": [{{"field": "имя поля из patch", "reason": "почему ты это вывел, коротко"}}],
 "shift_days": сдвиг дат в днях (+ позже, − раньше) или null,
 "nights_delta": изменение длительности в ночах или null,
 "budget_change": "down"|"up"|null,
 "select": номер выбранного варианта 1-4 или null,
 "post": {{"type": "{"|".join(sorted(POST_TYPES))}", "shift_days": число|null, "date_from": "YYYY-MM-DD"|null}} или null,
 "question": "фактический вопрос пользователя" или null
}}
Правила:
- Заполняй только то, что пользователь сказал или что прямо следует из слов. Не выдумывай.
- Пиши ТОЛЬКО найденные поля: null, false и пустые списки не выводи вовсе — ответ должен быть коротким. Пример: {{"intent": "plan", "patch": {{"month": 11, "kinds": ["sea"]}}}}
- Скрытые требования выводи осторожно и перечисляй их в "inferred": «с малышом» → children_ages [1]; «медовый месяц» → mood romantic, adults 2; «тёплое море» → kinds [sea], warm true; «без долгих перелётов» → max_hours 5; «недорого» → budget_level low; «с бабушкой» → seniors true.
- Числа: «100к», «сто тысяч» → 100000. «На неделю» → nights 7, «на 10 дней» → nights 9. Год выбирай ближайший в будущем.
- intent: plan — новый запрос или уточнение; modify — изменить уже собранный план («на 2 дня позже», «дешевле», «с нами едет собака»); select — выбрать вариант («второй», «давай Хургаду» → лучше plan с destination); book — оформить/оплатить; post — действия с уже купленной поездкой (ранний заезд, перенос дат, трансфер, отмена); question — вопрос о визе, погоде, что посмотреть; reset — начать заново; chat — болтовня.
- Сегодня {{today}}. Текущий этап: {{stage}}. Текущий бриф: {{brief}}."""


def _match_origin(name: str | None) -> str | None:
    if not name:
        return None
    found = find_origin("из " + name)
    if found:
        return found["id"]
    lowered = name.lower()
    for orig in origins().values():
        if orig["name"].lower() == lowered:
            return orig["id"]
    return None


def _clean_list(values, allowed: set) -> list | None:
    if not isinstance(values, list):
        return None
    return sorted({v for v in values if isinstance(v, str) and v in allowed})


def map_llm(data: dict, brief: dict, today: date) -> dict:
    """Ответ модели → тот же формат, что у разбора на правилах. Всё проверяем: модели не доверяем вслепую."""
    raw = data.get("patch") or {}
    patch: dict = {}
    unknown_destination = None
    origin_id = _match_origin(raw.get("origin_city"))
    if origin_id:
        patch["origin"] = origin_id
    if raw.get("destination_any"):
        patch["destination"] = None
    elif isinstance(raw.get("destination"), str) and raw["destination"].strip():
        dest = find_destination(raw["destination"])
        if dest:
            patch["destination"] = dest["id"]
        else:
            unknown_destination = raw["destination"].strip()[:60]
    excluded = []
    for name in raw.get("exclude") or []:
        dest = find_destination(str(name))
        if dest:
            excluded.append(dest["id"])
    if excluded:
        patch["exclude"] = sorted(set(brief["exclude"] + excluded))
    kinds = _clean_list(raw.get("kinds"), set(KIND_LABELS))
    if kinds:
        patch["kinds"] = sorted(set(brief["kinds"] + kinds))
    if raw.get("warm") is True:
        patch["warm"] = True
    month = raw.get("month")
    if isinstance(month, int) and 1 <= month <= 12:
        patch["month"] = month
    if isinstance(raw.get("date_from"), str):
        try:
            start = date.fromisoformat(raw["date_from"])
            if start >= today:
                patch["date_from"] = start.isoformat()
                patch["month"] = start.month
        except ValueError:
            pass
    nights = raw.get("nights")
    if isinstance(nights, (int, float)) and 1 <= nights <= 60:
        patch["nights"] = int(nights)
    adults = raw.get("adults")
    if isinstance(adults, (int, float)) and 1 <= adults <= 12:
        patch["adults"] = int(adults)
    ages = raw.get("children_ages")
    if isinstance(ages, list):
        clean = [int(a) for a in ages if isinstance(a, (int, float)) and 0 <= a < 18][:6]
        patch["children"] = clean
        if clean and "adults" not in patch and brief["adults"] == 2:
            patch["adults"] = 2
    if raw.get("seniors") is True:
        patch["seniors"] = True
    if raw.get("accessible") is True:
        patch["accessible"] = True
    if raw.get("pets") in ("dog", "cat"):
        patch["pets"] = raw["pets"]
    elif raw.get("pets") == "none":
        patch["pets"] = None
    budget = raw.get("budget_rub")
    if isinstance(budget, (int, float)) and 5_000 <= budget <= 50_000_000:
        party = patch.get("adults", brief["adults"]) + len(patch.get("children", brief["children"]))
        patch["budget"] = int(budget * party if raw.get("budget_per_person") else budget)
    if raw.get("budget_level") in ("low", "mid", "high"):
        patch["budget_level"] = raw["budget_level"]
    hours = raw.get("max_hours")
    if isinstance(hours, (int, float)) and 1 <= hours <= 30:
        patch["max_hours"] = float(hours)
    for key in ("direct_only", "avoid_night", "visa_free"):
        if raw.get(key) is True:
            patch[key] = True
    if raw.get("transport") in ("train", "flight"):
        patch["transport"] = raw["transport"]
    if raw.get("meal") in ("RO", "BB", "HB", "AI"):
        patch["meal"] = raw["meal"]
    diet = _clean_list(raw.get("diet"), set(DIET_LABELS))
    if diet:
        patch["diet"] = sorted(set(brief.get("diet") or []) | set(diet))
    if isinstance(raw.get("refundable"), bool):
        patch["refundable"] = raw["refundable"]
    stars = raw.get("min_stars")
    if isinstance(stars, int) and 1 <= stars <= 5:
        patch["min_stars"] = stars
    prefs = _clean_list(raw.get("hotel_prefs"), PREFS)
    if prefs:
        patch["hotel_prefs"] = sorted(set(brief["hotel_prefs"] + prefs))
    mood = _clean_list(raw.get("mood"), MOODS)
    if mood:
        patch["mood"] = sorted(set(brief["mood"] + mood))
    regions = _clean_list(raw.get("regions"), set(REGIONS))
    if regions:
        patch["regions"] = regions
    if raw.get("own_car") is True:
        patch["own_car"] = True

    reasons = {}
    for item in data.get("inferred") or []:
        if isinstance(item, dict) and isinstance(item.get("field"), str) and isinstance(item.get("reason"), str):
            field = {"children_ages": "children", "budget_rub": "budget", "origin_city": "origin"}.get(item["field"], item["field"])
            reasons[field] = item["reason"][:120]

    intent = data.get("intent") if data.get("intent") in INTENTS else "plan"
    if intent == "modify":
        intent = "plan"
    post = data.get("post") if isinstance(data.get("post"), dict) and data["post"].get("type") in POST_TYPES else None
    shift = data.get("shift_days") if isinstance(data.get("shift_days"), int) and abs(data["shift_days"]) <= 60 else None
    delta = data.get("nights_delta") if isinstance(data.get("nights_delta"), int) and abs(data["nights_delta"]) <= 30 else None
    if delta and "nights" not in patch:
        patch["nights"] = max(1, brief["nights"] + delta)
    select = data.get("select") if isinstance(data.get("select"), int) and 1 <= data["select"] <= 4 else None
    return {
        "intent": "post" if post else intent,
        "patch": patch,
        "inferred_reasons": reasons,
        "shift_days": shift,
        "select": select,
        "post": post,
        "question": data.get("question") if isinstance(data.get("question"), str) else None,
        "budget_change": data.get("budget_change") if data.get("budget_change") in ("down", "up") else None,
        "unknown_destination": unknown_destination,
        "source": "llm",
    }


def interpret(text: str, brief: dict, stage: str, today: date) -> dict:
    rules = parse_rules(text, brief, today, stage)
    rules["source"] = "rules"
    rules.setdefault("inferred_reasons", {})
    if not llm.enabled():
        return rules
    # приветствие, «кто ты» и вопрос о визе/погоде/дороге правила распознают надёжно, а отвечают шаблоном по данным;
    # модель тут только вредит («Да, виза не нужна… подтверждено официальными данными») и тратит ~40 с на CPU
    if rules["intent"] in ("chat", "handoff") or (rules["intent"] == "question" and rules.get("question") not in (None, "other")):
        return rules
    compact = {k: v for k, v in brief.items() if v not in (None, [], False) and k != "priorities"}
    prompt = (
        SYSTEM_PROMPT.replace("{today}", today.isoformat())
        .replace("{stage}", stage)
        .replace("{brief}", json.dumps(compact, ensure_ascii=False))
    )
    try:
        raw = llm.chat(
            [{"role": "system", "content": prompt}, {"role": "user", "content": text}], json_mode=True, max_tokens=350, temperature=0.0
        )
        result = map_llm(llm.extract_json(raw), brief, today)
    except (llm.LlmUnavailable, ValueError) as error:
        log.info("Разбор на правилах: %s", error)
        rules["fallback"] = True
        return rules
    # правила подстраховывают модель: что модель упустила, но правила уверенно нашли — добавляем
    for key, value in rules["patch"].items():
        if key not in result["patch"] and key in (
            "date_from",
            "budget",
            "origin",
            "pets",
            "children",
            "adults",
            "nights",
            "month",
            "diet",
            "accessible",
        ):
            result["patch"][key] = value
    # «$1500», «до 50 на человека»: правила считают по курсу, помеченному в брифе, а модель путает курсы
    # (на «$1500» qwen3 дала 300 000 ₽) — здесь правила главнее, вместе с пояснением
    if rules["inferred_reasons"].get("budget") and "budget" in rules["patch"]:
        result["patch"]["budget"] = rules["patch"]["budget"]
        result["inferred_reasons"]["budget"] = rules["inferred_reasons"]["budget"]
    for key in ("shift_days", "select"):
        if result.get(key) is None and rules.get(key) is not None and result["intent"] in ("plan", "select", "post"):
            result[key] = rules[key]
    if result["post"] is None and rules.get("post"):
        result["post"], result["intent"] = rules["post"], "post"
    for key in ("compare", "compare_picks"):  # «Турция или Египет?» — модель склонна выбрать одно место за человека
        if rules.get(key):
            result[key], result["unknown_destination"] = rules[key], None
            result["patch"].pop("destination", None)
    result["family_guess"] = rules.get("family_guess")
    result["ages_guessed"] = rules.get("ages_guessed") and not result["inferred_reasons"].get("children")
    return result


def known_destination_names() -> list[str]:
    return sorted(d["name"] for d in destinations().values())


def looks_like_place(text: str) -> str | None:
    """«Хочу в Норвегию» — направление, которого нет в базе. Возвращаем название для честного ответа."""
    hint = geo.hint_for(text)  # «хочу в норвегию на фьорды» — страна, даже со строчной буквы
    if hint and not find_destination(hint):
        return hint
    match = re.search(r"\b(?:в|во|на)\s+([А-ЯЁ][а-яё-]{3,}(?:\s+[А-ЯЁ][а-яё-]+)?)", text)
    if match:
        name = match.group(1)
    else:
        # «Токио в апреле»: название без предлога — любое слово с заглавной, кроме обычных начал фраз
        words = [
            w
            for w in re.findall(r"\b[А-ЯЁ][а-яё-]{3,}\b", text)
            if w.lower() not in geo.SENTENCE_STARTS and not w.lower().endswith(geo.NOT_A_NAME)  # «Романтические», «Хотелось»
        ]
        if not words:
            return geo.lower_place(text)
        name = words[0]
    skip = (
        "Январ",
        "Феврал",
        "Март",
        "Апрел",
        "Ма",
        "Июн",
        "Июл",
        "Август",
        "Сентябр",
        "Октябр",
        "Ноябр",
        "Декабр",
        "Нов",
        "Рожд",
        "Европ",
        "Ази",
    )
    if name.startswith(skip) or find_destination(name):
        return None
    return name
