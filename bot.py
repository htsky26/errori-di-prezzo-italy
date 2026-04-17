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

SOGLIA_SCONTO = 30  # pubblica sconti >= 30%
DB_PATH = "prezzi.db"

RAPIDAPI_HOST = "axesso-axesso-amazon-data-service-v1.p.rapidapi.com"

HEADERS_RAPID = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
}

# Categorie Amazon Italia da monitorare
CATEGORIE = [
    "electronics",
    "computers",
    "videogames",
    "kitchen",
    "toys",
]

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

# ── Axesso API ────────────────────────────────────────────────────────────────
def cerca_deals(categoria):
    """Cerca deals su Amazon Italia tramite Axesso"""
    url = f"https://{RAPIDAPI_HOST}/amz/amazon-search-by-keyword-asin"
    params = {
        "keyword": f"offerta sconto {categoria}",
        "domainCode": "it",
        "sortBy": "relevanceblender",
        "numberOfProducts": "20",
        "page": "1",
    }
    try:
        r = requests.get(url, headers=HEADERS_RAPID, params=params, timeout=15)
        logger.info(f"Axesso search {categoria}: status {r.status_code}")
        if r.status_code != 200:
            logger.error(f"Errore API: {r.text[:200]}")
            return []
        data = r.json()
        return data.get("searchProductList", []) or []
    except Exception as e:
        logger.error(f"Errore cerca_deals {categoria}: {e}")
        return []

def cerca_deals_diretti():
    """Cerca deals diretti dalla pagina offerte Axesso"""
    url = f"https://{RAPIDAPI_HOST}/amz/amazon-lookup-product"
    # Cerca prodotti in offerta lampo
    params = {
        "url": "https://www.amazon.it/deals",
        "domainCode": "it",
    }
    try:
        r = requests.get(url, headers=HEADERS_RAPID, params=params, timeout=15)
        if r.status_code == 200:
            return r.json().get("products", []) or []
        return []
    except Exception as e:
        logger.error(f"Errore deals diretti: {e}")
        return []

def get_dettaglio_prodotto(asin):
    """Recupera dettagli e prezzo di un prodotto specifico"""
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

def estrai_prodotto(item):
    """Estrae i dati utili da un item dell'API"""
    try:
        asin = item.get("asin") or item.get("productAsin", "")
        if not asin:
            return None

        titolo = item.get("productTitle") or item.get("title", "")
        if not titolo:
            return None
        titolo = titolo[:100]

        # Prezzo attuale
        prezzo_attuale = None
        for campo in ["price", "currentPrice", "salePrice", "priceAmount"]:
            val = item.get(campo)
            if val:
                prezzo_attuale = parse_prezzo(str(val))
                if prezzo_attuale:
                    break

        # Prezzo originale
        prezzo_originale = None
        for campo in ["listPrice", "originalPrice", "wasPrice", "strikethroughPrice"]:
            val = item.get(campo)
            if val:
                prezzo_originale = parse_prezzo(str(val))
                if prezzo_originale:
                    break

        # Calcola sconto
        sconto = 0
        if item.get("savingPercent"):
            sconto = int(str(item["savingPercent"]).replace("%", "").replace("-", "").strip() or 0)
        elif prezzo_attuale and prezzo_originale and prezzo_originale > prezzo_attuale:
            sconto = round((1 - prezzo_attuale / prezzo_originale) * 100)

        if sconto < SOGLIA_SCONTO:
            return None

        # Immagine
        immagine = item.get("productImage") or item.get("imageUrl") or item.get("imgUrl")

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

def parse_prezzo(testo):
    if not testo:
        return None
    import re
    testo = re.sub(r"[€$£\s]", "", str(testo))
    testo = testo.replace(".", "").replace(",", ".")
    try:
        val = float(testo)
        return val if val > 0 else None
    except ValueError:
        return None

# ── Link referral ─────────────────────────────────────────────────────────────
def build_link(asin):
    return f"https://www.amazon.it/dp/{asin}?tag={AMAZON_PARTNER_TAG}"

# ── Telegram ──────────────────────────────────────────────────────────────────
def pubblica_telegram(prodotto):
    titolo = prodotto["titolo"]
    prezzo_attuale = prodotto["prezzo_attuale"]
    prezzo_originale = prodotto["prezzo_originale"]
    sconto = prodotto["sconto"]
    immagine = prodotto["immagine"]
    link = build_link(prodotto["asin"])

    prezzo_str = f"€{prezzo_attuale:.2f}" if prezzo_attuale else "Prezzo scontato"
    originale_str = f"~~€{prezzo_originale:.2f}~~" if prezzo_originale else ""
    risparmio_str = ""
    if prezzo_attuale and prezzo_originale and prezzo_originale > prezzo_attuale:
        risparmio = prezzo_originale - prezzo_attuale
        risparmio_str = f"💸 Risparmi *€{risparmio:.2f}*\n"

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
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": immagine,
            "caption": testo,
            "parse_mode": "Markdown",
        }
        r = requests.post(f"{url_api}/sendPhoto", json=payload, timeout=10)
    else:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": testo,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        r = requests.post(f"{url_api}/sendMessage", json=payload, timeout=10)

    if r.status_code != 200:
        logger.error(f"Errore Telegram: {r.text}")
        return False

    logger.info(f"✅ Pubblicato: {titolo[:50]} — {sconto}%")
    return True

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    logger.info("🚀 Avvio scansione con Axesso RapidAPI...")

    prodotti_grezzi = []

    for categoria in CATEGORIE:
        logger.info(f"Scansione: {categoria}")
        items = cerca_deals(categoria)
        logger.info(f"  → {len(items)} risultati")
        prodotti_grezzi.extend(items)

    # Deduplicazione per ASIN
    visti = set()
    prodotti = []
    for item in prodotti_grezzi:
        prodotto = estrai_prodotto(item)
        if prodotto and prodotto["asin"] not in visti:
            visti.add(prodotto["asin"])
            prodotti.append(prodotto)

    logger.info(f"Prodotti con sconto >= {SOGLIA_SCONTO}%: {len(prodotti)}")

    pubblicati = 0
    for prodotto in prodotti:
        if gia_pubblicato(prodotto["asin"]):
            logger.info(f"Già pubblicato: {prodotto['asin']}")
            continue

        successo = pubblica_telegram(prodotto)
        if successo:
            segna_pubblicato(
                prodotto["asin"],
                prodotto["titolo"],
                prodotto["prezzo_attuale"],
                prodotto["prezzo_originale"],
                prodotto["sconto"],
            )
            pubblicati += 1

    logger.info(f"✅ Completato — pubblicati {pubblicati} nuovi prodotti")

if __name__ == "__main__":
    main()
