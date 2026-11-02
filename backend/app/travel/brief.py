"""Бриф поездки: что агент понял о запросе, откуда он это взял, и разбор текста на правилах.

У каждого поля брифа есть источник: explicit (сказал пользователь), inferred (агент вывел, с причиной),
memory (из прошлых поездок), default (допущение). Источники показываются в карточке «Я понял так».
"""

import re
from datetime import date, timedelta

from app.travel.catalog import (
    KIND_LABELS,
    MONTHS_GEN,
    MONTHS_IN,
    destination,
    destinations,
    find_destination,
    find_origin,
    origin,
)

DEFAULT_PRIORITIES = {"price": 0.5, "comfort": 0.5, "speed": 0.5, "beach": 0.5, "flex": 0.5}


def new_brief() -> dict:
    return {
        "origin": "MOW",
        "destination": None,
        "exclude": [],
        "kinds": [],
        "warm": False,
        "month": None,
        "date_from": None,
        "nights": 7,
        "adults": 2,
        "children": [],
        "seniors": False,
        "accessible": False,
        "pets": None,
        "budget": None,
        "budget_level": None,
        "max_hours": None,
        "direct_only": False,
        "transport": "any",
        "avoid_night": False,
        "visa_free": False,
        "meal": None,
        "diet": [],
        "refundable": None,
        "min_stars": None,
        "year": None,
        "regions": [],
        "own_car": False,
        "route": [],
        "route_nights": [],
        "mood": [],
        "hotel_prefs": [],
        "priorities": dict(DEFAULT_PRIORITIES),
    }


def new_sources() -> dict:
    return {
        "origin": {"kind": "default", "reason": "город вылета не назван — считаю из Москвы"},
        "nights": {"kind": "default", "reason": "длительность не названа — беру неделю"},
        "adults": {"kind": "default", "reason": "состав не назван — считаю двоих взрослых"},
    }


# ── Числа и даты ────────────────────────────────────────────────────────────

NUMBER_WORDS = {
    "один": 1, "одну": 1, "одна": 1, "два": 2, "две": 2, "двое": 2, "двоих": 2, "пару": 2, "три": 3, "трое": 3,
    "троих": 3, "четыре": 4, "четверо": 4, "пять": 5, "пятеро": 5, "шесть": 6, "шестеро": 6, "семь": 7,
    "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11, "двенадцать": 12, "четырнадцать": 14,
    "пятнадцать": 15, "двадцать": 20, "полторы": 1.5, "полтора": 1.5,
}  # fmt: skip

MONTH_STEMS = [
    ("январ", 1), ("феврал", 2), ("март", 3), ("апрел", 4), ("мая", 5), ("мае", 5), ("май", 5),
    ("июн", 6), ("июл", 7), ("август", 8), ("сентябр", 9), ("октябр", 10), ("ноябр", 11), ("декабр", 12),
]  # fmt: skip
MONTH_RE = r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йяе]\b|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)"
NUM = r"(\d+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"


