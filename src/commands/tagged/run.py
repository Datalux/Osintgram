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
            ids = []
            username = []
            full_name = []
            post_counter = []
            counter = 1

            for post in posts:
                if(int(super().get_option('output_limit')) > 0 and counter >= int(super().get_option('output_limit'))):
                    break

                if "usertags" in post:
                    c = post['usertags']['in']
                    for cc in c:
                        if cc['user']['pk'] not in ids:
                            ids.append(cc.get('user').get('pk'))
                            username.append(cc.get('user').get('username'))
                            full_name.append(cc.get('user').get('full_name'))
                            post_counter.append(1)
                        else:
                            index = ids.index(cc.get('user').get('pk'))
                            post_counter[index] += 1
                        counter = counter + 1
            
            tagged_list = []
            for i in range(len(ids)):
                tag = {
                        'post': post_counter[i],
                        'full_name': full_name[i],
                        'username': username[i],
                        'id': ids[i]
                    }
                tagged_list.append(tag)

            ssort = sorted(tagged_list, key=lambda value: value['post'], reverse=True)

            self.status.print_output(ssort, ['Post', 'Full Name', 'Username', 'ID'], ['post', 'full_name', 'username', 'id'])
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)
