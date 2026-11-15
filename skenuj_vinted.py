"""Ručný prehľad Vinted: python skenuj_vinted.py   (nič neposiela, nič neukladá)
Ukáže najlepšie aktuálne ponuky na Vinted aj pod hranicou zisku a prečo ich bot neposlal."""
import sys
import bazos_strazca as b

TOP = int(sys.argv[1]) if len(sys.argv) > 1 else 15
rows, total = [], 0
for q, max_price, *mn in b.VINTED_QUERIES:
    print(f"\rHľadám na Vinted: {q:16}", end="", flush=True)
    try:
        data = b._vinted_search_html(q, max_price, mn[0] if mn else 0)
    except Exception as e:
        print(f"\n[!] {q}: {e.__class__.__name__}")
        continue
    if data is None:
        print(f"\n[!] {q}: Vinted neodpovedá / blokuje")
        continue
    for x in data["items"]:
        total += 1
        title, full = x["title"], x.get("full", "")
        m = b.re.search(r"Model:\s*([^,]+)", full)
        if m and m.group(1).lower() not in title.lower():
            title = f"{title} {m.group(1)}"
        est = b.estimate(title, title)
        if not est:
            continue
        name, value, _ = est
        price = b._money(x["total_item_price"] or x["price"])
        tot = price + b.VINTED_SHIP
        profit = round(value * b.SELL_FACTOR - tot)
        need = max(b.VINTED_MIN_PROFIT, b.required_profit(value, name))
        why = []
        if b.VINTED_ACC.search(title) or (name.startswith(("iPhone", "Galaxy")) and "Model:" not in full) \
                or b.TITLE_PHOTO.search(title) or b.TITLE_PHOTO.search(full) or price < 0.55 * value \
                or b.too_cheap_console(name, value, tot, title) or b.is_accessory_or_bundle(name, title, tot, value):
            continue                       # kryty, volanty, disky, hry, fotky a podozrivo lacné – bot ich preskakuje tiež
        if b.VINTED_BAD.search(title) or b.VINTED_BAD_STATE.search(full):
            why.append("poškodené/zlý stav")
        if profit < need:
            why.append(f"zisk pod {need} €")
        rows.append((profit, need, name, price, value, why, x["url"]))

print(f"\rPrejdených {total} inzerátov na Vinted, rozpoznaných {len(rows)}.{' ' * 10}\n")
rows.sort(key=lambda r: -r[0])
seen = set()
shown = 0
for profit, need, name, price, value, why, url in rows:
    if url in seen:
        continue
    seen.add(url)
    mark = "✅" if not why else "  "
    print(f"{mark} {profit:+5d} € | {price:>5.0f} € (bežne {value}) | {name}")
    print(f"           {'; '.join(why) + ' · ' if why else ''}{url}")
    shown += 1
    if shown >= TOP:
        break
print("\n✅ = prešlo by rýchlou kontrolou (bot ešte overí popis, recenzie predajcu a podvody).")
