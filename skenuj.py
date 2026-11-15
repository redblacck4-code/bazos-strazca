"""Ručný prehľad trhu: python skenuj.py   (nič neposiela, nič neukladá)
Ukáže najlepšie aktuálne ponuky na Bazoši aj pod hranicou zisku, aby si videl, prečo nič neprišlo."""
import sys, requests
import bazos_strazca as b

TOP = int(sys.argv[1]) if len(sys.argv) > 1 else 15
pages = []
for sec in b.SECTIONS:
    for page in range(3):
        off = f"{page * 20}/" if page else ""
        pages.append((sec, f"?hledat=&{b.LOC}cenaod=50&cenado=", off))
for sec, q in b.EXTRA_SEARCHES:
    pages.append((sec, f"?hledat={requests.utils.quote(q)}&{b.LOC}cenaod=50&cenado=", ""))
for q in b.CONSOLE_SEARCHES:
    pages.append(("pc", f"?hledat={requests.utils.quote(q)}&{b.LOC}cenaod=15&cenado=", ""))

seen, rows, total = set(), [], 0
for i, (sec, query, off) in enumerate(pages, 1):
    print(f"\rPrechádzam {i}/{len(pages)} …", end="", flush=True)
    base = f"https://{sec}.bazos.sk"
    html = b.fetch(f"{base}/{off}{query}")
    if not html:
        continue
    for it in b.parse_list(html, base):
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        total += 1
        reg = b.region(it["loc"])
        if not reg or it["price"] <= 0:
            continue
        ev = b.evaluate(it, it["snippet"])
        if not ev:
            continue
        profit = ev["profit"] - reg[1]
        rows.append((profit, b.required_profit(ev["value"]), ev, it, reg))

print(f"\rPrejdených {total} inzerátov, rozpoznaných {len(rows)} v tvojich oblastiach.\n")
rows.sort(key=lambda r: -r[0])
for profit, need, ev, it, reg in rows[:TOP]:
    mark = "✅" if profit >= need else "  "
    print(f"{mark} {profit:+5d} € | {it['price']:>5} € (bežne {ev['value']}) | {ev['name']} | {reg[0]}")
    print(f"           {it['url']}")
print(f"\n✅ = bot by poslal (zisk aspoň {b.MIN_PROFIT} €). Ostatné sú najbližšie pod hranicou.")
