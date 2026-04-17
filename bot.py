
import os
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
    """
    discountRange valori: 1=fino10%, 2=10-25%, 3=25-50%, 4=oltre50%
    Usiamo 4 per massimo sconto, poi proviamo anche 3
    """
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
        logger.info(f"Risposta keys: {list(data.keys())}")
        # L'endpoint può restituire i deal in campi diversi
        for campo in ["deals", "dealList", "products", "items", "result", "data"]:
            if campo in data and data[campo]:
                logger.info(f"Trovati {len(data[campo])} deal nel campo '{campo}'")
                return data[campo]
        logger.info(f"Risposta completa: {str(data)[:500]}")
        return []
    except Exception as e:
        logger.error(f"Errore fetch_deals: {e}")
        return []

def get_dettaglio(asin):
    """Recupera dettagli prodotto tramite ASIN"""
    url = f"https://{RAPIDAPI_HOST}/amz/amazon-lookup-product"
    params = {
        "url": f"https://www.amazon.it/dp/{asin}",
        "domainCode": "it",
    }
    try:
        r = requests.get(url, headers=HEADERS_RAPID, params=params, timeout=15)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        logger.error(f"Errore dettaglio {asin}: {e}")
        return None

def parse_prezzo(testo):
    if not testo:
        return None
    import re
    testo = re.sub(r"[€$£\s,\xa0]", "", str(testo).replace(".", ""))
    # gestisce formato europeo: 1.299,00 → già rimosso il punto
    try:
        # prova prima con virgola come decimale
        testo2 = testo.replace(",", ".")
        val = float(testo2)
        return val if 0 < val < 100000 else None
    except ValueError:
        return None

def estrai_da_deal(item):
    """Estrae dati da un oggetto deal dell'API"""
    try:
        # Log del primo item per capire la struttura
        logger.debug(f"Item keys: {list(item.keys()) if isinstance(item, dict) else type(item)}")

        asin = (item.get("asin") or item.get("dealAsin") or
                item.get("productAsin") or item.get("id", ""))
        if not asin or len(str(asin)) != 10:
            return None

        titolo = (item.get("productTitle") or item.get("title") or
                  item.get("dealTitle") or item.get("name", ""))
        if not titolo:
            return None
        titolo = str(titolo)[:100]

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

# ── Telegram ──────────────────────────────────────────────────────────────────
def pubblica_telegram(prodotto):
    titolo          = prodotto["titolo"]
    prezzo_attuale  = prodotto["prezzo_attuale"]
    prezzo_originale= prodotto["prezzo_originale"]
    sconto          = prodotto["sconto"]
    immagine        = prodotto["immagine"]
    link            = build_link(prodotto["asin"])

    prezzo_str    = f"€{prezzo_attuale:.2f}" if prezzo_attuale else "Prezzo scontato"
    originale_str = f"~~€{prezzo_originale:.2f}~~" if prezzo_originale else ""
    risparmio_str = ""
    if prezzo_attuale and prezzo_originale and prezzo_originale > prezzo_attuale:
        risparmio_str = f"💸 Risparmi *€{prezzo_originale - prezzo_attuale:.2f}*\n"

    testo = (
        f"🔥 *OFFERTA AMAZON ITALIA* 🔥\n\n"
        f"📦 *{titolo}*\n\n"
        f"{originale_str} → *{prezzo_str}*\n"
        f"{risparmio_str}"
        f"🏷 Sconto: *{sconto}%*\n\n"
        f"🛒 [ACQUISTA ORA]({link})\n\n"
        f"⚡ _Offerta a tempo limitato!_"
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
    logger.info("🚀 Avvio scansione con endpoint Deals...")

    items_grezzi = []

    # Prende deals con sconto alto (range 4 = >50%) e medio (range 3 = 25-50%)
    for discount_range in ["4", "3"]:
        items = fetch_deals(pagina=1, discount_range=discount_range)
        items_grezzi.extend(items)
        if items:
            # Logga il primo item per debug struttura
            logger.info(f"Esempio item: {str(items[0])[:300]}")

    logger.info(f"Totale items grezzi: {len(items_grezzi)}")

    # Deduplicazione e estrazione
    visti = set()
    prodotti = []
    for item in items_grezzi:
        p = estrai_da_deal(item)
        if p and p["asin"] not in visti:
            visti.add(p["asin"])
            prodotti.append(p)

    logger.info(f"Prodotti estratti validi: {len(prodotti)}")

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
