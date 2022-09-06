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

        target_1 = self.osintgram.target
        _followers_target_1 = []
        _followers_target_2 = []
        followers_subset = []

        rank_token = self.osintgram.generate_uuid()
        data = self.osintgram.get_api().user_followers(str(self.osintgram.target_id), rank_token=rank_token)

        _followers_target_1.extend(data.get('users', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            if(int(super().get_option('output_limit')) > 0 and len(_followers_target_1) >= int(super().get_option('output_limit'))):
                break

            if(int(super().get_option('delay')) > 0):
                time.sleep(int(super().get_option('delay')))

            sys.stdout.write("\rCatched %i followers" % len(_followers_target_1))
            sys.stdout.flush()
            results = self.osintgram.get_api().user_followers(str(self.osintgram.target_id), rank_token=rank_token, max_id=next_max_id)
            _followers_target_1.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i followers\n" % len(_followers_target_1))
        sys.stdout.flush()

        print("\n")

        pc.printout("Insert target two username: ", pc.YELLOW)
        line = input()
        self.osintgram.setTarget(line, False)
        target_2 = self.osintgram.target
        if self.osintgram.check_private_profile():
            return


        pc.printout("Searching for " + self.osintgram.target + " followers...\n")

        rank_token = self.osintgram.generate_uuid()
        data = self.osintgram.get_api().user_following(str(self.osintgram.target_id), rank_token=rank_token)

        _followers_target_2.extend(data.get('users', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            if(int(super().get_option('output_limit')) > 0 and len(_followers_target_2) >= int(super().get_option('output_limit'))):
                break

            if(int(super().get_option('delay')) > 0):
                time.sleep(int(super().get_option('delay')))

            sys.stdout.write("\rCatched %i followers" % len(_followers_target_2))
            sys.stdout.flush()
            results = self.osintgram.get_api().user_following(str(self.osintgram.target_id), rank_token=rank_token, max_id=next_max_id)
            _followers_target_2.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i followers\n" % len(_followers_target_2))
        sys.stdout.flush()

        print("\n")
            
        for user in _followers_target_1:
            ff = list(filter(lambda x: x['pk'] == user['pk'], _followers_target_2))
            if(len(ff) > 0):
                f = {
                    'id': ff[0]['pk'],
                    'username': ff[0]['username'],
                    'full_name': ff[0]['full_name']
                }
                followers_subset.append(f)

        t = PrettyTable(['ID', 'Username', 'Full Name'])
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Full Name"] = "l"

        json_data = {}
        followers_subset_list = []

        for node in followers_subset:
            if(int(super().get_option('output_limit')) > 0 and len(followers_subset_list) >= int(super().get_option('output_limit'))):
                    break
            follow = {
                'id': node['id'],
                'username': node['username'],
                'full_name': node['full_name']
            }
            followers_subset_list.append(follow)

        self.status.print_output(followers_subset_list, ['ID', 'Username', 'Full Name'], ['id', 'username', 'full_name'])

        pc.printout("Founded " + str(len(followers_subset)) + " users!\n", pc.GREEN)