"""Rozpoznávanie modelov – SAMOSTATNÁ kópia z Bazoš strážcu (nie je s ním prepojená).
Ceny v tabuľkách sa tu nepoužívajú, iba názvy modelov."""
import re

IPHONE = {
    "12": {128: 160, 256: 190}, "12 mini": {128: 150, 256: 170},
    "12 pro": {128: 210, 256: 230, 512: 250}, "12 pro max": {128: 260, 256: 290, 512: 310},
    "13": {128: 230, 256: 240, 512: 280}, "13 mini": {128: 240, 256: 255, 512: 280},
    "13 pro": {128: 320, 256: 330, 512: 360, 1024: 400}, "13 pro max": {128: 380, 256: 400, 512: 430, 1024: 460},
    "14": {128: 300, 256: 330, 512: 360}, "14 plus": {128: 300, 256: 325, 512: 350},
    "14 pro": {128: 390, 256: 400, 512: 430, 1024: 460}, "14 pro max": {128: 440, 256: 460, 512: 500, 1024: 530},
    "15": {128: 390, 256: 420, 512: 450}, "15 plus": {128: 440, 256: 480, 512: 510},
    "15 pro": {128: 505, 256: 540, 512: 580, 1024: 620}, "15 pro max": {256: 580, 512: 630, 1024: 680},
    "16e": {128: 420, 256: 470}, "16": {128: 550, 256: 600, 512: 650}, "16 plus": {128: 590, 256: 640, 512: 690},
    "16 pro": {128: 650, 256: 700, 512: 760, 1024: 820}, "16 pro max": {256: 770, 512: 830, 1024: 900},
    "17e": {128: 450, 256: 500},                       # marec 2026 (nové ~699 €)
    "17": {256: 760, 512: 860}, "air": {256: 700, 512: 800},
    "17 pro": {256: 950, 512: 1080}, "17 pro max": {256: 1080, 512: 1200},
    # iPhone 18 (jeseň 2026 – zatiaľ len Pro/Pro Max; nové v obchode 1489/1639 €)
    "18 pro": {256: 1270, 512: 1470, 1024: 1820}, "18 pro max": {256: 1460, 512: 1660, 1024: 2020},
}

