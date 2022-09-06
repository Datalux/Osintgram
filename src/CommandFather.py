import yaml
import readline
import signal
from prettytable import PrettyTable
from src import printcolors as pc
from src import utils as utils
import json
import sys
import os
import time


class CommandFather(object):

    def __init__(self, status):
        self.commands = []
        self.path = status.get_path()
        self.status = status
        stream = open(self.path, 'r')
        self.config = yaml.safe_load(stream)
        self.options_values = self.config['options']

    def get_options(self):
        return self.config['options']

    def get_option(self, option_key):
        return self.options_values[option_key]

    def options(self):
        t = PrettyTable(['Option', 'Value'])
        for key, value in self.options_values.items():
            t.add_row([key, str(value)])
        print(t)

    def set(self):
        i = 1
        for key, value in self.options_values.items():
            print(str(i) + ". " + key)
            i = i + 1
        try:
            index = input("Choose option: ")
            key = list(self.options_values.keys())[int(index) - 1]
            while True:
                v = input("[" + key + "] Choose a value: ")
                if v == "":
                    utils.print_error("Empty value")
                else:
                    self.options_values[key] = v
                    break
            print(self.options_values)

        except ValueError:
            utils.print_error("Not a number")

        except IndexError:
            utils.print_error("Value not in range (1-" + str(i-1) + ")")

    def exit(self):
        self.status.release()

    def help(self):
        print(self.config['description'])

    def create_folder_if_not_exists(self):
        if not os.path.isdir(self.get_option('output_path')):
            os.makedirs(self.get_option('output_path'))