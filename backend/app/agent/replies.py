"""Тексты агента. Черновик собирается из фактов шаблоном; LLM (если есть) делает его живее,
но ответ с числом, которого нет в фактах, отбрасывается — агент не выдумывает цены и время."""

import json
import logging
import re
from datetime import date

from app.agent import llm
from app.travel.brief import money, party_label, plural
from app.travel.catalog import KIND_LABELS, MONTHS, MONTHS_IN, climate, destination, origin
from app.travel.planner import day_label, hours_label, time_of

log = logging.getLogger("replies")


def month_options(today: date, count: int = 4) -> list[int]:
    start = today.month if today.day <= 20 else today.month % 12 + 1
    return [((start - 1 + i) % 12) + 1 for i in range(count)]


def greeting(profile: dict) -> str:
    facts = profile.get("facts") or {}
    if facts:
        known = [fact["label"] for fact in facts.values()][:4]
        trips = profile.get("trips") or []
        repeat = f" Можно и так: «как в прошлый раз, но в горы» — возьму всё из поездки в {trips[-1]['dest']}." if trips else ""
        return (
            "С возвращением! Я помню: " + "; ".join(known) + ". "
            "Расскажите, куда и когда хотите в этот раз — или просто «хочу к морю», остальное подберу." + repeat
        )
    return (
        "Привет! Я Штурман — соберу поездку целиком: направление, транспорт, отель, трансфер и проверю все стыковки. "
        "Опишите своими словами, например: «хочу к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов»."
    )


ABOUT = (
    "Я Штурман: по одному сообщению собираю поездку целиком — направление, перелёт или поезд, отель и трансфер, "
    "проверяю стыковки и считаю цену от двери до двери. Потом пересоберу под новые условия и помогу после покупки. "
    "Напишите, куда и когда хочется, — например, кнопкой ниже."
)
EXAMPLES_QUICK = [
    {"label": "К морю в ноябре с ребёнком", "text": "хочу к тёплому морю в ноябре, недорого, с ребёнком 5 лет"},
    {"label": "Стамбул на выходные вдвоём", "text": "Стамбул на выходные вдвоём"},
    {"label": "Горы зимой", "text": "хочу покататься на лыжах в феврале, нас двое"},
]
# агент не справился или человек просит живого менеджера — диалог уходит в очередь консоли оператора
HANDOFF_QUICK = {"label": "Позвать менеджера", "action": {"type": "handoff"}}


def understood(brief: dict, chips: list[dict]) -> str:
    labels = [c["label"] for c in chips if c["kind"] in ("explicit", "memory", "inferred") and c["key"] not in ("origin",)]
    return ", ".join(labels[:7])


def clarify(brief: dict, sources: dict, chips: list[dict], ask_who: bool) -> str:
    got = understood(brief, chips)
    head = f"Понял: {got}. " if got else ""
    question = "Подскажите только одно: когда примерно едете?"
    if ask_who:
        question = "Подскажите две вещи, и я сразу подберу варианты: когда примерно едете и кто едет?"
    return head + question + " Остальное предложу сам и покажу, что предположил."


def clarify_quick(today: date, ask_who: bool, brief: dict) -> list[dict]:
    months = month_options(today)
    if ask_who:
        return [
            {"label": f"В {MONTHS_IN[months[0] - 1]} вдвоём", "text": f"в {MONTHS_IN[months[0] - 1]} вдвоём"},
            {"label": f"В {MONTHS_IN[months[1] - 1]} с ребёнком", "text": f"в {MONTHS_IN[months[1] - 1]} с ребёнком"},
            {"label": f"В {MONTHS_IN[months[2] - 1]} один", "text": f"в {MONTHS_IN[months[2] - 1]} один"},
            {"label": "На майские компанией из 4", "text": "на майские компанией из 4 человек"},
        ]
    return [{"label": MONTHS[m - 1].capitalize(), "text": f"в {MONTHS_IN[m - 1]}"} for m in months] + [
        {"label": "Даты не важны", "text": "в ближайший месяц"}
    ]


