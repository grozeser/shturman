// Сгенерировано scripts/fetch_photos.py — не править руками.
// Фото с Wikimedia Commons под свободными лицензиями; автор и лицензия показываются на фото.
export interface PhotoCredit {
    author: string;
    license: string;
    source: string;
}

export const DEST_PHOTOS: Record<string, PhotoCredit> = {
    "sochi": {
        "author": "Arne Müseler",
        "license": "CC BY-SA 3.0 de",
        "source": "https://commons.wikimedia.org/wiki/File:Sochi_adler_aerial_view_2018_23.jpg"
    },
    "krasnaya_polyana": {
        "author": "Alexander Novikov",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Roza-Hutor-009.jpg"
    },
    "anapa": {
        "author": "Max071086",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Anapa_beach.jpg"
    },
    "gelendzhik": {
        "author": "Alexxx1979",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Gelendzhik_IMG_6723_1725.jpg"
    },
    "yalta": {
        "author": "Marcin Konsek",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Widok_na_Ja%C5%82t%C4%99_ze_statku_04.JPG"
    },
    "kaliningrad": {
        "author": "Anton Zelenov",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Kaliningrad_fishing_village.jpg"
    },
    "spb": {
        "author": "Wolfgang Moroder",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Palace_of_Peter_II_Neva_Saint_Petersburg.jpg"
    },
    "moscow": {
        "author": "Diego Delso",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Vista_general_del_Kremlin,_Mosc%C3%BA,_Rusia,_2016-10-03,_DD_18-19_HDR.jpg"
    },
    "kazan": {
        "author": "Alexxx1979",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Kazan_Kremlin._Spasskaya_Tower_P8111872_2200.jpg"
    },
    "nizhny": {
        "author": "Florstein",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Dmitrovskaya_Tower_of_Nizhny_Novgorod_Kremlin.jpg"
    },
    "altai": {
        "author": "Alexandr frolov",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Lake_Akkul,_Altai_Republic,_Russia.jpg"
    },
    "baikal": {
        "author": "Vyacheslav Argenberg",
        "license": "CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Baikal,_Cape_Burhan,_Olkhon_Island,_Lake_Baikal,_Russia.jpg"
    },
    "dagestan": {
        "author": "Александр Байдуков",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:%D0%92%D0%B8%D0%B4_%D0%BD%D0%B0_%D0%BA%D0%B0%D0%BD%D1%8C%D0%BE%D0%BD_%D0%B8_%D1%80%D0%B5%D0%BA%D1%83_%D0%A1%D1%83%D0%BB%D0%B0%D0%BA_%D1%83_%D0%BF%D0%BE%D1%81%D0%B5%D0%BB%D0%BA%D0%B0_%D0%94%D1%83%D0%B1%D0%BA%D0%B8.jpg"
    },
    "kmv": {
        "author": "Anton Zelenov",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Cascading_staircase_Kislovodsk.jpg"
    },
    "elbrus": {
        "author": "Ted.ns",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:%D0%92%D0%B8%D0%B4_%D0%BD%D0%B0_%D0%AD%D0%BB%D1%8C%D0%B1%D1%80%D1%83%D1%81_%D0%BF%D0%BE_%D0%BF%D1%83%D1%82%D0%B8_%D0%B2_%D0%94%D0%B6%D0%B8%D0%BB%D1%8B-%D0%A1%D1%83.jpg"
    },
    "sheregesh": {
        "author": "Staselnik",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Sheregesh_09.jpg"
    },
    "karelia": {
        "author": "Александр Байдуков",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Severo-Priladozhsky_reserve._Ruskeala_waterfall_and_the_water_of_the_Tohmajoki_river.jpg"
    },
    "murmansk": {
        "author": "Dmitry A. Mottl",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Teriberka.jpg"
    },
    "kamchatka": {
        "author": "Козинцев",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:%D0%9A%D0%BE%D1%80%D1%8F%D0%BA%D1%81%D0%BA%D0%B8%D0%B9,_%D0%90%D0%B2%D0%B0%D1%87%D0%B8%D0%BD%D1%81%D0%BA%D0%B8%D0%B9,_%D0%9A%D0%BE%D0%B7%D0%B5%D0%BB%D1%8C%D1%81%D0%BA%D0%B8%D0%B9.jpg"
    },
    "vladivostok": {
        "author": "Alexxx1979",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Vladivostok_Zolotoy_Rog_Bay_P8050527_2200.jpg"
    },
    "suzdal": {
        "author": "Dmitry Makeev",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Suzdal._Church_of_the_Suzdal._Paraskeva_Pyatnitsa_Church_and_Resurrection_of_Christ.jpg"
    },
    "abkhazia": {
        "author": "Hons084",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:2014_Nowy_Aton,_Monaster_Nowy_Athos_(06).jpg"
    },
    "minsk": {
        "author": "Ludvig14",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Minsk_HolySpiritChurch_001_3673.jpg"
    },
    "antalya": {
        "author": "Bernard Gagnon",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Hadrian%27s_Gate,_Antalya_01.jpg"
    },
    "alanya": {
        "author": "kallerna",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Boat_in_Alanya.jpg"
    },
    "kemer": {
        "author": "Emin Başar ÖZDEMİR",
        "license": "CC BY 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Kemer_Antalya_T%C3%9CRK%C4%B0YE_-_panoramio_(11).jpg"
    },
    "bodrum": {
        "author": "Serhio Magpie",
        "license": "CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Bodrum_Castle_(2017).jpg"
    },
    "istanbul": {
        "author": "Arild Vågen",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Hagia_Sophia_Mars_2013.jpg"
    },
    "cappadocia": {
        "author": "Bernard Gagnon",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Hot_air_balloon_in_Cappadocia_02.jpg"
    },
    "dubai": {
        "author": "Laika ac",
        "license": "CC BY-SA 2.0",
        "source": "https://commons.wikimedia.org/wiki/File:Burj_Khalifa_(16260269606).jpg"
    },
    "rak": {
        "author": "Florian Kriechbaumer, Aristeas",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Mountains_of_Wadi_Shawka_denoised.jpg"
    },
    "hurghada": {
        "author": "kallerna",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Boats_near_Paradise_Island,_Hurghada.jpg"
    },
    "sharm": {
        "author": "Serhio Magpie",
        "license": "CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Gold_Beach_at_Ras_Um_Sid_Bay.jpg"
    },
    "phuket": {
        "author": "Anton Zelenov",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Banana_beach_Phuket_2017_-_05.jpg"
    },
    "pattaya": {
        "author": "iMahesh",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Boat_moving_towards_a_pier_in_Pattaya,_Thailand.jpg"
    },
    "samui": {
        "author": "Ruta Badina",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Pier_in_Bophut_village_in_Ko_Samui.jpg"
    },
    "bangkok": {
        "author": "Supanut Arunoprayote",
        "license": "CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Ubosot_of_Wat_Arun.jpg"
    },
    "nha_trang": {
        "author": "Christophe95",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Nha_Trang_Beach_10.jpg"
    },
    "phu_quoc": {
        "author": "Elmschrat",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Phu_Quoc_beach_01.jpg"
    },
    "bali": {
        "author": "Vyacheslav Argenberg",
        "license": "CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Rice_terraces,_Bali.jpg"
    },
    "maldives": {
        "author": "Martin Falbisoner",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Diamonds_Thudufushi_Beach_and_Water_Villas,_May_2017_-09.jpg"
    },
    "sri_lanka": {
        "author": "Satdeep Gill",
        "license": "CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Goyambokka_Beach,_Tangalle,_Sri_Lanka.jpg"
    },
    "goa": {
        "author": "Vyacheslav Argenberg",
        "license": "CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Anjuna_Beach,_Goa,_India,_Legendary_Curlies_beach_shack.jpg"
    },
    "sanya": {
        "author": "Steven Sun",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:%E4%B8%89%E4%BA%9A%E5%A4%AA%E9%98%B3%E6%B9%BE%E5%85%AC%E8%B7%AF%E6%97%81%E6%B5%B7%E6%BB%A9_20260115.jpg"
    },
    "tunisia": {
        "author": "Marc Ryckaert (MJJR)",
        "license": "CC BY 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Hammamet-Sud_beach_R02.jpg"
    },
    "budva": {
        "author": "Marcin Konsek",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Sveti_Stefan_(06).jpg"
    },
    "belgrade": {
        "author": "Petar Milošević",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Church_of_Saint_Sava_(Belgrade,_Serbia).jpg"
    },
    "tbilisi": {
        "author": "Vyacheslav Argenberg",
        "license": "CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Tbilisi,_Old_Tbilisi,_Kura_River_2,_Georgia.jpg"
    },
    "batumi": {
        "author": "Dmitry A. Mottl",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Batumi_sunset.jpg"
    },
    "gudauri": {
        "author": "rugbyxm",
        "license": "CC BY 2.0",
        "source": "https://commons.wikimedia.org/wiki/File:Gudauri_(10).jpg"
    },
    "yerevan": {
        "author": "Vyacheslav Argenberg",
        "license": "CC BY 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Mount_Ararat,_Ararat_Plain,_Armenia-Turkey_border,_Armenia.jpg"
    },
    "samarkand": {
        "author": "Bernard Gagnon",
        "license": "CC0",
        "source": "https://commons.wikimedia.org/wiki/File:Tilya-Kori_Madrasa_01.jpg"
    },
    "almaty": {
        "author": "Matti Blume",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Shymbulak,_Almaty_(P1180179).jpg"
    },
    "issyk_kul": {
        "author": "Bgag",
        "license": "CC0",
        "source": "https://commons.wikimedia.org/wiki/File:Lake_Issyk-Kul,_Kyrgyzstan.jpg"
    },
    "varadero": {
        "author": "J. Drevet",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Varaderobeach1.JPG"
    },
    "seychelles": {
        "author": "Tobias Alt, Tobi 87",
        "license": "CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Anse_Source_d%27Argent_3-La_Digue.jpg"
    },
    "mauritius": {
        "author": "dronepicr",
        "license": "CC BY 2.0",
        "source": "https://commons.wikimedia.org/wiki/File:Sunbathing_at_Le_Morne_Beach_in_Mauritius_(53697787846).jpg"
    },
    "doha": {
        "author": "Sebbe xy",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Doha_skyline0001.JPG"
    },
    "langkawi": {
        "author": "CEphoto, Uwe Aranas",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Langkawi_Malaysia_Langkawi-Cable-Car-03.jpg"
    },
    "paris": {
        "author": "Jorge Royan",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Paris_-_The_Eiffel_Tower_in_spring_-_2307.jpg"
    },
    "rome": {
        "author": "Wilfredor",
        "license": "CC0",
        "source": "https://commons.wikimedia.org/wiki/File:Colosseum_of_Rome,_Italy.jpg"
    },
    "barcelona": {
        "author": "Jopparn",
        "license": "CC BY-SA 3.0",
        "source": "https://commons.wikimedia.org/wiki/File:Sagrada_Fam%C3%ADlia_2010.JPG"
    }
};

