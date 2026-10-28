#!/usr/bin/env python3
"""One-time interactive login for the instagrapi backend.

Run this manually from a terminal:

    python scripts/instagrapi_login.py
    # or with sessionid directly:
    python scripts/instagrapi_login.py --sessionid <your_sessionid_cookie>

On success it saves the session to config/instagrapi_session.json, which the
web app's instagrapi backend (src/instagrapi_backend.py) then loads without
ever attempting an interactive login itself.
"""
import argparse
import getpass
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from instagrapi import Client

from src.instagrapi_backend import DEFAULT_SESSION_PATH, resolve_instagrapi_credentials, resolve_instagrapi_proxy, mask_proxy


def challenge_code_handler(username, choice):
    return input(f"\n[2FA Verification] Enter verification code ({choice}) for @{username}: ").strip()


def login_with_sessionid(sessionid: str, session_path: Path, proxy: Optional[str] = None):
    cl = Client()
    if proxy:
        cl.set_proxy(proxy)
    print("\nAttempting login with sessionid cookie...")
    try:
        cl.login_by_sessionid(sessionid.strip())
        cl.dump_settings(session_path)
        print(f"\n[SUCCESS] Successfully logged in as @{cl.username}!")
        print(f"Session saved to {session_path}.")
        return True
    except Exception as e:
        print(f"\n[ERROR] Login via sessionid failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Instagrapi login helper")
    parser.add_argument("--sessionid", help="Instagram sessionid cookie value", default=None)
    parser.add_argument("--proxy", help="Proxy URL (e.g. http://user:pass@host:port or socks5://host:port)", default=None)
    parser.add_argument("-u", "--username", help="Instagram username", default=None)
    parser.add_argument("-p", "--password", help="Instagram password", default=None)
    args = parser.parse_args()

    active_proxy = args.proxy or resolve_instagrapi_proxy()
    if active_proxy:
        print(f"[PROXY] Using proxy: {mask_proxy(active_proxy)}")
        if args.proxy and ("@" in args.proxy or ":" in args.proxy):
            print("  (Tip: Configure proxy in config/credentials.ini or INSTAGRAPI_PROXY to avoid exposing credentials in process list)")

    session_path = Path(DEFAULT_SESSION_PATH)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    if args.sessionid:
        if login_with_sessionid(args.sessionid, session_path, active_proxy):
            return
        sys.exit(1)

    username = args.username
    password = args.password
    if not username or not password:
        file_user, file_pass = resolve_instagrapi_credentials()
        username = username or file_user
        password = password or file_pass

    print("=" * 60)
    print("Osintgram - Instagram Account Login (instagrapi)")
    print("=" * 60)

    if not username:
        username = input("Instagram username: ").strip()

    attempt_pass = password
    while True:
        if not attempt_pass:
            attempt_pass = getpass.getpass(f"Instagram password for @{username} (or press Enter to use sessionid cookie): ").strip()
            if not attempt_pass:
                sess_id = input("\nEnter 'sessionid' cookie from browser (instagram.com -> DevTools -> Application/Storage -> Cookies -> sessionid): ").strip()
                if sess_id:
                    if login_with_sessionid(sess_id, session_path, active_proxy):
                        return
                sys.exit(1)

        cl = Client()
        if active_proxy:
            cl.set_proxy(active_proxy)
        cl.challenge_code_handler = challenge_code_handler

        print(f"\nAttempting login as @{username}...")
        try:
            cl.login(username, attempt_pass)
            cl.dump_settings(session_path)
            print(f"\n[SUCCESS] Successfully logged in as @{username}!")
            print(f"Session saved to {session_path}.")
            print("The web app will use this saved session without requiring another login.")
            return
        except Exception as e:
            err_msg = str(e)
            if "out of date" in err_msg or "needs_upgrade" in err_msg or "Incorrect password" in err_msg:
                print(f"\n[ERROR] Login failed.")
                print("Instagram rejected credentials (wrong password, challenge required, or API login block).")
            else:
                print(f"\n[ERROR] Login failed: {err_msg}")

            print("\nHow would you like to proceed?")
            print("1) Re-enter password")
            print("2) Use 'sessionid' cookie from browser (recommended, bypasses API login block)")
            print("3) Exit")
            try:
                choice = input("Choice [1/2/3]: ").strip()
            except (EOFError, KeyboardInterrupt):
                sys.exit(1)

            if choice == "1":
                attempt_pass = None
                continue
            elif choice == "2":
                sess_id = input("Enter browser 'sessionid' cookie: ").strip()
                if sess_id and login_with_sessionid(sess_id, session_path, active_proxy):
                    return
                sys.exit(1)
            else:
                sys.exit(1)


if __name__ == "__main__":
    main()
