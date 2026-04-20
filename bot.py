

import os
import re
import sqlite3
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configurazione ────────────────────────────────────────────────────────────
RAPIDAPI_KEY       = os.environ["RAPIDAPI_KEY"]
AMAZON_PARTNER_TAG = os.environ["AMAZON_PARTNER_TAG"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

DB_PATH = "prezzi.db"
RAPIDAPI_HOST = "axesso-axesso-amazon-data-service-v1.p.rapidapi.com"

HEADERS_RAPID = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
}

# Filtri prezzi realistici (esclude dati spazzatura)
PREZZO_MIN = 3.0       # sotto €3 probabilmente un errore API
PREZZO_MAX = 3000.0    # sopra €3000 probabilmente un errore API
SCONTO_MIN = 30        # pubblica solo sconti >= 30%

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS pubblicati (
            asin TEXT PRIMARY KEY,
            titolo TEXT,
            prezzo_attuale REAL,
            prezzo_originale REAL,
            sconto INTEGER,
            data TEXT
        )
    """)
    conn.commit()
    conn.close()

def gia_pubblicato(asin):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT asin FROM pubblicati WHERE asin=?", (asin,))
    row = c.fetchone()
    conn.close()
    return row is not None

def segna_pubblicato(asin, titolo, prezzo_attuale, prezzo_originale, sconto):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO pubblicati
        (asin, titolo, prezzo_attuale, prezzo_originale, sconto, data)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (asin, titolo, prezzo_attuale, prezzo_originale, sconto,
          datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ── Axesso Deals API ──────────────────────────────────────────────────────────
def fetch_deals(pagina=1, discount_range="4"):
    url = f"https://{RAPIDAPI_HOST}/amz/amazon-search-deals-v2"
    params = {
        "domainCode": "it",
        "page": str(pagina),
        "discountRange": discount_range,
    }
    try:
        r = requests.get(url, headers=HEADERS_RAPID, params=params, timeout=15)
        logger.info(f"Deals API page={pagina} discountRange={discount_range}: status {r.status_code}")
        if r.status_code != 200:
            logger.error(f"Errore API: {r.text[:300]}")
            return []
        data = r.json()
        for campo in ["deals", "dealList", "products", "items", "result", "data"]:
            if campo in data and data[campo]:
                logger.info(f"Trovati {len(data[campo])} deal nel campo '{campo}'")
                return data[campo]
        return []
    except Exception as e:
        logger.error(f"Errore fetch_deals: {e}")
        return []

# ── Parsing ───────────────────────────────────────────────────────────────────
def parse_prezzo(testo):
    if not testo:
        return None
    testo = re.sub(r"[€$£\s\xa0]", "", str(testo))
    # Formato europeo: 1.299,00 → rimuovi punto migliaia, virgola→punto
    if re.search(r"\d{1,3}\.\d{3},\d{2}", testo):
        testo = testo.replace(".", "").replace(",", ".")
    else:
        testo = testo.replace(",", ".")
    try:
        val = float(testo)
        return val if PREZZO_MIN <= val <= PREZZO_MAX else None
    except ValueError:
        return None

def estrai_da_deal(item):
    try:
        asin = (item.get("asin") or item.get("dealAsin") or
                item.get("productAsin") or item.get("id", ""))
        if not asin or len(str(asin)) != 10:
            return None

        titolo = (item.get("productTitle") or item.get("title") or
                  item.get("dealTitle") or item.get("name", ""))
        if not titolo:
            return None
        titolo = str(titolo).strip()
        # Tronca titolo lungo in modo pulito
        if len(titolo) > 60:
            titolo = titolo[:57] + "..."

        # Prezzo attuale
        prezzo_attuale = None
        for campo in ["dealPrice", "salePrice", "currentPrice", "price",
                      "priceAmount", "discountedPrice"]:
            val = item.get(campo)
            if val is not None:
                prezzo_attuale = parse_prezzo(str(val))
                if prezzo_attuale:
                    break

        # Prezzo originale
        prezzo_originale = None
        for campo in ["listPrice", "originalPrice", "wasPrice",
                      "strikethroughPrice", "regularPrice", "rrp"]:
            val = item.get(campo)
            if val is not None:
                prezzo_originale = parse_prezzo(str(val))
                if prezzo_originale:
                    break

        # Sconto %
        sconto = 0
        for campo in ["savingPercent", "discountPercent", "discount",
                      "percentOff", "saving"]:
            val = item.get(campo)
            if val is not None:
                try:
                    sconto = int(str(val).replace("%", "").replace("-", "").strip())
                    if sconto > 0:
                        break
                except Exception:
                    pass

        if sconto == 0 and prezzo_attuale and prezzo_originale and prezzo_originale > prezzo_attuale:
            sconto = round((1 - prezzo_attuale / prezzo_originale) * 100)

        # Scarta se sconto non abbastanza alto
        if sconto < SCONTO_MIN:
            return None

        # Scarta se prezzo originale non è credibile
        # (es. prezzo attuale > prezzo originale, o originale uguale ad attuale)
        if prezzo_attuale and prezzo_originale:
            if prezzo_attuale >= prezzo_originale:
                return None
            # Scarto se lo sconto calcolato non corrisponde
            sconto_calcolato = round((1 - prezzo_attuale / prezzo_originale) * 100)
            if abs(sconto_calcolato - sconto) > 20:
                sconto = sconto_calcolato

        # Immagine
        immagine = (item.get("productImage") or item.get("imageUrl") or
                    item.get("imgUrl") or item.get("image"))

        return {
            "asin": asin,
            "titolo": titolo,
            "prezzo_attuale": prezzo_attuale,
            "prezzo_originale": prezzo_originale,
            "sconto": sconto,
            "immagine": immagine,
        }
    except Exception as e:
        logger.debug(f"Errore estrazione: {e}")
        return None

# ── Link referral ─────────────────────────────────────────────────────────────
def build_link(asin):
    return f"https://www.amazon.it/dp/{asin}?tag={AMAZON_PARTNER_TAG}"

# ── Emoji sconto ──────────────────────────────────────────────────────────────
def emoji_sconto(sconto):
    if sconto >= 70:
        return "🤯"
    elif sconto >= 50:
        return "🔥"
    elif sconto >= 40:
        return "⚡"
    else:
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

    # Riga prezzi
    if prezzo_attuale and prezzo_originale:
        risparmio = prezzo_originale - prezzo_attuale
        riga_prezzi = (
            f"💸 ~~€{prezzo_originale:.2f}~~ → *€{prezzo_attuale:.2f}*\n"
            f"📉 *-{sconto}%* — risparmi *€{risparmio:.2f}*"
        )
    elif prezzo_attuale:
        riga_prezzi = f"💰 *€{prezzo_attuale:.2f}* — sconto *{sconto}%*"
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
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": immagine,
            "caption": testo,
            "parse_mode": "Markdown",
        }, timeout=10)
    else:
        r = requests.post(f"{url_api}/sendMessage", json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": testo,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }, timeout=10)

    if r.status_code != 200:
        logger.error(f"Errore Telegram: {r.text}")
        return False

    logger.info(f"✅ Pubblicato: {titolo[:50]} — {sconto}%")
    return True

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    logger.info("🚀 Avvio scansione...")

    items_grezzi = []
    for discount_range in ["4", "3"]:
        items = fetch_deals(pagina=1, discount_range=discount_range)
        items_grezzi.extend(items)

    logger.info(f"Totale items grezzi: {len(items_grezzi)}")

    visti = set()
    prodotti = []
    for item in items_grezzi:
        p = estrai_da_deal(item)
        if p and p["asin"] not in visti:
            visti.add(p["asin"])
            prodotti.append(p)

    logger.info(f"Prodotti validi dopo filtri: {len(prodotti)}")

    pubblicati = 0
    for prodotto in prodotti:
        if gia_pubblicato(prodotto["asin"]):
            continue
        if pubblica_telegram(prodotto):
            segna_pubblicato(
                prodotto["asin"], prodotto["titolo"],
                prodotto["prezzo_attuale"], prodotto["prezzo_originale"],
                prodotto["sconto"],
            )
            pubblicati += 1

    logger.info(f"✅ Completato — pubblicati {pubblicati} nuovi prodotti")

if __name__ == "__main__":
    main()
