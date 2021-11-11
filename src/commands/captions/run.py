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

        pc.printout("Searching for " + self.osintgram.target + " captions...\n")

        captions = []

        posts = []
        rank_token = self.osintgram.generate_uuid()
        data = self.osintgram.get_api().user_feed(str(self.osintgram.target_id), rank_token=rank_token)
        posts.extend(data.get('items', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            if(int(super().get_option('output_limit')) > 0 and len(posts) >= int(super().get_option('output_limit'))):
                break

            if(int(super().get_option('delay')) > 0):
                time.sleep(int(super().get_option('delay')))

            sys.stdout.write("\rCatched %i posts" % len(posts))
            sys.stdout.flush()
            results = self.osintgram.get_api().user_feed(str(self.osintgram.target_id), max_id=next_max_id, rank_token=rank_token)
            posts.extend(results.get('items', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i posts\n" % len(posts))
        sys.stdout.flush()
        
        counter = 1

        try:
            for item in posts:
                if(int(super().get_option('output_limit')) > 0 and len(captions) >= int(super().get_option('output_limit'))):
                    break

                if "caption" in item:
                    if item["caption"] is not None:
                        text = item["caption"]["text"]
                        captions.append({
                            'item': counter,
                            'caption': text
                        })
                        sys.stdout.write("\rFound %i" % counter)
                        sys.stdout.flush()
                        counter = counter + 1

        except AttributeError:
            pass

        except KeyError:
            pass


        if len(captions):
            pc.printout("\nWoohoo! We found " + str(len(captions)) + " captions\n", pc.GREEN)
            self.status.print_output(captions, ['Caption', 'Text'], ['item', 'caption'])

        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)