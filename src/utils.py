from __future__ import print_function

import sys
from os import environ

from prettytable import PrettyTable

from src import printcolors as pc
from src import artwork

import json
import csv


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
    print("\n")

    t = PrettyTable(header)
    for i in header:
        t.align[i] = "l"
    for d in data:
        t.add_row([d[i] for i in values])

    print(t)

def print_in_json(data, config):
    json_file_name = "output/" + config.get_target() + "_" + config.get_command() + ".json"
    with open(json_file_name, 'w') as f:
        json.dump(data, f)

def print_in_csv(data, keys, config):
    csv_file_name = "output/" + config.get_target() + "_" + config.get_command() + ".csv"
    with open(csv_file_name, 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)


def print_error(message):
    pc.printout(message +"\n", pc.RED)

class Completer(object):  # Custom completer

    def __init__(self, options):
        if(options is not None):
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
