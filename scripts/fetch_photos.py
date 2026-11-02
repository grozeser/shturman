"""Скачивает фото направлений и иллюстративные фото отелей с Wikimedia Commons (только свободные лицензии).

    pip install pillow
    python scripts/fetch_photos.py

Кладёт WebP в frontend/public/photos/{dest,hotel}/, пишет frontend/src/photos.ts (автор, лицензия, ссылка —
для подписи на фото) и frontend/public/photos/CREDITS.md. Запускать вручную: рантайм в сеть не ходит, фото
лежат в репозитории. Направление вне списка показывает нарисованную сцену (components/Scene.tsx).
"""

import html
import io
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public" / "photos"
TS = ROOT / "frontend" / "src" / "photos.ts"
API = "https://commons.wikimedia.org/w/api.php"
UA = "ShturmanHackathon/1.0 (https://github.com/grozeser/shturman)"
FREE = re.compile(r"^(CC0|Public domain|PD|CC BY(-SA)? [1-4]\.0)", re.I)

# id направления из backend/app/data/destinations.json → файл на Commons
DESTINATIONS: dict[str, str] = {
    "sochi": "File:Sochi adler aerial view 2018 23.jpg",
    "krasnaya_polyana": "File:Roza-Hutor-009.jpg",
    "anapa": "File:Anapa beach.jpg",
    "gelendzhik": "File:Gelendzhik IMG 6723 1725.jpg",
    "yalta": "File:Widok na Jałtę ze statku 04.JPG",
    "kaliningrad": "File:Kaliningrad fishing village.jpg",
    "spb": "File:Palace of Peter II Neva Saint Petersburg.jpg",
    "moscow": "File:Vista general del Kremlin, Moscú, Rusia, 2016-10-03, DD 18-19 HDR.jpg",
    "kazan": "File:Kazan Kremlin. Spasskaya Tower P8111872 2200.jpg",
    "nizhny": "File:Dmitrovskaya Tower of Nizhny Novgorod Kremlin.jpg",
    "altai": "File:Lake Akkul, Altai Republic, Russia.jpg",
    "baikal": "File:Baikal, Cape Burhan, Olkhon Island, Lake Baikal, Russia.jpg",
    "dagestan": "File:Вид на каньон и реку Сулак у поселка Дубки.jpg",
    "kmv": "File:Cascading staircase Kislovodsk.jpg",
    "elbrus": "File:Вид на Эльбрус по пути в Джилы-Су.jpg",
    "sheregesh": "File:Sheregesh 09.jpg",
    "karelia": "File:Severo-Priladozhsky reserve. Ruskeala waterfall and the water of the Tohmajoki river.jpg",
    "murmansk": "File:Teriberka.jpg",
    "kamchatka": "File:Корякский, Авачинский, Козельский.jpg",
    "vladivostok": "File:Vladivostok Zolotoy Rog Bay P8050527 2200.jpg",
    "suzdal": "File:Suzdal. Church of the Suzdal. Paraskeva Pyatnitsa Church and Resurrection of Christ.jpg",
    "abkhazia": "File:2014 Nowy Aton, Monaster Nowy Athos (06).jpg",
    "minsk": "File:Minsk HolySpiritChurch 001 3673.jpg",
    "antalya": "File:Hadrian's Gate, Antalya 01.jpg",
    "alanya": "File:Boat in Alanya.jpg",
    "kemer": "File:Kemer Antalya TÜRKİYE - panoramio (11).jpg",
    "bodrum": "File:Bodrum Castle (2017).jpg",
    "istanbul": "File:Hagia Sophia Mars 2013.jpg",
    "cappadocia": "File:Hot air balloon in Cappadocia 02.jpg",
    "dubai": "File:Burj Khalifa (16260269606).jpg",
    "rak": "File:Mountains of Wadi Shawka denoised.jpg",
    "hurghada": "File:Boats near Paradise Island, Hurghada.jpg",
    "sharm": "File:Gold Beach at Ras Um Sid Bay.jpg",
    "phuket": "File:Banana beach Phuket 2017 - 05.jpg",
    "pattaya": "File:Boat moving towards a pier in Pattaya, Thailand.jpg",
    "samui": "File:Pier in Bophut village in Ko Samui.jpg",
    "bangkok": "File:Ubosot of Wat Arun.jpg",
    "nha_trang": "File:Nha Trang Beach 10.jpg",
    "phu_quoc": "File:Phu Quoc beach 01.jpg",
    "bali": "File:Rice terraces, Bali.jpg",
    "maldives": "File:Diamonds Thudufushi Beach and Water Villas, May 2017 -09.jpg",
    "sri_lanka": "File:Goyambokka Beach, Tangalle, Sri Lanka.jpg",
    "goa": "File:Anjuna Beach, Goa, India, Legendary Curlies beach shack.jpg",
    "sanya": "File:三亚太阳湾公路旁海滩 20260115.jpg",
    "tunisia": "File:Hammamet-Sud beach R02.jpg",
    "budva": "File:Sveti Stefan (06).jpg",
    "belgrade": "File:Church of Saint Sava (Belgrade, Serbia).jpg",
    "tbilisi": "File:Tbilisi, Old Tbilisi, Kura River 2, Georgia.jpg",
    "batumi": "File:Batumi sunset.jpg",
    "gudauri": "File:Gudauri (10).jpg",
    "yerevan": "File:Mount Ararat, Ararat Plain, Armenia-Turkey border, Armenia.jpg",
    "samarkand": "File:Tilya-Kori Madrasa 01.jpg",
    "almaty": "File:Shymbulak, Almaty (P1180179).jpg",
    "issyk_kul": "File:Lake Issyk-Kul, Kyrgyzstan.jpg",
    "varadero": "File:Varaderobeach1.JPG",
    "seychelles": "File:Anse Source d'Argent 3-La Digue.jpg",
    "mauritius": "File:Sunbathing at Le Morne Beach in Mauritius (53697787846).jpg",
    "doha": "File:Doha skyline0001.JPG",
    "langkawi": "File:Langkawi Malaysia Langkawi-Cable-Car-03.jpg",
    "paris": "File:Paris - The Eiffel Tower in spring - 2307.jpg",
    "rome": "File:Colosseum of Rome, Italy.jpg",
    "barcelona": "File:Sagrada Família 2010.JPG",
}

