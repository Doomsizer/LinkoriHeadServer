from urllib.parse import unquote, urlparse

PRIORITY_COUNTRIES: dict[str, int] = {
    "NL": 1,
    "DE": 2,
    "SE": 3,
    "FI": 4,
    "LV": 5,
}

SECONDARY_COUNTRIES: set[str] = {
    "PL",
    "EE",
    "LT",
    "FR",
    "GB",
    "CH",
    "AT",
    "CZ",
    "NO",
    "DK",
    "ES",
    "IT",
    "IE",
    "BE",
    "LU",
    "RO",
    "MD",
    "BG",
    "HU",
    "SK",
    "SI",
    "PT",
    "GR",
    "IS",
    "US",
    "CA",
}

COUNTRY_NAMES_RU: dict[str, str] = {
    "NL": "Нидерланды",
    "DE": "Германия",
    "SE": "Швеция",
    "FI": "Финляндия",
    "LV": "Латвия",
    "PL": "Польша",
    "EE": "Эстония",
    "LT": "Литва",
    "FR": "Франция",
    "GB": "Великобритания",
    "CH": "Швейцария",
    "AT": "Австрия",
    "CZ": "Чехия",
    "NO": "Норвегия",
    "DK": "Дания",
    "ES": "Испания",
    "IT": "Италия",
    "IE": "Ирландия",
    "BE": "Бельгия",
    "LU": "Люксембург",
    "RO": "Румыния",
    "MD": "Молдова",
    "BG": "Болгария",
    "HU": "Венгрия",
    "SK": "Словакия",
    "SI": "Словения",
    "PT": "Португалия",
    "GR": "Греция",
    "IS": "Исландия",
    "US": "США",
    "CA": "Канада",
    "BR": "Бразилия",
    "TR": "Турция",
    "JP": "Япония",
    "SG": "Сингапур",
    "AE": "ОАЭ",
    "IN": "Индия",
    "KZ": "Казахстан",
    "HK": "Гонконг",
    "KR": "Корея",
    "AR": "Аргентина",
    "AU": "Австралия",
    "UA": "Украина",
    "RU": "Россия",
}

COUNTRY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("NL", ("нидерланд", "голланди", "амстердам", "netherland", "holland", "amsterdam", "dutch")),
    ("DE", ("германи", "франкфурт", "берлин", "мюнхен", "нюрнберг", "german", "deutsch", "frankfurt", "berlin", "falkenstein", "nuremberg")),
    ("SE", ("швеци", "стокгольм", "sweden", "stockholm")),
    ("FI", ("финлянд", "хельсинки", "finland", "helsinki")),
    ("LV", ("латви", "рига", "latvia", "riga")),
    ("PL", ("польш", "варшав", "poland", "warsaw")),
    ("EE", ("эстони", "таллин", "estonia", "tallinn")),
    ("LT", ("литв", "вильнюс", "lithuania", "vilnius")),
    ("FR", ("франци", "париж", "france", "paris")),
    ("GB", ("великобритан", "англия", "лондон", "britain", "england", "london")),
    ("CH", ("швейцар", "цюрих", "switzerland", "zurich")),
    ("AT", ("австри", "вена", "austria", "vienna")),
    ("CZ", ("чехи", "прага", "czech", "prague")),
    ("NO", ("норвеги", "осло", "norway", "oslo")),
    ("DK", ("дани", "копенгаген", "denmark", "copenhagen")),
    ("ES", ("испани", "мадрид", "spain", "madrid")),
    ("IT", ("итали", "милан", "рим", "italy", "milan")),
    ("IE", ("ирланди", "дублин", "ireland", "dublin")),
    ("BE", ("бельги", "брюссель", "belgium", "brussels")),
    ("RO", ("румыни", "бухарест", "romania", "bucharest")),
    ("MD", ("молдов", "молдави", "кишинев", "moldova", "chisinau")),
    ("BG", ("болгари", "софия", "bulgaria", "sofia")),
    ("HU", ("венгри", "будапешт", "hungary", "budapest")),
    ("US", ("сша", "америк", "нью-йорк", "united states", "usa", "ashburn", "dallas", "new york", "los angeles")),
    ("CA", ("канад", "торонто", "canada", "toronto")),
    ("BR", ("бразили", "сан-паулу", "brazil", "sao paulo")),
    ("TR", ("турци", "стамбул", "turkey", "istanbul")),
    ("JP", ("япони", "токио", "japan", "tokyo")),
    ("SG", ("сингапур", "singapore")),
    ("AE", ("оаэ", "дубай", "dubai", "uae")),
    ("IN", ("инди", "мумбаи", "india", "mumbai")),
    ("KZ", ("казахстан", "алматы", "kazakhstan")),
    ("HK", ("гонконг", "hong kong", "hongkong")),
    ("KR", ("корея", "сеул", "korea", "seoul")),
    ("AR", ("аргентин", "argentina")),
    ("AU", ("австрали", "сидней", "australia", "sydney")),
)

