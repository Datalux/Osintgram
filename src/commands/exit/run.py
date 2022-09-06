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
        pc.printout("\nGoodbye!\n", pc.RED)
        sys.exit(0)