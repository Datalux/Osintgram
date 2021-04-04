import configparser
import sys

from src import printcolors as pc

try:
    config = configparser.ConfigParser(interpolation=None)
    config.read("config/credentials.ini")
except FileNotFoundError:
    pc.printout('Error: file "config/credentials.ini" not found!\n', pc.RED)
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
