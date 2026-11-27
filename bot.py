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

SCONTO_MIN      = 25
PREZZO_MIN      = 5.0
PREZZO_MAX      = 2000.0
DB_PATH         = "pubblicati.txt"
GIORNI_SCADENZA = 30
MAX_PER_RUN     = 15   # massimo messaggi Telegram per run, totale su tutti i canali

# ── Ricerche Amazon (categoria, parole chiave) ───────────────────────────────
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
    ("GardenAndOutdoor", "monopattino elettrico"),
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
    # Fai da te
    ("ToolsAndHomeImprovement", "trapano avvitatore"),
    ("ToolsAndHomeImprovement", "utensili set"),
    ("ToolsAndHomeImprovement", "saldatrice"),
    ("ToolsAndHomeImprovement", "smerigliatrice"),
    ("ToolsAndHomeImprovement", "avvitatore a batteria"),
    # Sport e tempo libero
    ("SportsAndOutdoors", "bicicletta"),
    ("SportsAndOutdoors", "tapis roulant"),
    ("SportsAndOutdoors", "attrezzi palestra"),
    ("SportsAndOutdoors", "tenda campeggio"),
    ("SportsAndOutdoors", "zaino trekking"),
    # Illuminazione
    ("Lighting", "lampada LED"),
    ("Lighting", "faretto LED"),
    ("Lighting", "striscia LED"),
    # Strumenti musicali
    ("MusicalInstruments", "chitarra elettrica"),
    ("MusicalInstruments", "tastiera pianoforte digitale"),
    ("MusicalInstruments", "controller DJ"),
    ("MusicalInstruments", "cuffie DJ"),
    # Valigeria
    ("Luggage", "trolley"),
    ("Luggage", "valigia rigida"),
    ("Luggage", "zaino viaggio"),
    # Musica e strumentazioni
    ("Music", "vinile"),
    ("Music", "CD musica"),
    ("MusicalInstruments", "microfono"),
    ("MusicalInstruments", "mixer DJ"),
    ("MusicalInstruments", "amplificatore chitarra"),
    ("MusicalInstruments", "cuffie studio"),
    ("MusicalInstruments", "interfaccia audio"),
    ("MusicalInstruments", "pedale effetti chitarra"),
    # Sport: canale dedicato
    ("SportsAndOutdoors", "kettlebell"),
    ("SportsAndOutdoors", "manubri fitness"),
    ("SportsAndOutdoors", "bicicletta elettrica"),
    # Outdoor e valigeria: canale dedicato
    ("SportsAndOutdoors", "tenda campeggio"),
    ("SportsAndOutdoors", "zaino escursionismo"),
    ("Luggage", "valigia trolley"),
    ("Luggage", "borsone viaggio"),
]


# ── Routing: a quale canale tematico va ogni ricerca ─────────────────────────
# Prima vale la parola chiave, poi la categoria Amazon. Books resta solo sul principale.
REGOLE_PAROLE = [
    ("router",   ["router", "modem", "fritz", "access point", "range extender"]),
    ("stampa3d", ["filamento", "stampante 3d", "resina"]),
    ("musica",   ["microfono", "mixer", "amplificatore", "cuffie studio", "cuffie dj",
                  "controller dj", "interfaccia audio", "pedale", "vinile", "cd musica",
                  "chitarra", "tastiera pianoforte"]),
    ("outdoor",  ["tenda", "zaino", "trolley", "valigia", "borsone"]),
    ("casa",     ["smart home", "lampadina", "presa", "echo alexa", "telecamera", "videocitofono"]),
    ("giardino", ["monopattino", "trapano", "utensili", "saldatrice", "smerigliatrice",
                  "avvitatore", "tagliaerba"]),
    ("sport",    ["bicicletta", "tapis", "palestra", "kettlebell", "manubri", "e-bike"]),
]
REGOLE_INDICE = {
    "Electronics": "tech", "Computers": "tech", "VideoGames": "tech",
    "HomeAndKitchen": "casa", "Lighting": "casa", "Appliances": "casa",
    "HealthPersonalCare": "cura",
    "GardenAndOutdoor": "giardino", "Automotive": "giardino",
    "ToolsAndHomeImprovement": "giardino",
    "Baby": "giochi", "ToysAndGames": "giochi",
    "PetSupplies": "animali",
    "OfficeProducts": "ufficio",
    "MusicalInstruments": "musica", "Music": "musica",
    "SportsAndOutdoors": "sport",
    "Luggage": "outdoor",
}