def inspire(sugg: dict, brief: dict) -> str:
    month = sugg["month"]
    items = sugg["items"]
    lines = []
    for index, item in enumerate(items, start=1):
        weather = item["weather"]
        if weather["water"] is not None and "sea" in item["kinds"]:
            climate_text = f"вода +{weather['water']}°, воздух +{weather['air']}°"
        elif weather["air"] is not None:
            climate_text = f"днём {'+' if weather['air'] > 0 else ''}{weather['air']}°"
        else:
            climate_text = ""
        travel = hours_label(item["travel"]["minutes"])
        lines.append(f"{index}. {item['name']} — {climate_text}, в пути {travel}, от {money(item['price_from'])}")
    text = (
        f"Проверил {sugg['checked']} {plural(sugg['checked'], 'направление', 'направления', 'направлений')} под {MONTHS[month - 1]}: погоду, дорогу {origin(brief['origin'])['from']}, "
        f"визы и цены на {party_label(brief)}. Лучше всего подходят:\n" + "\n".join(lines)
    )
    if sugg["rejected"]:
        text += "\nНе предлагаю: " + "; ".join(f"{r['name']} — {r['reason']}" for r in sugg["rejected"][:3]) + "."
    text += "\nКакое собрать? Можно сравнить два — просто скажите."
    return text


def inspire_quick(sugg: dict) -> list[dict]:
    quick = [
        {"label": f"Собрать: {item['name']}", "action": {"type": "select_destination", "id": item["id"]}} for item in sugg["items"][:3]
    ]
    if sugg.get("more"):
        quick.append({"label": "Другие направления", "action": {"type": "more_destinations"}})
    return quick


def bundle_line(bundle: dict) -> str:
    h = bundle["hotel"]
    return f"«{bundle['label']}» — {money(bundle['total'])}: {h['name']} {h['stars']}★, {h['meal_label']}"


def route_text(plan: dict, brief: dict) -> str:
    trip = plan["bundles"][0]
    legs = trip["legs"]
    checkin, checkout = date.fromisoformat(plan["checkin"]), date.fromisoformat(plan["checkout"])
    split = " + ".join(f"{leg['nights']} {plural(leg['nights'], 'ночь', 'ночи', 'ночей')}" for leg in legs)
    lines = [
        f"Собрал маршрут {trip['dest_name']} на {day_label(checkin)} – {day_label(checkout)}, {party_label(brief)}: {split}. "
        f"Итого {money(trip['total'])} за всё, от двери до двери."
    ]
    for index, leg in enumerate(legs):
        h = leg["hotel"]
        lines.append(f"• {leg['dest_name']}, {leg['nights']} ноч.: {h['name']} {h['stars']}★, {h['meal_label']}")
        if index < len(legs) - 1:
            lines.append(f"• переезд {day_label(date.fromisoformat(leg['checkout']))}: {transport_line(leg['inbound'])}")
    fixed = [c for c in trip["checks"] if c["status"] == "fixed"]
    warns = [c for c in trip["checks"] if c["status"] in ("warn", "error")]
    text = "\n".join(lines)
    if fixed:
        text += "\nИсправил сам: " + "; ".join(c["title"] for c in fixed[:3]) + "."
    if warns:
        text += "\nОбратите внимание: " + "; ".join(c["title"] for c in warns[:3]) + "."
    return text


def transport_line(option: dict) -> str:
    kinds = {"flight": "рейс", "train": "поезд", "bus": "автобус", "car": "машина с водителем"}
    return f"{kinds.get(option['mode'], option['mode'])} в {time_of(option['depart'])}, {hours_label(option['duration_min'])}"


