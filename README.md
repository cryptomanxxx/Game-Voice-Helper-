# 🎮 Game Voice Helper

**Prata med en AI medan du spelar — den ser din stream och svarar med röst på svenska.**

Byggd för scenariot: du spelar Red Matter 2 på PS5 med PSVR2, kör fast, och vill slippa
ta av dig headsetet för att leta upp en YouTube-genomspelning på surfplattan. Istället
ställer du frågan högt — AI:n tittar på din livestream, förstår var du är i spelet och
svarar med ett kort talat svar.

```
PS5 → Twitch-livestream → frame-grabber (var 3:e sekund)
                                 │
Du (push-to-talk, svenska) ──────┼──→ Claude (vision) ──→ kort svenskt svar ──→ text-till-tal 🔊
```

Det här är egentligen mer än en spelhjälp — det är en **AI-kompanjon** som kan ge
ledtrådar, förklara spelmekanik, sammanfatta handlingen och svara på frågor om
spelets värld utan att spoila.

---

## Funktioner (MVP)

- **Twitch-frame-capture** — hämtar senaste bildrutan från din livestream var 3:e sekund
  (streamlink + ffmpeg, ingen tung videohantering i Python)
- **Push-to-talk i webbläsaren** — håll in knappen, prata svenska (Web Speech API)
- **Vision-AI** — bildruta + fråga skickas till Claude som svarar kort på svenska
- **Text-till-tal** — svaret läses upp automatiskt (webbläsarens svenska röst)
- **Tre lägen:**
  - 💡 **Ledtråd** — knuff i rätt riktning, avslöjar inte lösningen
  - 🎯 **Direkt svar** — rakt på sak när du bara vill vidare
  - 🎮 **Kontroller & hjälp** — knappar, grepp, mekanik, menyer
- **Manuell skärmbildsuppladdning** — funkar även utan stream
- **Anti-spoiler** — systemprompten instruerar modellen att inte avslöja handling
  längre fram än där du är
- **Discord-textbot (valfri)** — `!fraga <fråga>` i valfri kanal

## Kom igång

### 1. Beroenden

```bash
cd game-voice-helper
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# systemverktyg (frame-capture)
# macOS:          brew install ffmpeg streamlink
# Ubuntu/Debian:  sudo apt install ffmpeg && pip install streamlink
# Windows:        winget install ffmpeg  (streamlink kommer via pip)
```

### 2. Konfiguration

```bash
cp .env.example .env   # fyll i ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)
```

| Variabel | Standard | Beskrivning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Obligatorisk.** API-nyckel från platform.claude.com |
| `GAME_HELPER_MODEL` | `claude-opus-4-8` | Modell. `claude-haiku-4-5` för lägre latens/kostnad |
| `GAME_HELPER_SPEL` | `Red Matter 2` | Spelet du spelar (kontext i prompten) |
| `GAME_HELPER_PLATTFORM` | `PS5 med PSVR2` | Din plattform (kontext i prompten) |

### 3. Starta

```bash
uvicorn server:app --port 8000
```

Öppna **http://localhost:8000** i Chrome eller Edge (Web Speech API krävs för röst):

1. Starta din PS5-livestream till Twitch (PS-knappen → Dela → Sänd)
2. Klistra in Twitch-URL:en och klicka **Starta**
3. Håll in 🎙️-knappen och ställ din fråga på svenska
4. Svaret läses upp — klart

**Tips för VR:** öppna sidan på surfplattan bredvid dig, eller kör den i telefonen.
Push-to-talk-knappen är stor med flit — den ska gå att träffa med VR-headsetet på.

### Valfritt: Discord-textbot

```bash
pip install discord.py
export DISCORD_BOT_TOKEN=...   # bot med Message Content-intent
python discord_bot.py          # servern måste vara igång samtidigt
```

Kommandon: `!fraga …` (ledtråd) · `!svar …` (direkt) · `!kontroller …`

## API

| Metod | Route | Beskrivning |
|---|---|---|
| POST | `/api/stream/start` | `{url}` — börja hämta bildrutor från Twitch-strömmen |
| POST | `/api/stream/stop` | Stoppa frame-capture |
| GET | `/api/status` | Strömstatus + bildrutans ålder |
| GET | `/api/frame` | Senaste bildrutan (jpg) |
| POST | `/api/ask` | `{fraga, mode, spel?, screenshot_b64?, use_stream}` → `{svar, bildkalla, mode}` |

## Arkitekturval

- **Bildruta var 3:e sekund istället för kontinuerlig videoanalys** — en fråga behöver
  bara den *senaste* bildrutan. ffmpeg skriver om en enda jpg-fil; billigt och robust.
- **Web push-to-talk före Discord-röst** — webbläsarens Web Speech API ger gratis
  svensk taligenkänning och text-till-tal helt klientside. Discord-röst (lyssna i
  röstkanal) stöds inte officiellt av discord.py och hade tredubblat komplexiteten.
- **Stateless frågor** — varje fråga är oberoende (bild + fråga in, svar ut).
  Konversationsminne är en enkel påbyggnad senare.

## Roadmap

- [ ] **Discord-röstkanal** — boten sitter i röstkanalen, lyssnar (py-cord voice receive)
      och svarar med TTS-ljud direkt i kanalen. Då behövs ingen webbläsare alls.
- [ ] **Konversationsminne** — följdfrågor ("och sen då?") med bibehållen kontext
- [ ] **Handlingssammanfattning** — "vad har hänt hittills?" baserat på spelets story
      + hur långt du kommit enligt skärmbilden
- [ ] **Automatisk fastna-detektering** — om samma miljö syns i 10+ minuter kan
      kompanjonen själv fråga "vill du ha en ledtråd?"
- [ ] **Fler språk** och **valbar TTS-röst** (t.ex. ElevenLabs för naturligare röst)