// Отели в демо синтетические — это иллюстрации по типу отеля, а не их фото
export const HOTEL_PHOTOS: Record<'resort' | 'city' | 'mountain', (PhotoCredit & { file: string })[]> = {
    "resort": [
        {
            "file": "resort-1.webp",
            "author": "Timothy A",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Ideal_Beach_Resort_Pool_Mahabalipuram_Sep22_R16_06310.jpg"
        },
        {
            "file": "resort-2.webp",
            "author": "Scotch Mist",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Bir%C5%A1tonas_03.jpg"
        },
        {
            "file": "resort-3.webp",
            "author": "CEphoto, Uwe Aranas",
            "license": "CC BY-SA 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Onna_Okinawa_ANA-InterContinental-Manza-Beach-Resort-01.jpg"
        },
        {
            "file": "resort-4.webp",
            "author": "Ximonic (Simo Räsänen)",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Marine_Club_Beach_Resort_Boavista,_Boa_Vista,_Cape_Verde,_2010_December.jpg"
        },
        {
            "file": "resort-5.webp",
            "author": "Martin Falbisoner",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Infinity_Pool_Lopesan_Costa_Meloneras,_May_2018.jpg"
        },
        {
            "file": "resort-6.webp",
            "author": "Dietmar Rabich",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Norderney,_Weststrand,_Hotel_--_2018_--_1050.jpg"
        },
        {
            "file": "resort-7.webp",
            "author": "iMahesh",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Promenade_Hotel_on_Puducheery_beach_road.jpg"
        },
        {
            "file": "resort-8.webp",
            "author": "Scotch Mist",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Sopot_2023_34_Beach_Bar.jpg"
        },
        {
            "file": "resort-9.webp",
            "author": "Photographer: Mosbatho",
            "license": "CC BY 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:The_Palms_Beach_Hotel_%26_Spa_in_Kuwait.jpg"
        },
        {
            "file": "resort-10.webp",
            "author": "Cayambe",
            "license": "CC BY-SA 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Sal_Sta_Maria_beach_hotel.jpg"
        },
        {
            "file": "resort-11.webp",
            "author": "Carter Lacey",
            "license": "CC BY 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Ocean_Village_Beach_Resort_in_Tofino_Canada_-_2026.jpg"
        },
        {
            "file": "resort-12.webp",
            "author": "Terragio67",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Livorno_-_Hotel_Palazzo_-_2025-09-29_20-09-38_001.jpg"
        },
        {
            "file": "resort-13.webp",
            "author": "Arild Vågen",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Villa_Fridhem_September_2021_08.jpg"
        },
        {
            "file": "resort-14.webp",
            "author": "Дмитрий Мозжухин",
            "license": "CC BY 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:%D0%9A%D0%B0%D1%80%D0%BB%D0%BE%D0%B2%D1%8B_%D0%92%D0%B0%D1%80%D1%8B_-_panoramio_(12).jpg"
        },
        {
            "file": "resort-15.webp",
            "author": "Aripeskoe2",
            "license": "CC BY 2.0",
            "source": "https://commons.wikimedia.org/wiki/File:Beach_Resort_and_Seaside_Resort_setting_at_Ada-Foah,_Greater_Accra.jpg"
        },
        {
            "file": "resort-16.webp",
            "author": "Thejas",
            "license": "CC BY 2.0",
            "source": "https://commons.wikimedia.org/wiki/File:Rio_Mar_Beach_Resort_in_R%C3%ADo_Grande,_Puerto_Rico.jpg"
        },
        {
            "file": "resort-17.webp",
            "author": "Alex Bertha alexbertha",
            "license": "CC0",
            "source": "https://commons.wikimedia.org/wiki/File:Endless_Water_(Unsplash).jpg"
        },
        {
            "file": "resort-18.webp",
            "author": "Marc Ryckaert",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Infinity_Pool_Jolie_Ville_Luxor_R01.jpg"
        },
        {
            "file": "resort-19.webp",
            "author": "Sharon Hahn Darlin",
            "license": "CC BY 2.0",
            "source": "https://commons.wikimedia.org/wiki/File:Golem,_Qarku_i_Tiran%C3%ABs_(Tirana_County),_Albania_-_Grand_Blue_Fafa_Resort,_7_January_2023_-_Pool_and_Palms_at_Sunset.jpg"
        },
        {
            "file": "resort-20.webp",
            "author": "KishujiRapid",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Seaside_Hotel_Maiko_Villa.jpg"
        },
        {
            "file": "resort-21.webp",
            "author": "Rob Young from United Kingdom",
            "license": "CC BY 2.0",
            "source": "https://commons.wikimedia.org/wiki/File:Chan-Kah_Resort_Village,_Bungalow_74_(8264845598).jpg"
        },
        {
            "file": "resort-22.webp",
            "author": "DANIEL JULIE from Paris, France",
            "license": "CC BY 2.0",
            "source": "https://commons.wikimedia.org/wiki/File:DSC0065_Huahin%C3%A9_Island_Traditional_Bungalow_in_the_Lapitas_Resort_(8105100211).jpg"
        },
        {
            "file": "resort-23.webp",
            "author": "Stefan Fussan",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:View_from_Ao_Luek_Panoramic_Pool_Villa,_Krabi,_Thailand_SF0003.jpg"
        },
        {
            "file": "resort-24.webp",
            "author": "Elliott Brown from Birmingham, United Kingdom",
            "license": "CC BY-SA 2.0",
            "source": "https://commons.wikimedia.org/wiki/File:Hotel_Don_Paco_-_Seville_-_sun_loungers_(14531120584).jpg"
        }
    ],
    "city": [
        {
            "file": "city-1.webp",
            "author": "Basile Morin",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Restaurant_room_of_Amantaka_luxury_Resort_%26_Hotel_in_Luang_Prabang_Laos.jpg"
        },
        {
            "file": "city-2.webp",
            "author": "Selbymay",
            "license": "CC BY-SA 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Tadoussac_-_Hotel_(1).jpg"
        },
        {
            "file": "city-3.webp",
            "author": "Basile Morin",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Hotel_3_Nagas_with_old_red_Citroen_at_blue_hour_in_Luang_Prabang.jpg"
        },
        {
            "file": "city-4.webp",
            "author": "Porto de Rinlo",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Hotel_y_restaurante_12.jpg"
        },
        {
            "file": "city-5.webp",
            "author": "Photograph by Mike Peel (www.mikepeel.net).",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:At_Berlin_2024_002.jpg"
        },
        {
            "file": "city-6.webp",
            "author": "PPR 19",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Premier_room,_The_Peninsula_Paris,_4_June_2014.jpg"
        },
        {
            "file": "city-7.webp",
            "author": "Another one of my pictures: This photograph was taken by Med",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Les_Pagodes_de_Beauval_-_474.jpg"
        },
        {
            "file": "city-8.webp",
            "author": "King of Hearts",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Conrad_Las_Vegas_at_Resorts_World_February_2023_HDR.jpg"
        },
        {
            "file": "city-9.webp",
            "author": "King of Hearts",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Yardarm_Motel_Searsport_October_2021_HDR.jpg"
        },
        {
            "file": "city-10.webp",
            "author": "Basile Morin",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Lobby_hall_with_couches_and_chandelier_at_The_Fullerton_Bay_Hotel_Singapore.jpg"
        },
        {
            "file": "city-11.webp",
            "author": "Basile Morin",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Lobby_of_the_hotel_Crowne_Plaza_Vientiane.jpg"
        },
        {
            "file": "city-12.webp",
            "author": "Ermell",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Kissingen_Hotel_Kaiserhof_Lobby_0417RM0371.jpg"
        },
        {
            "file": "city-13.webp",
            "author": "Wilfredor",
            "license": "CC0",
            "source": "https://commons.wikimedia.org/wiki/File:Frontenac_Hotel,_Quebec_ville,_downtown_007.jpg"
        },
        {
            "file": "city-14.webp",
            "author": "Johann Jaritz",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Velden_Seepromenade_3_Boutique_Hotel_23122023_0339.jpg"
        },
        {
            "file": "city-15.webp",
            "author": "Michielverbeek",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Mari%C3%A1nsk%C3%A9_L%C3%A1zn%C4%9B,_hotel_restaurant_Villa_Dino_IMG_3158_2022-08-09_10.06.jpg"
        },
        {
            "file": "city-16.webp",
            "author": "PPR 19",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:The_Peninsula_Paris%27_Chinese_restaurant_LiLi,_12_August_2014.jpg"
        },
        {
            "file": "city-17.webp",
            "author": "Wolfgang Moroder",
            "license": "CC BY-SA 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Editing_File-El_Tovar_Hotel_inside_staircase.JPG"
        },
        {
            "file": "city-18.webp",
            "author": "E bailey",
            "license": "CC0",
            "source": "https://commons.wikimedia.org/wiki/File:Hotel_La_Rose,_Santa_Rosa,_CA_Sept_6_2025.jpg"
        },
        {
            "file": "city-19.webp",
            "author": "Basile Morin",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Lounge_InterContinental_Singapore.jpg"
        },
        {
            "file": "city-20.webp",
            "author": "Subhrajyoti07",
            "license": "CC0",
            "source": "https://commons.wikimedia.org/wiki/File:Morgan_House_Kalimpong_3.jpg"
        },
        {
            "file": "city-21.webp",
            "author": "Ermell",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Gereuth_Schloss_G%C3%A4stezimmer-20190908-RM-114159.jpg"
        },
        {
            "file": "city-22.webp",
            "author": "Larry D. Moore",
            "license": "CC BY 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Aurora_apartment_hotel_san_antonio.jpg"
        },
        {
            "file": "city-23.webp",
            "author": "Dietmar Rabich",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Nottuln,_Hotel_Steverburg_--_2016_--_1486.jpg"
        },
        {
            "file": "city-24.webp",
            "author": "Mtaylor848",
            "license": "CC BY-SA 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Midland_Hotel,_Bradford.jpg"
        }
    ],
    "mountain": [
        {
            "file": "mountain-1.webp",
            "author": "Timothy A",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Rigyal_Hotel_Padum_Oct22_A7C_03737.jpg"
        },
        {
            "file": "mountain-2.webp",
            "author": "Subhrajyoti07",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Cherry_Resort_inside_Temi_Tea_Garden,_Namchi,_Sikkim.jpg"
        },
        {
            "file": "mountain-3.webp",
            "author": "Max_Ryazanov",
            "license": "CC BY-SA 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Hotel_il_muraglione.jpg"
        },
        {
            "file": "mountain-4.webp",
            "author": "Pudelek",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Hotel_Lu%C4%8Dn%C3%AD_bouda_(Wiesenbaude).jpg"
        },
        {
            "file": "mountain-5.webp",
            "author": "DimiTalen",
            "license": "CC0",
            "source": "https://commons.wikimedia.org/wiki/File:Ski_patrol_cabin,_Signal_de_l%27Homme,_Auris,_2026.jpg"
        },
        {
            "file": "mountain-6.webp",
            "author": "Sergei Kazantsev",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Rosa_Plato.jpg"
        },
        {
            "file": "mountain-7.webp",
            "author": "Johann Jaritz",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Albeck_Benesirnitz_6_Alpenbad_St_Leonhard_06052015_3259.jpg"
        },
        {
            "file": "mountain-8.webp",
            "author": "Michal Klajban",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Mountain_lodge_Tom%C4%8Deva_ko%C4%8Da,_Karawanks,_Slovenia.jpg"
        },
        {
            "file": "mountain-9.webp",
            "author": "Frankemann",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Skogadalsb%C3%B8en_mountain_lodge_in_Jotunheimen_National_Park.jpg"
        },
        {
            "file": "mountain-10.webp",
            "author": "Agnes Monkelbaan",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Lukmanierpass,_Passo_del_Lucomagno._20-09-2022._(actm.)_26.jpg"
        },
        {
            "file": "mountain-11.webp",
            "author": "Daniel Kraft",
            "license": "CC BY-SA 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Glecksteinh%C3%BCtte_tele_20200207_2.jpg"
        },
        {
            "file": "mountain-12.webp",
            "author": "Igor123121",
            "license": "CC BY 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Krynica-Zdroj,_Aleja_Leona_Nowotarskiego_i_widok_na_Bulwary_Dietla.jpg"
        },
        {
            "file": "mountain-13.webp",
            "author": "Wolfgang Moroder",
            "license": "CC BY-SA 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Mountain_hut_Ciadinat_S%C3%ABlva.jpg"
        },
        {
            "file": "mountain-14.webp",
            "author": "Daniel Kraft",
            "license": "CC BY-SA 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Aescher-Wildkirchli_20210528_01.jpg"
        },
        {
            "file": "mountain-15.webp",
            "author": "DimiTalen",
            "license": "CC0",
            "source": "https://commons.wikimedia.org/wiki/File:Remote_view_of_the_Villarais_area_from_the_Villard_slope,_Villard-Reculas,_2026.jpg"
        },
        {
            "file": "mountain-16.webp",
            "author": "Benjamin D. Esham (bdesham)",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Cabin_at_Allegany_State_Park.jpg"
        },
        {
            "file": "mountain-17.webp",
            "author": "DimiTalen",
            "license": "CC0",
            "source": "https://commons.wikimedia.org/wiki/File:View_of_Les_Menuires_and_Mont_Blanc_from_Pointe_de_la_Masse,_2022.jpg"
        },
        {
            "file": "mountain-18.webp",
            "author": "DimiTalen",
            "license": "CC0",
            "source": "https://commons.wikimedia.org/wiki/File:Grand_Reberty_and_Les_Bruy%C3%A8res_from_the_Paturages_slope_at_2090_m,_Les_Menuires.jpg"
        },
        {
            "file": "mountain-19.webp",
            "author": "DimiTalen",
            "license": "CC0",
            "source": "https://commons.wikimedia.org/wiki/File:Brelin_from_front_de_neige_La_Croisette,_Les_Menuires.jpg"
        },
        {
            "file": "mountain-20.webp",
            "author": "Isiwal",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Almsee_Fischerh%C3%BCtte-4167.jpg"
        },
        {
            "file": "mountain-21.webp",
            "author": "Arild Vågen",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:%C3%85hls_minnesg%C3%A5rd_May_2018_04.jpg"
        },
        {
            "file": "mountain-22.webp",
            "author": "August Geyler",
            "license": "CC BY-SA 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Hotel_Auersberg_Haus_im_Winter.jpg"
        },
        {
            "file": "mountain-23.webp",
            "author": "SkywalkerPL",
            "license": "CC BY 3.0",
            "source": "https://commons.wikimedia.org/wiki/File:Samotnia_lato2013_od_strony_Strzechy.jpg"
        },
        {
            "file": "mountain-24.webp",
            "author": "Jakub Hałun",
            "license": "CC BY 4.0",
            "source": "https://commons.wikimedia.org/wiki/File:Schronisko_PTTK_Klimczok_w_Beskidzie_%C5%9Al%C4%85skim,_20251004_1107_4837.jpg"
        }
    ]
};