OTHER = [
    # --- Mac mini / iMac (iba Apple Silicon M1–M4) ---
    (r"mac\s*mini.*\bm4\s*pro", "Mac mini M4 Pro", 950),
    (r"mac\s*mini.*\bm4\b", "Mac mini M4", 600),
    (r"mac\s*mini.*\bm2\s*pro", "Mac mini M2 Pro", 650),
    (r"mac\s*mini.*\bm2\b", "Mac mini M2", 400),
    (r"mac\s*mini.*\bm1\b", "Mac mini M1", 300),
    (r"\bimac\b.*\bm4\b", "iMac 24 M4", 1000),
    (r"\bimac\b.*\bm3\b", "iMac 24 M3", 850),
    (r"\bimac\b.*\bm1\b", "iMac 24 M1", 550),
    (r"macbook\s*neo", "MacBook Neo", 450),                       # marec 2026, lacný MacBook (nové 599 $)
    (r"macbook\s*air.*\bm5\b", "MacBook Air M5", 1125),          # nový v obchode od ~1288 €
    (r"macbook\s*air.*\bm4\b", "MacBook Air M4", 940),
    (r"macbook\s*air.*\bm3\b", "MacBook Air M3", 780),
    (r"macbook\s*air.*\bm2\b", "MacBook Air M2", 670),
    (r"macbook\s*air.*\bm1\b", "MacBook Air M1", 450),
    (r"macbook\s*pro.*\bm5\s*(pro|max)\b", "MacBook Pro M5 Pro/Max", 1900),
    (r"macbook\s*pro.*\bm5\b(?!\s*(pro|max))", "MacBook Pro 14 M5", 1700),
    (r"macbook\s*pro.*\bm1\s*(pro|max)\b", "MacBook Pro M1 Pro/Max", 950),
    (r"macbook\s*pro.*\bm[234]\s*(pro|max)\b", "MacBook Pro M2–M4 Pro/Max", 1375),
    (r"macbook\s*pro.*\bm4\b(?!\s*(pro|max))", "MacBook Pro 14 M4", 1100),
    (r"macbook\s*pro.*\bm3\b(?!\s*(pro|max))", "MacBook Pro 14 M3", 900),
    (r"macbook\s*pro.*\bm2\b", "MacBook Pro 13 M2", 700),
    (r"macbook\s*pro.*\bm1\b", "MacBook Pro 13 M1", 580),
    # Galaxy S26 (február 2026; nové 1000 / 1250 / 1450 €)
    (r"galaxy\s*s26\s*ultra|\bs26\s*ultra", "Galaxy S26 Ultra", 850),
    (r"\bs26\s*(\+|plus)", "Galaxy S26+", 650), (r"\bs26\s*fe\b", "Galaxy S26 FE", 520), (r"(galaxy\s*)?\bs26\b", "Galaxy S26", 560),
    (r"galaxy\s*s25\s*ultra|\bs25\s*ultra", "Galaxy S25 Ultra", 680),
    (r"galaxy\s*s24\s*ultra|\bs24\s*ultra", "Galaxy S24 Ultra", 600),
    (r"galaxy\s*s23\s*ultra|\bs23\s*ultra", "Galaxy S23 Ultra", 400),
    (r"\bs25\s*(\+|plus)", "Galaxy S25+", 600), (r"\bs25\s*fe\b", "Galaxy S25 FE", 420), (r"(galaxy\s*)?\bs25\b", "Galaxy S25", 520),
    (r"\bs24\s*(\+|plus)", "Galaxy S24+", 450), (r"\bs24\s*fe\b", "Galaxy S24 FE", 330), (r"(galaxy\s*)?\bs24\b", "Galaxy S24", 330),
    (r"\bs23\s*(\+|plus)", "Galaxy S23+", 330), (r"\bs23\s*fe\b", "Galaxy S23 FE", 230), (r"(galaxy\s*)?\bs23\b", "Galaxy S23", 260),
    # Fold8 / Flip8 (august 2026)
    (r"fold\s*8\s*ultra", "Galaxy Z Fold 8 Ultra", 1400),
    (r"z\s*fold\s*8|fold\s*8", "Galaxy Z Fold 8", 1200),
    (r"z\s*flip\s*8|flip\s*8", "Galaxy Z Flip 8", 650),
    (r"z\s*fold\s*7|fold\s*7", "Galaxy Z Fold 7", 900),
    (r"z\s*fold\s*6|fold\s*6", "Galaxy Z Fold 6", 600),
    (r"z\s*fold\s*5|fold\s*5", "Galaxy Z Fold 5", 450),
    (r"z\s*flip\s*7|flip\s*7", "Galaxy Z Flip 7", 560),
    (r"z\s*flip\s*6|flip\s*6", "Galaxy Z Flip 6", 370),
    (r"z\s*flip\s*5|flip\s*5", "Galaxy Z Flip 5", 250),
    (r"watch\s*ultra\s*4(?!\d)", "Apple Watch Ultra 4", 650),            # september 2026
    (r"watch\s*ultra\s*3(?!\d)", "Apple Watch Ultra 3", 445),
    (r"watch\s*ultra\s*2(?!\d)", "Apple Watch Ultra 2", 390),
    (r"apple\s*watch\s*ultra|watch\s*ultra\s*1", "Apple Watch Ultra", 265),
    (r"(?s)^(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*(series\s*)?12\b", "Apple Watch Series 12", 330),
    (r"(?s)^(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*(series\s*)?11\b", "Apple Watch Series 11", 300),
    (r"(?s)^(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*(series\s*)?10\b", "Apple Watch Series 10", 250),
    (r"(?s)^(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*(series\s*)?9\b", "Apple Watch Series 9", 190),
    (r"(?s)^(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*(series\s*)?8\b", "Apple Watch Series 8", 135),
    (r"(?s)^(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*se\b", "Apple Watch SE", 110),
    # --- Garmin ---
    (r"f[eē]nix\s*9\s*pro", "Garmin Fenix 9 Pro", 900),           # august 2026
    (r"f[eē]nix\s*9", "Garmin Fenix 9", 750),
    (r"f[eē]nix\s*8", "Garmin Fenix 8", 650),
    (r"f[eē]nix\s*7\s*(x\s*)?pro", "Garmin Fenix 7 Pro", 450),
    (r"f[eē]nix\s*7\s*x", "Garmin Fenix 7X", 400),
    (r"f[eē]nix\s*7", "Garmin Fenix 7", 350),
    (r"epix\s*pro", "Garmin Epix Pro", 370), (r"\bepix\b", "Garmin Epix 2", 325),
    (r"forerunner\s*970", "Garmin Forerunner 970", 550), (r"forerunner\s*965", "Garmin Forerunner 965", 380),
    (r"forerunner\s*955", "Garmin Forerunner 955", 280), (r"forerunner\s*(265|570)", "Garmin Forerunner 265/570", 275),
    (r"forerunner\s*255", "Garmin Forerunner 255", 180),
    (r"venu\s*(3|x1)", "Garmin Venu 3/X1", 220), (r"instinct\s*(2x|3)", "Garmin Instinct 2X/3", 230),
    (r"airpods\s*pro\s*(2|3|ii)", "AirPods Pro 2/3", 120),
    (r"ipad\s*pro.*\bm[124]\b", "iPad Pro (M)", 550),
    (r"ipad\s*air.*\bm[123]\b", "iPad Air (M)", 380),
    (r"ps5\s*pro|playstation\s*5\s*pro", "PS5 Pro", 600),
]

