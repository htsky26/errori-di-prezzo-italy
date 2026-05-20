import os
import sqlite3
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configurazione ────────────────────────────────────────────────────────────
AMAZON_ACCESS_KEY  = os.environ["AMAZON_ACCESS_KEY"]
AMAZON_SECRET_KEY  = os.environ["AMAZON_SECRET_KEY"]
AMAZON_PARTNER_TAG = os.environ["AMAZON_PARTNER_TAG"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

SCONTO_MIN  = 40
PREZZO_MIN  = 5.0
PREZZO_MAX  = 2000.0
DB_PATH     = "prezzi.db"

CATEGORIE = [
    "Electronics",
    "Computers",
    "VideoGames",
    "HomeAndKitchen",
    "Toys",
    "Apparel",
    "Sports",
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

# ── Amazon PAAPI via SDK ──────────────────────────────────────────────────────
def cerca_offerte(categoria):
    from paapi5_python_sdk.api.default_api import DefaultApi
    from paapi5_python_sdk.models.partner_type import PartnerType
    from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
    from paapi5_python_sdk.models.search_items_resource import SearchItemsResource

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
    ]

    request = SearchItemsRequest(
        partner_tag=AMAZON_PARTNER_TAG,
        partner_type=PartnerType.ASSOCIATES,
        search_index=categoria,
        item_count=10,
        min_saving_percent=SCONTO_MIN,
        resources=risorse,
    )

    try:
        risposta = api.search_items(request)
        if risposta.search_result:
            return risposta.search_result.items or []
        if risposta.errors:
            for e in risposta.errors:
                logger.error(f"PAAPI errore {categoria}: {e.code} - {e.message}")
        return []
    except Exception as e:
        logger.error(f"Eccezione PAAPI {categoria}: {e}")
        return []

# ── Parsing prodotto ──────────────────────────────────────────────────────────
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
        asin = item.asin
        if not asin:
            return None

        titolo = ""
        try:
            titolo = item.item_info.title.display_value.strip()
        except Exception:
            return None
        if len(titolo) > 60:
            titolo = titolo[:57] + "..."

        listing = None
        try:
            listing = item.offers.listings[0]
        except Exception:
            return None

        prezzo_attuale = None
        try:
            prezzo_attuale = parse_prezzo(listing.price.amount)
        except Exception:
            pass

        prezzo_originale = None
        try:
            prezzo_originale = parse_prezzo(listing.saving_basis.amount)
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
            immagine = item.images.primary.medium.url
        except Exception:
            pass

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
        }, timeout=10)

    if r.status_code != 200:
        logger.error(f"Errore Telegram: {r.text}")
        return False

    logger.info(f"✅ Pubblicato: {titolo[:50]} — {sconto}%")
    return True

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    logger.info("🚀 Avvio scansione PAAPI ufficiale...")

    items_grezzi = []
    for categoria in CATEGORIE:
        logger.info(f"Scansione: {categoria}")
        items = cerca_offerte(categoria)
        logger.info(f"  → {len(items)} risultati")
        items_grezzi.extend(items)

    visti = set()
    prodotti = []
    for item in items_grezzi:
        p = estrai_prodotto(item)
        if p and p["asin"] not in visti:
            visti.add(p["asin"])
            prodotti.append(p)

    logger.info(f"Prodotti validi: {len(prodotti)}")

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
