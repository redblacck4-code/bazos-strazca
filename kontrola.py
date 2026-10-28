"""Kontrola nastavenia strážcu: python kontrola.py   (alebo: python kontrola.py offline)"""
import os, sys
import bazos_strazca as b

OK, NO = "✅", "❌"
live = "offline" not in sys.argv

print("=== NASTAVENIA ===")
print(f"Bazoš min. zisk: {b.MIN_PROFIT} € (lacné veci ~30 % z ceny)")
print(f"Vinted: {'zapnutý' if b.VINTED_ON else 'VYPNUTÝ'}, min. zisk {b.VINTED_MIN_PROFIT} €, "
      f"každých {b.VINTED_MIN} min, max {b.VINTED_MAX_ALERTS} tipy naraz")
print(f"Autá: {b.CAR_MIN_PRICE}–{b.CAR_MAX_PRICE} €, min. zisk {b.CAR_MIN_PROFIT} €")
print(f"Telegram: {'nastavený' if os.getenv('TELEGRAM_TOKEN') and os.getenv('TELEGRAM_CHAT_ID') else 'tu sa nekontroluje (bot ho má v strazca.sh)'}")

print("\n=== KATEGÓRIE (čo bot rozpozná) ===")
SAMPLES = {
    "iPhone": ["iPhone 13 128GB", "iPhone 14 Pro 256GB", "iPhone 15 Pro Max 256GB", "iPhone 16 128GB", "iPhone 17 Pro 256GB"],
    "MacBook / Mac": ["MacBook Air M1 8/256", "MacBook Air M3 16GB 512GB", "MacBook Pro 14 M3 512GB", "Mac mini M2", "iMac M1 24"],
    "Samsung / Google / Xiaomi": ["Samsung Galaxy S24 Ultra 256GB", "Samsung Galaxy S23 128GB", "Galaxy Z Fold 5", "Google Pixel 9 Pro", "Xiaomi 15T"],
    "Hodinky / AirPods / iPad": ["Apple Watch Ultra 2", "Apple Watch Series 9 45mm", "AirPods Pro 2", "iPad Air M2", "Garmin Fenix 7"],
    "Konzoly": ["PS5 Slim s mechanikou", "PS5 Pro", "Xbox Series X 1TB", "Steam Deck OLED 512GB", "Nintendo Switch OLED", "Ovládač DualSense"],
    "Drony DJI": ["DJI Mini 4 Pro", "DJI Air 3", "DJI Avata 2", "DJI Mavic 3 Classic", "DJI Neo"],
}
SHOULD_SKIP = ["Kryt na iPhone 15 Pro", "Hra na PS5 FIFA 25", "Xbox Series S 512GB", "Batéria DJI Mini 3", "Ovládač Xbox Series X"]
miss = 0
for cat, titles in SAMPLES.items():
    print(f"\n{cat}")
    for t in titles:
        r = b.estimate(t, t)
        if r:
            print(f"  {OK} {t:32} → {r[0]} (~{r[1]} €)")
        else:
            miss += 1
            print(f"  {NO} {t:32} → nerozpozná")
print("\nMá vynechať (príslušenstvo, hry, Series S)")
for t in SHOULD_SKIP:
    bad = b.evaluate({"title": t, "price": 20}, t)
    print(f"  {NO + ' berie' if bad else OK + ' vynechá'}  {t}")

print("\n=== OBLASTI (Bazoš) ===")
for loc in ["Prievidza 971 01", "Nitra 949 01", "Trenčín 911 01", "Bratislava 821 01", "Žilina 010 01",
            "Košice 040 01", "Rozhanovce 044 42", "Prešov 080 01"]:
    r = b.region(loc)
    how = {"osobne": "osobne", "znami": "známi v BA", "kosice": "kamarát v KE", "posta": "pošta"}
    print(f"  {OK if r else '⛔'} {loc:20} → " + (f"{how[r[3]]}, náklady {r[1]} €" if r else "vynechá"))

print("\n=== VINTED hľadá ===")
for q, mx, *mn in b.VINTED_QUERIES:
    print(f"  • {q} ({mn[0] if mn else 0}–{mx} €)")

if live:
    print("\n=== ŽIVÝ TEST ===")
    html = b.fetch("https://mobil.bazos.sk/?hledat=iphone&" + b.LOC + "cenaod=50&cenado=")
    n = len(b.parse_list(html, "https://mobil.bazos.sk")) if html else 0
    print(f"  {OK if n else NO} Bazoš: {n} inzerátov na 1. strane" + ("" if n else " (blok alebo zmena stránky)"))
    try:
        d = b._vinted_search_html("iphone 15", 500)
    except Exception as e:
        d = None
        print(f"  [!] Vinted: {e.__class__.__name__}")
    print(f"  {OK if d and d['items'] else NO} Vinted: " + (f"{len(d['items'])} inzerátov" if d else "zablokované / chyba"))
    if d and d["items"]:
        print("  Recenzie predajcov (prvé 3 inzeráty):")
        for x in d["items"][:3]:
            desc, rev = b._vinted_detail(x["url"])
            print(f"    {OK if rev is not None else NO} {rev if rev is not None else 'nezistené'} recenzií · "
                  f"popis {'OK' if desc else 'nenačítaný'} · {x['url']}")

print(f"\nHotovo. Nerozpoznané vzorky: {miss}")
