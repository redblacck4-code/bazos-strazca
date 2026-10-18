#!/usr/bin/env python3
"""
Bazoš strážca – každých pár minút prejde nové inzeráty na Bazoši v okolí Prievidze,
odhadne zisk pri preflipovaní a pošle dobré kúsky do Telegramu.

Spúšťa sa raz (jeden prechod) – opakovanie rieši cron / GitHub Actions.
Premenné prostredia:
  TELEGRAM_TOKEN    – token bota od @BotFather
  TELEGRAM_CHAT_ID  – tvoje chat ID (napr. cez @userinfobot)
  MIN_PROFIT        – minimálny odhadovaný zisk na upozornenie (default 60 €)
"""
import html as _html, json, os, random, re, sys, time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------- nastavenia
PSC = "97101"          # domov (Prievidza)
RADIUS_KM = 90         # (nepoužíva sa – hľadá sa po celom SK a filtruje podľa PSČ)
LOC = "hlokalita=&humkreis=&"   # celé Slovensko; výber oblastí robí funkcia region()
# Mimo domácej zóny (REGIONS):
BA_COST = int(os.getenv("BA_COST", "15"))        # elektronika z BA kraja – kúpia známi a pošlú (€)
POST_COST = int(os.getenv("POST_COST", "10"))    # elektronika zo zvyšku západu/stredu – poštou/Packetou (€)
CAR_BA_COST = 40       # auto z BA kraja – cesta vlakom tam, autom späť (€)
CAR_FAR_COST = 45      # auto zo zvyšku západu/stredu (€)
# Povolené PSČ (prvé 3 číslice) -> (oblasť, odhad nákladov na cestu tam a späť v €).
# Náklady na cestu sa odpočítajú zo zisku. Východ Slovenska tu zámerne nie je.
REGIONS = {
    # do ~30 min – bez nákladov
    "971": ("Prievidza a okolie", 0), "972": ("Prievidza a okolie", 0),
    "958": ("Partizánske", 0), "957": ("Bánovce n. B.", 0),
    # ~40–50 min
    "965": ("Žiar n. Hronom", 10), "966": ("Žarnovica", 10), "967": ("Kremnica", 15),
    "955": ("Topoľčany", 15), "956": ("Topoľčany – okolie", 15),
    "038": ("Turčianske Teplice", 15), "039": ("Turčianske Teplice", 15),
    # ~1 h
    "949": ("Nitra", 25), "950": ("Nitra – okolie", 25), "951": ("Nitra – okolie", 25),
    "953": ("Zlaté Moravce", 20),
    "911": ("Trenčín", 25), "912": ("Trenčín – okolie", 25), "913": ("Trenčín – okolie", 25),
    "914": ("Trenč. Teplice / Nemšová", 25),
    "018": ("Dubnica / Nová Dubnica", 25), "019": ("Ilava", 25),
    "974": ("Banská Bystrica", 25), "975": ("Banská Bystrica – okolie", 25), "976": ("BB – okolie", 25),
    "960": ("Zvolen", 25), "961": ("Zvolen – okolie", 25), "962": ("Zvolen – okolie", 25),
    "036": ("Martin", 20),
    # ~1 h 10 – hraničné, kľudne zmaž
    "010": ("Žilina", 30), "011": ("Žilina", 30), "017": ("Považská Bystrica", 30), "020": ("Púchov", 30),
}
SECTIONS = ["mobil", "pc"]   # mobil.bazos.sk, pc.bazos.sk
PAGES = 3                    # koľko strán (po 20) prejsť v každej sekcii (celé SK, každé 2–3 min stačí)
MIN_PROFIT = int(os.getenv("MIN_PROFIT", "60"))
SELL_FACTOR = 0.93           # reálne predáš ~7 % pod bežnou inzerovanou cenou
STATE_FILE = Path(__file__).with_name("seen.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "sk-SK,sk;q=0.9"}

# ---------------------------------------------------- bežné ceny (Bazoš, €)
# Odhad ceny funkčného kusu v dobrom stave. Uprav podľa seba.
# iPhone: model -> {GB: cena}
IPHONE = {
    "12": {128: 160, 256: 190}, "12 mini": {128: 150, 256: 170},
    "12 pro": {128: 210, 256: 230, 512: 250}, "12 pro max": {128: 260, 256: 290, 512: 310},
    "13": {128: 230, 256: 260, 512: 300}, "13 mini": {128: 200, 256: 240, 512: 270},
    "13 pro": {128: 320, 256: 330, 512: 360, 1024: 400}, "13 pro max": {128: 380, 256: 400, 512: 430, 1024: 460},
    "14": {128: 300, 256: 330, 512: 360}, "14 plus": {128: 300, 256: 325, 512: 350},
    "14 pro": {128: 390, 256: 400, 512: 430, 1024: 460}, "14 pro max": {128: 440, 256: 460, 512: 500, 1024: 530},
    "15": {128: 390, 256: 420, 512: 450}, "15 plus": {128: 440, 256: 480, 512: 510},
    "15 pro": {128: 510, 256: 550, 512: 590, 1024: 630}, "15 pro max": {256: 610, 512: 660, 1024: 700},
    "16e": {128: 420, 256: 470}, "16": {128: 550, 256: 600, 512: 650}, "16 plus": {128: 590, 256: 640, 512: 690},
    "16 pro": {128: 650, 256: 700, 512: 760, 1024: 820}, "16 pro max": {256: 770, 512: 830, 1024: 900},
    "17": {256: 760, 512: 860}, "air": {256: 700, 512: 800},
    "17 pro": {256: 950, 512: 1080}, "17 pro max": {256: 1080, 512: 1200},
}
# Ostatné: (regex na nadpis+popis, názov, cena). Prvá zhoda vyhráva – špecifickejšie hore.
OTHER = [
    # --- Mac mini / iMac (iba Apple Silicon M1–M4) ---
    (r"mac\s*mini.*\bm4\s*pro", "Mac mini M4 Pro", 950),
    (r"mac\s*mini.*\bm4\b", "Mac mini M4", 500),
    (r"mac\s*mini.*\bm2\s*pro", "Mac mini M2 Pro", 650),
    (r"mac\s*mini.*\bm2\b", "Mac mini M2", 400),
    (r"mac\s*mini.*\bm1\b", "Mac mini M1", 300),
    (r"\bimac\b.*\bm4\b", "iMac 24 M4", 1000),
    (r"\bimac\b.*\bm3\b", "iMac 24 M3", 850),
    (r"\bimac\b.*\bm1\b", "iMac 24 M1", 550),
    # --- grafické karty RTX 50 a AMD RX ---
    (r"rtx\s*5090", "RTX 5090", 2000), (r"rtx\s*5080", "RTX 5080", 900),
    (r"rtx\s*5070\s*ti", "RTX 5070 Ti", 650), (r"rtx\s*5070", "RTX 5070", 450),
    (r"rx\s*9070\s*xt", "RX 9070 XT", 580), (r"rx\s*9070", "RX 9070", 500),
    (r"rx\s*7900\s*xtx", "RX 7900 XTX", 750), (r"rx\s*7900\s*xt\b", "RX 7900 XT", 550),
    (r"rx\s*7900\s*gre", "RX 7900 GRE", 450), (r"rx\s*7800\s*xt", "RX 7800 XT", 380),
    # --- drony DJI ---
    (r"(?=.*\bdji\b).*avata\s*2", "DJI Avata 2", 650),
    (r"(?=.*\bdji\b).*avata", "DJI Avata", 450),
    (r"(?=.*\bdji\b).*mavic\s*3\s*pro", "DJI Mavic 3 Pro", 1300),
    (r"(?=.*\bdji\b).*mavic\s*3", "DJI Mavic 3 / Classic", 900),
    (r"(?=.*\bdji\b).*air\s*2s", "DJI Air 2S", 450),
    (r"(?=.*\bdji\b).*mini\s*5\s*pro", "DJI Mini 5 Pro", 750),
    (r"(?=.*\bdji\b).*mini\s*(2|se)\b", "DJI Mini 2 / SE", 170),
    (r"(?=.*\bdji\b).*\bneo\b", "DJI Neo", 140),
    (r"(?=.*\bdji\b).*air\s*3s", "DJI Air 3S", 850),
    (r"(?=.*\bdji\b).*air\s*3\b", "DJI Air 3", 700),
    (r"(?=.*\bdji\b).*mini\s*4\s*pro", "DJI Mini 4 Pro", 600),
    (r"(?=.*\bdji\b).*mini\s*4\s*k", "DJI Mini 4K", 200),
    (r"(?=.*\bdji\b).*mini\s*3\s*pro", "DJI Mini 3 Pro", 400),
    (r"(?=.*\bdji\b).*mini\s*3\b", "DJI Mini 3", 280),
    (r"macbook\s*air.*\bm4\b", "MacBook Air M4", 850),
    (r"macbook\s*air.*\bm3\b", "MacBook Air M3", 720),
    (r"macbook\s*air.*\bm2\b", "MacBook Air M2", 560),
    (r"macbook\s*air.*\bm1\b", "MacBook Air M1", 420),
    (r"macbook\s*pro.*\bm1\s*(pro|max)\b", "MacBook Pro M1 Pro/Max", 950),
    (r"macbook\s*pro.*\bm[234]\s*(pro|max)\b", "MacBook Pro M2–M4 Pro/Max", 1300),
    (r"macbook\s*pro.*\bm4\b(?!\s*(pro|max))", "MacBook Pro 14 M4", 1250),
    (r"macbook\s*pro.*\bm3\b(?!\s*(pro|max))", "MacBook Pro 14 M3", 1000),
    (r"macbook\s*pro.*\bm2\b", "MacBook Pro 13 M2", 700),
    (r"macbook\s*pro.*\bm1\b", "MacBook Pro 13 M1", 580),
    (r"galaxy\s*s25\s*ultra|\bs25\s*ultra", "Galaxy S25 Ultra", 800),
    (r"galaxy\s*s24\s*ultra|\bs24\s*ultra", "Galaxy S24 Ultra", 600),
    (r"galaxy\s*s23\s*ultra|\bs23\s*ultra", "Galaxy S23 Ultra", 400),
    (r"\bs25\s*(\+|plus)", "Galaxy S25+", 600), (r"\bs25\s*fe\b", "Galaxy S25 FE", 420), (r"(galaxy\s*)?\bs25\b", "Galaxy S25", 520),
    (r"\bs24\s*(\+|plus)", "Galaxy S24+", 450), (r"\bs24\s*fe\b", "Galaxy S24 FE", 330), (r"(galaxy\s*)?\bs24\b", "Galaxy S24", 380),
    (r"\bs23\s*(\+|plus)", "Galaxy S23+", 330), (r"\bs23\s*fe\b", "Galaxy S23 FE", 220), (r"(galaxy\s*)?\bs23\b", "Galaxy S23", 260),
    (r"z\s*fold\s*7|fold\s*7", "Galaxy Z Fold 7", 900),
    (r"z\s*fold\s*6|fold\s*6", "Galaxy Z Fold 6", 600),
    (r"z\s*fold\s*5|fold\s*5", "Galaxy Z Fold 5", 450),
    (r"z\s*flip\s*7|flip\s*7", "Galaxy Z Flip 7", 650),
    (r"z\s*flip\s*6|flip\s*6", "Galaxy Z Flip 6", 450),
    (r"z\s*flip\s*5|flip\s*5", "Galaxy Z Flip 5", 330),
    (r"pixel\s*9\s*pro", "Pixel 9 Pro", 550),
    (r"xiaomi\s*15\s*t\s*pro", "Xiaomi 15T Pro", 450),
    (r"xiaomi\s*15\s*t\b", "Xiaomi 15T", 350),
    (r"watch\s*ultra\s*3", "Apple Watch Ultra 3", 650),
    (r"watch\s*ultra\s*2", "Apple Watch Ultra 2", 390),
    (r"apple\s*watch\s*ultra|watch\s*ultra\s*1", "Apple Watch Ultra", 300),
    (r"(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*(series\s*)?11\b", "Apple Watch Series 11", 300),
    (r"(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*(series\s*)?10\b", "Apple Watch Series 10", 250),
    (r"(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*(series\s*)?9\b", "Apple Watch Series 9", 190),
    (r"(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*(series\s*)?8\b", "Apple Watch Series 8", 150),
    (r"(?!.*(galaxy|samsung|huawei|xiaomi|amazfit|garmin)).*watch\s*se\b", "Apple Watch SE", 110),
    # --- Garmin ---
    (r"f[eē]nix\s*8", "Garmin Fenix 8", 650),
    (r"f[eē]nix\s*7\s*(x\s*)?pro", "Garmin Fenix 7 Pro", 450),
    (r"f[eē]nix\s*7\s*x", "Garmin Fenix 7X", 400),
    (r"f[eē]nix\s*7", "Garmin Fenix 7", 350),
    (r"epix\s*pro", "Garmin Epix Pro", 550), (r"\bepix\b", "Garmin Epix 2", 380),
    (r"forerunner\s*970", "Garmin Forerunner 970", 550), (r"forerunner\s*965", "Garmin Forerunner 965", 380),
    (r"forerunner\s*955", "Garmin Forerunner 955", 280), (r"forerunner\s*(265|570)", "Garmin Forerunner 265/570", 260),
    (r"forerunner\s*255", "Garmin Forerunner 255", 180),
    (r"venu\s*(3|x1)", "Garmin Venu 3/X1", 260), (r"instinct\s*(2x|3)", "Garmin Instinct 2X/3", 220),
    (r"airpods\s*pro\s*(2|3|ii)", "AirPods Pro 2/3", 120),
    (r"ipad\s*pro.*\bm[124]\b", "iPad Pro (M)", 550),
    (r"ipad\s*air.*\bm[123]\b", "iPad Air (M)", 380),
    (r"ps5\s*pro|playstation\s*5\s*pro", "PS5 Pro", 600),
    (r"rtx\s*4090", "RTX 4090", 1500), (r"rtx\s*4080", "RTX 4080", 800),
    (r"rtx\s*4070\s*ti", "RTX 4070 Ti", 550), (r"rtx\s*4070", "RTX 4070", 420),
    (r"rtx\s*3080", "RTX 3080", 350),
]

# Kúsky, ktoré vôbec neposielať
HARD_EXCLUDE = re.compile(
    r"kúpim|kupim|vykúpim|výkup|icloud\s*(lock|zamk|blok)|zablokovan|na\s*diely|na\s*náhradné|"
    r"face\s*id\s*(nefung|nejde|nefunk|nie)|nefunguje\s*face|nezapne|nezapína|doska|"
    r"vodou|vytopen|navlhn|ohnut|zabanovan|\bban\b|prevodom\s*vopred|krabica\s*od|iba\s*krabic|obal\b|kryt\b|puzdro", re.I)
# Odpočty za opravy (€)
DAMAGE = [
    (re.compile(r"(displej|obrazovk|lcd)[^.]{0,40}(rozbit|prask|pukn|poškod|čiar|nefunk)|"
                r"(rozbit|prask|pukn)\w*[^.]{0,25}(displej|obrazovk)", re.I), 110, "displej"),
    (re.compile(r"(zadn\w* skl|chrbt)[^.]{0,30}(rozbit|prask|pukn)|(rozbit|prask|pukn)\w*[^.]{0,25}zadn", re.I), 50, "zadné sklo"),
    (re.compile(r"neorigin|menen\w* displej|vymenen\w* displej|neznám\w* diel", re.I), 40, "neoriginálny diel"),
]
# ------------------------------------------------ konzoly a ovládače (€)
# Rozpoznávajú sa iba podľa NADPISU (v popise býva "+ 2 ovládače", "+ hry" a pod.)
CONSOLE_VALUES = {
    "dualsense_edge": ("DualSense Edge", 150),
    "dualsense": ("Ovládač DualSense", 45),
    "ps5_pro": ("PS5 Pro", 650),
    "ps5_slim_digital": ("PS5 Slim Digital", 400),
    "ps5_slim": ("PS5 Slim s mechanikou", 450),
    "ps5_digital": ("PS5 Digital", 350),
    "ps5": ("PS5 s mechanikou", 400),
    "deck_oled_1tb": ("Steam Deck OLED 1TB", 560),
    "deck_oled": ("Steam Deck OLED 512GB", 480),
    "deck_lcd_512": ("Steam Deck LCD 512GB", 340),
    "deck_lcd": ("Steam Deck LCD", 300),
    "switch2": ("Nintendo Switch 2", 400),
    "switch_oled": ("Nintendo Switch OLED", 240),
}
# Inzeráty, ktoré iba spomínajú konzolu (hry, príslušenstvo, PS Portal…)
CONSOLE_JUNK = re.compile(
    r"portal|\bvr2?\b|psvr|headset|slúchad|sluchad|volant|stojan|nabíj|nabij|\bdok\b|dock|skin|cover|"
    r"kábel|kabel|chladen|vymením\s+za|hľadám|hladam|\b(na|pre|for)\s+(ps\s?5|playstation|switch|steam)", re.I)
GAMES = re.compile(r"\bhr(a|y|u|e|ou|ami)\b|\bhier\b|\bgames?\b|\bcd\b|\bdlc\b|\bkód\b|\bkod\b", re.I)
CONSOLE_NAMES = {v[0] for v in CONSOLE_VALUES.values()}
GAME_DESC = re.compile(r"^\W*(predám|predam|ponúkam|ponukam)?\s*(hru|hry|hra)\b|\bhr(u|a)\s+(na|pre)\s+(ps|playstation|switch|nintendo)", re.I)


def too_cheap_console(name, value, price, text=""):
    """Konzola za zlomok ceny = takmer vždy hra/príslušenstvo, nie konzola."""
    if name not in CONSOLE_NAMES:
        return False
    return price < 0.4 * value or bool(GAME_DESC.search(text or ""))
BUNDLE = re.compile(r"\+|konzol|\bs\s+hr|\ba\s+hr|\bplus\b", re.I)
# Dedikované hľadania, aby sa konzoly nestratili medzi ostatnými inzerátmi
CONSOLE_SEARCHES = ["ps5", "playstation 5", "steam deck", "switch oled", "switch 2", "dualsense", "ovládač ps5"]
# Ďalšie cielené hľadania: (sekcia Bazoša, dotaz)
EXTRA_SEARCHES = [("mobil", "apple watch"), ("mobil", "garmin"), ("mobil", "galaxy s2"), ("pc", "macbook pro"), ("pc", "mac mini"), ("pc", "imac"), ("pc", "rtx 50"), ("pc", "rx 9070"), ("pc", "rx 7900"),
                  ("pc", "rx 7800"), ("foto", "dji"), ("pc", "dji")]
# Príslušenstvo – v NADPISE znamená, že to nie je samotné zariadenie
ACCESSORY = re.compile(
    # nadpis ZAČÍNA príslušenstvom ("Batéria DJI Mini 3", "Stojan na Mac mini")
    r"^\W*(predám|predam|nová|nový|nove|original\w*)?\s*(batéri|bateri|vrtul|nabíja|nabija|filtr|filter|držiak|drziak|stojan|"
    r"hub\b|adaptér|adapter|kábel|kabel|klávesnic|klavesnic|myš|mys\b|chladič|chladic|kryt|obal|puzdr|taška|taska|ovládač|ovladac|rc\b|"
    r"remien|náramok|naramok|sklo|sklíčk|fóli|foli|ochrann|goggles|okuliar|motion\s*controller|rc\s*motion)"
    # príslušenstvo "na/pre" zariadenie, celé počítače/notebooky, výmeny a dopyty
    r"|\b(na|pre|for|do)\s+(dji|mac|imac|rtx|rx|grafik|apple|watch|garmin|galaxy|samsung|s2\d|fenix|forerunner|avata|mavic)|\bpc\b|počítač|pocitac|zostav|notebook|laptop|"
    r"vymením\s+za|hľadám|hladam", re.I)


def is_accessory_or_bundle(name, title, price, value):
    """Pre Mac mini/iMac, grafiky a drony: vyradiť príslušenstvo, celé PC/notebooky a podozrivo lacné kusy."""
    if not any(k in name for k in ("Mac mini", "iMac", "RTX 50", "RX ", "DJI", "Apple Watch Series", "Apple Watch SE",
                                   "Garmin", "Galaxy S2", "MacBook Pro 14")):
        return False
    if ACCESSORY.search(title):
        return True
    return price < 0.35 * value


def console_estimate(title):
    t = title.lower()
    if CONSOLE_JUNK.search(t) or (GAMES.search(t) and not BUNDLE.search(t)):
        return None
    is_pad = re.search(r"dualsense|ovl[aá]d[aá][cč]|gamepad|joystick", t)
    is_console = re.search(r"\+|konzol|ps5\s*(slim|pro|digital|disc)|playstation\s*5\s*(slim|pro|digital|disc)|"
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
    if "switch" in t and re.search(r"nintendo|switch\s*(oled|2)\b", t):
        if re.search(r"switch\s*2\b", t):
            return CONSOLE_VALUES["switch2"]
        if "oled" in t:
            return CONSOLE_VALUES["switch_oled"]
    return None


def required_profit(value):
    """Lacné veci (ovládače) by 60 € nikdy nedosiahli – pre ne stačí ~30 % z ceny."""
    return min(MIN_PROFIT, max(15, round(value * 0.3)))


MODEL_RE = re.compile(r"iph?one\s*(1[2-7])\s*(pro\s*max|pro|plus|mini|e)?\b|iphone\s*(17\s*)?air", re.I)
GB_RE = re.compile(r"\b(64|128|256|512)\s?gb|\b(1)\s?tb", re.I)
BAT_RE = re.compile(r"(\d{2,3})\s?%")


# ------------------------------------------------------------------ helpers
_blocked_until = 0.0
COOLDOWN = 600            # pri zablokovaní Bazošom pauza 10 minút
_http = requests.Session()


def fetch(url):
    """Šetrné sťahovanie: krátka pauza pred každou požiadavkou, pri zablokovaní (403/429/503) dlhá pauza."""
    global _blocked_until
    if time.time() < _blocked_until:
        return None
    for attempt in range(2):
        time.sleep(1.2 + random.random())
        try:
            r = _http.get(url, headers=UA, timeout=20)
        except requests.RequestException as e:
            print(f"[!] sieť: {e.__class__.__name__}", file=sys.stderr)
            time.sleep(5)
            continue
        if r.status_code == 200:
            return r.text
        if r.status_code in (403, 429, 503):
            _blocked_until = time.time() + COOLDOWN
            print(f"[!] Bazoš brzdí (HTTP {r.status_code}) – pauza {COOLDOWN // 60} min", file=sys.stderr)
            return None
        print(f"[!] HTTP {r.status_code}: {url[:60]}", file=sys.stderr)
        time.sleep(3)
    return None


def parse_list(html, base):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for box in soup.select("div.inzeraty"):
        a = box.select_one("h2.nadpis a") or box.select_one("h2 a")
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"/inzerat/(\d+)/", href)
        if not m:
            continue
        price_txt = (box.select_one(".inzeratycena") or {}).get_text(" ", strip=True) if box.select_one(".inzeratycena") else ""
        price = int(re.sub(r"[^\d]", "", price_txt) or 0)
        loc = box.select_one(".inzeratylok")
        loc = re.sub(r"\s+", " ", loc.get_text(" ", strip=True)) if loc else ""
        popis = box.select_one(".popis")
        out.append({
            "id": m.group(1),
            "url": href if href.startswith("http") else base + href,
            "title": a.get_text(strip=True),
            "price": price,
            "loc": loc,
            "snippet": popis.get_text(" ", strip=True) if popis else "",
        })
    return out


def detail_text(url):
    html = fetch(url)
    if not html:
        return ""
    d = BeautifulSoup(html, "html.parser").select_one(".popisdetail")
    return re.sub(r"\s+", " ", d.get_text(" ", strip=True)) if d else ""


def region(loc):
    """Vráti (oblasť, náklady elektronika, náklady auto, režim) alebo None (východ SK / neznáme PSČ).
    režim: 'osobne' = domáca zóna, 'znami' = Bratislavský kraj (kúpia známi), 'posta' = zvyšok západu a stredu."""
    m = re.search(r"(\d{3})\s?\d{2}\s*$", loc)
    if not m:
        return None
    p3 = m.group(1)
    town = re.sub(r"\s*\d{3}\s?\d{2}\s*$", "", loc).strip() or p3
    if p3 in REGIONS:
        area, cost = REGIONS[p3]
        return area, cost, cost, "osobne"
    if p3[0] == "8" or p3 in ("900", "901", "902", "903"):          # Bratislavský kraj
        return town, BA_COST, CAR_BA_COST, "znami"
    if p3[0] == "9" or p3[:2] in ("01", "02", "03"):                 # zvyšok západu a stredu
        return town, POST_COST, CAR_FAR_COST, "posta"
    return None                                                      # východ (04x–09x)


def estimate(title, text):
    """Vráti (názov, bežná cena, poznámky) alebo None."""
    notes = []
    c = console_estimate(title)
    if c:
        return c[0], c[1], notes
    t = f"{title} {text}".lower()
    m = MODEL_RE.search(t)
    if m:
        if m.group(1):
            model = m.group(1) + (" " + re.sub(r"\s+", " ", m.group(2).lower()) if m.group(2) else "")
            model = model.replace("16 e", "16e")
        else:
            model = "air"
        prices = IPHONE.get(model)
        if not prices:
            return None
        g = GB_RE.search(t)
        gb = (1024 if g.group(2) else int(g.group(1))) if g else None
        if gb is None or gb not in prices:
            if gb is not None and gb < min(prices):
                return None          # 64 GB a pod – ignorujeme
            gb = min(prices)
            notes.append("GB neuvedené – rátam s najnižšou")
        pretty = model.replace("pro max", "Pro Max").replace("pro", "Pro").replace("plus", "Plus").replace("air", "Air")
        name = f"iPhone {pretty} {str(gb) + ' GB' if gb < 1024 else '1 TB'}"
        return name, prices[gb], notes
    for rx, name, value in OTHER:
        if re.search(rx, t, re.I):
            return name, value, notes
    return None


def evaluate(item, text):
    full = f"{item['title']} {text}"
    if HARD_EXCLUDE.search(full):
        return None
    est = estimate(item["title"], text)
    if not est:
        return None
    name, value, notes = est
    if too_cheap_console(name, value, item["price"], text):
        return None
    if is_accessory_or_bundle(name, item["title"], item["price"], value):
        return None
    repair = 0
    for rx, cost, label in DAMAGE:
        if rx.search(full):
            repair += cost
            notes.append(f"{label} (−{cost} €)")
    bats = [int(b) for b in BAT_RE.findall(full) if 50 <= int(b) <= 100]
    if bats and bats[0] < 85:
        repair += 30
        notes.append(f"batéria {bats[0]} % (−30 €)")
    elif bats:
        notes.append(f"batéria {bats[0]} %")
    if item["price"] < 0.35 * value:
        notes.append("⚠️ podozrivo lacné – over si to")
    profit = round(value * SELL_FACTOR - item["price"] - repair)
    return {"name": name, "value": value, "repair": repair, "profit": profit, "notes": notes}


SIGNATURE = os.getenv("SELLER_NAME", "Andrej")


def offer_price(price):
    """Ponuka ~10 % pod cenou, zaokrúhlená na 5 €."""
    return max(5, int(round(price * 0.9 / 5.0)) * 5)


def seller_questions(name, text):
    """Otázky presne podľa typu zariadenia; vynechá to, čo už je v popise."""
    t = text.lower()
    n = name.lower()
    has_bat = bool(re.search(r"(\d{2,3})\s?%", t))
    q = []
    if n.startswith("iphone") or "ipad" in n:
        if not has_bat:
            q.append("aký je stav batérie v %")
        if "icloud" not in t:
            q.append("či je odhlásený z iCloudu")
        if n.startswith("iphone") and not re.search(r"face\s*id", t):
            q.append("či funguje Face ID")
        q.append("či nebol opravovaný (displej, batéria)")
    elif any(k in n for k in ("macbook", "mac mini", "imac")):
        if "macbook" in n and not re.search(r"cykl", t):
            q.append("koľko cyklov má batéria")
        q.append("či je odhlásené Apple ID a nie je na ňom firemný profil (MDM)")
    elif any(k in n for k in ("galaxy", "pixel", "xiaomi")):
        if not has_bat:
            q.append("v akom stave je batéria")
        q.append("či je odhlásený z Google účtu")
        q.append("či nebol opravovaný")
    elif "watch" in n:
        if not has_bat:
            q.append("aký je stav batérie")
        q.append("či sú odpojené od účtu")
    elif "garmin" in n:
        q.append("koľko dní vydrží batéria")
        q.append("či sú odpojené od Garmin Connect účtu")
    elif "airpods" in n:
        q.append("či sú originál a máte k nim doklad o kúpe")
    elif any(k in n for k in ("ps5", "steam deck", "switch", "dualsense")):
        if "dualsense" in n:
            q.append("či nemá drift páčok")
        else:
            q.append("či konzola nie je zabanovaná")
            q.append("či ovládače nemajú drift")
    elif "rtx" in n or n.startswith("rx "):
        q.append("či sa na nej ťažilo")
        q.append("či máte doklad o kúpe / platí ešte záruka")
    elif "dji" in n:
        q.append("či mal dron niekedy pád")
        q.append("či je odpojený od DJI účtu")
        q.append("koľko má batérií a cyklov")
    else:
        q.append("či je všetko plne funkčné")
    return q


def seller_message(item, ev, text, mode="osobne"):
    qs = seller_questions(ev["name"], text)
    if len(qs) > 1:
        q_txt = " Chcel by som sa spýtať, " + ", ".join(qs[:-1]) + " a " + qs[-1] + "."
    elif qs:
        q_txt = " Chcel by som sa spýtať, " + qs[0] + "."
    else:
        q_txt = ""
    return (f"Dobrý deň, mám záujem o {ev['name']} z Bazoša. Je inzerát ešte aktuálny?{q_txt} "
            + ("Viete ho poslať Packetou alebo na dobierku? Poštovné samozrejme zaplatím. "
               "Pred odoslaním by som poprosil o krátke video, že všetko funguje. "
               if mode == "posta" else "Viem prísť osobne a zaplatiť v hotovosti. ")
            + f"Za {offer_price(item['price'])} € by som to zobral hneď, dalo by sa? Ďakujem, {SIGNATURE}")


def send_telegram(msg, preview=True):
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print(msg + "\n---")
        return
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  data={"chat_id": chat, "text": msg, "parse_mode": "HTML",
                        "disable_web_page_preview": "false" if preview else "true"}, timeout=20)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# =====================================================================
