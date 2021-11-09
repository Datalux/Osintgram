import yaml
import readline
import signal
from prettytable import PrettyTable
from src import printcolors as pc
from src import utils as utils
from src import Command
import json
import sys
import time

from src import CommandFather as CommandFather


class Command():

    def __init__(self, status, api):
        # super().__init__(status, api)
        self.commands = []
        self.path = status.get_path()
        self.status = status
        stream = open(self.path, 'r')
        self.config = yaml.safe_load(stream)
        self.options_values = self.config['options']
        self.osintgram = api

    def get_options(self):
        return self.config['options']

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
            v = input("[" + key + "] Choose a value: ")
            self.options_values[key] = v
            print(self.options_values)

        except ValueError:
            utils.print_error("Not a number")

        except IndexError:
            utils.print_error("Value not in range (1-" + str(i-1) + ")")

    def run(self):
        if self.osintgram.check_private_profile():
            return

        pc.printout("Searching for " + self.osintgram.target + " followers...\n")

        followers = []

        rank_token = self.osintgram.generate_uuid()
        data = self.osintgram.get_api().user_followers(str(self.osintgram.target_id), rank_token=rank_token)

        followers.extend(data.get('users', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            if(int(self.options_values['output_limit']) > 0 and len(followers) > int(self.options_values['output_limit'])):
                break

            if(int(self.options_values['delay']) > 0):
                time.sleep(int(self.options_values['delay']))

            sys.stdout.write("\rCatched %i followers" % len(followers))
            sys.stdout.flush()
            results = self.osintgram.get_api().user_followers(str(self.osintgram.target_id), rank_token=rank_token, max_id=next_max_id)
            followers.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i followers" % len(followers))
        sys.stdout.flush()

        data = []
        for user in followers:
            u = {
                'id': user['pk'],
                'username': user['username'],
                'full_name': user['full_name']
            }
            data.append(u)

        # utils.print_in_table(data, ['ID', 'Username', 'Full Name'], ['id', 'username', 'full_name'])
        self.status.print_output(data, ['ID', 'Username', 'Full Name'], ['id', 'username', 'full_name'])
