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
            if(int(super().get_option('output_limit')) > 0 and len(followers) >= int(super().get_option('output_limit'))):
                break

            if(int(super().get_option('delay')) > 0):
                time.sleep(int(super().get_option('delay')))

            sys.stdout.write("\rCatched %i followers" % len(followers))
            sys.stdout.flush()
            results = self.osintgram.get_api().user_followers(str(self.osintgram.target_id), rank_token=rank_token, max_id=next_max_id)
            followers.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i followers\n" % len(followers))
        sys.stdout.flush()

        data = []
        for user in followers:
            u = {
                'id': user['pk'],
                'username': user['username'],
                'full_name': user['full_name']
            }
            data.append(u)

        self.status.print_output(data, ['ID', 'Username', 'Full Name'], ['id', 'username', 'full_name'])