def canale_tematico(categoria, keywords):
    k = keywords.lower()
    for canale, parole in REGOLE_PAROLE:
        if any(p in k for p in parole):
            return canale
    return REGOLE_INDICE.get(categoria)

# ── Canali Telegram: nome canale -> nomi dei secret su GitHub ─────────────────
CANALI = {
    "main":     ("TELEGRAM_TOKEN",          "TELEGRAM_CHAT_ID"),
    "tech":     ("TELEGRAM_TOKEN_TECH",     "TELEGRAM_CHAT_ID_TECH"),
    "casa":     ("TELEGRAM_TOKEN_CASA",     "TELEGRAM_CHAT_ID_CASA"),
    "router":   ("TELEGRAM_TOKEN_ROUTER",   "TELEGRAM_CHAT_ID_ROUTER"),
    "stampa3d": ("TELEGRAM_TOKEN_3D",       "TELEGRAM_CHAT_ID_3D"),
    "cura":     ("TELEGRAM_TOKEN_CURA",     "TELEGRAM_CHAT_ID_CURA"),
    "giardino": ("TELEGRAM_TOKEN_GIARDINO", "TELEGRAM_CHAT_ID_GIARDINO"),
    "giochi":   ("TELEGRAM_TOKEN_GIOCHI",   "TELEGRAM_CHAT_ID_GIOCHI"),
    "animali":  ("TELEGRAM_TOKEN_ANIMALI",  "TELEGRAM_CHAT_ID_ANIMALI"),
    "ufficio":  ("TELEGRAM_TOKEN_UFFICIO",  "TELEGRAM_CHAT_ID_UFFICIO"),
    "musica":   ("TELEGRAM_TOKEN_MUSICA",   "TELEGRAM_CHAT_ID_MUSICA"),
    "sport":    ("TELEGRAM_TOKEN_SPORT",    "TELEGRAM_CHAT_ID_SPORT"),
    "outdoor":  ("TELEGRAM_TOKEN_OUTDOOR",  "TELEGRAM_CHAT_ID_OUTDOOR"),
}

def credenziali_canale(nome):
    env_token, env_chat = CANALI[nome]
    token = os.environ.get(env_token, "").strip()
    chat = os.environ.get(env_chat, "").strip()
    return (token, chat) if token and chat else (None, None)

# ── Database: ASIN -> canali già pubblicati, con scadenza ────────────────────
def carica_pubblicati():
    """Formato riga: asin|data_iso|canale1,canale2. Le righe duplicate si uniscono."""
    if not os.path.exists(DB_PATH):
        return {}
    scadenza = datetime.now() - timedelta(days=GIORNI_SCADENZA)
    unione = {}  # asin -> [data_massima, set_canali]
    with open(DB_PATH, "r") as f:
        for line in f:
            parti = line.strip().split("|")
            if len(parti) < 2 or not parti[0]:
                continue
            try:
                data = datetime.fromisoformat(parti[1])
            except Exception:
                continue
            canali = set(parti[2].split(",")) if len(parti) >= 3 and parti[2] else {"main"}
            if parti[0] in unione:
                unione[parti[0]][0] = max(unione[parti[0]][0], data)
                unione[parti[0]][1] |= canali
            else:
                unione[parti[0]] = [data, canali]
    pubblicati = {a: c for a, (d, c) in unione.items() if d > scadenza}
    righe = [f"{a}|{unione[a][0].isoformat()}|{','.join(sorted(c))}"
             for a, c in pubblicati.items()]
    with open(DB_PATH, "w") as f:
        f.write("\n".join(righe) + ("\n" if righe else ""))
    logger.info(f"Database: {len(pubblicati)} ASIN attivi")
    return pubblicati

