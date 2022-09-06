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
            
        pc.printout("Searching for " + self.osintgram.target + " total likes...\n")

        like_counter = 0
        posts = 0

        data = []
        result = self.osintgram.get_api().user_feed(str(self.osintgram.target_id))
        data.extend(result.get('items', []))

        next_max_id = result.get('next_max_id')
        while next_max_id:
            if(int(super().get_option('output_limit')) > 0 and len(data) >= int(super().get_option('output_limit'))):
                break

            if(int(super().get_option('delay')) > 0):
                time.sleep(int(super().get_option('delay')))

            results = self.osintgram.get_api().user_feed(str(self.osintgram.target_id), max_id=next_max_id)
            data.extend(results.get('items', []))
            next_max_id = results.get('next_max_id')

        for post in data:
            if(int(super().get_option('output_limit')) > 0 and posts == int(super().get_option('output_limit'))):
                break
                
            like_counter += post['like_count']
            posts += 1

        output = {
                'like_counter': like_counter,
                'posts': posts
            }

        self.status.print_output([output], ['Likes', 'Posts'], ['like_counter', 'posts'])