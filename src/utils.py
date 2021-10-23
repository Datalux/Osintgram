from __future__ import print_function

import sys
from os import environ

from prettytable import PrettyTable

from src import printcolors as pc
from src import artwork


def printlogo(version, author):
    pc.printout(artwork.ascii_art, pc.YELLOW)
    pc.printout("\nVersion " + version + " - Developed by " + author + "\n\n", pc.YELLOW)
    pc.printout("Type 'list' to show all allowed commands\n")

def completer(commands, text, state):
    options = [i for i in commands if i.startswith(text)]
    if state < len(options):
        return options[state]
    else:
        return None    


def print_in_table(data, header, values):
    t = PrettyTable(header)
    for i in header:
        t.align[i] = "l"

    for d in data:
        t.add_row([d[i] for i in values])

    print(t)



class Completer(object):  # Custom completer

    def __init__(self, options):
        self.options = sorted(options)

    def complete(self, text, state):
        if state == 0:  # on first trigger, build possible matches
            if not text:
                self.matches = self.options[:]
            else:
                self.matches = [s for s in self.options
                                if s and s.startswith(text)]

        # return match indexed by state
        try:
            return self.matches[state]
        except IndexError:
            return None

    def display_matches(self, substitution, matches, longest_match_length):
        line_buffer = readline.get_line_buffer()
        columns = environ.get("COLUMNS", 80)

        print()

        tpl = "{:<" + str(int(max(map(len, matches)) * 1.2)) + "}"

        buffer = ""
        for match in matches:
            match = tpl.format(match[len(substitution):])
            if len(buffer + match) > columns:
                print(buffer)
                buffer = ""
            buffer += match

        if buffer:
            print(buffer)

        print("> ", end="")
        print(line_buffer, end="")
        sys.stdout.flush()