#                              AUTÁ
# =====================================================================
# Pri autách nemá zmysel pevná cenovka – cena závisí od roku a km.
# Bot preto pre každý kandidát nájde podobné autá (rovnaký model, rok ±1)
# na celom Bazoši a porovná cenu s ich mediánom.
CARS_ON = os.getenv("CARS_ON", "1") == "1"
CAR_MIN_PRICE = int(os.getenv("CAR_MIN_PRICE", "1000"))
CAR_MAX_PRICE = int(os.getenv("CAR_MAX_PRICE", "8000"))
CAR_MIN_PROFIT = int(os.getenv("CAR_MIN_PROFIT", "500"))
CAR_MAX_KM = 280_000
CAR_PREP_COST = 300        # umytie/čistenie, drobnosti, prepis, STK/EK – paušál
CAR_SELL_FACTOR = 0.93     # reálne predáš ~7 % pod mediánom inzerátov
CAR_PAGES = 3
# Modely, ktoré sa na Slovensku dobre a rýchlo predávajú: (regex, dotaz na porovnanie, názov)
CAR_MODELS = [
    (r"(š|s)koda\s+octavia|\boctavia\b", "octavia", "Škoda Octavia"),
    (r"(š|s)koda\s+fabia|\bfabia\b", "fabia", "Škoda Fabia"),
    (r"(š|s)koda\s+superb|\bsuperb\b", "superb", "Škoda Superb"),
    (r"(š|s)koda\s+rapid|\brapid\b", "skoda rapid", "Škoda Rapid"),
    (r"(š|s)koda\s+yeti|\byeti\b", "skoda yeti", "Škoda Yeti"),
    (r"\b(vw|volkswagen)\s+golf|\bgolf\b", "golf", "VW Golf"),
    (r"\b(vw|volkswagen)\s+passat|\bpassat\b", "passat", "VW Passat"),
    (r"\b(vw|volkswagen)\s+polo\b", "vw polo", "VW Polo"),
    (r"toyota\s+yaris|\byaris\b", "yaris", "Toyota Yaris"),
    (r"toyota\s+auris|\bauris\b", "auris", "Toyota Auris"),
    (r"toyota\s+corolla|\bcorolla\b", "corolla", "Toyota Corolla"),
    (r"toyota\s+rav\s?4|\brav\s?4\b", "rav4", "Toyota RAV4"),
    (r"hyundai\s+i30|\bi30\b", "hyundai i30", "Hyundai i30"),
    (r"hyundai\s+i20|\bi20\b", "hyundai i20", "Hyundai i20"),
    (r"hyundai\s+(ix35|tucson)|\bix35\b|\btucson\b", "tucson", "Hyundai Tucson/ix35"),
    (r"kia\s+c'?ee'?d|\bc'?ee'?d\b", "kia ceed", "Kia Ceed"),
    (r"kia\s+sportage|\bsportage\b", "sportage", "Kia Sportage"),
    (r"ford\s+focus|\bfocus\b", "ford focus", "Ford Focus"),
    (r"dacia\s+duster|\bduster\b", "duster", "Dacia Duster"),
    (r"dacia\s+sandero|\bsandero\b", "sandero", "Dacia Sandero"),
    (r"suzuki\s+(vitara|sx4|swift)|\b(vitara|sx4)\b", "suzuki", "Suzuki Vitara/SX4/Swift"),
    (r"honda\s+(civic|jazz|cr-?v)|\b(civic|jazz)\b", "honda", "Honda Civic/Jazz/CR-V"),
    (r"mazda\s*(3|6|cx-?5)\b", "mazda", "Mazda 3/6/CX-5"),
]
CAR_BAD = re.compile(
    r"havarovan|havári|havari|búran|buran|na\s+diely|na\s+náhradné|nepojazd|nejazdi|bez\s+(stk|ek|tp|špz|spz)|"
    r"motor\s+(klepe|dymí|dymi|zadret|nejde|na\s+opravu)|prevodovk\w*\s+(nefung|na\s+opravu|vadn)|"
    r"leasing|odstúpim|odstupim|prenájom|prenajom|požičovň|kúpim|kupim|výkup|vykup|"
    r"vymením\s+za|vymenim\s+za|iba\s+výmena|zálohu|zalohu|dovoz\s+na\s+objednávku|bez\s+dokladov", re.I)
