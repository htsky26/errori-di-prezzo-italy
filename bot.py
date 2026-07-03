import os
import sqlite3
import requests
import logging
import time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configurazione ────────────────────────────────────────────────────────────
AMAZON_ACCESS_KEY  = os.environ["AMAZON_ACCESS_KEY"]
AMAZON_SECRET_KEY  = os.environ["AMAZON_SECRET_KEY"]
AMAZON_PARTNER_TAG = os.environ["AMAZON_PARTNER_TAG"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

SCONTO_MIN = 25
PREZZO_MIN = 5.0
PREZZO_MAX = 2000.0
DB_PATH    = "pubblicati.txt"  # file di testo semplice invece di SQLite

CATEGORIE = [
    ("Electronics",        "offerta lampo sconto"),
    ("Computers",          "offerta lampo sconto"),
    ("VideoGames",         "offerta lampo sconto"),
    ("HomeAndKitchen",     "offerta lampo sconto"),
    ("Apparel",            "offerta lampo sconto"),
    ("HealthPersonalCare", "offerta lampo sconto"),
    ("GardenAndOutdoor",   "offerta lampo sconto"),
]

# ── Database leggero — file di testo con ASIN pubblicati ─────────────────────
def carica_pubblicati():
    if not os.path.exists(DB_PATH):
        return set()
    with open(DB_PATH, "r") as f:
        return set(line.strip() for line in f if line.strip())

def salva_pubblicato(asin):
    with open(DB_PATH, "a") as f:
        f.write(asin + "\n")

def commit_database():
    """Salva il file pubblicati.txt nel repository GitHub"""
    try:
        os.system('git config user.email "bot@github-actions"')
        os.system('git config user.name "GitHub Actions Bot"')
        os.system(f'git add {DB_PATH}')
        os.system(f'git commit -m "Update pubblicati.txt [skip ci]" 2>/dev/null || true')
        os.system('git push 2>/dev/null || true')
        logger.info("Database salvato nel repository")
    except Exception as e:
        logger.error(f"Errore commit: {e}")

# ── Creators API Auth ─────────────────────────────────────────────────────────
def get_access_token():
    url = "https://api.amazon.com/auth/o2/token"
    data = {
        "grant_type":    "client_credentials",
        "client_id":     AMAZON_ACCESS_KEY,
        "client_secret": AMAZON_SECRET_KEY,
        "scope":         "creatorsapi::default",
    }
    try:
        r = requests.post(url, data=data, timeout=15)
        logger.info(f"Token request: status {r.status_code}")
        if r.status_code != 200:
            logger.error(f"Token error: {r.text[:300]}")
            return None
        token = r.json().get("access_token")
        logger.info("✅ Token ottenuto")
        return token
    except Exception as e:
        logger.error(f"Token exception: {e}")
        return None

# ── Creators API Search ───────────────────────────────────────────────────────
def cerca_offerte(categoria, keywords, token):
    url = "https://creatorsapi.amazon/catalog/v1/searchItems"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json; charset=utf-8",
        "x-marketplace": "www.amazon.it",
    }
    payload = {
        "partnerTag":  AMAZON_PARTNER_TAG,
        "partnerType": "Associates",
        "marketplace": "www.amazon.it",
        "searchIndex": categoria,
        "keywords":    keywords,
        "itemCount":   10,
        "resources": [
            "itemInfo.title",
            "offersV2.listings.price",
            "images.primary.large",
        ],
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        logger.info(f"Search {categoria}: status {r.status_code}")
        if r.status_code != 200:
            logger.error(f"Search error {categoria}: {r.text[:200]}")
            return []
        data = r.json()
        items = (data.get("searchResult") or data.get("SearchResult") or {})
        return items.get("items") or items.get("Items") or []
    except Exception as e:
        logger.error(f"Search exception {categoria}: {e}")
        return []

# ── Parsing ───────────────────────────────────────────────────────────────────
def parse_prezzo(val):
    if val is None:
        return None
    try:
        v = float(str(val).replace(",", ".").replace("€", "").strip())
        return v if PREZZO_MIN <= v <= PREZZO_MAX else None
    except Exception:
        return None

def estrai_prodotto(item):
    try:
        asin = item.get("asin") or item.get("ASIN", "")
        if not asin:
            return None

        try:
            titolo = item["itemInfo"]["title"]["displayValue"].strip()
        except Exception:
            try:
                titolo = item["ItemInfo"]["Title"]["DisplayValue"].strip()
            except Exception:
                return None
        if len(titolo) > 60:
            titolo = titolo[:57] + "..."

        prezzo_attuale   = None
        prezzo_originale = None
        try:
            listings = item["offersV2"]["listings"]
            if listings:
                listing = listings[0]
                prezzo_attuale = parse_prezzo(listing["price"]["money"]["amount"])
                sb = listing["price"].get("savingBasis")
                if sb:
                    prezzo_originale = parse_prezzo(sb["money"]["amount"])
        except Exception:
            pass

        if not prezzo_attuale:
            return None

        sconto = 0
        if prezzo_attuale and prezzo_originale and prezzo_originale > prezzo_attuale:
            sconto = round((1 - prezzo_attuale / prezzo_originale) * 100)

        if sconto < SCONTO_MIN:
            return None

        immagine = None
        try:
            immagine = item["images"]["primary"]["large"]["url"]
        except Exception:
            try:
                immagine = item["images"]["primary"]["medium"]["url"]
            except Exception:
                pass

        return {
            "asin":             asin,
            "titolo":           titolo,
            "prezzo_attuale":   prezzo_attuale,
            "prezzo_originale": prezzo_originale,
            "sconto":           sconto,
            "immagine":         immagine,
        }
    except Exception as e:
        logger.debug(f"Errore estrazione: {e}")
        return None

# ── Link e helper ─────────────────────────────────────────────────────────────
def build_link(asin):
    return f"https://www.amazon.it/dp/{asin}?tag={AMAZON_PARTNER_TAG}"

def emoji_sconto(sconto):
    if sconto >= 70: return "🤯"
    if sconto >= 50: return "🔥"
    if sconto >= 40: return "⚡"
    return "💰"

# ── Telegram ──────────────────────────────────────────────────────────────────
def pubblica_telegram(prodotto):
    titolo           = prodotto["titolo"]
    prezzo_attuale   = prodotto["prezzo_attuale"]
    prezzo_originale = prodotto["prezzo_originale"]
    sconto           = prodotto["sconto"]
    immagine         = prodotto["immagine"]
    link             = build_link(prodotto["asin"])
    emoji            = emoji_sconto(sconto)

    if prezzo_attuale and prezzo_originale:
        risparmio   = prezzo_originale - prezzo_attuale
        riga_prezzi = (
            f"💸 ~~€{prezzo_originale:.2f}~~ → *€{prezzo_attuale:.2f}*\n"
            f"📉 *-{sconto}%* — risparmi *€{risparmio:.2f}*"
        )
    else:
        riga_prezzi = f"🏷 Sconto: *{sconto}%*"

    testo = (
        f"{emoji} *ERRORE DI PREZZO* {emoji}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"*{titolo}*\n\n"
        f"{riga_prezzi}\n\n"
        f"[🛒 ACQUISTA ORA SU AMAZON]({link})\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ _Offerta a tempo limitato_"
    )

    url_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

    if immagine:
        r = requests.post(f"{url_api}/sendPhoto", json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "photo":      immagine,
            "caption":    testo,
            "parse_mode": "Markdown",
        }, timeout=10)
    else:
        r = requests.post(f"{url_api}/sendMessage", json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       testo,
            "parse_mode": "Markdown",
        }, timeout=10)

    if r.status_code != 200:
        logger.error(f"Errore Telegram: {r.text}")
        return False

    logger.info(f"✅ Pubblicato: {titolo[:50]} — {sconto}%")
    return True

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pubblicati = carica_pubblicati()
    logger.info(f"🚀 Avvio — {len(pubblicati)} ASIN già pubblicati nel database")

    token = get_access_token()
    if not token:
        logger.error("❌ Token non ottenuto")
        return

    items_grezzi = []
    for categoria, keywords in CATEGORIE:
        logger.info(f"Scansione: {categoria}")
        items = cerca_offerte(categoria, keywords, token)
        logger.info(f"  → {len(items)} risultati")
        items_grezzi.extend(items)
        time.sleep(2)

    visti    = set()
    prodotti = []
    for item in items_grezzi:
        p = estrai_prodotto(item)
        if p and p["asin"] not in visti:
            visti.add(p["asin"])
            prodotti.append(p)

    logger.info(f"Prodotti validi: {len(prodotti)}")

    nuovi = 0
    for prodotto in prodotti:
        if prodotto["asin"] in pubblicati:
            logger.info(f"Già pubblicato: {prodotto['asin']}")
            continue
        if pubblica_telegram(prodotto):
            salva_pubblicato(prodotto["asin"])
            pubblicati.add(prodotto["asin"])
            nuovi += 1

    if nuovi > 0:
        commit_database()

    logger.info(f"✅ Completato — pubblicati {nuovi} nuovi prodotti")

if __name__ == "__main__":
    main()