# Пул иллюстраций для синтетических отелей: курорт у моря, город, горы
HOTELS: dict[str, list[str]] = {
    "resort": [
        "File:Ideal Beach Resort Pool Mahabalipuram Sep22 R16 06310.jpg",
        "File:Birštonas 03.jpg",
        "File:Onna Okinawa ANA-InterContinental-Manza-Beach-Resort-01.jpg",
        "File:Marine Club Beach Resort Boavista, Boa Vista, Cape Verde, 2010 December.jpg",
        "File:Infinity Pool Lopesan Costa Meloneras, May 2018.jpg",
        "File:Norderney, Weststrand, Hotel -- 2018 -- 1050.jpg",
        "File:Promenade Hotel on Puducheery beach road.jpg",
        "File:Sopot 2023 34 Beach Bar.jpg",
        "File:The Palms Beach Hotel & Spa in Kuwait.jpg",
        "File:Sal Sta Maria beach hotel.jpg",
        "File:Ocean Village Beach Resort in Tofino Canada - 2026.jpg",
        "File:Livorno - Hotel Palazzo - 2025-09-29 20-09-38 001.jpg",
        "File:Villa Fridhem September 2021 08.jpg",
        "File:Карловы Вары - panoramio (12).jpg",
        "File:Beach Resort and Seaside Resort setting at Ada-Foah, Greater Accra.jpg",
        "File:Rio Mar Beach Resort in Río Grande, Puerto Rico.jpg",
        "File:Endless Water (Unsplash).jpg",
        "File:Infinity Pool Jolie Ville Luxor R01.jpg",
        "File:Golem, Qarku i Tiranës (Tirana County), Albania - Grand Blue Fafa Resort, 7 January 2023 - Pool and Palms at Sunset.jpg",
        "File:Seaside Hotel Maiko Villa.jpg",
        "File:Chan-Kah Resort Village, Bungalow 74 (8264845598).jpg",
        "File:DSC0065 Huahiné Island Traditional Bungalow in the Lapitas Resort (8105100211).jpg",
        "File:View from Ao Luek Panoramic Pool Villa, Krabi, Thailand SF0003.jpg",
        "File:Hotel Don Paco - Seville - sun loungers (14531120584).jpg",
    ],
    "city": [
        "File:Restaurant room of Amantaka luxury Resort & Hotel in Luang Prabang Laos.jpg",
        "File:Tadoussac - Hotel (1).jpg",
        "File:Hotel 3 Nagas with old red Citroen at blue hour in Luang Prabang.jpg",
        "File:Hotel y restaurante 12.jpg",
        "File:At Berlin 2024 002.jpg",
        "File:Premier room, The Peninsula Paris, 4 June 2014.jpg",
        "File:Les Pagodes de Beauval - 474.jpg",
        "File:Conrad Las Vegas at Resorts World February 2023 HDR.jpg",
        "File:Yardarm Motel Searsport October 2021 HDR.jpg",
        "File:Lobby hall with couches and chandelier at The Fullerton Bay Hotel Singapore.jpg",
        "File:Lobby of the hotel Crowne Plaza Vientiane.jpg",
        "File:Kissingen Hotel Kaiserhof Lobby 0417RM0371.jpg",
        "File:Frontenac Hotel, Quebec ville, downtown 007.jpg",
        "File:Velden Seepromenade 3 Boutique Hotel 23122023 0339.jpg",
        "File:Mariánské Lázně, hotel restaurant Villa Dino IMG 3158 2022-08-09 10.06.jpg",
        "File:The Peninsula Paris' Chinese restaurant LiLi, 12 August 2014.jpg",
        "File:Editing File-El Tovar Hotel inside staircase.JPG",
        "File:Hotel La Rose, Santa Rosa, CA Sept 6 2025.jpg",
        "File:Lounge InterContinental Singapore.jpg",
        "File:Morgan House Kalimpong 3.jpg",
        "File:Gereuth Schloss Gästezimmer-20190908-RM-114159.jpg",
        "File:Aurora apartment hotel san antonio.jpg",
        "File:Nottuln, Hotel Steverburg -- 2016 -- 1486.jpg",
        "File:Midland Hotel, Bradford.jpg",
    ],
    "mountain": [
        "File:Rigyal Hotel Padum Oct22 A7C 03737.jpg",
        "File:Cherry Resort inside Temi Tea Garden, Namchi, Sikkim.jpg",
        "File:Hotel il muraglione.jpg",
        "File:Hotel Luční bouda (Wiesenbaude).jpg",
        "File:Ski patrol cabin, Signal de l'Homme, Auris, 2026.jpg",
        "File:Rosa Plato.jpg",
        "File:Albeck Benesirnitz 6 Alpenbad St Leonhard 06052015 3259.jpg",
        "File:Mountain lodge Tomčeva koča, Karawanks, Slovenia.jpg",
        "File:Skogadalsbøen mountain lodge in Jotunheimen National Park.jpg",
        "File:Lukmanierpass, Passo del Lucomagno. 20-09-2022. (actm.) 26.jpg",
        "File:Glecksteinhütte tele 20200207 2.jpg",
        "File:Krynica-Zdroj, Aleja Leona Nowotarskiego i widok na Bulwary Dietla.jpg",
        "File:Mountain hut Ciadinat Sëlva.jpg",
        "File:Aescher-Wildkirchli 20210528 01.jpg",
        "File:Remote view of the Villarais area from the Villard slope, Villard-Reculas, 2026.jpg",
        "File:Cabin at Allegany State Park.jpg",
        "File:View of Les Menuires and Mont Blanc from Pointe de la Masse, 2022.jpg",
        "File:Grand Reberty and Les Bruyères from the Paturages slope at 2090 m, Les Menuires.jpg",
        "File:Brelin from front de neige La Croisette, Les Menuires.jpg",
        "File:Almsee Fischerhütte-4167.jpg",
        "File:Åhls minnesgård May 2018 04.jpg",
        "File:Hotel Auersberg Haus im Winter.jpg",
        "File:Samotnia lato2013 od strony Strzechy.jpg",
        "File:Schronisko PTTK Klimczok w Beskidzie Śląskim, 20251004 1107 4837.jpg",
    ],
}


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception as error:  # noqa: BLE001 — сеть: повторяем с паузой
            print("  retry", attempt + 1, error)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"не удалось получить {url}")


