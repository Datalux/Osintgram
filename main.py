#!/usr/bin/env python
# -*- coding: utf-8 -*-

from src.Osintgram import Osintgram
import argparse
from src import printcolors as pc
import sys
import signal
import readline

commands = ["quit", "exit", "list", "help", "addrs", "captions", "comments", "followers",
            "followings", "fwersemail", "fwingsemail", "hashtags", "info", "likes",
            "mediatype", "photodes", "photos", "propic", "stories", "tagged", "target",
            "wcommented", "wtagged"]


def printlogo():
    pc.printout("________         .__        __                               \n", pc.YELLOW)
    pc.printout("\_____  \   _____|__| _____/  |_  ________________    _____  \n", pc.YELLOW)
    pc.printout(" /   |   \ /  ___/  |/    \   __\/ ___\_  __ \__  \  /     \ \n", pc.YELLOW)
    pc.printout("/    |    \\\___ \|  |   |  \  | / /_/  >  | \// __ \|  Y Y  \\\n", pc.YELLOW)
    pc.printout("\_______  /____  >__|___|  /__| \___  /|__|  (____  /__|_|  /\n", pc.YELLOW)
    pc.printout("        \/     \/        \/    /_____/            \/      \/ \n", pc.YELLOW)
    print('\n')
    pc.printout("Version 0.9 - Developed by Giuseppe Criscione - 2019\n\n", pc.YELLOW)
    pc.printout("Type 'list' to show all allowed commands\n")
    pc.printout("Type 'FILE=y' to save results to files like '<target username>_<command>.txt (deafult is disabled)'\n")
    pc.printout("Type 'FILE=n' to disable saving to files'\n")
    pc.printout("Type 'JSON=y' to export results to a JSON files like '<target username>_<command>.json (deafult is "
                "disabled)'\n")
    pc.printout("Type 'JSON=n' to disable exporting to files'\n")


def cmdlist():
    pc.printout("FILE=y/n\t")
    print("Enable/disable output in a '<target username>_<command>.txt' file'")
    pc.printout("JSON=y/n\t")
    print("Enable/disable export in a '<target username>_<command>.json' file'")
    pc.printout("addrs\t\t")
    print("Get all registered addressed by target photos")
    pc.printout("captions\t")
    print("Get target's photos captions")
    pc.printout("comments\t")
    print("Get total comments of target's posts")
    pc.printout("followers\t")
    print("Get target followers")
    pc.printout("followings\t")
    print("Get users followed by target")
    pc.printout("fwersemail\t")
    print("Get email of target followers")
    pc.printout("fwingsemail\t")
    print("Get email of users followed by target")
    pc.printout("hashtags\t")
    print("Get hashtags used by target")
    pc.printout("info\t\t")
    print("Get target info")
    pc.printout("likes\t\t")
    print("Get total likes of target's posts")
    pc.printout("mediatype\t")
    print("Get target's posts type (photo or video)")
    pc.printout("photodes\t")
    print("Get description of target's photos")
    pc.printout("photos\t\t")
    print("Download target's photos in output folder")
    pc.printout("propic\t\t")
    print("Download target's profile picture")
    pc.printout("stories\t\t")
    print("Download target's sories")
    pc.printout("tagged\t\t")
    print("Get list of users tagged by target")
    pc.printout("target\t\t")
    print("Set new target")
    pc.printout("wcommented\t")
    print("Get a list of user who commented target's photos")
    pc.printout("wtagged\t\t")
    print("Get a list of user who tagged target")


def signal_handler(sig, frame):
    pc.printout("\nGoodbye!\n", pc.RED)
    sys.exit(0)


def completer(text, state):
    options = [i for i in commands if i.startswith(text)]
    if state < len(options):
        return options[state]
    else:
        return None


signal.signal(signal.SIGINT, signal_handler)
readline.parse_and_bind("tab: complete")
readline.set_completer(completer)

printlogo()

parser = argparse.ArgumentParser(description='Osintgram is a OSINT tool on Instagram. It offers an interactive shell '
                                             'to perform analysis on Instagram account of any users by its nickname ')
parser.add_argument('id', type=str,  # var = id
                    help='username')
parser.add_argument('-j', '--json', help='save commands output as JSON file', action='store_true')
parser.add_argument('-f', '--file', help='save output in a file', action='store_true')

args = parser.parse_args()

api = Osintgram(args.id, args.file, args.json)

while True:
    pc.printout("Run a command: ", pc.YELLOW)
    cmd = input()
    if cmd == "quit" or cmd == "exit":
        pc.printout("Goodbye!\n", pc.RED)
        sys.exit(0)
    elif cmd == "list" or cmd == "help":
        cmdlist()
    elif cmd == "addrs":
        api.get_addrs()
    elif cmd == "captions":
        api.get_captions()
    elif cmd == "comments":
        api.get_total_comments()
    elif cmd == "followers":
        api.get_followers()
    elif cmd == "followings":
        api.get_followings()
    elif cmd == 'fwersemail':
        api.get_fwersemail()
    elif cmd == 'fwingsemail':
        api.get_fwingsemail()
    elif cmd == "hashtags":
        api.get_hashtags()
    elif cmd == "info":
        api.get_user_info()
    elif cmd == "likes":
        api.get_total_likes()
    elif cmd == "mediatype":
        api.get_media_type()
    elif cmd == "photodes":
        api.get_photo_description()
    elif cmd == "photos":
        api.get_user_photo()
    elif cmd == "propic":
        api.get_user_propic()
    elif cmd == "stories":
        api.get_user_stories()
    elif cmd == "tagged":
        api.get_people_tagged_by_user()
    elif cmd == "target":
        api.change_target()
    elif cmd == "wcommented":
        api.get_people_who_commented()
    elif cmd == "wtagged":
        api.get_people_who_tagged()
    elif cmd == "FILE=y":
        api.set_write_file(True)
    elif cmd == "FILE=n":
        api.set_write_file(False)
    elif cmd == "JSON=y":
        api.set_json_dump(True)
    elif cmd == "JSON=n":
        api.set_json_dump(False)
    else:
        pc.printout("Unknown command\n", pc.RED)
