# Bazoš strážca

Každých ~10 minút prejde nové inzeráty na mobil.bazos.sk a pc.bazos.sk v okolí Prievidze
(okres PD, Partizánske, Bánovce, Žiar, Žarnovica), odhadne zisk pri preflipovaní a dobré
kúsky pošle do Telegramu. Upozorní aj vtedy, keď už videný inzerát zlacnie (ako ten MacBook).

## Nastavenie (cca 10 minút)

1. **Telegram bot:** v Telegrame napíš `@BotFather` → `/newbot` → skopíruj **token**.
   Potom napíš svojmu novému botovi hocičo (napr. „ahoj“) a otvor
   `https://api.telegram.org/bot<TOKEN>/getUpdates` – v odpovedi nájdeš `"chat":{"id": ...}` = **chat ID**.
2. **GitHub repo:** vytvor nové repo (verejné = neobmedzené minúty Actions zadarmo;
   súkromné má 2000 min/mesiac, čo pri 10-min intervale nestačí → daj interval 20–30 min).
   Nahraj doň všetky súbory z tohto priečinka (aj `.github/workflows/strazca.yml`).
3. **Secrets:** repo → Settings → Secrets and variables → Actions →
   *New repository secret*: `TELEGRAM_TOKEN` a `TELEGRAM_CHAT_ID`.
   Voliteľne v záložke *Variables* pridaj `MIN_PROFIT` (default 60 €).
4. **Prvé spustenie:** záložka Actions → *Bazoš strážca* → **Run workflow**.
   V logu by malo byť `Hotovo. Upozornení: X`. Ak vidíš `strana 0 sa nenačítala`,
   Bazoš blokuje servery GitHubu – vtedy to treba spustiť na inom stroji (VPS, Raspberry Pi).

## Úpravy

V `bazos_strazca.py` hore:
- `IPHONE` a `OTHER` – bežné ceny, z ktorých sa ráta zisk. Keď sa trh pohne, uprav čísla.
- `ALLOWED_PSC` – ktoré PSČ brať do úvahy.
- `MIN_PROFIT`, `SELL_FACTOR` – od akého zisku posielať a o koľko pod bežnou cenou reálne predáš.
- `HARD_EXCLUDE`, `DAMAGE` – čo úplne ignorovať a koľko odpočítať za opravy.

Lokálny test bez Telegramu: `pip install -r requirements.txt && python bazos_strazca.py`
(správy sa vypíšu do konzoly).

Odhad je orientačný – pred kúpou si inzerát vždy pozri sám.