MODEL_RE = re.compile(r"iph?one\s*(1[2-8])\s*(pro\s*max|pro|plus|mini|e)?\b|iphone\s*(17\s*)?air", re.I)

GB_RE = re.compile(r"\b(64|128|256|512)\s?gb|\b(1)\s?tb", re.I)

_NORM = [(re.compile(r"\b(?:i|aj|ay)\s+ph?one\b", re.I), "iphone"), (re.compile(r"\bip?hone(?=\d)", re.I), "iphone "),
         (re.compile(r"\bmac\s+book\b", re.I), "macbook"), (re.compile(r"\bplay\s+station\b", re.I), "playstation"),
         (re.compile(r"\bmac\s*book(?=air|pro)", re.I), "macbook "), (re.compile(r"\bapple\s*watch(?=\d)", re.I), "apple watch ")]

_IPH_FALLBACK = re.compile(r"(?:iphone|model)\D{0,20}?\b(1[2-8])\s*(pro\s*max|pro|plus|mini|e)?\b", re.I)

OTHER_BRAND = re.compile(r"\b(honor|huawei|xiaomi|redmi|poco|oppo|oneplus|one\s*plus|vivo|realme|motorola|moto\s*g|"
                         r"pixel|nothing\s*phone|lenovo|asus|zte|nokia|sony\s*xperia|tcl|infinix|tecno|ulefone|doogee)\b", re.I)

OUR_BRAND = re.compile(r"iphone|apple|macbook|samsung|galaxy|playstation|ps5|xbox|nintendo|steam\s*deck|garmin|dji|airpods|ipad", re.I)

HARD_EXCLUDE = re.compile(
    r"(všetko|vsetko|vsetky|všetky)\s+(funguje\s+|funkčné\s+|ide\s+)?okrem|funguje\s+(všetko|vsetko)\s+okrem|"
    r"kúpim|kupim|vykúpim|výkup|icloud\s*(lock|zamk|blok)|zablokovan|na\s*diely|na\s*náhradné|"
    r"face\s*id\s*(nefung|nejde|nefunk)|nefunguje\s*face|nezapne|nezapína|(základn\w*\s*)?dosk\w*\s*(nefunk|odišl|zl[aá]|vadn|chyb)|"
    r"pod\s*vodou|vo\s*vode|vytopen|navlhn|ohnut|zabanovan|\bban\b|prevodom\s*vopred|krabica\s*od|iba\s*krabic", re.I)

TITLE_ACCESSORY = re.compile(r"^\W*(nov[ýéá]\s+|originál\w*\s+)?(obal|kryt|puzdr|púzdr|sklo|fólia|folia|nabíjač|nabijac|kábel|kabel|držiak|remienok)|"
                             r"\b(obal|kryt|puzdro|púzdro|sklo|fólia)\s+(na|pre|for)\b", re.I)

