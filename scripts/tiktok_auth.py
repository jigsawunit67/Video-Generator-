"""Einmalig lokal ausführen, um den TikTok-Refresh-Token zu erzeugen.

1. https://developers.tiktok.com -> "Manage apps" -> App anlegen (Plattform: Desktop)
2. Produkte hinzufügen: "Login Kit" und "Content Posting API" (Direct Post aktivieren)
3. Scopes: user.info.basic, video.publish
4. Redirect-URI eintragen:  http://localhost:8080/callback/
5. Client Key + Client Secret in .env eintragen (TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET)
6. python scripts/tiktok_auth.py
   -> Browser öffnet sich, mit dem TikTok-Konto anmelden, auf das gepostet werden soll.
7. Den ausgegebenen TIKTOK_REFRESH_TOKEN in .env bzw. als GitHub-Secret eintragen
   (gültig 365 Tage).
"""
import argparse
import hashlib
import http.server
import os
import secrets
import sys
import urllib.parse
import webbrowser
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reddit_video_bot.config import load_config  # noqa: E402  (lädt .env)

PORT = int(os.getenv("TIKTOK_AUTH_PORT", "8080"))
REDIRECT_URI = f"http://localhost:{PORT}/callback/"
SCOPES = "user.info.basic,video.publish"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", action="store_true",
                    help="Für Tablet/Codespaces: Browser-Adresse nach der Anmeldung selbst einfügen")
    args = ap.parse_args()
    load_config()
    key, secret = os.getenv("TIKTOK_CLIENT_KEY"), os.getenv("TIKTOK_CLIENT_SECRET")
    if not key or not secret:
        sys.exit("TIKTOK_CLIENT_KEY und TIKTOK_CLIENT_SECRET zuerst in .env eintragen.")

    # PKCE – TikTok (Desktop) erwartet den SHA256-Hash HEX-kodiert
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = hashlib.sha256(verifier.encode()).hexdigest()
    state = secrets.token_urlsafe(16)
    auth_url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    result: dict = {}

    if args.manual:
        print("1) Öffne diese Adresse im Browser und melde dich bei TikTok an:\n")
        print(auth_url, "\n")
        print("2) Nach dem Erlauben zeigt der Browser eine Fehlerseite (localhost nicht erreichbar).")
        print("   Das ist normal! Kopiere die KOMPLETTE Adresse aus der Adressleiste")
        print("   (sie beginnt mit http://localhost:8080/callback/?code=...)\n")
        pasted = input("3) Hier einfügen und Enter drücken: ").strip()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)
        result.update({k: v[0] for k, v in q.items()})
        if "code" not in result and "error" not in result:
            sys.exit("In dieser Adresse steckt kein 'code'. Bitte die komplette Adresse kopieren.")
    else:

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                result.update({k: v[0] for k, v in q.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h2>Fertig – du kannst dieses Fenster schließen.</h2>".encode())

            def log_message(self, *args):
                pass

        print("Öffne im Browser (falls nicht automatisch):\n", auth_url, "\n")
        webbrowser.open(auth_url)
        with http.server.HTTPServer(("localhost", PORT), Handler) as srv:
            while "code" not in result and "error" not in result:
                srv.handle_request()

    if "error" in result:
        sys.exit(f"TikTok-Fehler: {result}")
    if result.get("state") != state:
        sys.exit("State stimmt nicht überein – bitte erneut versuchen.")

    resp = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
        "client_key": key,
        "client_secret": secret,
        "code": result["code"],
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    })
    data = resp.json()
    if "refresh_token" not in data:
        sys.exit(f"Token-Abruf fehlgeschlagen: {data}")
    print("\nFertig! In .env / GitHub-Secrets eintragen:\n")
    print(f"TIKTOK_REFRESH_TOKEN={data['refresh_token']}")
    print(f"\n(Konto open_id: {data.get('open_id')}, Scopes: {data.get('scope')})")


if __name__ == "__main__":
    main()
