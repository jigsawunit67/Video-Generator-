# 🎬 Reddit Story Video Bot

Erstellt automatisch Kurzvideos im Stil von „Reddit-Story + Hintergrundclip“ und veröffentlicht sie als **YouTube Shorts** und auf **TikTok** – standardmäßig **2× pro Tag**.

```
Reddit (Top-Posts) ──► Text säubern ──► Text-zu-Sprache (edge-tts)
                                              │  + Wort-Zeitstempel
                                              ▼
 Hintergrundclip (9:16) ◄── ffmpeg ◄── Untertitel (Wort für Wort, gelb hervorgehoben)
        │
        ▼
 output/*.mp4 ──► YouTube Shorts + TikTok ──► data/used_posts.json (keine Doppelten)
```

**Was drin ist**

- Holt Storys aus konfigurierbaren Subreddits (AITA, TIFU, pettyrevenge …), filtert nach Upvotes, Länge, NSFW und Stichwörtern
- Schreibt Reddit-Kürzel aus, damit die Stimme sie richtig vorliest („AITA“ → „Am I the asshole“, „(23F)“ → „23 year old female“)
- Kostenlose, natürliche Microsoft-Neural-Stimmen über `edge-tts`, ohne API-Key
- Titelkarte im Reddit-Look, danach animierte Untertitel Wort für Wort
- Zufälliger Ausschnitt aus deinen Hintergrundclips, automatisch auf 1080×1920 zugeschnitten, optional leise Musik
- Upload über die offiziellen APIs von YouTube (Shorts) und TikTok (Content Posting API)
- Zeitplan über GitHub Actions (kostenlos, dein PC muss nicht laufen) oder lokal

---

## 1. Installation (lokal)

Voraussetzungen: **Python 3.10+** und **ffmpeg**

