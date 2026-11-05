"""Einmalig lokal ausführen, um den YouTube-Refresh-Token zu erzeugen.

1. In der Google Cloud Console ein Projekt anlegen und die "YouTube Data API v3" aktivieren.
2. OAuth-Zustimmungsbildschirm einrichten (Typ "Extern", dich selbst als Testnutzer eintragen).
3. Anmeldedaten -> OAuth-Client-ID -> Typ "Desktop-App" -> JSON herunterladen
   und als client_secret.json in den Projektordner legen.
4. python scripts/youtube_auth.py
   -> Browser öffnet sich, mit dem YouTube-Kanal-Konto anmelden.
5. Die ausgegebenen drei Werte in .env bzw. als GitHub-Secrets eintragen.
"""
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    secret = Path(sys.argv[1] if len(sys.argv) > 1 else "client_secret.json")
    if not secret.exists():
        sys.exit(f"{secret} nicht gefunden – siehe Anleitung oben in dieser Datei.")
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    info = json.loads(secret.read_text())
    client = info.get("installed") or info.get("web") or {}
    print("\nFertig! Diese Werte in .env / GitHub-Secrets eintragen:\n")
    print(f"YOUTUBE_CLIENT_ID={client.get('client_id')}")
    print(f"YOUTUBE_CLIENT_SECRET={client.get('client_secret')}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