PHOTO_SCAM = re.compile(
    r"(predávam|predavam|prodávám|prodavam|sprzedaj\w*|selling|sell|verkaufe|vendo|vends?)\s+(len\s+|iba\s+|jen\s+|pouze\s+|tylko\s+|only\s+|nur\s+|solo\s+|seulement\s+)?"
    r"(the\s+|a\s+|an\s+|das\s+|ein\s+|la\s+|une?\s+)?(fotk|fotograf|obr[aá]z|zdj[eę]ci|photo|picture|pic\b|image|bild|foto)|"
    r"(len|iba|jen|pouze|tylko|only|nur|solo|seulement)\s+(the\s+|das\s+|la\s+)?(fotk|fotograf|obr[aá]z|zdj[eę]ci|photo|picture|bild|foto|krabic|pude[lł]k|box|karton|schachtel|scatola|bo[iî]te)|"
    r"\bnie\s+(je\s+)?telef[oó]n|nen[ií]\s+telefon|\bnie\s+telefon|not\s+(the\s+|a\s+)?(phone|device|iphone)|kein\s+(handy|telefon|iphone)|"
    r"non\s+(il\s+)?telefono|pas\s+(le\s+)?t[eé]l[eé]phone|no\s+(el\s+)?tel[eé]fono|"
    r"(fotk|fotograf|zdj[eę]ci|photo|picture|bild|foto)\w*\s+(telef[oó]n|telefonu|phone|iphone|handy)\w*\s*,?\s*(nie|not|nicht|non|pas|no)\b|"
    r"pr[aá]zdn\w*\s+krabic|pust\w*\s+pude[lł]k|empty\s+box|leere\s+(box|schachtel|verpackung)", re.I)

TITLE_PHOTO = re.compile(
    r"^\W*(foto|fotka|fotku|fotografi\w*|zdj[eę]ci\w*|photo|picture|bild|obr[aá]z\w*|image)\b|"
    r"(značka|znacka|brand|marka):\s*(zdj[eę]ci\w*|foto\w*|photo|picture|obr[aá]z\w*|bild)\b", re.I)

ACCESSORY = re.compile(
    # nadpis ZAČÍNA príslušenstvom ("Batéria DJI Mini 3", "Stojan na Mac mini")
    r"^\W*(predám|predam|nová|nový|nove|original\w*)?\s*(batéri|bateri|vrtul|nabíja|nabija|filtr|filter|držiak|drziak|stojan|"
    r"hub\b|adaptér|adapter|kábel|kabel|klávesnic|klavesnic|myš|mys\b|chladič|chladic|kryt|obal|puzdr|taška|taska|ovládač|ovladac|rc\b|"
    r"remien|náramok|naramok|sklo|sklíčk|fóli|foli|ochrann|goggles|okuliar|motion\s*controller|rc\s*motion)"
    # príslušenstvo "na/pre" zariadenie, celé počítače/notebooky, výmeny a dopyty
    r"|\b(na|pre|for|do)\s+(dji|mac|imac|rtx|rx|grafik|apple|watch|garmin|galaxy|samsung|s2\d|fenix|forerunner|avata|mavic)|\bpc\b|počítač|pocitac|zostav|notebook|laptop|"
    r"vymením\s+za|hľadám|hladam", re.I)

CONSOLE_VALUES = {
    "dualsense_edge": ("DualSense Edge", 150),
    "dualsense": ("Ovládač DualSense", 48),
    "ps5_pro": ("PS5 Pro", 650),
    "ps5_slim_digital": ("PS5 Slim Digital", 470),
    "ps5_slim": ("PS5 Slim s mechanikou", 510),
    "ps5_digital": ("PS5 Digital", 400),
    "ps5": ("PS5 s mechanikou", 450),
    "deck_oled_1tb": ("Steam Deck OLED 1TB", 615),
    "deck_oled": ("Steam Deck OLED 512GB", 515),
    "deck_lcd_512": ("Steam Deck LCD 512GB", 340),
    "deck_lcd": ("Steam Deck LCD", 300),
    "switch2": ("Nintendo Switch 2", 400),
    "switch_oled": ("Nintendo Switch OLED", 240),
    "xbox_x_digital": ("Xbox Series X Digital", 280),
    "xbox_x": ("Xbox Series X", 320),
}

