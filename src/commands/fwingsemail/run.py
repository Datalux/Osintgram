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
from instagram_private_api import ClientThrottledError


class Command(CommandFather):

    def __init__(self, status, api):
        super().__init__(status)
        self.status = status
        self.osintgram = api

    def run(self):
        if self.osintgram.check_private_profile():
            return

        pc.printout("Searching for " + self.osintgram.target + " followings...\n")

        followings = []
        results = []

        try:

            rank_token = self.osintgram.generate_uuid()
            data = self.osintgram.get_api().user_following(str(self.osintgram.target_id), rank_token=rank_token)

            for user in data.get('users', []):
                u = {
                    'id': user['pk'],
                    'username': user['username'],
                    'full_name': user['full_name']
                }
                followings.append(u)

            next_max_id = data.get('next_max_id')
            while next_max_id:
                if(int(super().get_option('output_limit')) > 0 and len(followings) >= int(super().get_option('output_limit'))):
                    break

                if(int(super().get_option('delay')) > 0):
                    time.sleep(int(super().get_option('delay')))

                sys.stdout.write("\rCatched %i followings" % len(followings))
                sys.stdout.flush()
                data = self.osintgram.get_api().user_following(str(self.osintgram.target_id), rank_token=rank_token, max_id=next_max_id)
                
                for user in data.get('users', []):
                    u = {
                        'id': user['pk'],
                        'username': user['username'],
                        'full_name': user['full_name']
                    }
                    followings.append(u)

                next_max_id = results.get('next_max_id')

            sys.stdout.write("\rCatched %i followings\n" % len(followings))
            sys.stdout.flush()

            for follow in followings:
                if(int(super().get_option('output_limit')) > 0 and len(results) >= int(super().get_option('output_limit'))):
                    break

                sys.stdout.write("\rCatched %i followings email" % len(results))
                sys.stdout.flush()

                if(int(super().get_option('delay')) > 0):
                    time.sleep(int(super().get_option('delay')))

                user = self.osintgram.get_api().user_info(str(follow['id']))
                if 'public_email' in user['user'] and user['user']['public_email']:
                    follow['email'] = user['user']['public_email']
                    results.append(follow)
                sys.stdout.write("\rCatched %i followings email" % len(results))
                sys.stdout.flush()

        except ClientThrottledError as e:
            utils.print_error("\nError: Instagram blocked the requests. Please wait a few minutes before you try again.")

        if len(results) > 0:
            self.status.print_output(results, ['ID', 'Username', 'Full Name', 'Email'], ['id', 'username', 'full_name', 'email'])
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)