def plan_text(plan: dict, brief: dict) -> str:
    if plan.get("multi"):
        return route_text(plan, brief)
    best = plan["bundles"][0]
    dest = destination(plan["dest"])
    checkin, checkout = date.fromisoformat(plan["checkin"]), date.fromisoformat(plan["checkout"])
    when = f"{day_label(checkin)} – {day_label(checkout)}"
    how = ""
    if plan["dates_how"] == "best_in_month":
        how = " (выбрал самые выгодные даты в месяце)"
    h = best["hotel"]
    out = best["outbound"]
    text = (
        f"Собрал поездку {dest['loc']} на {when}{how}, {party_label(brief)}.\n"
        f"Рекомендую «{best['label']}»: {money(best['total'])} за всё, от двери до двери. "
        f"{'Рейс' if out['mode'] == 'flight' else 'Поезд'} {out['number']} в {time_of(out['depart'])}, "
        f"отель {h['name']} {h['stars']}★ ({h['meal_label']}), {best['transfer_in']['title'].lower()}."
    )
    why = [w for w in best["why"][1:4]]
    if why:
        text += " Почему он: " + ", ".join(why) + "."
    fixed = [c for c in best["checks"] if c["status"] == "fixed"]
    for check in fixed:
        text += f" Заметил и исправил: {check['detail'][0].lower() + check['detail'][1:]}."
    warns = [c for c in best["checks"] if c["status"] in ("warn", "error")]
    if warns:
        text += " Обратите внимание: " + "; ".join(f"{c['title'].lower()}" for c in warns[:3]) + "."
    for hack in (best.get("hacks") or [])[:1]:
        text += f"\nЛайфхак: {hack['title'][0].lower()}{hack['title'][1:]} — {hack['detail']}."
    if dest.get("dynamic"):
        text += (
            f"\nНаправления «{dest['name']}» нет в моей базе: нашёл его на карте, погоду взял из реального архива Open-Meteo, "
            "а отели и рейсы смоделировал — цены ориентировочные."
        )
    if brief.get("own_car"):
        text += (
            " На своей машине маршрут я пока не строю — посчитал дорогу общественным транспортом; если поедете сами, вычтите её из суммы."
        )
    if plan["relaxed"]:
        # уступку говорим первой строкой: «без перелётов» на Мальдивы невыполнимо, и это важнее цены
        text = "Под все ваши условия к дороге вариантов нет — пришлось уступить: " + ", ".join(plan["relaxed"]) + ".\n" + text
    others = plan["bundles"][1:]
    if others:
        text += "\nЕщё " + " и ".join(bundle_line(b) for b in others) + "."
    return text


def plan_quick(plan: dict) -> list[dict]:
    return [
        {"label": "Оформить", "action": {"type": "checkout"}},
        {"label": "А если на 2 дня позже?", "text": "а если на два дня позже?"},
        {"label": "Подешевле", "text": "подешевле"},
        {"label": "С нами едет собака", "text": "с нами едет собака"},
    ]


def replan_text(state: dict, diff: dict, plan: dict, reason: str) -> str:
    kept = ", ".join(part.lower() for part in diff["kept"] if part != "Доплаты")
    text = f"Пересобрал план, а не искал заново ({reason})."
    if kept:
        text += f" Осталось как было: {kept}."
    for change in diff["changes"]:
        delta = change["delta"]
        tail = "" if not delta else f" ({'+' if delta > 0 else '−'}{money(abs(delta))})"
        text += f"\n• {change['part']}: {change['after']}{tail}"
    for step in plan.get("downgrade") or []:
        text += f"\n• чтобы уложиться в бюджет: {step['text']} (−{money(step['saving'])})"
    delta = diff["delta"]
    if delta:
        text += f"\nИтого: {money(diff['total_before'])} → {money(diff['total_after'])} ({'+' if delta > 0 else '−'}{money(abs(delta))})."
    else:
        text += f"\nИтого без изменений: {money(diff['total_after'])}."
    if not diff["same_hotel"] and diff["changes"]:
        hotel_change = next((c for c in diff["changes"] if c["part"] == "Отель"), None)
        if hotel_change:
            text += " Отель пришлось сменить — прежний не подходит под новые условия или занят."
    warns = [c for c in plan["bundles"][0]["checks"] if c["status"] in ("warn", "error")]
    fixed = [c for c in plan["bundles"][0]["checks"] if c["status"] == "fixed"]
    for check in fixed:
        text += f" Исправил: {check['title'].lower()}."
    if warns:
        text += " Внимание: " + "; ".join(c["title"].lower() for c in warns[:2]) + "."
    return text


