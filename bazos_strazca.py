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
import json, os, re, sys, time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------- nastavenia
PSC = "97101"          # stred hľadania (Prievidza)
RADIUS_KM = 90         # okruh na Bazoši (vzdušnou čiarou) – presný výber robia PSČ nižšie
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
PAGES = 4                    # koľko strán (po 20) prejsť v každej sekcii
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
    (r"macbook\s*air.*\bm4\b", "MacBook Air M4", 850),
    (r"macbook\s*air.*\bm3\b", "MacBook Air M3", 720),
    (r"macbook\s*air.*\bm2\b", "MacBook Air M2", 560),
    (r"macbook\s*air.*\bm1\b", "MacBook Air M1", 420),
    (r"macbook\s*pro.*\bm1\s*(pro|max)\b", "MacBook Pro M1 Pro/Max", 950),
    (r"macbook\s*pro.*\bm[234]\s*(pro|max)\b", "MacBook Pro M2–M4 Pro/Max", 1300),
    (r"macbook\s*pro.*\bm2\b", "MacBook Pro 13 M2", 700),
    (r"macbook\s*pro.*\bm1\b", "MacBook Pro 13 M1", 580),
    (r"galaxy\s*s25\s*ultra|\bs25\s*ultra", "Galaxy S25 Ultra", 800),
    (r"galaxy\s*s24\s*ultra|\bs24\s*ultra", "Galaxy S24 Ultra", 600),
    (r"galaxy\s*s23\s*ultra|\bs23\s*ultra", "Galaxy S23 Ultra", 400),
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
GAMES = re.compile(r"\bhr[ay]\b|\bhier\b|\bgames?\b|\bcd\b", re.I)
BUNDLE = re.compile(r"\+|konzol|\bs\s+hr|\ba\s+hr|\bplus\b", re.I)
# Dedikované hľadania, aby sa konzoly nestratili medzi ostatnými inzerátmi
CONSOLE_SEARCHES = ["ps5", "playstation 5", "steam deck", "switch oled", "switch 2", "dualsense", "ovládač ps5"]


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
def fetch(url):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.status_code == 200:
                return r.text
        except requests.RequestException:
            pass
        time.sleep(3 + attempt * 5)
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
    """Vráti (oblasť, náklady na cestu) alebo None, ak je PSČ mimo sledovaných oblastí."""
    m = re.search(r"(\d{3})\s?\d{2}\s*$", loc)
    return REGIONS.get(m.group(1)) if m else None


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


def send_telegram(msg):
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print(msg + "\n---")
        return
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  data={"chat_id": chat, "text": msg, "parse_mode": "HTML",
                        "disable_web_page_preview": "false"}, timeout=20)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------- main
def main():
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    first_run = not state
    alerts = 0
    # zoznam stránok na prejdenie: najnovšie inzeráty v sekciách + cielené hľadania konzol
    pages = []
    for sec in SECTIONS:
        for page in range(PAGES):
            off = f"{page * 20}/" if page else ""
            pages.append((sec, f"?hledat=&hlokalita={PSC}&humkreis={RADIUS_KM}&cenaod=50&cenado=", off))
    for q in CONSOLE_SEARCHES:
        pages.append(("pc", f"?hledat={requests.utils.quote(q)}&hlokalita={PSC}&humkreis={RADIUS_KM}&cenaod=15&cenado=", ""))

    for sec, query, off in pages:
        base = f"https://{sec}.bazos.sk"
        html = fetch(f"{base}/{off}{query}")
        if not html:
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
            area, travel = reg
            quick = estimate(it["title"], it["snippet"])
            if not quick or quick[1] * SELL_FACTOR - it["price"] - travel < required_profit(quick[1]):
                continue                      # ani bez opráv to nevychádza
            text = detail_text(it["url"]) or it["snippet"]
            time.sleep(1)
            ev = evaluate(it, text)
            if ev:
                ev["profit"] -= travel
                if travel:
                    ev["notes"].append(f"cesta: {area} (−{travel} €)")
            if not ev or ev["profit"] < required_profit(ev["value"]):
                continue
            drop = f" (zlacnené z {prev} €)" if prev else ""
            msg = (f"💰 <b>{esc(ev['name'])}</b> – <b>{it['price']} €</b>{drop}\n"
                   f"Bežná cena ~{ev['value']} € · odhad zisku <b>~{ev['profit']} €</b>\n"
                   f"📍 {esc(it['loc'])}\n"
                   + (f"ℹ️ {esc('; '.join(ev['notes']))}\n" if ev["notes"] else "")
                   + f"📝 {esc(text[:250])}\n{it['url']}")
            send_telegram(msg)
            alerts += 1
        time.sleep(1.5)
    # drž stav menší – nechaj posledných 5000 ID
    if len(state) > 5000:
        state = dict(list(state.items())[-5000:])
    STATE_FILE.write_text(json.dumps(state))
    print(f"Hotovo. Upozornení: {alerts}{' (prvý beh)' if first_run else ''}")


if __name__ == "__main__":
    main()
