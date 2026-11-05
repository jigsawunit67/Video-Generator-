"""Einmalig ausführen, um den YouTube-Refresh-Token zu erzeugen.

Vorbereitung (Google Cloud Console, console.cloud.google.com):
1. Projekt anlegen und "YouTube Data API v3" aktivieren.
2. OAuth-Zustimmungsbildschirm: Typ "Extern", dich selbst als Testnutzer eintragen,
   danach "App veröffentlichen" (Status "In Produktion"), sonst läuft der Token nach 7 Tagen ab.
3. Anmeldedaten -> OAuth-Client-ID -> Typ "Desktop-App" erstellen.

Dann gibt es zwei Wege:

  A) Mit Browser auf demselben Rechner:
       python scripts/youtube_auth.py [client_secret.json]

  B) Ohne eigenen Rechner (Tablet/Codespaces):
       YOUTUBE_CLIENT_ID und YOUTUBE_CLIENT_SECRET in .env eintragen, dann
       python scripts/youtube_auth.py --manual
     -> Adresse öffnen, anmelden, danach die komplette Adresse der Fehlerseite
        (beginnt mit http://localhost:8080/?code=...) ins Terminal einfügen.

Die ausgegebenen drei Werte in .env bzw. als GitHub-Secrets eintragen.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reddit_video_bot.config import load_config  # noqa: E402  (lädt .env)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
PORT = int(os.getenv("YOUTUBE_AUTH_PORT", "8080"))
REDIRECT_URI = f"http://localhost:{PORT}/"


def _client_config(secret_file: Path) -> dict:
    """Client-Daten aus client_secret.json oder aus YOUTUBE_CLIENT_ID/SECRET."""
    if secret_file.exists():
        data = json.loads(secret_file.read_text())
        return data if ("installed" in data or "web" in data) else {"installed": data}
    cid, secret = os.getenv("YOUTUBE_CLIENT_ID"), os.getenv("YOUTUBE_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit(f"{secret_file} nicht gefunden und YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET "
                 "fehlen in .env – siehe Anleitung oben in dieser Datei.")
    return {"installed": {
        "client_id": cid,
        "client_secret": secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [REDIRECT_URI],
    }}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("secret_file", nargs="?", default="client_secret.json")
    ap.add_argument("--manual", action="store_true",
                    help="Für Tablet/Codespaces: Adresse nach der Anmeldung selbst einfügen")
    args = ap.parse_args()
    load_config()

    config = _client_config(Path(args.secret_file))
    flow = InstalledAppFlow.from_client_config(config, SCOPES)

    if args.manual:
        # localhost ist http; Google gibt den Code dort nur an die lokale Adresse zurück.
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
        flow.redirect_uri = REDIRECT_URI
        auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        url_file = Path(__file__).resolve().parent.parent / "auth_url.txt"
        url_file.write_text(auth_url, encoding="utf-8")
        print("1) Öffne die Datei auth_url.txt im Editor (Explorer links), markiere ALLES,")
        print("   kopiere es, öffne es in einem neuen Browser-Tab und melde dich mit dem")
        print("   Google-Konto deines YouTube-Kanals an. (Warnung 'nicht überprüft' -> Weiter)")
        print("   (Alternativ ist die Adresse hier:)\n")
        print(auth_url, "\n")
        print("2) Danach zeigt der Browser eine Fehlerseite (localhost nicht erreichbar).")
        print("   Das ist normal! Kopiere die KOMPLETTE Adresse aus der Adressleiste")
        print(f"   (sie beginnt mit {REDIRECT_URI}?code=...)\n")
        pasted = input("3) Hier einfügen und Enter drücken: ").strip()
        if "code=" not in pasted:
            sys.exit("In dieser Adresse steckt kein 'code'. Bitte die komplette Adresse kopieren.")
        flow.fetch_token(authorization_response=pasted)
        creds = flow.credentials
    else:
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        sys.exit("Google hat keinen Refresh-Token ausgegeben. In myaccount.google.com/permissions "
                 "den Zugriff der App entfernen und das Skript erneut ausführen.")
    client = config.get("installed") or config.get("web") or {}
    print("\nFertig! Diese Werte in .env / GitHub-Secrets eintragen:\n")
    print(f"YOUTUBE_CLIENT_ID={client.get('client_id')}")
    print(f"YOUTUBE_CLIENT_SECRET={client.get('client_secret')}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