def bundle_selected(bundle: dict) -> str:
    h = bundle["hotel"]
    checks = bundle["checks"]
    ok = sum(1 for c in checks if c["status"] in ("ok", "fixed"))
    warn = [c for c in checks if c["status"] in ("warn", "error")]
    text = f"Выбрал «{bundle['label']}»: {money(bundle['total'])}, {h['name']} {h['stars']}★, {h['meal_label']}. Проверок пройдено: {ok} из {len(checks)}."
    if warn:
        text += " Требует внимания: " + "; ".join(c["title"].lower() for c in warn) + "."
    return text


def checkout_text(bundle: dict) -> str:
    ok = all(c["status"] != "error" for c in bundle["checks"])
    h = bundle["hotel"]
    cancel = (
        f"бесплатная отмена отеля до {day_label(date.fromisoformat(h['free_cancel_until']))}"
        if h["refundable"] and h["free_cancel_until"]
        else "тариф отеля невозвратный"
    )
    text = (
        f"Перед оплатой ещё раз сверил всё: даты, стыковки, состав гостей. К оплате {money(bundle['total'])}, {cancel}. "
        "Оплата здесь имитируется — деньги не списываются. Укажите имя и почту для ваучера."
    )
    if not ok:
        text = (
            "Есть критичная проблема: "
            + "; ".join(c["title"] for c in bundle["checks"] if c["status"] == "error")
            + ". Оформить всё равно можно, но я бы сначала поправил. "
            + text
        )
    return text


def booked_text(booking: dict) -> str:
    bundle = booking["bundle"]
    text = (
        f"Готово! Поездка оформлена, номер брони {booking['id']}. Оплачено {money(booking['payment']['amount'])} (имитация). "
        f"Ваучер и план — в разделе «Мои поездки». Я рядом и после покупки: могу запросить ранний заезд, "
        f"перенести даты, добавить трансфер или напомнить о регистрации на {'рейс' if bundle['outbound']['mode'] == 'flight' else 'поезд'}."
    )
    requests = booking.get("requests") or []
    if requests:
        text += " Заранее предупредил: " + "; ".join(f"{r['who']} — {r['what']}" for r in requests) + " (имитация)."
    return text


def booked_quick() -> list[dict]:
    return [
        {"label": "Ранний заезд", "text": "можно заселиться пораньше?"},
        {"label": "Перенести на 2 дня позже", "text": "перенеси поездку на два дня позже"},
        {"label": "Трансфер получше", "text": "нужен индивидуальный трансфер"},
        {"label": "Напоминания", "text": "какие напоминания ты поставил?"},
    ]


def weather_verdict(c: dict) -> str:
    notes = []
    if c["water"] is not None:
        notes.append(
            "купаться комфортно"
            if c["water"] >= 24
            else "купаться можно, но свежо"
            if c["water"] >= 21
            else "для купания холодно — разве что для закалённых"
        )
    if c["air"] is not None:
        if c["air"] >= 32:
            notes.append("днём жарко — экскурсии лучше утром")
        elif c["air"] <= 0:
            notes.append("морозно — нужна зимняя одежда")
        elif c["air"] <= 12:
            notes.append("прохладно — нужна куртка")
    if c["rain"] is not None and c["rain"] >= 10:
        notes.append("часто бывают ливни — держите в плане занятия под крышей")
    return "; ".join(notes)


def trip_facts(dest: dict, brief: dict, plan: dict | None) -> dict:
    """Всё, что агент точно знает о направлении и поездке, — основа для ответа на свободный вопрос."""
    facts = {
        "направление": dest["name"],
        "страна": dest["country"],
        "виза для граждан РФ": dest["visa"],
        "тип отдыха": [KIND_LABELS.get(k, k) for k in dest["kinds"]],
        "особенности": dest["highlights"],
        "доля отелей с детской инфраструктурой": "высокая" if dest["kids"] >= 0.8 else "средняя" if dest["kids"] >= 0.55 else "низкая",
        "климат по месяцам (днём °C / вода °C / дней с ливнями)": {
            MONTHS[m - 1]: f"{climate(dest, m)['air']} / {climate(dest, m)['water']} / {climate(dest, m)['rain']}" for m in range(1, 13)
        },
        "путешественники": party_label(brief),
    }
    if dest.get("note"):
        facts["маршрут"] = dest["note"]
    if plan and plan.get("bundles"):
        b = plan["bundles"][0]
        facts["план"] = {
            "даты": f"{b['checkin']} — {b['checkout']}",
            "туда": f"{b['outbound']['number']}, {b['outbound']['depart']} → {b['outbound']['arrive']}, {hours_label(b['outbound']['duration_min'])}",
            "отель": f"{b['hotel']['name']} {b['hotel']['stars']}★, {b['hotel']['meal_label']}, до пляжа {b['hotel']['beach_m']} м, до центра {b['hotel']['center_km']} км",
            "итого": money(b["total"]),
        }
    return facts


