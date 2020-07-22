#!/usr/bin/env python
# -*- coding: utf-8 -*-

from Osintgram import Osintgram
import argparse
import printcolors as pc
import sys


def printlogo():
    pc.printout("________         .__        __                               \n", pc.YELLOW)
    pc.printout("\_____  \   _____|__| _____/  |_  ________________    _____  \n", pc.YELLOW)
    pc.printout(" /   |   \ /  ___/  |/    \   __\/ ___\_  __ \__  \  /     \ \n", pc.YELLOW)
    pc.printout("/    |    \\\___ \|  |   |  \  | / /_/  >  | \// __ \|  Y Y  \\\n", pc.YELLOW)
    pc.printout("\_______  /____  >__|___|  /__| \___  /|__|  (____  /__|_|  /\n", pc.YELLOW)
    pc.printout("        \/     \/        \/    /_____/            \/      \/ \n", pc.YELLOW)
    print('\n')
    pc.printout("Version 0.3 - Developed by Giuseppe Criscione - 2019\n\n", pc.YELLOW)
    pc.printout("Type 'list' to show all allowed commands\n")
    pc.printout("Type 'FILE=y' to save results to files like '<target username>_<command>.txt (deafult is disabled)'\n")
    pc.printout("Type 'FILE=n' to disable saving to files'\n")


def cmdlist():
    pc.printout("FILE=y/n\t")
    print("Enable/disable output in a '<target username>_<command>.txt' file'")
    pc.printout("info\t\t")
    print("Get target info")
    pc.printout("addrs\t\t")
    print("Get all registered addressed by target photos")
    pc.printout("followers\t")
    print("Get target followers")
    pc.printout("followings\t")
    print("Get users followed by target")
    pc.printout("hashtags\t")
    print("Get hashtags used by target")
    pc.printout("likes\t\t")
    print("Get total likes of target's posts")
    pc.printout("comments\t")
    print("Get total comments of target's posts")
    pc.printout("tagged\t\t")
    print("Get list of users tagged by target")
    pc.printout("photodes\t")
    print("Get description of target's photos")
    pc.printout("photos\t\t")
    print("Download target's photos in output folder")
    pc.printout("captions\t")
    print("Get target's photos captions")
    pc.printout("mediatype\t")
    print("Get target's posts type (photo or video)")
    pc.printout("propic\t\t")
    print("Download target's profile picture")
    pc.printout("stories\t\t")
    print("Download target's sories")


printlogo()

parser = argparse.ArgumentParser()
parser.add_argument('id', type=str,  # var = id
                    help='username')
args = parser.parse_args()

api = Osintgram(args.id)

while True:
    pc.printout("Run a command: ", pc.YELLOW)
    cmd = input()
    if cmd == "quit" or cmd == "exit":
        pc.printout("Goodbye!\n", pc.RED)
        sys.exit(0)
    elif cmd == "list" or cmd == "help":
        cmdlist()
    elif cmd == "addrs":
        api.getAddrs()
    elif cmd == "followers":
        api.getFollowers()
    elif cmd == "followings":
        api.getFollowings()
    elif cmd == "hashtags":
        api.getHashtags()
    elif cmd == "likes":
        api.getTotalLikes()
    elif cmd == "comments":
        api.getTotalComments()
    elif cmd == "info":
        api.getUserInfo()
    elif cmd == "tagged":
        api.getPeopleTaggedByUser()
    elif cmd == "photodes":
        api.getPhotoDescription()
    elif cmd == "FILE=y":
        api.setWriteFile(True)
    elif cmd == "FILE=n":
        api.setWriteFile(False)
    elif cmd == "photos":
        api.getUserPhoto()
    elif cmd == "captions":
        api.getCaptions()
    elif cmd == "mediatype":
        api.getMediaType()
    elif cmd == "propic":
        api.getUserPropic()
    elif cmd == "stories":
        api.getUserStories()
    elif cmd == "target":
        api.changeTarget()

    else:
        pc.printout("Unknown command\n", pc.RED)
