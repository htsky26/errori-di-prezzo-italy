import os
import requests
import logging
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configurazione ────────────────────────────────────────────────────────────
AMAZON_ACCESS_KEY  = os.environ["AMAZON_ACCESS_KEY"]
AMAZON_SECRET_KEY  = os.environ["AMAZON_SECRET_KEY"]
AMAZON_PARTNER_TAG = os.environ["AMAZON_PARTNER_TAG"]
TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]

SCONTO_MIN      = 25
PREZZO_MIN      = 5.0
PREZZO_MAX      = 2000.0
DB_PATH         = "pubblicati.txt"
GIORNI_SCADENZA = 30
MAX_PER_RUN     = 15   # massimo messaggi Telegram per ogni run

# Nota: "Toys" e "GroceryGourmet" rimossi, non sono SearchIndex validi per amazon.it
CATEGORIE = [
    # Elettronica
    ("Electronics", "smartphone"),
    ("Electronics", "cuffie bluetooth"),
    ("Electronics", "televisore smart tv"),
    ("Electronics", "tablet"),
    ("Electronics", "fotocamera"),
    ("Electronics", "smartwatch"),
    ("Electronics", "cassa bluetooth"),
    ("Electronics", "batteria portatile"),
    ("Electronics", "videocamera"),
    ("Electronics", "proiettore"),
    ("Electronics", "drone"),
    # Informatica
    ("Computers", "laptop"),
    ("Computers", "hard disk SSD"),
    ("Computers", "monitor PC"),
    ("Computers", "tastiera mouse"),
    ("Computers", "memoria RAM"),
    ("Computers", "scheda video"),
    ("Computers", "webcam"),
    ("Computers", "stampante"),
    ("Computers", "UPS gruppo continuità"),
    # Gaming
    ("VideoGames", "videogiochi"),
    ("VideoGames", "console gaming"),
    ("VideoGames", "accessori gaming"),
    ("VideoGames", "joystick controller"),
    ("VideoGames", "cuffie gaming"),
    ("VideoGames", "sedia gaming"),
    # Casa e cucina
    ("HomeAndKitchen", "robot aspirapolvere"),
    ("HomeAndKitchen", "airfryer"),
    ("HomeAndKitchen", "macchina caffe"),
    ("HomeAndKitchen", "frigorifero"),
    ("HomeAndKitchen", "lavatrice"),
    ("HomeAndKitchen", "lavastoviglie"),
    ("HomeAndKitchen", "forno microonde"),
    ("HomeAndKitchen", "ferro da stiro"),
    ("HomeAndKitchen", "purificatore aria"),
    ("HomeAndKitchen", "climatizzatore"),
    ("HomeAndKitchen", "ventilatore"),
    ("HomeAndKitchen", "lampada led"),
    ("HomeAndKitchen", "presa smart"),
    # Cura personale e salute
    ("HealthPersonalCare", "rasoio elettrico"),
    ("HealthPersonalCare", "spazzolino elettrico"),
    ("HealthPersonalCare", "integratori vitamina"),
    ("HealthPersonalCare", "bilancia smart"),
    ("HealthPersonalCare", "misuratore pressione"),
    ("HealthPersonalCare", "depilatore"),
    ("HealthPersonalCare", "massaggiatore"),
    # Sport, outdoor, fai da te
    ("GardenAndOutdoor", "bicicletta"),
    ("GardenAndOutdoor", "monopattino elettrico"),
    ("GardenAndOutdoor", "tenda campeggio"),
    ("GardenAndOutdoor", "zaino trekking"),
    ("GardenAndOutdoor", "attrezzi palestra"),
    ("GardenAndOutdoor", "tapis roulant"),
    ("GardenAndOutdoor", "tagliaerba"),
    ("GardenAndOutdoor", "trapano elettrico"),
    ("GardenAndOutdoor", "utensili fai da te"),
    # Auto
    ("Automotive", "supporto auto smartphone"),
    ("Automotive", "dashcam"),
    ("Automotive", "compressore portatile"),
    ("Automotive", "aspirapolvere auto"),
    # Libri
    ("Books", "libri bestseller"),
    ("Books", "kindle"),
    # Animali
    ("PetSupplies", "cibo cane"),
    ("PetSupplies", "cibo gatto"),
    ("PetSupplies", "accessori animali"),
    # Ufficio
    ("OfficeProducts", "sedia ufficio ergonomica"),
    ("OfficeProducts", "scrivania"),
    ("OfficeProducts", "cartucce stampante"),
    # Router e modem
    ("Electronics", "router wifi"),
    ("Electronics", "modem router"),
    ("Electronics", "router mesh"),
    ("Electronics", "router wifi 6"),
    ("Electronics", "range extender wifi"),
    ("Electronics", "fritz box"),
    ("Electronics", "access point wifi"),
    # Stampa 3D
    ("Electronics", "filamento PLA"),
    ("Electronics", "stampante 3D"),
    ("Electronics", "filamento PETG"),
    ("Computers", "resina stampante 3D"),
    # Black Friday: elettronica extra
    ("Electronics", "smart home"),
    ("Electronics", "lampadina smart"),
    ("Electronics", "Echo Alexa"),
    ("Electronics", "e-reader kindle"),
    ("Electronics", "AirTag localizzatore"),
    ("Electronics", "power bank"),
    ("Electronics", "caricabatterie rapido"),
    ("Electronics", "hub USB"),
    ("Electronics", "SSD esterno"),
    ("Electronics", "cuffie wireless"),
    ("Electronics", "smart TV 4K"),
    ("Electronics", "soundbar"),
    ("Electronics", "telecamera sorveglianza"),
    ("Electronics", "videocitofono"),
    ("Electronics", "e-bike"),
    ("Electronics", "monopattino"),
    ("Electronics", "microfono"),
    # Black Friday: informatica extra
    ("Computers", "notebook gaming"),
    ("Computers", "mini PC"),
    ("Computers", "processore CPU"),
    ("Computers", "mouse gaming"),
    ("Computers", "tastiera meccanica"),
    ("Computers", "docking station"),
    ("Computers", "NAS"),
    # Black Friday: gaming extra
    ("VideoGames", "Nintendo Switch"),
    ("VideoGames", "PlayStation 5"),
    ("VideoGames", "Xbox"),
    ("VideoGames", "volante gaming"),
    ("VideoGames", "giochi PS5"),
    ("VideoGames", "giochi Nintendo Switch"),
    # Black Friday: casa extra
    ("HomeAndKitchen", "robot cucina"),
    ("HomeAndKitchen", "tostapane"),
    ("HomeAndKitchen", "macchina espresso"),
    ("HomeAndKitchen", "frullatore"),
    ("HomeAndKitchen", "bollitore"),
    ("HomeAndKitchen", "pentole set"),
    ("HomeAndKitchen", "materasso"),
    ("HomeAndKitchen", "aspirapolvere senza fili"),
    ("HomeAndKitchen", "deumidificatore"),
    # Black Friday: cura personale extra
    ("HealthPersonalCare", "piastra capelli"),
    ("HealthPersonalCare", "phon"),
    ("HealthPersonalCare", "epilatore"),
    ("HealthPersonalCare", "trimmer barba"),
    ("HealthPersonalCare", "idropulsore denti"),
    # Black Friday: giardino e fai da te extra
    ("GardenAndOutdoor", "robot tosaerba"),
    ("GardenAndOutdoor", "idropulitrice"),
    ("GardenAndOutdoor", "barbecue"),
    ("GardenAndOutdoor", "piscina gonfiabile"),
    ("GardenAndOutdoor", "power station"),
    # Giochi e giocattoli
    ("ToysAndGames", "LEGO"),
    ("ToysAndGames", "giochi da tavolo"),
    ("ToysAndGames", "giocattoli bambini"),
    ("ToysAndGames", "puzzle"),
    # Neonati e idee regalo
    ("Baby", "idee regalo neonato"),
    ("Baby", "regalo nascita"),
    ("Baby", "passeggino"),
    ("Baby", "seggiolino auto"),
    ("Baby", "giochi neonato"),
    # Compressori portatili per auto
    ("Automotive", "compressore gonfiare ruote auto"),
    ("Automotive", "compressore portatile 12V"),
]