ANSWER_PROMPT = (
    "Ты — Штурман, тревел-агент. Ответь на вопрос путешественника по-русски, коротко (до 70 слов), на «вы». "
    "Опирайся на ФАКТЫ. Если ответа в фактах нет, можешь ответить из общих знаний, но начни такую часть словами "
    "«По общим сведениям» и посоветуй проверить перед поездкой. Не придумывай цены, расписания и названия отелей. "
    "Не добавляй советов про состав поездки (дети, питомцы), которого нет в фактах. "
    "Не называй данные «официальными»: это справка по открытым данным."
)


def answer_free(question: str, dest: dict, brief: dict, plan: dict | None, metrics: dict) -> str | None:
    """Ответ LLM, привязанный к фактам поездки. None — LLM нет или ответ не прошёл проверку."""
    if not llm.enabled():
        return None
    facts = trip_facts(dest, brief, plan)
    facts_text = json.dumps(facts, ensure_ascii=False)
    try:
        text = llm.chat(
            [{"role": "system", "content": ANSWER_PROMPT}, {"role": "user", "content": f"ФАКТЫ: {facts_text}\n\nВОПРОС: {question}"}],
            max_tokens=350,
            temperature=0.2,
        )
    except llm.LlmUnavailable:
        metrics["llm_fallbacks"] = metrics.get("llm_fallbacks", 0) + 1
        return None
    metrics["llm_calls"] = metrics.get("llm_calls", 0) + 1
    invented = numbers(text) - numbers(facts_text) - numbers(question)
    if invented and "общим сведениям" not in text.lower():
        metrics["number_violations"] = metrics.get("number_violations", 0) + 1
        return None  # числа не из фактов и без пометки «по общим сведениям» — не показываем
    return text


