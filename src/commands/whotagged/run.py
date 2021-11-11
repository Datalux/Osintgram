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

        pc.printout("Searching for users who tagged target...\n")

        posts = []
        rank_token = self.osintgram.generate_uuid()
        data = self.osintgram.get_api().usertag_feed(str(self.osintgram.target_id), rank_token=rank_token)
        posts.extend(data.get('items', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            if(int(super().get_option('output_limit')) > 0 and len(posts) >= int(super().get_option('output_limit'))):
                break

            if(int(super().get_option('delay')) > 0):
                time.sleep(int(super().get_option('delay')))

            sys.stdout.write("\rCatched %i posts" % len(posts))
            sys.stdout.flush()
            results = self.osintgram.get_api().usertag_feed(str(self.osintgram.target_id), max_id=next_max_id, rank_token=rank_token)
            posts.extend(results.get('items', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i posts\n" % len(posts))
        sys.stdout.flush()

        if len(posts) > 0:
            users = []

            for post in posts:
                if(int(super().get_option('output_limit')) > 0 and len(users) >= int(super().get_option('output_limit'))):
                    break

                if not any(u['id'] == post['user']['pk'] for u in users):
                    user = {
                        'id': post['user']['pk'],
                        'username': post['user']['username'],
                        'full_name': post['user']['full_name'],
                        'counter': 1
                    }
                    users.append(user)
                else:
                    for user in users:
                        if user['id'] == post['user']['pk']:
                            user['counter'] += 1
                            break

            ssort = sorted(users, key=lambda value: value['counter'], reverse=True)
            self.status.print_output(ssort, ['Photos', 'ID', 'Username', 'Full Name'], ['counter', 'id', 'username', 'full_name'])
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)