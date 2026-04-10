# ⚡ Errori di Prezzo Amazon Italia — Bot Telegram

Bot automatico che monitora Amazon Italia h24, trova errori di prezzo e pubblica su Telegram con link referral.

## Come funziona

- GitHub Actions lo esegue ogni 15 minuti gratuitamente
- Usa Amazon Product Advertising API (PAAPI) per cercare prodotti con sconto ≥50%
- Salva i prodotti già pubblicati per evitare duplicati
- Pubblica su Telegram con foto, prezzo barrato, prezzo attuale e link referral

---

## Setup — segui nell'ordine

### 1. Crea il repository su GitHub

- Vai su github.com → "New repository"
- Nome: `errori-di-prezzo-italy`
- Seleziona **Private**
- Clicca "Create repository"
- Carica tutti i file di questo progetto

### 2. Ottieni le credenziali Amazon PAAPI

- Vai su https://affiliate-program.amazon.it/
- In alto a destra: "Strumenti" → "Product Advertising API"
- Clicca "Unisciti ora" o "Manage your credentials"
- Crea un nuovo Access Key → ti dà **Access Key** e **Secret Key**
- Il tuo **Partner Tag** è il tuo tag affiliato (es. `tuonome-21`)

### 3. Aggiungi i Secrets su GitHub

Vai nel tuo repository → Settings → Secrets and variables → Actions → "New repository secret"

Aggiungi questi 5 secrets uno per uno:

| Nome secret | Valore |
|---|---|
| `AMAZON_ACCESS_KEY` | La tua Access Key PAAPI |
| `AMAZON_SECRET_KEY` | La tua Secret Key PAAPI |
| `AMAZON_PARTNER_TAG` | Il tuo tag es. `tuonome-21` |
| `TELEGRAM_TOKEN` | Il token del tuo bot da BotFather |
| `TELEGRAM_CHAT_ID` | Es. `@nomedelcanale` o `-1001234567890` |

### 4. Attiva GitHub Actions

- Vai nel repository → tab "Actions"
- Clicca "I understand my workflows, go ahead and enable them"
- Vai su "Scanner Errori Prezzo Amazon" → "Run workflow" per testarlo subito

---

## Personalizzazione

Nel file `bot.py` puoi modificare:

```python
SOGLIA_SCONTO = 50   # abbassa a 40 per trovare più prodotti, alza a 60 per solo errori veri

CATEGORIE = [
    "Electronics",
    "Computers", 
    "VideoGames",
    "HomeAndKitchen",
    "Toys",
]
```

Per cambiare la frequenza modifica il file `.github/workflows/scanner.yml`:
```yaml
- cron: "*/15 * * * *"   # ogni 15 minuti
- cron: "*/10 * * * *"   # ogni 10 minuti
- cron: "*/30 * * * *"   # ogni 30 minuti
```

---

## Struttura file

```
errori-di-prezzo-italy/
├── bot.py                          # script principale
├── requirements.txt                # dipendenze Python
├── .gitignore                      # esclude db e file sensibili
└── .github/
    └── workflows/
        └── scanner.yml             # automazione GitHub Actions
```

---

## Commissioni Amazon per categoria

| Categoria | Commissione |
|---|---|
| Elettronica | 1% |
| Informatica | 2.5% |
| Videogiochi | 1% |
| Casa e cucina | 4% |
| Giocattoli | 3% |
| Moda | 10% |
