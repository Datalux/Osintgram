import yaml
import readline
import signal
from prettytable import PrettyTable
from src import printcolors as pc
from src import utils as utils
import json
import sys
import time

from src.CommandFather import CommandFather


class Command(CommandFather):

    def __init__(self, status, api):
        super().__init__(status)
        self.status = status
        self.osintgram = api

        while True:
            pc.printout("Insert new target username: ", pc.YELLOW)
            line = input()
            if self.osintgram.setTarget(line, True):
                self.status.release()
                break
            else:
                utils.print_error("User not found")