```bash
# ffmpeg:  Windows: winget install ffmpeg | macOS: brew install ffmpeg | Linux: sudo apt install ffmpeg
git clone <dein-repo> && cd Video-Generator-
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. Hintergrundclips hinzufügen

Lege deine ASMR- oder Gameplay-Clips (`.mp4`, `.mov`, `.mkv`, `.webm`) in **`assets/backgrounds/`**. Pro Video wird zufällig ein Clip und darin ein zufälliger Ausschnitt gewählt. Querformat ist kein Problem, es wird automatisch auf Hochformat zugeschnitten. Optional kannst du Musik in `assets/music/` legen.

> ⚠️ Nimm nur Clips, die du selbst gefilmt hast oder die ausdrücklich frei nutzbar sind (z. B. Pexels oder Pixabay). Fremde Minecraft-Parkour- oder Seifenschneide-Videos von anderen Kanälen führen schnell zu Copyright-Strikes.

Ohne Clips nutzt der Bot einen generierten Farbverlauf. Das reicht zum Testen.

## 3. Erster Test (ohne Upload)

```bash
python -m reddit_video_bot run --dry-run
```

Das fertige Video landet in `output/`.

## 4. Reddit-Zugang (empfohlen)

Reddit blockiert anonyme Abfragen immer häufiger. So legst du einen kostenlosen Zugang an:

1. https://www.reddit.com/prefs/apps → **„create another app“** → Typ **script**, Redirect-URI `http://localhost:8080`
2. Die ID unter dem App-Namen und das „secret“ in `.env` eintragen (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`)
3. `REDDIT_USER_AGENT` mit deinem Reddit-Namen ausfüllen

## Auf welches Konto wird gepostet?

Auf das Konto, mit dem du dich **einmalig** in `scripts/youtube_auth.py` bzw. `scripts/tiktok_auth.py` anmeldest. Der Bot speichert dafür nur einen Refresh-Token und kein Passwort. Um das Konto zu wechseln, führst du das Skript erneut aus und meldest dich mit dem anderen Konto an.

- **YouTube:** Hat dein Google-Konto mehrere Kanäle (z. B. Brand-Accounts), fragt Google beim Login, welcher Kanal gemeint ist. Am besten legst du dir einen eigenen Kanal für den Bot an.
- **TikTok:** Gepostet wird auf das TikTok-Konto, mit dem du dich im Browser anmeldest. Das kann ein anderes Konto sein als das Entwicklerkonto.

**Nur Shorts:** Die Videos sind immer Hochformat (1080×1920) und höchstens 175 Sekunden lang. YouTube stuft sie dadurch automatisch als **Shorts** ein, normale lange Videos entstehen nie. Wenn du lieber nur Videos unter 60 Sekunden willst, setze `video.max_duration: 59` und `reddit.max_words: 150`.

## 5. YouTube einrichten

1. https://console.cloud.google.com → neues Projekt → **„YouTube Data API v3“** aktivieren
2. **OAuth-Zustimmungsbildschirm**: Typ „Extern“, dich als Testnutzer eintragen, danach **„App veröffentlichen“** (Status *In Produktion*). Im Status *Test* läuft der Token nach 7 Tagen ab.
3. **Anmeldedaten → OAuth-Client-ID → Desktop-App** → JSON als `client_secret.json` in den Projektordner legen
4. `python scripts/youtube_auth.py` ausführen und mit dem Google-Konto deines Kanals anmelden
5. Die drei ausgegebenen Werte in `.env` eintragen

> ⚠️ **Wichtig:** YouTube stellt Uploads aus **nicht geprüften** API-Projekten automatisch auf **privat**. Damit Videos öffentlich erscheinen, musst du einmalig das [YouTube API Audit](https://support.google.com/youtube/contact/yt_api_form) beantragen. Das ist kostenlos und dauert meist einige Tage bis Wochen. Bis dahin werden die Videos trotzdem hochgeladen und du kannst sie in YouTube Studio von Hand auf öffentlich stellen.

## 5b. TikTok einrichten

1. Auf https://developers.tiktok.com einloggen → **Manage apps → Connect an app**
2. Plattform **Desktop**, Produkte **Login Kit** und **Content Posting API** hinzufügen, bei Content Posting **Direct Post** aktivieren
3. Scopes `user.info.basic` und `video.publish` auswählen
4. Als Redirect-URI `http://localhost:8080/callback/` eintragen
5. **Client Key** und **Client Secret** in `.env` eintragen (`TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`)
6. `python scripts/tiktok_auth.py` ausführen und mit dem TikTok-Konto anmelden, auf das gepostet werden soll
7. Den ausgegebenen `TIKTOK_REFRESH_TOKEN` eintragen (gültig 365 Tage)

> ⚠️ **Wichtig:** Solange deine TikTok-App **nicht geprüft** ist, erlaubt TikTok nur **private Posts** (nur du siehst sie). Der Bot erkennt das und postet dann automatisch privat. Für öffentliche Posts musst du im Developer-Portal das **Audit** für die Content Posting API beantragen. Dafür verlangt TikTok eine Beschreibung bzw. ein Demo-Video deiner App.

Wenn du nur eine Plattform willst, passt du in `config.yaml` die Zeile `upload.platforms` an, z. B. `[youtube]` oder `[tiktok]`.

## 5c. Testen

Danach erstellst du ein Video und lädst es hoch mit:

```bash
python -m reddit_video_bot run
```

## 6. Automatisch 2× pro Tag veröffentlichen

### Variante A: GitHub Actions (empfohlen, dein PC muss nicht laufen)

Der Workflow `.github/workflows/publish.yml` läuft täglich gegen **12:17 und 18:47 Uhr** (deutsche Winterzeit; in der Sommerzeit eine Stunde später).

1. Im Repo: **Settings → Secrets and variables → Actions → New repository secret** und diese Werte anlegen:
   `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`
2. Hintergrundclips entweder in `assets/backgrounds/` committen (max. 100 MB pro Datei) **oder** als direkte Download-Links im Secret `BACKGROUND_URLS` angeben (komma-getrennt)
3. Testen: **Actions → „Reddit-Story-Video veröffentlichen“ → Run workflow** mit Haken bei *dry_run*. Das Video kannst du danach als Artefakt herunterladen.

Die Uhrzeiten änderst du in den `cron`-Zeilen (Zeitangaben in UTC). GitHub startet geplante Läufe manchmal ein paar Minuten zu spät, das ist normal.

### Variante B: Lokal oder auf einem Server

```bash
python -m reddit_video_bot schedule --times 12:00 19:00
```

Alternativ per Cron (`crontab -e`):

```
0 12,19 * * * cd /pfad/zum/projekt && .venv/bin/python -m reddit_video_bot run >> bot.log 2>&1
```

## 7. Anpassen (`config.yaml`)

| Was | Wo |
|---|---|
| Subreddits, Mindest-Upvotes, Länge | `reddit:` |
| Stimme und Tempo (`edge-tts --list-voices`) | `tts.voice`, `tts.rate` |
| Max. Videolänge (Shorts: ≤ 180 s) | `video.max_duration` |
| Schriftgröße, Farben, Wörter pro Zeile | `subtitles:` |
| Plattformen | `upload.platforms: [youtube, tiktok]` |
| YouTube-Titel, Beschreibung, Tags, Sichtbarkeit | `upload.youtube:` |
| TikTok-Caption, Sichtbarkeit, Duett/Stitch | `upload.tiktok:` |
| Nur rendern, nichts hochladen | `upload.platforms: []` |

**Deutsche Videos:** Trage deutschsprachige Subreddits ein und stelle `tts.voice` auf z. B. `de-DE-ConradNeural` oder `de-DE-KatjaNeural`. Eine deutsche Stimme, die englischen Text vorliest, klingt schlecht.

## Befehle

```bash
python -m reddit_video_bot run              # 1 Video erstellen + hochladen
python -m reddit_video_bot run --dry-run    # nur erstellen (Story wird nicht als benutzt markiert)
python -m reddit_video_bot run --no-upload  # erstellen + als benutzt markieren
python -m reddit_video_bot schedule --times 12:00 19:00
python -m unittest discover -s tests -t .   # Tests
```

## Gut zu wissen

- **Wenn eine Plattform ausfällt:** Die andere wird trotzdem bedient. Die Story gilt danach als benutzt, und der GitHub-Lauf wird rot markiert, damit dir der Fehler auffällt.
- **TikTok-Token:** Gibt TikTok beim Erneuern einen neuen Refresh-Token aus, speichert der Bot ihn lokal in `.tiktok_refresh_token` und weist im Log darauf hin. Bei GitHub Actions musst du dann das Secret aktualisieren.
- **Instagram Reels** können später über `reddit_video_bot/uploaders/` ergänzt werden.
- **Monetarisierung:** YouTube stuft reine „Reddit vorlesen + fremdes Gameplay“-Videos oft als *wiederverwendete Inhalte* ein. Eigene Clips, eigene Musik und ein wiedererkennbarer Stil helfen.
- **Rechte:** Die Storys gehören ihren Autoren. Der Bot verlinkt deshalb automatisch den Original-Post in der Beschreibung. Beachte außerdem die Nutzungsbedingungen der Reddit-API.
- **YouTube-Kontingent:** Ein Upload kostet ca. 1.600 von 10.000 täglichen API-Einheiten. 2 Uploads pro Tag sind also kein Problem.
