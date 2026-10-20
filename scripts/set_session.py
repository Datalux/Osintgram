#!/usr/bin/env python3
"""Save an active Instagram web session via sessionid."""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from instagrapi import Client


def main():
    if len(sys.argv) > 1:
        sid = sys.argv[1].strip()
    else:
        sid = input("Wklej sessionid: ").strip()

    # Fix accidental double paste
    if len(sid) > 60 and len(sid) % 2 == 0 and sid[: len(sid) // 2] == sid[len(sid) // 2 :]:
        sid = sid[: len(sid) // 2]
        print("Wykryto i naprawiono podwójnie wklejony sessionid.")

    cl = Client()
    try:
        cl.login_by_sessionid(sid)
        out = Path("config/instagrapi_session.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(out)
        print(f"\n✓ Zalogowano pomyślnie jako @{cl.username} (ID: {cl.user_id})!")
        print(f"✓ Sesja zapisana w: {out}")
    except Exception as e:
        print(f"\n✗ Błąd logowania przez sessionid: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