YEAR_RE = re.compile(r"\b(199\d|20[0-2]\d)\b")
KM_RE = re.compile(r"(\d{2,3})[\s.]?(\d{3})\s?km|(\d{2,3})\s?(tis\.?|tisíc|k)\s?km", re.I)
_comp_cache = {}


def car_model(text):
    t = text.lower()
    for rx, q, name in CAR_MODELS:
        if re.search(rx, t):
            return q, name
    return None


def car_year(text):
    ys = [int(y) for y in YEAR_RE.findall(text) if 1998 <= int(y) <= time.gmtime().tm_year]
    return ys[0] if ys else None


def car_km(text):
    m = KM_RE.search(text)
    if not m:
        return None
    if m.group(1):
        return int(m.group(1) + m.group(2))
    return int(m.group(3)) * 1000


def car_comps(query, year, own_id):
    """Ceny podobných áut (rok ±1) z celého Slovenska; medián a počet."""
    key = (query, year)
    if key not in _comp_cache:
        prices = []
        for off in ("", "20/", "40/"):
            html = fetch(f"https://auto.bazos.sk/{off}?hledat={requests.utils.quote(query)}&cenaod=500&cenado=60000")
            time.sleep(1)
            if not html:
                break
            for c in parse_list(html, "https://auto.bazos.sk"):
                txt = f"{c['title']} {c['snippet']}"
                y = car_year(txt)
                if c["id"] == own_id or not y or abs(y - year) > 1 or CAR_BAD.search(txt) or c["price"] < 500:
                    continue
                prices.append(c["price"])
        prices.sort()
        _comp_cache[key] = (prices[len(prices) // 2] if len(prices) >= 5 else None, len(prices))
    return _comp_cache[key]


def car_seller_message(it, name, year, km, text):
    t = text.lower()
    q = []
    if not re.search(r"servis", t):
        q.append("či má servisnú históriu")
    if not re.search(r"majiteľ|majitel", t):
        q.append("koľký ste majiteľ")
    if not re.search(r"\bstk\b|\bek\b", t):
        q.append("do kedy má STK a EK")
    q.append("či nebolo havarované a nemá koróziu")
    qtxt = (" Chcel by som sa spýtať, " + ", ".join(q[:-1]) + " a " + q[-1] + ".") if len(q) > 1 \
        else (" Chcel by som sa spýtať, " + q[0] + ".")
    offer = max(100, int(round(it["price"] * 0.9 / 50.0)) * 50)
    return (f"Dobrý deň, mám záujem o {name}{' ' + str(year) if year else ''} z Bazoša. Je inzerát ešte aktuálny?{qtxt} "
            f"Mohli by ste mi poslať VIN, aby som si overil históriu a km? Viem prísť osobne na obhliadku a skúšobnú jazdu. "
            f"Pri dohode by som za {offer} € kupoval hneď. Ďakujem, {SIGNATURE}")


def process_cars(state):
    if not CARS_ON:
        return 0
    alerts = 0
    base = "https://auto.bazos.sk"
    for page in range(CAR_PAGES):
        off = f"{page * 20}/" if page else ""
        html = fetch(f"{base}/{off}?hledat=&{LOC}cenaod={CAR_MIN_PRICE}&cenado={CAR_MAX_PRICE}")
        if not html:
            if time.time() >= _blocked_until:
                print(f"[!] auto strana {page} sa nenačítala", file=sys.stderr)
            break
        for it in parse_list(html, base):
            prev = state.get(it["id"])
            if prev is not None and it["price"] >= prev:
                continue
            state[it["id"]] = it["price"]
            reg = region(it["loc"])
            if not reg or not (CAR_MIN_PRICE <= it["price"] <= CAR_MAX_PRICE):
                continue
            area, _, travel, mode = reg
            head = f"{it['title']} {it['snippet']}"
            mdl = car_model(it["title"]) or car_model(head)
            if not mdl or CAR_BAD.search(head):
                continue
            text = detail_text(it["url"]) or it["snippet"]
            time.sleep(1)
            full = f"{it['title']} {text}"
            if CAR_BAD.search(full):
                continue
            year = car_year(it["title"]) or car_year(full)
            if not year:
                continue
            km = car_km(full)
            if km and km > CAR_MAX_KM:
                continue
            median, n = car_comps(mdl[0], year, it["id"])
            if not median or it["price"] > 0.85 * median:
                continue
            profit = round(median * CAR_SELL_FACTOR - it["price"] - CAR_PREP_COST - travel)
            if profit < CAR_MIN_PROFIT:
                continue
            notes = [f"porovnané s {n} inzerátmi ({year}±1)", f"príprava −{CAR_PREP_COST} €"]
            if travel:
                notes.append(f"{'🤝 BA – ' if mode == 'znami' else 'cesta: '}{area} (−{travel} €)")
            if not km:
                notes.append("km neuvedené")
            if it["price"] < 0.55 * median:
                notes.append("⚠️ podozrivo lacné – over VIN, nikdy neplať zálohu vopred")
            drop = f" (zlacnené z {prev} €)" if prev else ""
            km_txt = (", " + f"{km:,}".replace(",", " ") + " km") if km else ""
            msg = (f"🚗 <b>{esc(mdl[1])} {year}{km_txt}</b> – <b>{it['price']} €</b>{drop}\n"
                   f"Zisk ~<b>{profit} €</b> (podobné ~{median} €) · 📍 {esc(it['loc'])}\n"
                   f"ℹ️ {esc('; '.join(notes))}\n"
                   f"🔗 <a href=\"{it['url']}\">Otvoriť inzerát</a>")
            send_telegram(msg)
            send_telegram(f"<code>{esc(car_seller_message(it, mdl[1], year, km, text))}</code>", preview=False)
            alerts += 1
        time.sleep(1.5)
    return alerts


# =====================================================================
#                              VINTED
# =====================================================================
# Vinted sa kontroluje zriedkavo (predvolene ~každých 20 min), aby nás neblokoval.
VINTED_ON = os.getenv("VINTED_ON", "1") == "1"
VINTED_EVERY = int(os.getenv("VINTED_EVERY", "15"))   # každý N-tý beh (pri intervale 120 s = ~30 min)
VINTED_SHIP = int(os.getenv("VINTED_SHIP", "8"))      # poštovné odhadom (SK/CZ/PL) €
VINTED_BASE = "https://www.vinted.sk"
VINTED_QUERIES = [
    ("iphone 12 pro", 260), ("iphone 13", 300), ("iphone 14", 400), ("iphone 15", 500), ("iphone 16", 700),
    ("macbook air", 650), ("macbook pro", 1100), ("playstation 5", 420),
]
_vinted_session = requests.Session()
_vinted_blocked_until = 0.0
_vinted_ready = False


def _vinted_cookie():
    """Získa anonymnú cookie (bez prihlásenia), ktorú Vinted vyžaduje pre API."""
    global _vinted_ready
    _vinted_session.cookies.clear()
    r = _vinted_session.get(VINTED_BASE + "/", headers=UA, timeout=20)
    _vinted_ready = r.status_code == 200
    return _vinted_ready


def _vinted_get(path):
    global _vinted_blocked_until, _vinted_ready
    if time.time() < _vinted_blocked_until:
        return None
    for attempt in range(2):
        if not _vinted_ready and not _vinted_cookie():
            break
        time.sleep(2 + random.random() * 2)
        r = _vinted_session.get(VINTED_BASE + path, headers={**UA, "Accept": "application/json"}, timeout=20)
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                return None
        if r.status_code == 401:                 # cookie vypršala – obnov a skús znova
            _vinted_ready = False
            continue
        if r.status_code in (403, 429, 503):
            _vinted_blocked_until = time.time() + 3600
            print(f"[!] Vinted brzdí (HTTP {r.status_code}) – pauza 60 min", file=sys.stderr)
            return None
        print(f"[!] Vinted HTTP {r.status_code}", file=sys.stderr)
        return None
    return None


_A_RE = re.compile(r"<a\b[^>]*>", re.I)
# Príslušenstvo na Vinted (SK/CZ/PL/EN) – nadpis tým začína alebo je "na/do/for <zariadenie>"
VINTED_ACC = re.compile(
    r"^\W*(nov[ýéá]\s+|nowe?\s+|orygina\w*\s+|origin\w*\s+)?(etui|obudow|case|pokrowie|obal|kryt|pouzdr|puzdr|"
    r"szk[łl]o|sklo|sklíčk|folia|fólia|ładowark|ladowark|nabíj|nabij|kabel|kábel|cover|charger|plecki|"
    r"ochran|ochron|stojan|uchwyt|držiak|drziak|pasek|remien|náramok|klawiatur|klávesnic)"
    r"|\b(etui|obudowa|case|pokrowiec|obal|kryt)\s+(na|do|pre|for)\b", re.I)


def _vinted_search_html(q, max_price):
    """Katalóg Vinted ako HTML (rovnako ako v prehliadači). Vráti zoznam položiek ako z API."""
    global _vinted_blocked_until
    if time.time() < _vinted_blocked_until:
        return None
    time.sleep(2 + random.random() * 2)
    url = f"{VINTED_BASE}/catalog?search_text={requests.utils.quote(q)}&order=newest_first&price_to={max_price}"
    r = _vinted_session.get(url, headers=UA, timeout=30)
    if r.status_code in (403, 429, 503):
        _vinted_blocked_until = time.time() + 3600
        print(f"[!] Vinted brzdí (HTTP {r.status_code}) – pauza 60 min", file=sys.stderr)
        return None
    if r.status_code != 200:
        print(f"[!] Vinted HTTP {r.status_code}", file=sys.stderr)
        return None
    items, seen = [], set()
    for tag in _A_RE.findall(r.text):
        h = re.search(r'href="([^"]*/items/(\d+)[^"]*)"', tag)
        t = re.search(r'title="([^"]+)"', tag)
        if not h or not t or h.group(2) in seen:
            continue
        title_attr = _html.unescape(t.group(1))
        prices = re.findall(r"(\d+(?:[.,]\d+)?)\s?€", title_attr)
        if not prices:
            continue
        seen.add(h.group(2))
        href = h.group(1) if h.group(1).startswith("http") else VINTED_BASE + h.group(1)
        items.append({"id": h.group(2), "title": title_attr.split(", Značka")[0].split(", Stav")[0],
                      "full": title_attr, "price": prices[0], "total_item_price": prices[-1], "url": href.split("?")[0]})
    return {"items": items}


def _money(v):
    if isinstance(v, dict):
        v = v.get("amount")
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _vinted_desc(url):
    """Popis z detailu inzerátu (iba pre kandidátov)."""
    try:
        time.sleep(2 + random.random())
        t = _vinted_session.get(url, headers=UA, timeout=20).text
        m = re.search(r'"description":"((?:[^"\\]|\\.)*)"', t)
        return json.loads('"' + m.group(1) + '"')[:900] if m else ""
    except Exception:
        return ""


VINTED_MIN_PROFIT = int(os.getenv("VINTED_MIN_PROFIT", "100"))   # na Vinted prísnejšie – kupuješ naslepo
VINTED_MAX_ALERTS = int(os.getenv("VINTED_MAX_ALERTS", "3"))     # max. počet tipov z jedného prechodu
VINTED_MAX_RATIO = 0.75        # cena s poštovným najviac 75 % bežnej ceny
VINTED_BAD = re.compile(
    r"uszkodz|na\s+części|na\s+czesci|pękni|pekni|pęknię|rozbit|zbit|nie\s+działa|nie\s+dziala|zablokow|blokad|"
    r"icloud\s*(lock|blok|zablok)|simlock|poškoden|poskoden|prasknut|nefunk|na\s+diely|na\s+díly|"
    r"vadn|ohnut|wymian\w*\s+(ekran|wyświetl)|neorigin|nieorygin|zamiennik|replika|kopia|podróbk", re.I)
VINTED_BAD_STATE = re.compile(r"Stav:\s*(Uspokojivé|Uspokojivý|Satisfactory|Dostateczny)", re.I)


def process_vinted(state):
    if not VINTED_ON:
        return 0
    cands = []
    for q, max_price in VINTED_QUERIES:
        data = _vinted_search_html(q, max_price)
        if data is None:
            if time.time() < _vinted_blocked_until:
                break
            continue
        for x in data.get("items", []):
            key = f"v{x.get('id')}"
            price = _money(x.get("total_item_price") or x.get("price"))
            prev = state.get(key)
            if not price or (prev is not None and price >= prev):
                continue
            state[key] = price
            title = x.get("title") or ""
            full = x.get("full", "")
            model_attr = re.search(r"Model:\s*([^,]+)", full)
            if model_attr and model_attr.group(1).lower() not in title.lower():
                title = f"{title} {model_attr.group(1)}"
            quick = estimate(title, title)
            if not quick or VINTED_ACC.search(title) or VINTED_BAD.search(title) or VINTED_BAD_STATE.search(full):
                continue
            # telefóny majú na Vinted v atribútoch "Model: …" – kryty a príslušenstvo nie
            if quick[0].startswith(("iPhone", "Galaxy", "Pixel", "Xiaomi")) and "Model:" not in full:
                continue
            total = price + VINTED_SHIP
            if price < 0.4 * quick[1] or total > VINTED_MAX_RATIO * quick[1]:
                continue
            if quick[1] * SELL_FACTOR - total < VINTED_MIN_PROFIT:
                continue
            url = x.get("url") or f"{VINTED_BASE}/items/{x.get('id')}"
            text = _vinted_desc(url) or title
            if VINTED_BAD.search(text):
                continue                       # na Vinted iba nepoškodené kusy (batéria je OK)
            item = {"title": title, "price": round(total), "loc": "Vinted", "url": url, "snippet": ""}
            if too_cheap_console(quick[0], quick[1], total, text) or is_accessory_or_bundle(quick[0], title, total, quick[1]):
                continue
            ev = evaluate(item, text)
            if not ev or ev["profit"] < VINTED_MIN_PROFIT or any("GB neuvedené" in n for n in ev["notes"]):
                continue
            if any(k in n for n in ev["notes"] for k in ("displej", "zadné sklo", "neoriginálny")):
                continue
            ev["notes"].insert(0, f"cena s ochranou {price:.0f} € + poštovné ~{VINTED_SHIP} €")
            cands.append((ev["profit"], price, prev, url, ev))
    cands.sort(key=lambda c: -c[0])
    for profit, price, prev, url, ev in cands[:VINTED_MAX_ALERTS]:
        drop = f" (zlacnené z {prev:.0f} €)" if prev else ""
        msg = (f"🟢 <b>Vinted · {esc(ev['name'])}</b> – <b>{price:.0f} €</b>{drop}\n"
               f"Zisk ~<b>{profit} €</b> (bežne ~{ev['value']} €)\n"
               f"ℹ️ {esc('; '.join(ev['notes']))}\n"
               f"🔗 <a href=\"{url}\">Otvoriť na Vinted</a>")
        send_telegram(msg)
    return min(len(cands), VINTED_MAX_ALERTS)


# --------------------------------------------------------------------- main
_cycle = 0


def main():
    global _cycle
    _cycle += 1
    targeted = (_cycle % 5 == 1)     # cielené hľadania len pri každom 5. behu (1., 6., 11. …)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    first_run = not state
    alerts = 0
    # zoznam stránok na prejdenie: najnovšie inzeráty v sekciách + cielené hľadania konzol
    pages = []
    for sec in SECTIONS:
        for page in range(PAGES):
            off = f"{page * 20}/" if page else ""
            pages.append((sec, f"?hledat=&{LOC}cenaod=50&cenado=", off))
    for sec, q in (EXTRA_SEARCHES if targeted else []):
        pages.append((sec, f"?hledat={requests.utils.quote(q)}&{LOC}cenaod=50&cenado=", ""))
    for q in (CONSOLE_SEARCHES if targeted else []):
        pages.append(("pc", f"?hledat={requests.utils.quote(q)}&{LOC}cenaod=15&cenado=", ""))

    for sec, query, off in pages:
        base = f"https://{sec}.bazos.sk"
        html = fetch(f"{base}/{off}{query}")
        if not html:
            if time.time() < _blocked_until:
                break                         # Bazoš brzdí – zvyšok behu preskoč
            print(f"[!] {sec} {off or 'strana 0'} {query[:40]} sa nenačítala", file=sys.stderr)
            continue
        for it in parse_list(html, base):
            prev = state.get(it["id"])
            if prev is not None and it["price"] >= prev:
                continue                      # už videné a nezlacnelo
            state[it["id"]] = it["price"]
            reg = region(it["loc"])
            if not reg or it["price"] <= 0:
                continue
            area, travel, _, mode = reg
            quick = estimate(it["title"], it["snippet"])
            if quick and (too_cheap_console(quick[0], quick[1], it["price"], it["snippet"])
                          or is_accessory_or_bundle(quick[0], it["title"], it["price"], quick[1])):
                continue
            if not quick or quick[1] * SELL_FACTOR - it["price"] - travel < required_profit(quick[1]):
                continue                      # ani bez opráv to nevychádza
            text = detail_text(it["url"]) or it["snippet"]
            time.sleep(1)
            ev = evaluate(it, text)
            if ev:
                ev["profit"] -= travel
                if mode == "znami":
                    ev["notes"].append(f"🤝 kúpia známi v BA a pošlú (−{travel} €)")
                elif mode == "posta":
                    ev["notes"].append(f"📦 poslať poštou/Packetou na dobierku (−{travel} €)")
                    if re.search(r"(iba|len|výhradne)\s+osobn|osobný\s+odber\s+(iba|len)", text, re.I):
                        ev["notes"].append("⚠️ predajca chce iba osobný odber")
                elif travel:
                    ev["notes"].append(f"cesta: {area} (−{travel} €)")
            if not ev or ev["profit"] < required_profit(ev["value"]):
                continue
            drop = f" (zlacnené z {prev} €)" if prev else ""
            msg = (f"💰 <b>{esc(ev['name'])}</b> – <b>{it['price']} €</b>{drop}\n"
                   f"Zisk ~<b>{ev['profit']} €</b> (bežne ~{ev['value']} €) · 📍 {esc(it['loc'])}\n"
                   + (f"ℹ️ {esc('; '.join(ev['notes']))}\n" if ev["notes"] else "")
                   + f"🔗 <a href=\"{it['url']}\">Otvoriť inzerát</a>")
            send_telegram(msg)
            # správa pre predajcu – ťuknutím na text sa skopíruje
            send_telegram(f"<code>{esc(seller_message(it, ev, text, mode))}</code>", preview=False)
            alerts += 1
        time.sleep(1.5)
    alerts += process_cars(state)
    if VINTED_ON and _cycle % VINTED_EVERY == 1:
        try:
            alerts += process_vinted(state)
        except Exception as e:
            print(f"[!] Vinted chyba: {e}", file=sys.stderr)
    # drž stav menší – nechaj posledných 15000 ID
    if len(state) > 15000:
        state = dict(list(state.items())[-15000:])
    STATE_FILE.write_text(json.dumps(state))
    blocked = " · Bazoš brzdí, pauza" if time.time() < _blocked_until else ""
    print(f"{time.strftime('%d.%m. %H:%M')} Hotovo. Upozornení: {alerts}{' (prvý beh)' if first_run else ''}{blocked}")


def loop(interval):
    """Nepretržitý režim pre server/VPS/starý mobil: prechádza Bazoš každých `interval` sekúnd."""
    print(f"Strážca beží v slučke, interval {interval} s. Zastavíš Ctrl+C.")
    last_cache_clear = time.time()
    while True:
        start = time.time()
        try:
            main()
        except Exception as e:                      # nech jedna chyba nezastaví strážcu
            print(f"[!] chyba v behu: {e}", file=sys.stderr)
        if time.time() - last_cache_clear > 3600:   # porovnania áut obnov raz za hodinu
            _comp_cache.clear()
            last_cache_clear = time.time()
        time.sleep(max(10, interval - (time.time() - start)))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        loop(int(sys.argv[2]) if len(sys.argv) > 2 else 120)
    else:
        main()