CONSOLE_JUNK = re.compile(
    r"portal|\bvr2?\b|psvr|headset|slúchad|sluchad|volant|stojan|nabíj|nabij|\bdok\b|dock|skin|cover|"
    r"kábel|kabel|chladen|vymením\s+za|hľadám|hladam|\b(na|pre|for)\s+(ps\s?5|playstation|switch|steam|xbox)|"
    # Vinted (PL/CZ/EN): volanty, disky, panely, kamery, slúchadlá, nabíjačky…
    r"kierownic|\bwheel|thrustmaster|logitech|\bg29\b|\bg92[03]\b|\bt300|\bt248|pedał|pedal|shifter|"
    r"dysk|\bssd\b|nvme|panel|osłon|oslon|obudow|naklejk|kamera|camera|słuchawk|sluchawk|ładowark|ladowark|stacja|"
    r"\bdo\s+(ps\s?5|playstation|konsol)", re.I)

GAMES = re.compile(r"\bhr(a|y|u|e|ou|ami)\b|\bhier\b|\bgames?\b|\bcd\b|\bdlc\b|\bkód\b|\bkod\b|"
                   r"\bgr(a|y|ę)\b|\bgier\b|edycj|edition|collector|kolekcjon|steelbook|\bpl\s*ps|nowa\s+foli", re.I)

GAME_DESC = re.compile(r"^\W*(predám|predam|ponúkam|ponukam)?\s*(hru|hry|hra)\b|\bhr(u|a)\s+(na|pre)\s+(ps|playstation|switch|nintendo)", re.I)

BUNDLE = re.compile(r"\+|konzol|\bs\s+hr|\ba\s+hr|\bplus\b", re.I)

def console_estimate(title):
    t = title.lower()
    if CONSOLE_JUNK.search(t) or (GAMES.search(t) and not BUNDLE.search(t)):
        return None
    is_pad = re.search(r"dualsense|ovl[aá]d[aá][cč]|gamepad|joystick|\bpad\b|kontroler|controller|scuf", t)
    is_console = re.search(r"\+|konzol|xbox\s*series|ps5\s*(slim|pro|digital|disc)|playstation\s*5\s*(slim|pro|digital|disc)|"
                           r"\b(825|1)\s?(gb|tb)\b", t)
    if is_pad and not is_console:
        key = "dualsense_edge" if "edge" in t else ("dualsense" if re.search(r"dualsense|ps5|playstation", t) else None)
        return CONSOLE_VALUES[key] if key else None
    if re.search(r"ps\s?5|playstation\s*5", t):
        if re.search(r"\bpro\b", t):
            return CONSOLE_VALUES["ps5_pro"]
        digital = re.search(r"digit", t)
        if "slim" in t:
            return CONSOLE_VALUES["ps5_slim_digital" if digital else "ps5_slim"]
        return CONSOLE_VALUES["ps5_digital" if digital else "ps5"]
    if "steam deck" in t or "steamdeck" in t:
        if "oled" in t:
            return CONSOLE_VALUES["deck_oled_1tb" if re.search(r"\b1\s?tb", t) else "deck_oled"]
        return CONSOLE_VALUES["deck_lcd_512" if "512" in t else "deck_lcd"]
    if re.search(r"xbox\s*series\s*x\b|\bxsx\b", t) and not re.search(r"series\s*s\b|x\s*[/|-]\s*s\b", t) \
            and not re.match(r"\W*(predám\s+|predam\s+|nový\s+|novy\s+)?(ovl[aá]d[aá][cč]|gamepad|joystick)", t):
        return CONSOLE_VALUES["xbox_x_digital" if re.search(r"digit", t) else "xbox_x"]
    if "switch" in t and re.search(r"nintendo|switch\s*(oled|2)\b", t):
        if re.search(r"switch\s*2\b", t):
            return CONSOLE_VALUES["switch2"]
        if "oled" in t:
            return CONSOLE_VALUES["switch_oled"]
    return None