def to_number(token: str) -> float | None:
    token = token.lower().strip()
    if token in NUMBER_WORDS:
        return float(NUMBER_WORDS[token])
    try:
        return float(token.replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def month_of(token: str) -> int | None:
    token = token.lower()
    for stem, number in MONTH_STEMS:
        if token.startswith(stem):
            return number
    return None


def resolve_date(day: int, month: int, today: date, year: int | None = None) -> date | None:
    year = year or today.year
    try:
        result = date(year, month, day)
    except ValueError:
        return None
    if result < today and year == today.year:
        result = result.replace(year=year + 1)
    return result


def next_month_start(month: int, today: date) -> date:
    year = today.year if month >= today.month else today.year + 1
    return date(year, month, 1)


def parse_amount(text: str) -> int | None:
    """Самая крупная сумма в тексте (≥ 10 000 ₽): «150к», «150 тысяч», «1,5 млн», «200 000 ₽»."""
    best = None
    pattern = re.compile(
        r"(\d{1,3}(?:[\s ]\d{3})+|\d+(?:[.,]\d+)?|полтора|полмиллиона)\s*"
        r"(млн|миллион\w*|тыс\w*|т\.?\s?р\.?|к\b|k\b|руб\w*|₽|р\b|косар\w*)?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        raw, unit = match.group(1).lower(), (match.group(2) or "").lower()
        if raw == "полмиллиона":
            value = 500_000.0
        else:
            value = to_number(raw)
        if value is None:
            continue
        if unit.startswith(("млн", "миллион")):
            value *= 1_000_000
        elif unit.startswith(("тыс", "т", "к", "k", "косар")):
            value *= 1_000
        elif not unit and value < 10_000:
            continue  # голое число — скорее дата, срок или количество
        if value >= 10_000 and (best is None or value > best):
            best = value
    inverted = re.search(r"\b(тысяч|тыщ|косар)\w*\s+(?:на|в|около|примерно|где-то)\s+(\d{2,4})\b", text, re.IGNORECASE)
    if inverted and (best is None or int(inverted.group(2)) * 1000 > best):
        best = int(inverted.group(2)) * 1000  # разговорное «денег тысяч на 250»
    return int(best) if best else None


# shortcut: курс зашит и помечается в брифе как допущение; живой курс ЦБ — если понадобится точность
RATES = {"usd": (80, "$"), "eur": (92, "€")}  # евро — от доллара по паре EUR/USD ≈ 1,15
SHORT_UNITS = r"(лет|год|мин|час|ч\b|км|ноч|дн|сут|недел|кг|звезд|град|%|чел|взросл|раз|ребен|дет)"


def parse_foreign_or_short_amount(text: str) -> tuple[int | None, str]:
    """«$1500», «2000 евро» → рубли по зашитому курсу; «до 50 на человека» → 50 тысяч. Возвращает сумму и пояснение."""
    match = re.search(r"(\$|€)\s*(\d[\d\s]*\d|\d)", text) or re.search(r"(\d[\d\s]*\d|\d)\s*(\$|€|usd|долл\w*|бакс\w*|eur\b|евро)", text)
    if match:
        number_part, unit = (match.group(2), match.group(1)) if match.group(1) in "$€" else (match.group(1), match.group(2))
        value = int(re.sub(r"\s", "", number_part))
        rate, sign = RATES["eur"] if unit.startswith(("€", "eur", "евро")) else RATES["usd"]
        if 50 <= value <= 100_000:
            return value * rate, f"{value} {sign} по курсу ≈ {rate} ₽ — поправьте, если считали иначе"
    match = re.search(r"(?:\bдо|\bза|бюджет|в пределах|не дороже|около|примерно)\s+(\d{2,3})\b", text)
    if match and 20 <= int(match.group(1)) <= 999:
        after = text[match.end() :].split()
        if not after or not (month_of(after[0]) or re.match(SHORT_UNITS, after[0])):
            return int(match.group(1)) * 1000, f"«{match.group(0).strip()}» — считаю в тысячах рублей"
    return None, ""


# ── Разбор текста на правилах ───────────────────────────────────────────────

KIND_WORDS = {
    "sea": ["мор", "пляж", "купат", "искупат", "поплават", "загорат", "океан", "остров", "лагун", "побережь"],
    "mountains": ["горы", "горах", "горн", "гору", "хайкинг", "треккинг", "трекинг", "поход"],
    "ski": ["лыж", "сноуборд", "горнолыж", "кататься на", "покатать", "склон"],
    "city": ["город", "мегаполис", "шопинг", "прогулк", "погулять"],
    "culture": ["музе", "экскурс", "истори", "архитектур", "достопримечат", "культур", "театр"],
    # « еда» с пробелом: без него «еда» находится внутри «недалеко», «обеда»
    "food": [" еда", "едой", "гастро", "вкусн", "кухн", "ресторан", "вино", "винн", "поесть"],
    "nature": ["природ", "фьорд", "лес", "озер", "тишин", "сияни", "вулкан", "водопад", "каньон"],
    "spa": [
        "спа-",
        "спа ",
        " спа",
        "оздоров",
        "санатор",
        "термал",
        "минеральн",
        "лечени",
        "массаж",
        "баня",
        "баню",
        "бане",
        "банька",
        "сауна",
    ],
    "party": ["тусов", "вечерин", "ночная жизнь", "ночной жизн", "клубы", "клубов", "потусить"],
    "romantic": ["романт", "медовый", "годовщин", "свадеб", "предложение сделать", "для двоих"],
    "exotic": ["экзот", "тропик", "пальм", "джунгл", "необычн", "необыкновен", "уникальн", "удивит", "впечатлен"],
    "active": ["активн", "дайвинг", "сёрф", "серф", "рафтинг", "снорклинг", "кайт", "экстрим", "велосипед"],
}

WARM_WORDS = ["тепл", "тёпл", "погреться", "солнц", "жарк", "лето зимой", "от холода", "от зимы"]
CHEAP_WORDS = [
    "недорог",
    "не дорог",
    "бюджетн",
    "дешев",
    "дёшев",
    "эконом",
    "подешевле",
    "без лишних трат",
    "не тратить",
    "кучу бабок",
    "кучу денег",
    "сэконом",
]
RICH_WORDS = ["люкс", "премиум", "роскош", "шикарн", "vip", "дорого-богато", "не важно сколько", "неважно сколько", "деньги не важны"]
# «позовите менеджера», «хочу поговорить с человеком» — просьба о живом человеке, а не часть запроса о поездке
HANDOFF_WORDS = (
    r"((позов|позв|соедин|переключ|передай|нуж|хочу|дайте|можно)\w*\s+(?:[а-я]+\s+){0,2}"
    r"(менеджер|оператор|специалист|поддержк|сотрудник)\w*|жив\w+\s+(человек|менеджер|оператор)\w*|\bоператор\w*\b|"
    r"служб\w+ поддержки|(поговорить|связаться|соедин\w*|переключ\w*)\s+с\s+(?:живым\s+)?человеком|позов\w*\s+человека)"
)

REGIONS = {
    "europe": ("Европа", ["европ"]),
    "black_sea": ("Черноморье", ["черное море", "черном море", "черному морю", "черноморск", "черноморь"]),
    "asia": ("Азия", ["в азию", "азиатск", "юго-восточн", "в азии"]),
    "russia": ("Россия", ["по россии", "в россии", "внутри страны", "по стране", "не за границ", "без загранпаспорт"]),
    "abroad": ("за границей", ["за границ", "заграниц", "за рубеж"]),
    "caucasus": ("Кавказ", ["кавказ"]),
}
REGION_MEMBERS = {
    "europe": {"belgrade", "budva", "minsk", "kaliningrad", "paris", "rome", "barcelona", "istanbul"},
    "black_sea": {"sochi", "anapa", "gelendzhik", "yalta", "abkhazia", "batumi"},
    "asia": {"phuket", "pattaya", "samui", "bangkok", "nha_trang", "phu_quoc", "bali", "sanya", "langkawi", "sri_lanka", "goa", "maldives"},
    "caucasus": {"krasnaya_polyana", "sochi", "dagestan", "kmv", "elbrus", "tbilisi", "batumi", "gudauri", "yerevan", "abkhazia"},
}

# особое питание: кухня отеля должна это уметь, а отель — знать заранее
DIET_PATTERNS = {
    "halal": r"халял",
    "vegan": r"веган",
    "vegetarian": r"(вегетариан|без мяса|не (?:ед|ест)\w* мяс)",
    "gluten_free": r"(глютен|целиаки)",
    "lactose_free": r"(лактоз|без молочн)",
    "nut_free": r"(аллерги\w*\s+(?:на\s+)?(?:орех|арахис)|без\s+орех|арахис|орехов\w*\s+аллерги)",
}

ORDINALS = {
    "перв": 1, "втор": 2, "трет": 3, "четв": 4, "1": 1, "2": 2, "3": 3, "4": 4,
}  # fmt: skip
BUNDLE_LABELS = {"оптимал": 1, "экономн": 2, "эконом": 2, "дешёв": 2, "комфорт": 3}


ACCESS_WORDS = (
    r"(на\s+(?:инвалидной\s+)?коляске|инвалидн\w*\s+коляск|колясочник|инвалид|без\s+лестниц|без\s+ступен|"
    r"(?:плохо|тяжело|трудно|не\s+может)\s+ход|ходунк|маломобильн|на\s+костыл|доступн\w*\s+сред)"
)


def _has(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _party(text: str, brief: dict) -> dict:
    patch: dict = {}
    child_match = re.search(
        r"(?:\bс|\bи)\s+(?:(\d+|двумя|тремя|двух|трёх|трех)\s+)?(?:маленьк\w+\s+)?(реб[её]нк\w*|детьми|сыном|сынишк\w*|дочк\w*|дочерью|малыш\w*|младенц\w*|"
        r"сыновьями|дочерьми|внук\w*|внучк\w*|детей|пацан\w*|мальчик\w*|мальчишк\w*|девочк\w*|детишк\w*|школьник\w*)",
        text,
    )
    count = None
    if child_match:
        word = child_match.group(2)
        number = child_match.group(1)
        if number:
            count = {"двумя": 2, "двух": 2, "тремя": 3, "трёх": 3, "трех": 3}.get(number) or int(to_number(number) or 1)
        elif word.startswith(("детьми", "детей", "сыновьями", "дочерьми")):
            count = 2
        else:
            count = 1
    elif re.search(r"\b(семь[её]й|всей семьей|всей семьёй|семейн)", text):
        count = 1
        patch["_family_guess"] = True
    formula = re.search(r"\b(\d)\s*\+\s*(\d)\b", text)  # «2+2», «семья 2+1»
    if formula and 1 <= int(formula.group(1)) <= 6 and int(formula.group(2)) <= 5:
        count = int(formula.group(2)) or None
    # «1.5 года» → 1 год; дробная часть иначе превратилась бы в дату «1.5» = 1 мая
    ages = [int(a) for a in re.findall(r"(?<![\d.,])(\d{1,2})(?:[.,]\d)?\s*(?:-|–)?\s*(?:лет|года|годик\w*|год)\b", text) if int(a) < 18]
    # «4 и 9 лет», «3, 5 и 8 лет» — единица измерения только у последнего возраста
    for group in re.finditer(r"((?:\d{1,2}\s*(?:,|и)\s*)+)(\d{1,2})\s*(?:лет|года|год)\b", text):
        ages = [int(a) for a in re.findall(r"\d{1,2}", group.group(1)) if int(a) < 18] + ages
    # возраст без «лет»: «ребёнку 3», «дети 5 и 10», «сыну 7»
    bare = re.search(
        r"\b(?:реб[её]нку|сыну|дочке|дочери|детям|дети|детей)\s+((?:\d{1,2}\s*(?:,|и)\s*)*\d{1,2})\b(?!\s*(?:лет|года|год|чел|взросл))",
        text,
    )
    if bare and not ages:
        ages = [int(a) for a in re.findall(r"\d{1,2}", bare.group(1)) if int(a) < 18]
    if re.search(r"(младен|грудн|годовал|малыш)", text) and not ages:
        ages = [1]
    if count is not None or ages:
        count = max(count or 0, len(ages))
        patch["_ages_guessed"] = len(ages) < count  # возраст хоть одного ребёнка придумали мы — пометим допущением
        ages = (ages + [6] * count)[:count]
        patch["children"] = ages
    adults = None
    group = re.search(r"\b(вдвоём|вдвоем|втроём|втроем|вчетвером|впятером|вшестером)\b", text)
    if group:
        adults = {"вдв": 2, "втр": 3, "вче": 4, "впя": 5, "вше": 6}[group.group(1)[:3]]
        if patch.get("children"):
            adults = max(1, adults - len(patch["children"]))
    people = re.search(rf"(?:нас|компани\w+ из|группа из|на|для)\s+{NUM}\s*(?:человек|чел|взросл|персон)", text) or re.search(
        r"\bнас\s+(двое|трое|четверо|пятеро|шестеро)\b", text
    )
    if people:
        adults = int(to_number(people.group(1)) or 2)
        if patch.get("children") and "взросл" not in people.group(0):  # «нас 2 взрослых» — дети сверху, не внутри
            adults = max(1, adults - len(patch["children"]))
    if formula and adults is None:
        adults = int(formula.group(1))
    if re.search(
        r"\bс\s+(женой|мужем|девушкой|парнем|подругой|другом|любим\w+|супруг\w*|невестой|женихом|мамой|папой|бабушкой|дедушкой|сестрой|братом)",
        text,
    ):
        adults = max(adults or 0, 2)
    if re.search(r"\bс\s+(?:\w+\s+)?(родителями|бабушкой и дедушкой|мамой и папой)", text):
        adults = max(adults or 0, 3)
    if re.search(r"(бабушк|дедушк|пожил|пенсионер|родител)", text):
        patch["seniors"] = True
    # «мама на коляске», «без лестниц» — доступная среда; «с коляской» чаще про малыша, это не она
    if re.search(ACCESS_WORDS, text) and not re.search(r"без\s+(?:инвалидной\s+)?коляски", text):
        patch["accessible"] = True
    solo = re.search(r"(?:^|[\s,])(один|одна|одному|одной|в одиночку|соло)(?=$|[\s,.!?])", text)
    if solo and not re.search(r"(на|за|в)\s+(один|одну|одной)\b|(один|одна)\s+(день|ночь|раз|отел|из|вариант|неделю)", text):
        adults = 1
    if adults is not None:
        patch["adults"] = adults
    elif patch.get("children"):
        patch["adults"] = 2 if not re.search(r"\b(я|мама|папа)\s+с\s+", text) else 1
        if re.search(r"\b(одна|один)\s+с\s+", text):
            patch["adults"] = 1
    if re.search(r"(собак|пс[оа]м|щенк|пёс|пес\b|собачк|той-терьер|шпиц|корги)", text) and not re.search(r"без\s+собак", text):
        patch["pets"] = "dog"
    elif re.search(r"(кошк|котом|кот\b|котик)", text) and not re.search(r"без\s+(кошк|кот)", text):
        patch["pets"] = "cat"
    if re.search(r"(без собаки|собака не едет|собаку оставим|без животных|без питомц)", text):
        patch["pets"] = None
    if re.search(r"без\s+(детей|реб[её]нка|ребят|малыш\w*|сына|дочк\w*|дочери)", text):
        patch["children"] = []
    return patch


def _dates(text: str, today: date) -> dict:
    patch: dict = {}
    # «с 10 по 17 ноября», «10–17 ноября», «с 28 декабря по 5 января»
    match = re.search(rf"(?:с\s+)?(\d{{1,2}})\s*(?:{MONTH_RE}\s*)?(?:по|до|-|–|—)\s*(\d{{1,2}})\s+{MONTH_RE}", text)
    if match:
        d1, m1, d2, m2 = match.group(1), match.group(2), match.group(3), match.group(4)
        month2 = month_of(m2)
        month1 = month_of(m1) if m1 else month2
        start = resolve_date(int(d1), month1, today) if month1 else None
        end = resolve_date(int(d2), month2, today) if month2 else None
        if start and end:
            if end <= start:
                end = end.replace(year=end.year + 1)
            if 1 <= (end - start).days <= 60:
                return {"date_from": start.isoformat(), "nights": (end - start).days, "month": start.month}
    match = re.search(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\s*(?:-|–|—|по|до)\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", text)
    if match:
        start = resolve_date(int(match.group(1)), int(match.group(2)), today) if 1 <= int(match.group(2)) <= 12 else None
        end = resolve_date(int(match.group(4)), int(match.group(5)), today) if 1 <= int(match.group(5)) <= 12 else None
        if start and end and 1 <= (end - start).days <= 60:
            return {"date_from": start.isoformat(), "nights": (end - start).days, "month": start.month}
    match = re.search(rf"(?:с\s+|^|\s)(\d{{1,2}})\s+{MONTH_RE}", text)
    if match:
        month = month_of(match.group(2))
        start = resolve_date(int(match.group(1)), month, today) if month else None
        if start:
            patch.update(date_from=start.isoformat(), month=start.month)
    else:
        match = re.search(
            r"(?:^|\s)(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?(?=$|[\s,])(?!\s*(?:года|лет|год|час|ч\b|км|кг|тыс|млн|звезд|%|раз))", text
        )
        if match and 1 <= int(match.group(2)) <= 12:
            start = resolve_date(int(match.group(1)), int(match.group(2)), today)
            if start:
                patch.update(date_from=start.isoformat(), month=start.month)
    if "month" not in patch:
        match = re.search(rf"(?:в|на|к|до|середин\w*|начал\w*|кон\w*)\s+{MONTH_RE}", text) or re.search(MONTH_RE, text)
        if match:
            token = match.group(match.lastindex or 1)
            month = month_of(token)
            if month:
                patch["month"] = month
                prefix = text[max(0, match.start() - 12) : match.start() + 12]
                if "середин" in prefix:
                    patch["date_from"] = next_month_start(month, today).replace(day=12).isoformat()
                elif "начал" in prefix:
                    patch["date_from"] = max(next_month_start(month, today).replace(day=2), today + timedelta(days=5)).isoformat()
                elif "кон" in prefix:
                    patch["date_from"] = next_month_start(month, today).replace(day=22).isoformat()
    if "month" not in patch:
        if re.search(r"(новый год|новогодн|\bнг\b)", text):
            start = resolve_date(30, 12, today)
            patch.update(date_from=start.isoformat(), month=12, nights=7)
        elif re.search(r"майск", text):
            start = resolve_date(1, 5, today)
            patch.update(date_from=start.isoformat(), month=5, nights=5)
        elif re.search(r"(выходн(ые|ых)|уикенд|викенд)", text):
            friday = today + timedelta(days=(4 - today.weekday()) % 7 or 7)
            patch.update(date_from=friday.isoformat(), month=friday.month, nights=2)
        elif re.search(r"\bзавтра\b", text):  # не «завтраки»
            day = today + timedelta(days=1)
            patch.update(date_from=day.isoformat(), month=day.month)
        elif match := re.search(rf"через\s+{NUM}?\s*(недел|месяц|дн)", text):
            amount = int(to_number(match.group(1)) or 1) if match.group(1) else 1
            unit = match.group(2)
            delta = timedelta(days=amount * (7 if unit == "недел" else 30 if unit == "месяц" else 1))
            day = today + delta
            patch.update(date_from=day.isoformat(), month=day.month)
        elif re.search(r"(следующ\w+ месяц|в следующем месяце)", text):
            month = today.month % 12 + 1
            patch["month"] = month
        elif re.search(r"\b(летом|лето|летний|летнее|летние)\b", text):  # \b: не «самолЁТОМ»
            patch["month"] = 7
        elif re.search(r"\b(осенью|осень|осенний)\b", text):
            patch["month"] = 9 if today.month < 9 else 10 if today.month < 11 else 9
        elif re.search(r"\b(зимой|зима|на зиму|зимн\w*)\b", text):
            patch["month"] = 1 if today.month != 12 else 12
        elif re.search(r"\b(весной|весна|на весну|весенн\w*)\b", text):
            patch["month"] = 4
        elif re.search(r"(сейчас|прямо сейчас|в ближайшее время|поскорее|срочно|на следующей неделе)", text):
            day = today + timedelta(days=7)
            patch.update(date_from=day.isoformat(), month=day.month)
    nights = None
    match = re.search(rf"на\s+{NUM}\s*(ноч|ночей|ночи|дн|дня|дней|сут)", text) or re.search(rf"{NUM}\s*(ноч)", text)
    if match:
        value = to_number(match.group(1))
        if value:
            # «на 10 дней» — 9 ночей, но «на пару дней» и «на 3 дня» по смыслу — 2 ночи
            nights = int(value) if match.group(2).startswith("ноч") else max(2, int(value) - 1)
    elif match := re.search(rf"(?<!через\s)(?:\bна\s+)?\b{NUM}\s+недел", text):  # «2 недели», но не «через 2 недели»
        nights = int((to_number(match.group(1)) or 1) * 7)
    elif re.search(r"на\s+(одну\s+)?неделю|на недельку|неделю отдыха|\bнеделю\b(?!\s+(позже|раньше))", text) and "через неделю" not in text:
        nights = 7
    elif re.search(r"на\s+пару\s+дней|на\s+несколько\s+дней", text):
        nights = 3
    elif re.search(r"(выходн(ые|ых)|уикенд|викенд)", text):
        nights = 2
    elif re.search(r"на\s+месяц", text):
        nights = 28
    if nights and 1 <= nights <= 60:
        patch["nights"] = nights
    if re.search(r"(следующ\w+|будущ\w+)\s+год", text) and "month" in patch and "date_from" not in patch:
        patch["year"] = today.year + 1
    return patch


COMPARE_WORDS = r"(\bили\b|\bлибо\b|\bvs\b|\bпротив\b|\bсравн|что лучше|какой лучше|какая лучше|куда лучше|выбира\w+ между|выбрать между)"
COMPARE_SPLIT = r"\s*(?:\bили\b|\bлибо\b|\bvs\.?|\bпротив\b|,|\bи\b|:)\s*"


def find_compare(text: str) -> list[str]:
    """Два-три места каталога с «или», «сравни», «что лучше» → id направлений по порядку упоминания."""
    if not re.search(COMPARE_WORDS, text):
        return []
    ids: list[str] = []
    for part in re.split(COMPARE_SPLIT, text):
        dest = find_destination(part) if part.strip() else None
        if dest and not dest.get("dynamic") and dest["id"] not in ids:
            ids.append(dest["id"])
    return ids[:3] if len(ids) >= 2 else []


def parse_rules(text: str, brief: dict, today: date, stage: str = "start") -> dict:
    """Разбор сообщения без LLM. Возвращает intent, patch и дополнительные поля (сдвиг дат, выбор варианта)."""
    raw = text.strip()
    t = raw.lower().replace("ё", "е")
    patch: dict = {}
    result: dict = {"intent": "plan", "patch": patch, "shift_days": None, "select": None, "post": None, "question": None}

    if re.search(
        r"(начать заново|начнем заново|начнём заново|новый поиск|с чистого листа|сбрось|^заново$|давай сначала|начн[её]м сначала|с самого начала|^\s*сначала\s*[.!]?\s*$)",  # «сначала Рим, потом…» — маршрут, а не сброс
        t,
    ):
        result["intent"] = "reset"
        return result
    if re.search(HANDOFF_WORDS, t):
        result["intent"] = "handoff"
        return result

    # пересборка: сдвиг дат и длительности
    shift = re.search(rf"(?:на\s+)?{NUM}?\s*(дн\w*|день|недел\w*)\s+(позже|раньше|попозже|пораньше)", t) or re.search(
        rf"(позже|раньше|попозже|пораньше)\s+на\s+{NUM}?\s*(дн\w*|день|недел\w*)", t
    )
    if shift:
        groups = shift.groups()
        if groups[0] in ("позже", "раньше", "попозже", "пораньше"):
            direction, amount, unit = groups[0], groups[1], groups[2]
        else:
            amount, unit, direction = groups
        value = int(to_number(amount) or 1) if amount else 1
        if unit.startswith("недел"):
            value *= 7
        result["shift_days"] = value if direction in ("позже", "попозже") else -value
        t = t[: shift.start()] + " " + t[shift.end() :]  # «на два дня позже» — сдвиг, а не длительность «на 2 дня»
    longer = re.search(rf"(?:на|еще|ещё)\s+{NUM}?\s*(дн\w*|ноч\w*|день)\s+(дольше|больше|длиннее)", t) or re.search(
        rf"(?:продли\w*|добав\w*)\s+(?:еще|ещё)?\s*{NUM}?\s*(дн\w*|ноч\w*|день)", t
    )
    shorter = re.search(rf"на\s+{NUM}?\s*(дн\w*|ноч\w*|день)\s+(меньше|короче)", t)
    patch.update(_dates(t, today))
    # «на 2 дня меньше» — изменение длительности, а не «на 2 дня»: применяем после разбора дат
    if longer and brief.get("nights"):
        patch["nights"] = brief["nights"] + int(to_number(longer.group(1) or "1") or 1)
    if shorter and brief.get("nights"):
        patch["nights"] = max(1, brief["nights"] - int(to_number(shorter.group(1) or "1") or 1))
    party = _party(t, brief)
    family_guess = party.pop("_family_guess", False)
    ages_guessed = party.pop("_ages_guessed", False)
    patch.update(party)
    # «с нами ещё мама поедет», «плюс один взрослый» — прибавляем к текущему составу, а не заменяем его
    plus_adult = re.search(
        r"(?:ещё|еще|плюс|\+)\s*(?:один\s+|одна\s+)?(мам\w*|пап\w*|бабушк\w*|дедушк\w*|тещ\w*|свекров\w*|друг\w*|подруг\w*|сестр\w*|брат\w*|коллег\w*|взросл\w*|человек)",
        t,
    ) or re.search(r"\b(мама|папа|бабушка|дедушка|теща|свекровь|друг|подруга|сестра|брат)\s+(?:тоже\s+)?(?:поедет|едет|с нами)", t)
    if plus_adult and "adults" not in party:
        patch["adults"] = brief["adults"] + 1
        if re.match(r"(бабушк|дедушк|тещ|свекров)", plus_adult.group(1)):
            patch["seniors"] = True
    if re.search(r"(ещё|еще|плюс)\s+(?:один\s+|одного\s+)?(реб[её]н|сын|доч|малыш)", t) and party.get("children") and brief["children"]:
        patch["children"] = brief["children"] + party["children"]
    if re.search(
        r"^(спасибо|благодарю|спс|супер|класс|отлично|круто|понятно|ясно|ок|окей|привет|здравствуй\w*|добрый (день|вечер))[!.) ]*$", t
    ):
        result["intent"] = "chat"
        return result
    if (
        re.search(r"^(а\s+)?(кто ты|ты кто|что ты (умеешь|можешь)|что умеешь|как ты работаешь|помощь|help|как дела|как жизнь)\b", t)
        and not patch
    ):
        result["intent"], result["chat"] = "chat", "about"
        return result
    if brief.get("destination") and re.search(r"(друг\w+ направлен|что-то другое|что-нибудь другое|не туда|другую страну|другой город)", t):
        patch["exclude"] = sorted(set(brief.get("exclude", []) + [brief["destination"]]))
    result["family_guess"] = family_guess
    result["ages_guessed"] = ages_guessed

    orig = find_origin(t)
    if orig:
        patch["origin"] = orig["id"]
    dest = find_destination(t)
    excluded = []
    for d in destinations().values():
        for alias in d["aliases"]:
            # после алиаса — только окончание: «не катаюсь» не должно исключать курорт с алиасом «ката»
            tail = 1 if len(alias) <= 4 else 4
            if re.search(rf"(?:\bне|кроме|только не|без|не хочу в|не хочу на)\s+(?:в|на|во)?\s*{re.escape(alias)}\w{{0,{tail}}}\b", t):
                excluded.append(d["id"])
                break
    if excluded:
        patch["exclude"] = sorted(set(brief.get("exclude", []) + excluded))
    if dest and dest["id"] not in excluded:
        patch["destination"] = dest["id"]
    if re.search(
        r"(куда[- ]нибудь|куда угодно|не знаю куда|подскажи куда|посоветуй|без разницы куда|любое направление|другое направление|другие направления)",
        t,
    ):
        patch["destination"] = None
    # «Турция или Египет в мае?» — выбор между местами: собираем обе поездки рядом, а не берём одну молча
    compare = find_compare(t)
    if compare:
        result["compare"] = compare
        patch.pop("destination", None)
    elif re.search(r"\bсравн", t):
        picks = re.findall(r"\b([1-8])\b", t) + [str(ORDINALS[w[:4]]) for w in re.findall(r"\b(перв|втор|трет|четв)\w*", t)]
        if re.search(r"(перв\w+\s+(два|две|двух)|(два|две|двух)\s+перв)", t) or not picks:
            picks = ["1", "2"]  # «сравни первые два» и просто «сравни» — два лучших из подборки
        result["compare_picks"] = sorted({int(p) for p in picks})[:3]

    budget, budget_reason = parse_amount(t), ""
    if not budget:
        budget, budget_reason = parse_foreign_or_short_amount(t)
    if budget:
        per_person = re.search(r"(на человека|на каждого|с человека|на одного|на чел)", t)
        people = patch.get("adults", brief["adults"]) + len(patch.get("children", brief["children"]))
        patch["budget"] = budget * people if per_person else budget
        if budget_reason:
            result["inferred_reasons"] = {"budget": budget_reason}
    if _has(t, CHEAP_WORDS):
        patch["budget_level"] = "low"
    if _has(t, RICH_WORDS):
        patch["budget_level"] = "high"
    stars = re.search(r"(\d|пять|четыре|три)\s*(звезд|\*)", t)
    if stars:
        patch["min_stars"] = int(to_number(stars.group(1)) or 4)

    kinds = [kind for kind, words in KIND_WORDS.items() if _has(t, words)]
    regions = [key for key, (_, words) in REGIONS.items() if _has(t, words)]
    if "abroad" in regions and "russia" in regions:
        regions.remove("abroad")  # «не за границу» содержит «за границ»
    if regions:
        patch["regions"] = regions
        if "black_sea" in regions:
            kinds.append("sea")
    if re.search(r"\b(на (своей |личной )?машине|на авто(мобиле)?|своим ходом|на своей тачке|автопутешеств)", t):
        patch["own_car"] = True
    if "детский клуб" in t or "клуб для детей" in t:
        kinds = [k for k in kinds if k != "party"]
    if re.search(r"(вс[её] включено|all inclusive|олл инклюзив|ол инклюзив|ультра)", t):
        patch["meal"] = "AI"
        kinds.append("allinclusive")
    elif re.search(r"(полупансион|завтрак\w* и ужин)", t):
        patch["meal"] = "HB"
    elif re.search(r"(завтрак)", t) and not re.search(r"без завтрак", t):
        patch["meal"] = "BB"
    elif re.search(r"(без питания|без завтрак|питание не нужно)", t):
        patch["meal"] = "RO"
    diets = [key for key, pattern in DIET_PATTERNS.items() if re.search(pattern, t)]
    if "vegan" in diets:
        diets = [d for d in diets if d != "vegetarian"]  # веганское меню и так вегетарианское
    if diets:
        patch["diet"] = sorted(set(brief.get("diet") or []) | set(diets))
    if kinds:
        patch["kinds"] = sorted(set(brief.get("kinds", []) + kinds))
    if _has(t, WARM_WORDS):
        patch["warm"] = True

    hours = re.search(rf"(?:не больше|не более|до|максимум|меньше|не дольше)\s+{NUM}\s*(?:-х|х)?\s*час", t)
    if hours:
        patch["max_hours"] = to_number(hours.group(1))
    elif re.search(r"(без долгих перел|недолго лететь|недалеко|не далеко|близко|недолгий перел|без длинных перел|не хочу долго лететь)", t):
        patch["max_hours"] = 5
    if re.search(r"(без пересад|прям\w+ рейс|прям\w+ перел|прямым)", t):
        patch["direct_only"] = True
    if re.search(
        r"(на поезде|поездом|не самол|боюсь летать|не летать|не люблю летать|без самол|на жд|ржд|без перел[её]т|без авиа|только поезд)", t
    ):
        patch["transport"] = "train"
    elif re.search(r"(самол[её]том|на самол[её]те|перел[её]том|авиа)", t):
        patch["transport"] = "flight"
    if re.search(
        r"(без ночных|не ночью|ночные не|не ночн|днем лететь|дневной рейс|ночью (лететь |ехать )?не (хотим|хочу|любим|люблю|надо))", t
    ):
        patch["avoid_night"] = True
    if re.search(
        r"(без визы|безвиз|виза не нужна|не нужна виза|без оформления визы|нет визы|нет шенген|визу (делать|оформлять) (неохота|не хочу|лень)|не хочу (делать |оформлять )?визу)",
        t,
    ):
        patch["visa_free"] = True
    if re.search(r"(возможност\w+ отмен|бесплатн\w+ отмен|возвратн|можно отменить|могут поменяться|могут измениться|не уверен)", t):
        patch["refundable"] = True
    elif re.search(r"(невозвратн|отмена не нужна)", t):
        patch["refundable"] = False

    prefs = []
    if re.search(
        r"(перв\w+ лини|у моря|у самого моря|рядом с морем|близко к морю|ближе к морю|поближе к морю|у пляжа|к пляжу|ближе к пляжу|у воды|возле моря)",
        t,
    ):
        prefs.append("near_beach")
    if "бассейн" in t:
        prefs.append("pool")
    if re.search(r"\bспа\b", t):
        prefs.append("spa")
    if re.search(
        r"(тих\w+|спокойн\w+|уединен\w+|без шума|выспаться|отдохнуть от всего|перезагруз|релакс|расслаб|никого вокруг|без людей|подальше от людей|малолюдн|без толп)",
        t,
    ):
        prefs.append("quiet")
    if re.search(r"(детск\w+ клуб|анимаци|аквапарк|горк)", t):
        prefs.append("kids_club")
    if prefs:
        patch["hotel_prefs"] = sorted(set(brief.get("hotel_prefs", []) + prefs))
    mood = []
    if "romantic" in kinds:
        mood.append("romantic")
    if "party" in kinds:
        mood.append("party")
    if "quiet" in prefs:
        mood.append("calm")
    if "active" in kinds:
        mood.append("active")
    if mood:
        patch["mood"] = sorted(set(brief.get("mood", []) + mood))
    if "romantic" in mood and "adults" not in patch and not patch.get("children"):
        patch["adults"] = 2
        result["romantic_pair"] = True

    if (
        re.search(r"(подешевле|дешевле|бюджет меньше|меньше бюджет|урежь|сэконом|дорого\b|слишком дорого|не потянем)", t)
        and stage == "plan"
    ):
        result["budget_change"] = "down"
    if re.search(r"(получше|покомфортнее|подороже|можно дороже|бюджет больше|увелич\w+ бюджет)", t) and stage == "plan":
        result["budget_change"] = "up"

    # выбор варианта: «второй», «вариант 2», «оптимальный»
    select = None
    match = re.search(r"(?:вариант|номер|№|#)\s*(\d)", t) or re.search(
        r"\b(перв|втор|трет|четв)\w*\b(?!\s+(?:дн|ноч|недел|линии|линия|раз))", t
    )
    if match:
        select = ORDINALS.get(match.group(1)[:4]) or ORDINALS.get(match.group(1))
    elif re.fullmatch(r"\s*(давай\s+|беру\s+|хочу\s+)?(\d)\s*[.!]?\s*", t):
        select = int(re.fullmatch(r"\s*(давай\s+|беру\s+|хочу\s+)?(\d)\s*[.!]?\s*", t).group(2))
    else:
        for label, index in BUNDLE_LABELS.items():
            if label in t and stage == "plan":
                select = index
    if select and 1 <= select <= 4 and not result.get("compare_picks"):  # «сравни первые два» — не выбор первого
        result["select"] = select

    booked = stage == "booked"
    if booked and re.search(r"(рейс\w*\s+(отмен|перенес|задерж)|отменил\w*\s+рейс|отмен\w+ (вылет|поезд)|поезд\s+отмен)", t):
        result["post"] = {"type": "disruption", "what": "flight_cancelled"}
    elif booked and re.search(r"(отель\s+(не\s+(может|сможет)|отказ)|не\s+(заселя|засел)|овербук|нет\s+(мест|номеров)\s+в\s+отеле)", t):
        result["post"] = {"type": "disruption", "what": "hotel_overbooked"}
    elif booked and re.search(r"(ранн\w+ заезд|заехать пораньше|заселиться (раньше|пораньше)|пораньше заселит)", t):
        result["post"] = {"type": "early_checkin"}
    elif booked and re.search(r"(поздн\w+ выезд|выехать позже|выселиться позже|задержаться в номере)", t):
        result["post"] = {"type": "late_checkout"}
    elif booked and re.search(r"(трансфер|такси из аэропорта|встретить в аэропорту|как добраться до отеля)", t):
        result["post"] = {"type": "add_transfer"}
    elif booked and re.search(r"(отмен\w+ (брон|поездк|заказ)|отменить вс[её])", t):
        result["post"] = {"type": "cancel"}
    elif booked and (result["shift_days"] or "date_from" in patch or re.search(r"(перенест|поменять даты|изменить даты|сдвинуть)", t)):
        result["post"] = {"type": "change_dates", "shift_days": result["shift_days"], "date_from": patch.get("date_from")}
    elif booked and re.search(r"(напомин|напомни)", t):
        result["post"] = {"type": "reminders"}
    if result["post"]:
        result["intent"] = "post"
        return result

    if re.search(r"(брониру|бронь|забронир|оформ|оплат|покупаю|купить|беру\b|берём|берем|давай этот|подходит,? берем|подходит,? беру)", t):
        result["intent"] = "book"
        return result

    # «как в прошлый раз, но в горы» — просьба повторить поездку, а не вопрос, хоть и начинается с «как»
    if re.search(r"(как (и )?в прошлый раз|как в прошлом году|как в тот раз|как тогда|туда же|опять туда|снова туда|как обычно)", t):
        result["like_last"] = True
    question = None
    asking = not result.get("like_last") and (
        "?" in t
        or bool(
            re.match(
                r"^(а\s+)?(какая|какой|какие|сколько|можно ли|нужна ли|нужен ли|нужно ли|есть ли|как |где |когда |что |чем |почему|зачем|стоит ли)",
                t,
            )
        )
    )
    weather_words = r"(погод|температур|холодн|холод|тепло|жарк|дожд|ливн|вода|купат|снег|морозн)"
    # «безопасно ли там с детьми?» — это вопрос, а не «добавь детей в поездку»
    if re.match(r"^(а\s+)?(можно ли|стоит ли|безопасно ли|опасно ли|подойд[её]т ли|нормально ли|правда ли|есть ли|как там|что там)", t) or (
        "?" in t and re.search(r"\bли\b", t)
    ):
        if not result["shift_days"] and "destination" not in patch:
            result["question_month"] = patch.get("month")
            patch.clear()
    # «а в декабре там тепло?» — вопрос о погоде в другом месяце, а не просьба пересобрать поездку
    if asking and re.search(weather_words, t) and set(patch) <= {"month", "date_from", "warm", "kinds"}:
        result["question_month"] = patch.get("month") or result.get("question_month")
        patch.clear()
    if re.search(r"(виз[аыу]|загран|паспорт|документ)", t) and ("?" in t or re.search(r"(нужн|какие|какой)", t)):
        question = "visa"
    elif re.search(weather_words, t) and asking:
        question = "weather"
    elif re.search(
        r"(что\s+(?:там\s+)?посмотреть|чем\s+(?:там\s+)?заняться|что\s+(?:там\s+)?делать|куда\s+(?:там\s+)?сходить|достопримечат|что интересного)",
        t,
    ):
        question = "todo"
    elif re.search(r"(сколько лететь|сколько ехать|время в пути)", t):
        question = "travel_time"
    elif re.search(r"(почему|зачем|откуда)", t) and "?" in t:
        question = "why"
    elif asking and not patch and not result["shift_days"] and not result.get("budget_change") and not result["select"]:
        question = "other"  # любой другой вопрос: ответим по данным поездки, а где данных нет — честно скажем
    if question and not patch and not result.get("compare"):  # «Турция или Египет?» — выбор, а не вопрос
        result["intent"] = "question"
        result["question"] = question
        return result
    if result["select"] and not any(k for k in patch if k not in ("nights",)):
        result["intent"] = "select"
    if re.search(r"(запомни|учти на будущее|на будущее)", t):
        result["remember"] = raw
    return result


# ── Применение изменений и выводы ───────────────────────────────────────────


def apply_patch(brief: dict, sources: dict, patch: dict, kind: str = "explicit", reasons: dict | None = None) -> list[str]:
    """Применяет изменения к брифу и записывает источник. Возвращает список изменённых полей."""
    changed = []
    for key, value in patch.items():
        if key not in brief:
            continue
        if brief[key] == value:
            # «вдвоём» совпало с допущением по умолчанию — значение то же, но теперь его сказал пользователь
            if kind == "explicit" and sources.get(key, {}).get("kind") == "default":
                sources[key] = {"kind": kind, "reason": ""}
            continue
        brief[key] = value
        sources[key] = {"kind": kind, "reason": (reasons or {}).get(key, "")}
        changed.append(key)
    return changed


def derive(brief: dict, sources: dict, changed: list[str] | None = None) -> list[dict]:
    """Скрытые требования из явных: «с ребёнком» → короткий перелёт, без ночных рейсов, детский клуб.
    changed — что поменялось в этом ходе: справочные пояснения (питомец, тепло) показываем только при изменении."""
    inferred = []

    def infer(key: str, value, reason: str) -> None:
        if sources.get(key, {}).get("kind") in ("explicit", "memory"):
            return
        if brief[key] == value and sources.get(key, {}).get("kind") == "inferred":
            return
        brief[key] = value
        sources[key] = {"kind": "inferred", "reason": reason}
        inferred.append({"key": key, "reason": reason})

    kids = [age for age in brief["children"] if age < 12]
    if not kids:
        # «а если без ребёнка» — снимаем то, что вывели из ребёнка; сказанное явно и память не трогаем
        for key, empty in (("max_hours", None), ("avoid_night", False)):
            source = sources.get(key, {})
            if source.get("kind") == "inferred" and "ребён" in source.get("reason", "") and not brief["seniors"]:
                brief[key] = empty
                sources.pop(key)
        if sources.get("hotel_prefs", {}).get("kind") == "inferred" and "kids_club" in brief["hotel_prefs"]:
            brief["hotel_prefs"] = [p for p in brief["hotel_prefs"] if p != "kids_club"]
    if kids:
        youngest = min(kids)
        infer("max_hours", 5 if youngest < 4 else 6, "с ребёнком долгий перелёт утомляет")
        infer("avoid_night", True, "с ребёнком ночные рейсы и заселение под утро тяжело")
        if youngest >= 3 and "kids_club" not in brief["hotel_prefs"]:
            brief["hotel_prefs"] = sorted(set(brief["hotel_prefs"] + ["kids_club"]))
            sources["hotel_prefs"] = {"kind": "inferred", "reason": "ребёнку будет чем заняться"}
            inferred.append({"key": "hotel_prefs", "reason": "детский клуб — ребёнку будет чем заняться"})
    if brief["seniors"]:
        infer("avoid_night", True, "старшим путешественникам тяжело ночью")
        infer("max_hours", 6, "старшим путешественникам тяжело долго лететь")
    if brief["budget_level"] == "low" and sources.get("priorities", {}).get("kind") != "explicit":
        brief["priorities"] = brief["priorities"] | {"price": 0.85, "comfort": 0.35}
    if brief["budget_level"] == "high" and sources.get("priorities", {}).get("kind") != "explicit":
        brief["priorities"] = brief["priorities"] | {"price": 0.2, "comfort": 0.9}
    if "near_beach" in brief["hotel_prefs"] and sources.get("priorities", {}).get("kind") != "explicit":
        brief["priorities"] = brief["priorities"] | {"beach": 0.9}
    if brief["refundable"] and sources.get("priorities", {}).get("kind") != "explicit":
        brief["priorities"] = brief["priorities"] | {"flex": 0.85}
    if "romantic" in brief["mood"] and "quiet" not in brief["hotel_prefs"]:
        brief["hotel_prefs"] = sorted(set(brief["hotel_prefs"] + ["quiet"]))
    fresh = lambda key: changed is None or key in changed  # noqa: E731
    if brief["pets"] and fresh("pets"):
        inferred.append({"key": "pets", "reason": "ищу только отели, где можно с животным, и рейсы с перевозкой в салоне"})
    if brief["warm"] and "sea" in brief["kinds"] and (fresh("warm") or fresh("kinds")):
        inferred.append({"key": "warm", "reason": "«тёплое море» — вода от +23°, воздух от +25°"})
    if brief.get("accessible"):
        infer("direct_only", True, "на коляске пересадка тяжела — ищу прямые рейсы")
        if fresh("accessible"):
            inferred.append({"key": "accessible", "reason": "только отели с доступной средой, трансфер с подъёмником, помощь в аэропорту"})
    elif sources.get("direct_only", {}).get("kind") == "inferred" and "коляск" in sources["direct_only"].get("reason", ""):
        brief["direct_only"] = False  # доступную среду убрали — снимаем и то, что из неё вывели
        sources.pop("direct_only")
    return inferred


def knows_when(brief: dict) -> bool:
    return bool(brief["month"] or brief["date_from"])


def knows_who(sources: dict) -> bool:
    return any(sources.get(key, {}).get("kind") in ("explicit", "memory", "inferred") for key in ("adults", "children"))


# ── Подписи для интерфейса ──────────────────────────────────────────────────


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def money(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", " ") + " ₽"


def party_label(brief: dict) -> str:
    adults = brief["adults"]
    text = f"{adults} {plural(adults, 'взрослый', 'взрослых', 'взрослых')}"
    kids = brief["children"]
    if len(kids) == 1:
        age = kids[0]
        text += f" + ребёнок {age} {plural(age, 'год', 'года', 'лет')}" if age >= 1 else " + младенец"
    elif kids:
        ages = sorted(kids)
        listed = ", ".join(str(a) for a in ages[:-1]) + f" и {ages[-1]}"
        text += f" + {len(kids)} {plural(len(kids), 'ребёнок', 'ребёнка', 'детей')} ({listed} {plural(ages[-1], 'год', 'года', 'лет')})"
    return text


def dates_label(brief: dict) -> str:
    nights = brief["nights"]
    tail = f"{nights} {plural(nights, 'ночь', 'ночи', 'ночей')}"
    if brief["date_from"]:
        start = date.fromisoformat(brief["date_from"])
        end = start + timedelta(days=nights)
        if start.month == end.month:
            return f"{start.day}–{end.day} {MONTHS_GEN[end.month - 1]} · {tail}"
        return f"{start.day} {MONTHS_GEN[start.month - 1]} – {end.day} {MONTHS_GEN[end.month - 1]} · {tail}"
    if brief["month"]:
        return f"в {MONTHS_IN[brief['month'] - 1]} · {tail}"
    return f"даты не выбраны · {tail}"


PREF_LABELS = {
    "near_beach": "близко к морю",
    "pool": "бассейн",
    "spa": "спа",
    "quiet": "тихий отель",
    "kids_club": "детский клуб",
}
MEAL_LABELS = {"RO": "без питания", "BB": "завтраки", "HB": "полупансион", "AI": "всё включено"}
DIET_LABELS = {
    "halal": "халяль",
    "vegetarian": "вегетарианское меню",
    "vegan": "веганское меню",
    "gluten_free": "без глютена",
    "lactose_free": "без лактозы",
    "nut_free": "без орехов",
}


def diet_label(diets: list[str]) -> str:
    return ", ".join(DIET_LABELS[d] for d in diets if d in DIET_LABELS)


def chips(brief: dict, sources: dict) -> list[dict]:
    """Карточка «Я понял так»: что агент учитывает и откуда это взял."""

    def chip(key: str, label: str, source_key: str | None = None) -> dict:
        source = sources.get(source_key or key, {"kind": "explicit", "reason": ""})
        return {"key": key, "label": label, "kind": source["kind"], "reason": source.get("reason", "")}

    start = origin(brief["origin"])["from"]
    result = [chip("origin", start[0].upper() + start[1:])]
    if len(brief["route"]) >= 2:
        result.append(chip("destination", " → ".join(destination(d)["name"] for d in brief["route"])))
    elif brief["destination"]:
        result.append(chip("destination", destination(brief["destination"])["name"]))
    else:
        result.append({"key": "destination", "label": "направление подберу", "kind": "default", "reason": "куда ехать, решим вместе"})
    result.append(chip("dates", dates_label(brief), "date_from" if brief["date_from"] else "month" if brief["month"] else "nights"))
    result.append(chip("party", party_label(brief), "children" if brief["children"] else "adults"))
    if brief["pets"]:
        result.append(chip("pets", "с собакой" if brief["pets"] == "dog" else "с кошкой"))
    if brief.get("accessible"):
        result.append(chip("accessible", "доступная среда"))
    if brief["budget"]:
        result.append(chip("budget", f"до {money(brief['budget'])}"))
    elif brief["budget_level"]:
        result.append(
            chip("budget_level", {"low": "недорого", "mid": "средний бюджет", "high": "комфорт важнее цены"}[brief["budget_level"]])
        )
    for kind in brief["kinds"]:
        if not (kind == "allinclusive" and brief["meal"] == "AI"):
            result.append(chip(f"kind:{kind}", KIND_LABELS.get(kind, kind), "kinds"))
    if brief["warm"]:
        result.append(chip("warm", "тепло", "warm"))
    if brief["max_hours"]:
        result.append(chip("max_hours", f"в пути до {brief['max_hours']:g} ч"))
    if brief["avoid_night"]:
        result.append(chip("avoid_night", "без ночных рейсов"))
    if brief["direct_only"]:
        result.append(chip("direct_only", "без пересадок"))
    if brief["transport"] == "train":
        result.append(chip("transport", "на поезде"))
    if brief["visa_free"]:
        result.append(chip("visa_free", "без визы"))
    if brief["meal"]:
        result.append(chip("meal", MEAL_LABELS[brief["meal"]]))
    for diet in brief.get("diet") or []:
        result.append(chip(f"diet:{diet}", f"кухня: {DIET_LABELS[diet]}", "diet"))
    if brief["refundable"]:
        result.append(chip("refundable", "с бесплатной отменой"))
    if brief["min_stars"]:
        result.append(chip("min_stars", f"от {brief['min_stars']}★"))
    for pref in brief["hotel_prefs"]:
        result.append(chip(f"pref:{pref}", PREF_LABELS.get(pref, pref), "hotel_prefs"))
    for excluded in brief["exclude"]:
        result.append(chip(f"exclude:{excluded}", f"не {destination(excluded)['name']}", "exclude"))
    for region in brief["regions"]:
        result.append(chip(f"region:{region}", REGIONS[region][0], "regions"))
    if brief["own_car"]:
        result.append(chip("own_car", "на своей машине"))
    return result


def remove_chip(brief: dict, sources: dict, key: str) -> None:
    """Пользователь убирает чип — значит, это требование ему не нужно. Запоминаем как явное."""
    base = new_brief()
    field, _, value = key.partition(":")
    mapping = {"party": "children", "dates": "date_from", "budget": "budget", "budget_level": "budget_level"}
    if field == "kind":
        brief["kinds"] = [k for k in brief["kinds"] if k != value]
        sources["kinds"] = {"kind": "explicit", "reason": ""}
    elif field == "pref":
        brief["hotel_prefs"] = [p for p in brief["hotel_prefs"] if p != value]
        sources["hotel_prefs"] = {"kind": "explicit", "reason": ""}
    elif field == "exclude":
        brief["exclude"] = [e for e in brief["exclude"] if e != value]
    elif field == "region":
        brief["regions"] = [r for r in brief["regions"] if r != value]
        sources["regions"] = {"kind": "explicit", "reason": ""}
    elif field == "diet":
        brief["diet"] = [d for d in brief.get("diet") or [] if d != value]
        sources["diet"] = {"kind": "explicit", "reason": ""}
    else:
        target = mapping.get(field, field)
        if target in brief:
            brief[target] = base[target]
            sources[target] = {"kind": "explicit", "reason": "убрано пользователем"}
