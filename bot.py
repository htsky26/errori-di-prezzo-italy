import os
import sqlite3
import requests
import logging
import hmac
import hashlib
import json
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configurazione ────────────────────────────────────────────────────────────
AMAZON_ACCESS_KEY  = os.environ["AMAZON_ACCESS_KEY"]
AMAZON_SECRET_KEY  = os.environ["AMAZON_SECRET_KEY"]
AMAZON_PARTNER_TAG = os.environ["AMAZON_PARTNER_TAG"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

SCONTO_MIN = 40
PREZZO_MIN = 5.0
PREZZO_MAX = 2000.0
DB_PATH    = "prezzi.db"

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

# ── Firma AWS4 ────────────────────────────────────────────────────────────────
def hmac_sha256(key, msg):
    if isinstance(key, str):
        key = key.encode("utf-8")
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

def get_signing_key(secret_key, date_stamp, region, service):
    k1 = hmac_sha256("AWS4" + secret_key, date_stamp)
    k2 = hmac_sha256(k1, region)
    k3 = hmac_sha256(k2, service)
    k4 = hmac_sha256(k3, "aws4_request")
    return k4

def paapi_search(categoria):
    host     = "webservices.amazon.it"
    region   = "eu-west-1"
    service  = "ProductAdvertisingAPI"
    endpoint = f"https://{host}/paapi5/searchitems"
    target   = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"

    now        = datetime.now(timezone.utc)
    amz_date   = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    payload = {
        "PartnerTag":         AMAZON_PARTNER_TAG,
        "PartnerType":        "Associates",
        "Marketplace":        "www.amazon.it",
        "SearchIndex":        categoria,
        "ItemCount":          10,
        "MinSavingPercent":   SCONTO_MIN,
        "SortBy":             "Featured",
        "Resources": [
            "ItemInfo.Title",
            "Offers.Listings.Price",
            "Offers.Listings.SavingBasis",
            "Images.Primary.Medium",
        ],
    }
    body = json.dumps(payload, separators=(",", ":"))
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

    # Headers canonici (in ordine alfabetico)
    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"content-type:application/json; charset=utf-8\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date}\n"
        f"x-amz-target:{target}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"

    canonical_request = "\n".join([
        "POST",
        "/paapi5/searchitems",
        "",
        canonical_headers,
        signed_headers,
        body_hash,
    ])

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])

    signing_key = get_signing_key(AMAZON_SECRET_KEY, date_stamp, region, service)
    signature   = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        f"AWS4-HMAC-SHA256 "
        f"Credential={AMAZON_ACCESS_KEY}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    headers = {
        "content-encoding": "amz-1.0",
        "content-type":     "application/json; charset=utf-8",
        "host":             host,
        "x-amz-date":       amz_date,
        "x-amz-target":     target,
        "Authorization":    authorization,
    }

    try:
        r = requests.post(endpoint, headers=headers, data=body.encode("utf-8"), timeout=15)
        logger.info(f"PAAPI {categoria}: status {r.status_code}")
        if r.status_code != 200:
            logger.error(f"Errore: {r.text[:300]}")
            return []
        data = r.json()
        return data.get("SearchResult", {}).get("Items", [])
    except Exception as e:
        logger.error(f"Eccezione {categoria}: {e}")
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
        asin = item.get("ASIN", "")
        if not asin:
            return None

        try:
            titolo = item["ItemInfo"]["Title"]["DisplayValue"].strip()
        except Exception:
            return None
        if len(titolo) > 60:
            titolo = titolo[:57] + "..."

        try:
            listing = item["Offers"]["Listings"][0]
        except Exception:
            return None

        try:
            prezzo_attuale = parse_prezzo(listing["Price"]["Amount"])
        except Exception:
            prezzo_attuale = None

        try:
            prezzo_originale = parse_prezzo(listing["SavingBasis"]["Amount"])
        except Exception:
            prezzo_originale = None

        if not prezzo_attuale:
            return None

        sconto = 0
        if prezzo_attuale and prezzo_originale and prezzo_originale > prezzo_attuale:
            sconto = round((1 - prezzo_attuale / prezzo_originale) * 100)

        if sconto < SCONTO_MIN:
            return None

        try:
            immagine = item["Images"]["Primary"]["Medium"]["URL"]
        except Exception:
            immagine = None

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
    init_db()
    logger.info("🚀 Avvio scansione PAAPI...")

    items_grezzi = []
    for categoria in CATEGORIE:
        logger.info(f"Scansione: {categoria}")
        items = paapi_search(categoria)
        logger.info(f"  → {len(items)} risultati")
        items_grezzi.extend(items)

    visti    = set()
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
