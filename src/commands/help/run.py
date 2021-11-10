import yaml
import readline
import signal
from prettytable import PrettyTable
from src import printcolors as pc
from src import utils as utils
import json
import sys
import time


class Command:

    def __init__(self, status, api):
        stream = open("src/setup.yaml", 'r')
        setup = yaml.safe_load(stream)

        cmds = []

        for command in setup['commands']:
            s = yaml.safe_load(open("src/commands/" + command + "/config.yaml", 'r'))
            x = {
                'c': s['name'],
                'd': s['description'],
                'o': list(s['options'].keys()) if s['options'] is not None else ""
            }
            cmds.append(x)

        utils.print_in_table(cmds, ['Command', 'Description', 'Options'], ['c', 'd', 'o'])

        status.release()
