#!/usr/bin/env python3

from src.Osintgram import Osintgram
import argparse
from src import printcolors as pc
from src import artwork
import sys
import signal

is_windows = False

try:
    import gnureadline  
except: 
    is_windows = True
    import pyreadline


def printlogo():
    pc.printout(artwork.ascii_art, pc.YELLOW)
    pc.printout("\nVersion 1.1 - Developed by Giuseppe Criscione\n\n", pc.YELLOW)
    pc.printout("Type 'list' to show all allowed commands\n")
    pc.printout("Type 'FILE=y' to save results to files like '<target username>_<command>.txt (default is disabled)'\n")
    pc.printout("Type 'FILE=n' to disable saving to files'\n")
    pc.printout("Type 'JSON=y' to export results to a JSON files like '<target username>_<command>.json (default is "
                "disabled)'\n")
    pc.printout("Type 'JSON=n' to disable exporting to files'\n")


def cmdlist():
    pc.printout("FILE=y/n\t")
    print("Enable/disable output in a '<target username>_<command>.txt' file'")
    pc.printout("JSON=y/n\t")
    print("Enable/disable export in a '<target username>_<command>.json' file'")
    pc.printout("addrs\t\t")
    print("Get all registered addressed by target photos")
    pc.printout("cache\t\t")
    print("Clear cache of the tool")
    pc.printout("captions\t")
    print("Get target's photos captions")
    pc.printout("commentdata\t")
    print("Get a list of all the comments on the target's posts")
    pc.printout("comments\t")
    print("Get total comments of target's posts")
    pc.printout("followers\t")
    print("Get target followers")
    pc.printout("followings\t")
    print("Get users followed by target")
    pc.printout("fwersemail\t")
    print("Get email of target followers")
    pc.printout("fwersnumber\t")
    print("Get phone number of target followers")
    pc.printout("fwersubset\t")
    print("Get the list of users who follow both target1 and target2")
    pc.printout("fwingsemail\t")
    print("Get email of users followed by target")
    pc.printout("fwingsnumber\t")
    print("Get phone number of users followed by target")
    pc.printout("fwingsubset\t")
    print("Get the list of users followed by both target1 and target2")        
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
    print("Download target's stories")
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

def _quit():
    pc.printout("Goodbye!\n", pc.RED)
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
if is_windows:
    pyreadline.Readline().parse_and_bind("tab: complete")
    pyreadline.Readline().set_completer(completer)
else:
    gnureadline.parse_and_bind("tab: complete")
    gnureadline.set_completer(completer)

parser = argparse.ArgumentParser(description='Osintgram is a OSINT tool on Instagram. It offers an interactive shell '
                                             'to perform analysis on Instagram account of any users by its nickname ')
parser.add_argument('id', type=str,  # var = id
                    help='username')
parser.add_argument('-C','--cookies', help='clear\'s previous cookies', action="store_true")
parser.add_argument('-j', '--json', help='save commands output as JSON file', action='store_true')
parser.add_argument('-f', '--file', help='save output in a file', action='store_true')
parser.add_argument('-c', '--command', help='run in single command mode & execute provided command', action='store')
parser.add_argument('-o', '--output', help='where to store photos', action='store')

args = parser.parse_args()


api = Osintgram(args.id, args.file, args.json, args.command, args.output, args.cookies)



commands = {
    'list':             cmdlist,
    'help':             cmdlist,
    'quit':             _quit,
    'exit':             _quit,
    'addrs':            api.get_addrs,
    'cache':            api.clear_cache,
    'captions':         api.get_captions,
    "commentdata":      api.get_comment_data,
    'comments':         api.get_total_comments,
    'followers':        api.get_followers,
    'followings':       api.get_followings,
    'fwersemail':       api.get_fwersemail,
    'fwersnumber':      api.get_fwersnumber,
    'fwersubset':       api.get_followers_subset,
    'fwingsemail':      api.get_fwingsemail,
    'fwingsnumber':     api.get_fwingsnumber,
    'fwingsubset':      api.get_followings_subset,
    'hashtags':         api.get_hashtags,
    'info':             api.get_user_info,
    'likes':            api.get_total_likes,
    'mediatype':        api.get_media_type,
    'photodes':         api.get_photo_description,
    'photos':           api.get_user_photo,
    'propic':           api.get_user_propic,
    'stories':          api.get_user_stories,
    'tagged':           api.get_people_tagged_by_user,
    'target':           api.change_target,
    'wcommented':       api.get_people_who_commented,
    'wtagged':          api.get_people_who_tagged
}


signal.signal(signal.SIGINT, signal_handler)
if is_windows:
    pyreadline.Readline().parse_and_bind("tab: complete")
    pyreadline.Readline().set_completer(completer)
else:
    gnureadline.parse_and_bind("tab: complete")
    gnureadline.set_completer(completer)

if not args.command:
    printlogo()


while True:
    if args.command:
        cmd = args.command
        _cmd = commands.get(args.command)
    else:
        signal.signal(signal.SIGINT, signal_handler)
        if is_windows:
            pyreadline.Readline().parse_and_bind("tab: complete")
            pyreadline.Readline().set_completer(completer)
        else:
            gnureadline.parse_and_bind("tab: complete")
            gnureadline.set_completer(completer)
        pc.printout("Run a command: ", pc.YELLOW)
        cmd = input()

        _cmd = commands.get(cmd)

    if _cmd:
        _cmd()
    elif cmd == "FILE=y":
        api.set_write_file(True)
    elif cmd == "FILE=n":
        api.set_write_file(False)
    elif cmd == "JSON=y":
        api.set_json_dump(True)
    elif cmd == "JSON=n":
        api.set_json_dump(False)
    elif cmd == "":
        print("")
    else:
        pc.printout("Unknown command\n", pc.RED)

    if args.command:
        break
