"""Prehľad dňa: python dnes.py   (alebo: python dnes.py 13.11.)
Ukáže výpadky internetu a medzery v behu bota z ~/strazca.log."""
import os, re, sys, time

day = sys.argv[1] if len(sys.argv) > 1 else time.strftime("%d.%m.")
path = os.path.expanduser("~/strazca.log")
try:
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
except FileNotFoundError:
    sys.exit("Log ~/strazca.log neexistuje.")

outages, times, alerts = [], [], 0
for ln in lines:
    if not ln.startswith(day):
        continue
    if "bez internetu" in ln or "internet je späť" in ln:
        outages.append(ln)
    m = re.match(r"\S+ (\d\d):(\d\d) ", ln)
    if m:
        times.append(int(m.group(1)) * 60 + int(m.group(2)))
    a = re.search(r"Upozornení: (\d+)", ln)
    if a:
        alerts += int(a.group(1))

print(f"=== {day} ===")
print("\nVýpadky internetu:")
print("\n".join("  " + o for o in outages) if outages else "  žiadne ✅")

gaps = []
for prev, cur in zip(times, times[1:]):
    if cur - prev > 5 and prev >= 5 * 60:          # nočný kľud 0:00–5:00 ignoruj
        gaps.append(f"  {prev // 60:02d}:{prev % 60:02d} -> {cur // 60:02d}:{cur % 60:02d} ({cur - prev} min)")
print("\nMedzery v behu (nad 5 min):")
print("\n".join(gaps) if gaps else "  žiadne ✅")

if times:
    t0, t1 = times[0], times[-1]
    print(f"\nBot zapisoval od {t0 // 60:02d}:{t0 % 60:02d} do {t1 // 60:02d}:{t1 % 60:02d}, poslal {alerts} upozornení.")
