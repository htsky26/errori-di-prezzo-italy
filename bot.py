import os
import json
import sqlite3
import requests
import logging
from datetime import datetime
from paapi5_python_sdk.api.default_api import DefaultApi
from paapi5_python_sdk.models.partner_type import PartnerType
from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
from paapi5_python_sdk.models.search_items_resource import SearchItemsResource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configurazione ──────────────────────────────────────────────────────────
AMAZON_ACCESS_KEY = os.environ["AMAZON_ACCESS_KEY"]
AMAZON_SECRET_KEY = os.environ["AMAZON_SECRET_KEY"]
AMAZON_PARTNER_TAG = os.environ["AMAZON_PARTNER_TAG"]   # es. tuotag-21
TELEGRAM_TOKEN    = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID  = os.environ["TELEGRAM_CHAT_ID"]      # es. @nomcanale o -1001234567890

# Soglia per considerare un errore di prezzo (sconto % minimo)
SOGLIA_SCONTO = 50

# Categorie Amazon da monitorare
CATEGORIE = [
    "Electronics",
    "Computers",
    "VideoGames",
    "HomeAndKitchen",
    "Toys",
]

DB_PATH = "prezzi.db"

# ── Database ─────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS prodotti (
            asin TEXT PRIMARY KEY,
            titolo TEXT,
            prezzo_attuale REAL,
            prezzo_riferimento REAL,
            prima_vista TEXT,
            ultima_vista TEXT,
            pubblicato INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS storico_prezzi (
            asin TEXT,
            prezzo REAL,
            data TEXT
        )
    """)
    conn.commit()
    conn.close()

def salva_prodotto(asin, titolo, prezzo_attuale, prezzo_riferimento):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    ora = datetime.now().isoformat()
    c.execute("""
        INSERT INTO prodotti (asin, titolo, prezzo_attuale, prezzo_riferimento, prima_vista, ultima_vista)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(asin) DO UPDATE SET
            prezzo_attuale=excluded.prezzo_attuale,
            ultima_vista=excluded.ultima_vista
    """, (asin, titolo, prezzo_attuale, prezzo_riferimento, ora, ora))
    c.execute(
        "INSERT INTO storico_prezzi (asin, prezzo, data) VALUES (?, ?, ?)",
        (asin, prezzo_attuale, ora)
    )
    conn.commit()
    conn.close()

def gia_pubblicato(asin):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT pubblicato FROM prodotti WHERE asin=?", (asin,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

def segna_pubblicato(asin):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE prodotti SET pubblicato=1 WHERE asin=?", (asin,))
    conn.commit()
    conn.close()

# ── Amazon PAAPI ──────────────────────────────────────────────────────────────
def cerca_offerte(categoria):
    api = DefaultApi(
        access_key=AMAZON_ACCESS_KEY,
        secret_key=AMAZON_SECRET_KEY,
        host="webservices.amazon.it",
        region="eu-west-1",
    )
    risorse = [
        SearchItemsResource.ITEMINFO_TITLE,
        SearchItemsResource.OFFERS_LISTINGS_PRICE,
        SearchItemsResource.OFFERS_LISTINGS_SAVINGBASIS,
        SearchItemsResource.IMAGES_PRIMARY_MEDIUM,
        SearchItemsResource.OFFERS_LISTINGS_PROMOTIONS,
    ]
    request = SearchItemsRequest(
        partner_tag=AMAZON_PARTNER_TAG,
        partner_type=PartnerType.ASSOCIATES,
        search_index=categoria,
        item_count=10,
        min_saving_percent=SOGLIA_SCONTO,
        resources=risorse,
    )
    try:
        risposta = api.search_items(request)
        return risposta.search_result.items if risposta.search_result else []
    except Exception as e:
        logger.error(f"Errore PAAPI categoria {categoria}: {e}")
        return []

# ── Link referral ─────────────────────────────────────────────────────────────
def build_link(asin):
    return f"https://www.amazon.it/dp/{asin}?tag={AMAZON_PARTNER_TAG}"

# ── Telegram ──────────────────────────────────────────────────────────────────
def pubblica_telegram(titolo, prezzo_attuale, prezzo_riferimento, sconto, link, immagine_url):
    sconto_euro = prezzo_riferimento - prezzo_attuale
    testo = (
        f"🔥 *ERRORE DI PREZZO AMAZON* 🔥\n\n"
        f"📦 *{titolo}*\n\n"
        f"~~€{prezzo_riferimento:.2f}~~ → *€{prezzo_attuale:.2f}*\n"
        f"💸 Risparmi *€{sconto_euro:.2f}* ({sconto}% di sconto)\n\n"
        f"🛒 [ACQUISTA ORA]({link})\n\n"
        f"⚡ _Offerta a tempo limitato — potrebbe finire presto!_"
    )
    url_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    if immagine_url:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": immagine_url,
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
    else:
        logger.info(f"Pubblicato: {titolo}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    logger.info("Avvio scansione...")
    trovati = 0

    for categoria in CATEGORIE:
        logger.info(f"Scansione categoria: {categoria}")
        items = cerca_offerte(categoria)

        for item in items:
            try:
                asin = item.asin
                titolo = item.item_info.title.display_value if item.item_info and item.item_info.title else "Prodotto Amazon"
                titolo = titolo[:80] + "..." if len(titolo) > 80 else titolo

                listing = item.offers.listings[0] if item.offers and item.offers.listings else None
                if not listing:
                    continue

                prezzo_attuale = listing.price.amount if listing.price else None
                prezzo_riferimento = listing.saving_basis.amount if listing.saving_basis else None

                if not prezzo_attuale or not prezzo_riferimento:
                    continue

                sconto = round((1 - prezzo_attuale / prezzo_riferimento) * 100)
                if sconto < SOGLIA_SCONTO:
                    continue

                immagine_url = None
                if item.images and item.images.primary and item.images.primary.medium:
                    immagine_url = item.images.primary.medium.url

                salva_prodotto(asin, titolo, prezzo_attuale, prezzo_riferimento)

                if gia_pubblicato(asin):
                    logger.info(f"Già pubblicato: {asin}")
                    continue

                link = build_link(asin)
                pubblica_telegram(titolo, prezzo_attuale, prezzo_riferimento, sconto, link, immagine_url)
                segna_pubblicato(asin)
                trovati += 1

            except Exception as e:
                logger.error(f"Errore prodotto {item.asin}: {e}")

    logger.info(f"Scansione completata. Pubblicati: {trovati}")

if __name__ == "__main__":
    main()
