"""Prieskum cien na Bazoši: python ceny.py
Pre každý model zistí medián inzerovaných cien (celé SK, len funkčné kusy) a porovná ho s cenou v bote.
Výsledok uloží do ceny_report.txt a pošle do Telegramu (ak je nastavený). Bot počas behu radšej zastav.
Beží pomaly (~15 min), aby nás Bazoš nezablokoval."""
import os, re, sys, time, random, statistics, requests
import bazos_strazca as b

# (sekcia Bazoša, hľadaný text, počet strán po 20)
Q = []
for n in range(12, 19):
    Q.append(("mobil", f"iphone {n}", 2))
Q += [("mobil", "iphone 16e", 1), ("mobil", "iphone air", 1)]
Q += [("pc", f"macbook air m{n}", 2) for n in range(1, 6)]
Q += [("pc", f"macbook pro m{n}", 2) for n in range(1, 6)]
Q += [("pc", "mac mini", 2), ("pc", "imac m", 1)]
Q += [("mobil", q, 2) for q in ("galaxy s23", "galaxy s24", "galaxy s25", "galaxy z fold", "galaxy z flip",
                                  "pixel 9 pro", "xiaomi 15t")]
Q += [("mobil", q, 2) for q in ("apple watch ultra", "apple watch series", "apple watch se", "airpods pro",
                                  "garmin fenix", "garmin epix", "garmin forerunner", "garmin venu", "garmin instinct")]
Q += [("pc", q, 1) for q in ("ipad pro m", "ipad air m")]
Q += [("pc", q, 2) for q in ("ps5", "playstation 5", "xbox series x", "steam deck", "nintendo switch oled",
                               "nintendo switch 2", "dualsense")]
Q += [("pc", q, 2) for q in ("rtx 3080", "rtx 4070", "rtx 4080", "rtx 4090", "rtx 5070", "rtx 5080", "rtx 5090",
                               "rx 7800", "rx 7900", "rx 9070")]
Q += [("foto", "dji", 2), ("pc", "dji", 1)]


def bad(it, name, value):
    full = f"{it['title']} {it['snippet']}"
    if b.HARD_EXCLUDE.search(full) or b.PHOTO_SCAM.search(full) or b.TITLE_PHOTO.search(it["title"]):
        return True
    if any(rx.search(full) for rx, _, _ in b.DAMAGE):
        return True
    if b.too_cheap_console(name, value, it["price"], it["snippet"]) or \
            b.is_accessory_or_bundle(name, it["title"], it["price"], value):
        return True
    return not (0.4 * value <= it["price"] <= 1.7 * value)    # odľahlé ceny (diely, preklepy, "nové 2x")


prices, values, seen = {}, {}, set()
for i, (sec, q, npages) in enumerate(Q, 1):
    print(f"\r[{i}/{len(Q)}] {q:28}", end="", flush=True)
    for p in range(npages):
        off = f"{p * 20}/" if p else ""
        base = f"https://{sec}.bazos.sk"
        url = f"{base}/{off}?hledat={requests.utils.quote(q)}&{b.LOC}cenaod=40&cenado="
        time.sleep(random.uniform(4, 7))                 # pomaly, nech nás Bazoš nebrzdí
        html = b.fetch(url)
        if not html and time.time() < b._blocked_until:
            wait = int(b._blocked_until - time.time()) + 5
            print(f"\n[!] Bazoš brzdí – čakám {wait // 60} min a pokračujem…")
            time.sleep(wait)
            html = b.fetch(url)
        if not html:
            break
        items = b.parse_list(html, base)
        for it in items:
            if it["id"] in seen or it["price"] <= 0:
                continue
            seen.add(it["id"])
            est = b.estimate(it["title"], it["title"])      # model len z nadpisu = spoľahlivejšie
            if not est or any("GB neuvedené" in n for n in est[2]):
                continue
            name, value, _ = est
            if bad(it, name, value):
                continue
            prices.setdefault(name, []).append(it["price"])
            values[name] = value
        if len(items) < 20:
            break

lines, upd = [], []
for name in sorted(prices, key=lambda n: (n.split()[0], n)):
    ps = prices[name]
    if len(ps) < 4:
        continue
    med = round(statistics.median(ps) / 5) * 5
    v = values[name]
    diff = (med - v) / v * 100
    mark = "⚠️" if abs(diff) >= 10 else "✅"
    lines.append(f"{mark} {name}: bot {v} € | trh {med} € ({diff:+.0f} %, {len(ps)} ks)")
    if abs(diff) >= 10:
        upd.append(f"{name}={med}")

head = f"📊 Prieskum cien Bazoš {time.strftime('%d.%m.%Y')} – {len(seen)} inzerátov, {len(lines)} modelov"
out = "\n".join([head, ""] + lines + ["", "Na úpravu (rozdiel 10 % a viac):"] + (upd or ["nič"]))
print("\n\n" + out)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ceny_report.txt"), "w", encoding="utf-8") as f:
    f.write(out + "\n")
if os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
    chunk = ""
    for line in out.split("\n"):
        if len(chunk) + len(line) > 3800:
            b.send_telegram(b.esc(chunk), preview=False)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        b.send_telegram(b.esc(chunk), preview=False)
    print("\nPoslané aj do Telegramu.")