def answer_question(
    topic: str | None, brief: dict, plan: dict | None, text: str = "", month: int | None = None, metrics: dict | None = None
) -> str:
    dest_id = (plan or {}).get("dest") or brief["destination"]
    if not dest_id:
        return "Сначала выберем направление — тогда расскажу про визу, погоду и дорогу. Куда думаете поехать?"
    dest = destination(dest_id)
    plan_month = brief["month"] or (date.fromisoformat(plan["checkin"]).month if plan else date.today().month)
    month = month or plan_month
    if topic == "visa":
        return f"{dest['name']} ({dest['country']}): виза — {dest['visa']}. Это справка по открытым данным — перед поездкой сверьтесь с консульством."
    weather = (plan or {}).get("forecast")
    if topic == "weather" and weather and month == plan_month:
        part = (
            ""
            if weather["covered"] == weather["total"]
            else f" ({weather['covered']} из {weather['total']} дней — дальше прогноз пока не заглядывает)"
        )
        return f"{weather['line']}. Это настоящий прогноз Open-Meteo на даты поездки{part}, а не многолетняя норма."
    if topic == "weather":
        c = climate(dest, month)
        parts = [f"днём около {'+' if (c['air'] or 0) > 0 else ''}{c['air']}°"]
        if c["water"] is not None:
            parts.append(f"вода +{c['water']}°")
        if c["rain"] is not None:
            parts.append(f"дней с ливнями — около {c['rain']}" if c["rain"] else "ливней почти нет")
        verdict = weather_verdict(c)
        answer = (
            f"{dest['name']} в {MONTHS_IN[month - 1]}: "
            + ", ".join(parts)
            + "."
            + (f" {verdict[0].upper()}{verdict[1:]}." if verdict else "")
        )
        answer += " Это средние многолетние значения по данным Open-Meteo."
        if month != plan_month:
            answer += f" Сейчас план на {MONTHS[plan_month - 1]} — могу пересобрать на {MONTHS[month - 1]}."
        return answer
    if topic == "todo":
        return f"{dest['name']}: " + "; ".join(dest["highlights"]) + "."
    if topic == "travel_time" and plan and plan.get("bundles"):
        out = plan["bundles"][0]["outbound"]
        return f"Дорога туда: {hours_label(out['duration_min'])}, {'прямой рейс' if not out['stops'] else 'с пересадкой в ' + out['via']}."
    if topic == "why" and plan and plan.get("bundles"):
        best = plan["bundles"][0]
        return (
            "Логика выбора: "
            + "; ".join(best["why"])
            + ". Чем пожертвовали: "
            + ("; ".join(best["sacrifices"]) or "ничем существенным")
            + "."
        )
    free = answer_free(text, dest, brief, plan, metrics if metrics is not None else {}) if text else None
    if free:
        return free
    lowered = text.lower()
    if re.search(r"(дет|реб[её]н|малыш)", lowered):
        level = "много" if dest["kids"] >= 0.8 else "есть" if dest["kids"] >= 0.55 else "мало"
        return (
            f"{dest['name']} с детьми: отелей с детскими клубами и бассейнами {level}. "
            "Под ребёнка я и так подбираю: перелёт покороче, без ночных рейсов, детский клуб и семейные номера. "
            "Вопросы безопасности и медицины лучше уточнить в официальных источниках — таких данных у меня нет."
        )
    c = climate(dest, month)
    known = [
        f"виза — {dest['visa']}",
        f"в {MONTHS_IN[month - 1]} днём около {c['air']}°" + (f", вода +{c['water']}°" if c["water"] else ""),
    ]
    known.append("особенности: " + "; ".join(dest["highlights"][:2]))
    return (
        "Точного ответа на этот вопрос в моих данных нет, а выдумывать не буду. Что знаю наверняка "
        f"({dest['name']}): " + "; ".join(known) + ". Могу пересобрать поездку или рассказать про визу, погоду и дорогу."
    )


def unknown_destination(name: str) -> str:
    return (
        f"«{name}» пока нет в моей демо-базе: в ней 62 направления, данные отелей синтетические. "
        "Подберу похожие по погоде, дороге и типу отдыха — смотрите ниже."
    )


# ── LLM делает текст живее, но без новых фактов ─────────────────────────────

NARRATE_PROMPT = (
    "Ты — Штурман, дружелюбный тревел-агент. Перепиши черновик ответа пользователю живо и коротко (до 110 слов), "
    "по-русски, на «вы», без markdown-заголовков и таблиц. Сохрани ВСЕ факты, числа, названия и даты из черновика "
    "в точности. Не добавляй новых чисел, цен, дат, названий и обещаний. Списки «1.», «•» оставь списками."
)


def numbers(text: str) -> set[str]:
    return {re.sub(r"[\s ]", "", n) for n in re.findall(r"\d[\d\s ]*\d|\d", text)}


def narrate(draft: str, metrics: dict) -> str:
    """Возвращает живой текст или черновик, если LLM нет или она добавила чисел от себя."""
    if not llm.enabled() or not llm.settings()["narrate"]:
        return draft
    try:
        text = llm.chat(
            [{"role": "system", "content": NARRATE_PROMPT}, {"role": "user", "content": draft}], max_tokens=500, temperature=0.4
        )
    except llm.LlmUnavailable:
        metrics["llm_fallbacks"] = metrics.get("llm_fallbacks", 0) + 1
        return draft
    metrics["llm_calls"] = metrics.get("llm_calls", 0) + 1
    invented = numbers(text) - numbers(draft)
    if invented or len(text) < 20:
        metrics["number_violations"] = metrics.get("number_violations", 0) + 1
        log.info("LLM добавила числа %s — отдаю черновик", sorted(invented)[:5])
        return draft
    return text