# ── Database con scadenza ─────────────────────────────────────────────────────
def carica_pubblicati():
    if not os.path.exists(DB_PATH):
        return {}
    pubblicati = {}
    scadenza = datetime.now() - timedelta(days=GIORNI_SCADENZA)
    righe_valide = []
    with open(DB_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parti = line.split("|")
            if len(parti) == 2:
                asin, data_str = parti
                try:
                    data = datetime.fromisoformat(data_str)
                    if data > scadenza:
                        pubblicati[asin] = data
                        righe_valide.append(line)
                except Exception:
                    pass
    with open(DB_PATH, "w") as f:
        f.write("\n".join(righe_valide) + "\n" if righe_valide else "")
    logger.info(f"Database: {len(pubblicati)} ASIN attivi")
    return pubblicati

def salva_pubblicato(asin):
    with open(DB_PATH, "a") as f:
        f.write(f"{asin}|{datetime.now().isoformat()}\n")

def commit_database():
    try:
        os.system('git config user.email "bot@github-actions"')
        os.system('git config user.name "GitHub Actions Bot"')
        os.system(f'git add {DB_PATH}')
        os.system('git commit -m "Update pubblicati.txt [skip ci]" 2>/dev/null || true')
        os.system('git pull --rebase 2>/dev/null || true')
        os.system('git push 2>/dev/null || true')
        logger.info("Database salvato")
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
        if r.status_code != 200:
            logger.error(f"Token error: {r.text[:300]}")
            return None
        logger.info("✅ Token ottenuto")
        return r.json().get("access_token")
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
        if r.status_code == 403:
            logger.error("AssociateNotEligible — API bloccata")
            return None  # None = API bloccata, si ferma tutto
        if r.status_code != 200:
            logger.error(f"Search error '{keywords}': {r.text[:200]}")
            return []
        data = r.json()
        items = (data.get("searchResult") or data.get("SearchResult") or {})
        risultati = items.get("items") or items.get("Items") or []
        logger.info(f"  '{keywords}': {len(risultati)} risultati")
        return risultati
    except Exception as e:
        logger.error(f"Search exception '{keywords}': {e}")
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
        if prezzo_originale and prezzo_originale > prezzo_attuale:
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

# ── Telegram (robusto: non fa mai crashare lo script) ─────────────────────────
def telegram_post(metodo, payload, tentativi=3):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{metodo}"
    for tentativo in range(1, tentativi + 1):
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                return True
            if r.status_code == 429:
                try:
                    attesa = int(r.json().get("parameters", {}).get("retry_after", 5))
                except Exception:
                    attesa = 5
                logger.warning(f"Telegram 429, attendo {attesa}s")
                time.sleep(min(attesa, 60) + 1)
                continue
            logger.error(f"Errore Telegram {metodo}: {r.text[:200]}")
            return False
        except requests.exceptions.RequestException as e:
            logger.warning(f"Telegram {metodo} tentativo {tentativo}/{tentativi}: {e}")
            time.sleep(3 * tentativo)
    return False

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

    ok = False
    if immagine:
        ok = telegram_post("sendPhoto", {
            "chat_id": TELEGRAM_CHAT_ID, "photo": immagine,
            "caption": testo, "parse_mode": "Markdown",
        })
    if not ok:
        # fallback: se la foto fallisce, manda solo il testo
        ok = telegram_post("sendMessage", {
            "chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "Markdown",
        })
    if ok:
        logger.info(f"✅ Pubblicato: {titolo[:50]} — {sconto}%")
    return ok

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pubblicati = carica_pubblicati()
    logger.info(f"🚀 Avvio — {len(pubblicati)} ASIN attivi nel database")

    token = get_access_token()
    if not token:
        logger.error("❌ Token non ottenuto")
        return

    items_grezzi = []
    for categoria, keywords in CATEGORIE:
        items = cerca_offerte(categoria, keywords, token)
        if items is None:
            logger.error("❌ API bloccata — stop scansione")
            return
        items_grezzi.extend(items)
        time.sleep(2)

    visti, prodotti = set(), []
    for item in items_grezzi:
        p = estrai_prodotto(item)
        if p and p["asin"] not in visti:
            visti.add(p["asin"])
            prodotti.append(p)

    # Solo i nuovi, con lo sconto più alto per primi
    nuovi_prodotti = [p for p in prodotti if p["asin"] not in pubblicati]
    nuovi_prodotti.sort(key=lambda p: p["sconto"], reverse=True)
    logger.info(f"Prodotti validi: {len(prodotti)} — nuovi: {len(nuovi_prodotti)} — "
                f"ne pubblico al massimo {MAX_PER_RUN}")

    nuovi = 0
    try:
        for prodotto in nuovi_prodotti[:MAX_PER_RUN]:
            if pubblica_telegram(prodotto):
                salva_pubblicato(prodotto["asin"])
                nuovi += 1
                time.sleep(3)
    finally:
        # il database viene salvato anche se qualcosa va storto a metà
        if nuovi > 0:
            commit_database()

    logger.info(f"✅ Completato — pubblicati {nuovi} nuovi prodotti")

if __name__ == "__main__":
    main()
