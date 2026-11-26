"""Jednorazové dohnanie: python dohnat.py
Prejde inzeráty, ktoré zachytil štatistický bot (posledné 4 dni), overí, či sú ešte na predaj,
a výhodné kusy (zisk aspoň 100 €, rovnaké pravidlá ako strážca) pošle do Telegramu.
Už poslané si pamätá v dohnane.json, takže ho môžeš spustiť aj viackrát."""
import json, os, re, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup


def _load_env():
    """Pri ručnom spustení si načíta Telegram token a chat ID zo štartovacieho skriptu bota."""
    try:
        for ln in open(os.path.expanduser("~/.termux/boot/strazca.sh"), encoding="utf-8"):
            m = re.match(r"\s*export\s+([A-Z_]+)=(.*)$", ln.strip())
            if m and not os.getenv(m.group(1)):
                os.environ[m.group(1)] = m.group(2).strip().strip("'\"")
    except OSError:
        pass


_load_env()
import bazos_strazca as b  # noqa: E402  (až po načítaní nastavení)

if not (os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")):
    raise SystemExit("Nenašiel som TELEGRAM_TOKEN / TELEGRAM_CHAT_ID v ~/.termux/boot/strazca.sh")

URL = "https://raw.githubusercontent.com/redblacck4-code/bazos-statistiky/main/data/listings.json"
DONE = Path(__file__).with_name("dohnane.json")
DAYS = 4
MAX = 40              # najviac toľko kusov overí (najvýhodnejšie podľa ceny)

done = set(json.loads(DONE.read_text())) if DONE.exists() else set()
L = requests.get(URL, timeout=60).json()
now = time.time()

# 1) predvýber podľa nadpisu a ceny (bez sťahovania)
cands = []
for i, r in L.items():
    if r.get("g") or r.get("x") or i in done or now - r["f"] > DAYS * 86400:
        continue
    est = b.estimate(r["t"], r["t"])
    if not est:
        continue
    name, value, _ = est
    if value * b.SELL_FACTOR - r["p"] >= b.required_profit(value, name) - 10:
        cands.append((value * b.SELL_FACTOR - r["p"], i, r))
cands = [(i, r) for _, i, r in sorted(cands, key=lambda c: -c[0])][:MAX]   # najvýhodnejšie najprv
print(f"Inzerátov za {DAYS} dni: {sum(1 for r in L.values() if now - r['f'] <= DAYS * 86400)}, "
      f"podľa nadpisu výhodných: {len(cands)}. Overujem, či sú ešte na predaj…")


def location(soup):
    txt = soup.get_text(" ", strip=True)
    m = re.search(r"Lokalita:?\s*(.{0,80})", txt)
    part = m.group(1) if m else txt
    psc = re.search(r"(\d{3})\s?(\d{2})", part)
    if not psc:
        return ""
    town = re.sub(r"[\d:]+", " ", part[psc.end():psc.end() + 40]).split("  ")[0].strip()
    town = re.split(r"\s(Videlo|Vidělo|Meno|Cena|Pridané)\b", town)[0].strip() or "?"
    return f"{town} {psc.group(1)} {psc.group(2)}"


sent = gone = skipped = 0
for i, r in cands:
    html = b.fetch(r["u"])
    soup = BeautifulSoup(html, "html.parser") if html else None
    if not soup or not soup.select_one(".popisdetail"):
        gone += 1
        continue                                     # už predané / zmazané
    text = re.sub(r"\s+", " ", soup.select_one(".popisdetail").get_text(" ", strip=True))
    loc = location(soup)
    reg = b.region(loc) if loc else None
    if loc and not reg:
        skipped += 1
        continue                                     # východ SK / vylúčený okres
    travel, mode = (reg[1], reg[3]) if reg else (b.POST_COST, "posta")
    item = {"id": i, "title": r["t"], "snippet": "", "price": r["p"], "url": r["u"], "loc": loc}
    ev = b.evaluate(item, text)
    if ev:
        ev["profit"] -= travel
    if not ev or ev["profit"] < b.required_profit(ev["value"], ev["name"]):
        skipped += 1
        done.add(i)
        continue
    tag = {"posta": " 📦", "znami": " 🤝BA", "kosice": " 🤝KE"}.get(mode, "")
    notes = b.short_notes(ev["notes"] + (["lokalita neznáma"] if not loc else []))
    msg = b.compact_alert("🔁", ev["name"], r["p"], ev["profit"], ev["value"], r["u"],
                          (b.short_loc(loc) if loc else "?") + tag, notes, None, i)
    print(f"  → {ev['name']} {r['p']} € · zisk {ev['profit']} € · {b.short_loc(loc) if loc else '?'}")
    if b.send_telegram(msg, preview=r["u"]):
        sent += 1
        done.add(i)
    else:
        print("    [!] do Telegramu sa neposlalo")
    time.sleep(1)
    DONE.write_text(json.dumps(sorted(done)))

DONE.write_text(json.dumps(sorted(done)))
print(f"Hotovo: poslaných {sent}, už predaných/zmazaných {gone}, nevyhovuje (stav, región, zisk) {skipped}.")