def salva_pubblicato(asin, canali):
    with open(DB_PATH, "a") as f:
        f.write(f"{asin}|{datetime.now().isoformat()}|{','.join(sorted(canali))}\n")

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
            return None
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

        prezzo_attuale = None
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

# ── Link e helper ─────────────────────────────────────────────────────────────
def build_link(asin):
    return f"https://www.amazon.it/dp/{asin}?tag={AMAZON_PARTNER_TAG}"

def emoji_sconto(sconto):
    if sconto >= 70: return "🤯"
    if sconto >= 50: return "🔥"
    if sconto >= 40: return "⚡"
    return "💰"

# ── Telegram (robusto: non fa mai crashare lo script) ─────────────────────────
def telegram_post(token, metodo, payload, tentativi=3):
    url = f"https://api.telegram.org/bot{token}/{metodo}"
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

def pubblica_su_canale(prodotto, canale):
    token, chat = credenziali_canale(canale)
    if not token:
        logger.warning(f"Canale '{canale}': secret mancanti, salto")
        return False

    titolo = prodotto["titolo"]
    prezzo_attuale = prodotto["prezzo_attuale"]
    prezzo_originale = prodotto["prezzo_originale"]
    sconto = prodotto["sconto"]
    immagine = prodotto["immagine"]
    link = build_link(prodotto["asin"])
    emoji = emoji_sconto(sconto)

    if prezzo_attuale and prezzo_originale:
        risparmio = prezzo_originale - prezzo_attuale
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
        ok = telegram_post(token, "sendPhoto", {
            "chat_id": chat, "photo": immagine,
            "caption": testo, "parse_mode": "Markdown",
        })
    if not ok:
        # se la foto fallisce, manda solo il testo
        ok = telegram_post(token, "sendMessage", {
            "chat_id": chat, "text": testo, "parse_mode": "Markdown",
        })
    if ok:
        logger.info(f"✅ [{canale}] {titolo[:50]} — {sconto}%")
    return ok

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pubblicati = carica_pubblicati()
    logger.info(f"🚀 Avvio — {len(pubblicati)} ASIN attivi nel database")

    token = get_access_token()
    if not token:
        logger.error("❌ Token non ottenuto")
        return

    coppie = []  # (item grezzo, canale tematico)
    for categoria, keywords in CATEGORIE:
        risultati = cerca_offerte(categoria, keywords, token)
        if risultati is None:
            logger.error("❌ API bloccata — stop scansione")
            return
        tematico = canale_tematico(categoria, keywords)
        coppie.extend((item, tematico) for item in risultati)
        time.sleep(2)

    visti = {}
    for item, tematico in coppie:
        p = estrai_prodotto(item)
        if p and p["asin"] not in visti:
            p["destinazioni"] = ["main"] + ([tematico] if tematico else [])
            visti[p["asin"]] = p
    prodotti = list(visti.values())

    # un prodotto entra in lavorazione solo se manca almeno un canale di destinazione
    da_pubblicare = [
        p for p in prodotti
        if any(c not in pubblicati.get(p["asin"], set()) for c in p["destinazioni"])
    ]
    da_pubblicare.sort(key=lambda p: p["sconto"], reverse=True)
    logger.info(f"Prodotti validi: {len(prodotti)} — da pubblicare: {len(da_pubblicare)} — "
                f"limite {MAX_PER_RUN} messaggi")

    messaggi = 0
    try:
        for p in da_pubblicare:
            if messaggi >= MAX_PER_RUN:
                break
            inviati = set(pubblicati.get(p["asin"], set()))
            for canale in p["destinazioni"]:
                if canale in inviati or messaggi >= MAX_PER_RUN:
                    continue
                if pubblica_su_canale(p, canale):
                    inviati.add(canale)
                    messaggi += 1
                    time.sleep(3)
            if inviati != set(pubblicati.get(p["asin"], set())):
                salva_pubblicato(p["asin"], inviati)
                pubblicati[p["asin"]] = inviati
    finally:
        # il database viene salvato anche se la run si interrompe a metà
        if messaggi > 0:
            commit_database()

    logger.info(f"✅ Completato — messaggi inviati: {messaggi}")

if __name__ == "__main__":
    main()
