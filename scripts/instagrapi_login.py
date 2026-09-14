#!/usr/bin/env python3
"""One-time interactive login for the instagrapi backend.

Run this manually from a terminal (never from the web server) so any 2FA or
challenge prompt Instagram throws can be answered interactively:

    python scripts/instagrapi_login.py

On success it saves the session to config/instagrapi_session.json, which the
web app's instagrapi backend (src/instagrapi_backend.py) then loads without
ever attempting an interactive login itself.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from instagrapi import Client

from src.instagrapi_backend import DEFAULT_SESSION_PATH, resolve_instagrapi_credentials


def challenge_code_handler(username, choice):
    return input(f"Inserisci il codice di verifica ({choice}) ricevuto per {username}: ").strip()


def main():
    username, password = resolve_instagrapi_credentials()
    if not username:
        username = input("Instagram username: ").strip()
    if not password:
        import getpass

        password = getpass.getpass("Instagram password: ")

    cl = Client()
    cl.challenge_code_handler = challenge_code_handler

    print(f"\nAccesso a Instagram come @{username}...")
    try:
        cl.login(username, password)
    except Exception as e:
        print(f"\nLogin fallito: {e}")
        sys.exit(1)

    session_path = Path(DEFAULT_SESSION_PATH)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    cl.dump_settings(session_path)
    print(f"\nLogin riuscito. Sessione salvata in {session_path}.")
    print("Il backend instagrapi userà questa sessione senza richiedere un nuovo login.")


if __name__ == "__main__":
    main()
