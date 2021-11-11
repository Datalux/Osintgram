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

    def __get_comments__(self, media_id):
        comments = []

        result = self.osintgram.get_api().media_comments(str(media_id))
        comments.extend(result.get('comments', []))

        next_max_id = result.get('next_max_id')
        while next_max_id:
            results = self.osintgram.get_api().media_comments(str(media_id), max_id=next_max_id)
            comments.extend(results.get('comments', []))
            next_max_id = results.get('next_max_id')

        return comments

    def run(self):

        if self.osintgram.check_private_profile():
            return

        pc.printout("Searching for users who commented...\n")

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

        if len(posts) > 0:
            output = []

            item_counter = 1
            for post in posts:
                if(int(super().get_option('output_limit')) > 0 and len(output) >= int(super().get_option('output_limit'))):
                    break
                    
                comments = self.__get_comments__(post['id'])
                for comment in comments:
                    output.append({
                        'item': item_counter,
                        'comment': comment['text']
                    })
                    item_counter += 1

            self.status.print_output(output, ['Comment', 'Text'], ['item', 'comment'])

        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)
