import os
import configparser
import sys
from pathlib import Path

from src import printcolors as pc

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "credentials.ini"
config = configparser.ConfigParser(interpolation=None)

try:
    loaded_files = config.read(CONFIG_PATH, encoding="utf-8")
    if not loaded_files:
        pc.printout('Error: file "config/credentials.ini" not found!\n', pc.RED)
        sys.exit(0)
    if "Credentials" not in config:
        pc.printout('Error: missing "Credentials" section in "config/credentials.ini"\n', pc.RED)
        sys.exit(0)
except Exception as e:
    pc.printout("Error: {}\n".format(e), pc.RED)
    sys.exit(0)

def getUsername():
    try:

        username = config["Credentials"]["username"]

        if username == '':
            pc.printout('Error: "username" field cannot be blank in "config/credentials.ini"\n', pc.RED)
            sys.exit(0)

        return username
    except KeyError:
        pc.printout('Error: missing "username" field in "config/credentials.ini"\n', pc.RED)
        sys.exit(0)

def getPassword():
    try:

        password = config["Credentials"]["password"]

        if password == '':
            pc.printout('Error: "password" field cannot be blank in "config/credentials.ini"\n', pc.RED)
            sys.exit(0)

        return password
    except KeyError:
        pc.printout('Error: missing "password" field in "config/credentials.ini"\n', pc.RED)
        sys.exit(0)


def getHikerToken():
    return config["Credentials"].get("hikerapi_token") or os.getenv("HIKERAPI_TOKEN")