KNOWN_ISO_CODES: set[str] = (
    set(PRIORITY_COUNTRIES.keys())
    | SECONDARY_COUNTRIES
    | set(COUNTRY_NAMES_RU.keys())
)


def _extract_flag_iso(text: str) -> str:
    chars = list(text)
    for i in range(len(chars) - 1):
        c1, c2 = ord(chars[i]), ord(chars[i + 1])
        if 0x1F1E6 <= c1 <= 0x1F1FF and 0x1F1E6 <= c2 <= 0x1F1FF:
            return chr(ord("A") + (c1 - 0x1F1E6)) + chr(ord("A") + (c2 - 0x1F1E6))
    return ""


def iso_to_flag_emoji(country_code: str) -> str:
    code = (country_code or "").upper().strip()
    if len(code) != 2 or not code.isalpha() or code == "ZZ":
        return "🌐"
    return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))


def get_country_display(country_code: str) -> str:
    code = (country_code or "").upper().strip()
    if not code or code == "ZZ":
        return "🌐 Прочие"
    flag = iso_to_flag_emoji(code)
    name = COUNTRY_NAMES_RU.get(code, code)
    return f"{flag} {name}"


def detect_country_code(uri: str) -> str:
    parsed = urlparse(uri.strip())
    remark = unquote(parsed.fragment or "")
    host = (parsed.hostname or "").lower()

    flag_code = _extract_flag_iso(remark)
    if flag_code:
        return flag_code

    remark_lower = remark.lower()
    for code, keywords in COUNTRY_KEYWORDS:
        if any(kw in remark_lower for kw in keywords):
            return code

    tokens = [
        t.strip("[](){}|:-_., ")
        for t in remark.replace("-", " ").replace("_", " ").split()
    ]
    for token in tokens:
        up = token.upper()
        if len(up) == 2 and up in KNOWN_ISO_CODES:
            return up

    host_parts = host.split(".")
    for part in host_parts:
        up = part.upper()
        if len(up) == 2 and up in KNOWN_ISO_CODES and part != host_parts[-1]:
            return up
    if host_parts and len(host_parts[-1]) == 2 and host_parts[-1].upper() in KNOWN_ISO_CODES:
        return host_parts[-1].upper()

    return ""


def get_country_rank(country_code: str) -> tuple[int, int, str]:
    code = (country_code or "").upper().strip()
    if code in PRIORITY_COUNTRIES:
        return (0, PRIORITY_COUNTRIES[code], code)
    if code in SECONDARY_COUNTRIES:
        return (1, 10, code)
    if code and code != "ZZ":
        return (2, 50, code)
    return (2, 99, "ZZ")


def extract_origin_bucket(origin_source: str, uri: str) -> str:
    cleaned = (origin_source or "").strip().lower()
    if cleaned:
        return cleaned
    parsed = urlparse(uri.strip())
    host = (parsed.hostname or "").lower()
    parts = host.split(".")
    if len(parts) >= 2 and not host.replace(".", "").isdigit():
        return ".".join(parts[-2:])
    return host or "unknown"