def clean_author(raw: str) -> str:
    """Имя автора из поля Artist: без разметки и приписок вида «This photo was taken by X. Please credit…»."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", raw))).strip()
    taken = re.search(r"(?i)(?:photo|image) (?:was )?taken by ([^.,;]+)", text)
    if taken:
        text = taken.group(1)
    derivative = re.match(r"(?i)original:\s*(.+?)\s*derivative work:\s*(.+)", text)
    if derivative:
        text = f"{derivative.group(1)}, {derivative.group(2)}"
    return text.strip(" \"'")[:60] or "автор не указан"


def info(title: str, width: int) -> dict:
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": str(width),
    }
    page = next(iter(json.loads(get(f"{API}?{urllib.parse.urlencode(params)}"))["query"]["pages"].values()))
    image = page["imageinfo"][0]
    meta = image["extmetadata"]
    license_name = meta.get("LicenseShortName", {}).get("value", "")
    if not FREE.match(license_name):
        raise ValueError(f"{title}: несвободная лицензия {license_name!r}")
    return {
        "thumb": image["thumburl"],
        "author": clean_author(meta.get("Artist", {}).get("value", "")),
        "license": license_name,
        "license_url": meta.get("LicenseUrl", {}).get("value", ""),
        "source": image["descriptionurl"],
        "title": title,
    }


def save_webp(data: bytes, path: Path, width: int, quality: int) -> None:
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        if image.width > width:
            image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, "WEBP", quality=quality, method=6)


def credit(item: dict) -> dict:
    return {"author": item["author"], "license": item["license"], "source": item["source"]}


def main() -> None:
    dest_credits: dict[str, dict] = {}
    for dest, title in DESTINATIONS.items():
        item = info(title, 1280)
        save_webp(get(item["thumb"]), PUBLIC / "dest" / f"{dest}.webp", 1200, 60)
        dest_credits[dest] = item
        print(dest, "←", title, f"({item['license']})")
        time.sleep(0.5)

    hotel_credits: dict[str, list[dict]] = {}
    for kind, titles in HOTELS.items():
        hotel_credits[kind] = []
        for index, title in enumerate(titles, 1):
            item = info(title, 960)
            file = f"{kind}-{index}.webp"
            save_webp(get(item["thumb"]), PUBLIC / "hotel" / file, 640, 62)
            hotel_credits[kind].append({**item, "file": file})
            print(kind, index, "←", title)
            time.sleep(0.5)

    dest_ts = json.dumps({key: credit(value) for key, value in dest_credits.items()}, ensure_ascii=False, indent=4)
    hotel_ts = json.dumps(
        {kind: [{"file": i["file"], **credit(i)} for i in items] for kind, items in hotel_credits.items()},
        ensure_ascii=False,
        indent=4,
    )
    TS.write_text(
        "// Сгенерировано scripts/fetch_photos.py — не править руками.\n"
        "// Фото с Wikimedia Commons под свободными лицензиями; автор и лицензия показываются на фото.\n"
        "export interface PhotoCredit {\n    author: string;\n    license: string;\n    source: string;\n}\n\n"
        f"export const DEST_PHOTOS: Record<string, PhotoCredit> = {dest_ts};\n\n"
        "// Отели в демо синтетические — это иллюстрации по типу отеля, а не их фото\n"
        "export const HOTEL_PHOTOS: Record<'resort' | 'city' | 'mountain', (PhotoCredit & { file: string })[]> = "
        f"{hotel_ts};\n",
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# Фото: авторы и лицензии",
        "",
        "Все фото — с [Wikimedia Commons](https://commons.wikimedia.org/), уменьшены и пересжаты в WebP.",
        "Фото отелей — иллюстрации по типу отеля: отели в демо синтетические.",
        "",
        "| Файл | Автор | Лицензия | Источник |",
        "|---|---|---|---|",
    ]
    rows = [(f"dest/{k}.webp", v) for k, v in dest_credits.items()]
    rows += [(f"hotel/{i['file']}", i) for items in hotel_credits.values() for i in items]
    for file, item in rows:
        author = item["author"].replace("|", "/")
        license_cell = f"[{item['license']}]({item['license_url']})" if item["license_url"] else item["license"]
        lines.append(f"| `{file}` | {author} | {license_cell} | [{item['title']}]({item['source']}) |")
    (PUBLIC / "CREDITS.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
