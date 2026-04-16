import os
import json
import sqlite3
import requests
import logging
from datetime import datetime
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configurazione ────────────────────────────────────────────────────────────
AMAZON_PARTNER_TAG = os.environ["AMAZON_PARTNER_TAG"]   # es. tuotag-21
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]     # es. @nomedelcanale

SOGLIA_SCONTO = 10   # pubblica solo sconti >= 50%

DB_PATH = "prezzi.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# URL pagine da monitorare
URLS_DA_MONITORARE = [
    "https://www.amazon.it/deals?deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-lightning-deals%2522%257D",
    "https://www.amazon.it/gp/goldbox",
    "https://www.amazon.it/deals?deals-widget=%257B%2522version%2522%253A1%252C%2522viewIndex%2522%253A0%252C%2522presetId%2522%253A%2522deals-collection-all-deals%2522%257D",
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
        INSERT OR IGNORE INTO pubblicati (asin, titolo, prezzo_attuale, prezzo_originale, sconto, data)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (asin, titolo, prezzo_attuale, prezzo_originale, sconto, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ── Scraping ──────────────────────────────────────────────────────────────────
def scrapa_offerte_goldbox():
    """Scrapa la pagina goldbox/deals di Amazon Italia"""
    prodotti = []

    for url in URLS_DA_MONITORARE:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                logger.warning(f"Status {r.status_code} per {url}")
                continue

            soup = BeautifulSoup(r.text, "html.parser")

            # Cerca i blocchi prodotto nelle pagine deals
            # Amazon usa vari selettori — proviamo i principali
            selettori = [
                "div[data-asin]",
                "[data-component-type='s-search-result']",
                ".s-result-item[data-asin]",
            ]

            items = []
            for sel in selettori:
                items = soup.select(sel)
                if items:
                    break

            logger.info(f"Trovati {len(items)} elementi in {url}")

            for item in items:
                try:
                    asin = item.get("data-asin", "").strip()
                    if not asin or len(asin) != 10:
                        continue

                    # Titolo
                    titolo_el = item.select_one("h2 span, h2 a span, .a-text-normal")
                    titolo = titolo_el.get_text(strip=True) if titolo_el else None
                    if not titolo:
                        continue

                    # Prezzo attuale
                    prezzo_el = item.select_one(".a-price .a-offscreen, .a-price-whole")
                    prezzo_str = prezzo_el.get_text(strip=True) if prezzo_el else ""
                    prezzo_attuale = parse_prezzo(prezzo_str)

                    # Prezzo originale (barrato)
                    originale_el = item.select_one(".a-text-price .a-offscreen, .a-price.a-text-price .a-offscreen")
                    originale_str = originale_el.get_text(strip=True) if originale_el else ""
                    prezzo_originale = parse_prezzo(originale_str)

                    # Percentuale sconto
                    sconto_el = item.select_one(".a-badge-text, [data-a-badge-color] span")
                    sconto = 0
                    if sconto_el:
                        testo = sconto_el.get_text(strip=True)
                        sconto = estrai_percentuale(testo)

                    # Calcola sconto se non trovato direttamente
                    if sconto == 0 and prezzo_attuale and prezzo_originale and prezzo_originale > prezzo_attuale:
                        sconto = round((1 - prezzo_attuale / prezzo_originale) * 100)

                    if sconto < SOGLIA_SCONTO:
                        continue

                    # Immagine
                    img_el = item.select_one("img.s-image, img[data-image-latency]")
                    immagine = img_el.get("src") if img_el else None

                    prodotti.append({
                        "asin": asin,
                        "titolo": titolo[:100],
                        "prezzo_attuale": prezzo_attuale,
                        "prezzo_originale": prezzo_originale,
                        "sconto": sconto,
                        "immagine": immagine,
                    })

                except Exception as e:
                    logger.debug(f"Errore parsing item: {e}")
                    continue

        except Exception as e:
            logger.error(f"Errore scraping {url}: {e}")

    return prodotti


def scrapa_ricerca_sconti():
    """Cerca prodotti con sconto alto tramite ricerca Amazon"""
    prodotti = []
    query_urls = [
        "https://www.amazon.it/s?i=electronics&rh=p_n_pct-off-with-tax%3A5000-&s=price-desc-rank",
        "https://www.amazon.it/s?i=computers&rh=p_n_pct-off-with-tax%3A5000-&s=price-desc-rank",
        "https://www.amazon.it/s?i=videogames&rh=p_n_pct-off-with-tax%3A5000-&s=price-desc-rank",
        "https://www.amazon.it/s?i=kitchen&rh=p_n_pct-off-with-tax%3A5000-&s=price-desc-rank",
        "https://www.amazon.it/s?i=toys-and-games&rh=p_n_pct-off-with-tax%3A5000-&s=price-desc-rank",
    ]

    for url in query_urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("[data-component-type='s-search-result'][data-asin]")

            for item in items:
                try:
                    asin = item.get("data-asin", "").strip()
                    if not asin or len(asin) != 10:
                        continue

                    titolo_el = item.select_one("h2 span")
                    titolo = titolo_el.get_text(strip=True) if titolo_el else None
                    if not titolo:
                        continue

                    prezzo_el = item.select_one(".a-price .a-offscreen")
                    prezzo_str = prezzo_el.get_text(strip=True) if prezzo_el else ""
                    prezzo_attuale = parse_prezzo(prezzo_str)

                    originale_el = item.select_one(".a-text-price .a-offscreen")
                    originale_str = originale_el.get_text(strip=True) if originale_el else ""
                    prezzo_originale = parse_prezzo(originale_str)

                    sconto = 0
                    if prezzo_attuale and prezzo_originale and prezzo_originale > prezzo_attuale:
                        sconto = round((1 - prezzo_attuale / prezzo_originale) * 100)

                    sconto_el = item.select_one(".a-badge-text")
                    if sconto_el and sconto == 0:
                        sconto = estrai_percentuale(sconto_el.get_text(strip=True))

                    if sconto < SOGLIA_SCONTO:
                        continue

                    img_el = item.select_one("img.s-image")
                    immagine = img_el.get("src") if img_el else None

                    prodotti.append({
                        "asin": asin,
                        "titolo": titolo[:100],
                        "prezzo_attuale": prezzo_attuale,
                        "prezzo_originale": prezzo_originale,
                        "sconto": sconto,
                        "immagine": immagine,
                    })

                except Exception:
                    continue

        except Exception as e:
            logger.error(f"Errore ricerca {url}: {e}")

    return prodotti


def parse_prezzo(testo):
    """Converte stringa prezzo in float"""
    if not testo:
        return None
    testo = testo.replace("€", "").replace("\xa0", "").replace(" ", "").strip()
    testo = testo.replace(".", "").replace(",", ".")
    try:
        return float(testo)
    except ValueError:
        return None


def estrai_percentuale(testo):
    """Estrae numero percentuale da stringa tipo '-65%' o '65% di sconto'"""
    import re
    match = re.search(r"(\d+)", testo)
    return int(match.group(1)) if match else 0


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
    if prezzo_attuale and prezzo_originale:
        risparmio = prezzo_originale - prezzo_attuale
        risparmio_str = f"💸 Risparmi *€{risparmio:.2f}*\n"

    testo = (
        f"🔥 *ERRORE DI PREZZO AMAZON* 🔥\n\n"
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
    else:
        logger.info(f"✅ Pubblicato: {titolo[:50]} — {sconto}% sconto")
        return True


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    init_db()
    logger.info("🚀 Avvio scansione...")

    # Raccoglie prodotti da entrambe le fonti
    prodotti = []
    prodotti += scrapa_offerte_goldbox()
    prodotti += scrapa_ricerca_sconti()

    # Deduplicazione per ASIN
    visti = set()
    prodotti_unici = []
    for p in prodotti:
        if p["asin"] not in visti:
            visti.add(p["asin"])
            prodotti_unici.append(p)

    logger.info(f"Trovati {len(prodotti_unici)} prodotti con sconto >= {SOGLIA_SCONTO}%")

    pubblicati = 0
    for prodotto in prodotti_unici:
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

    logger.info(f"✅ Scansione completata — pubblicati {pubblicati} nuovi prodotti")


if __name__ == "__main__":
    main()
