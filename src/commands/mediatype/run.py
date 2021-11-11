from prettytable import PrettyTable
from src import printcolors as pc
import sys
import time
import urllib
import os


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

        counter = 0
        photo_counter = 0
        video_counter = 0

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
            if "media_type" in post:
                if post["media_type"] == 1:
                    photo_counter = photo_counter + 1
                elif post["media_type"] == 2:
                    video_counter = video_counter + 1
                elif post["media_type"] == 8: # it's a carousel
                    for c in post['carousel_media']:
                        if c["media_type"] == 1:
                            photo_counter = photo_counter + 1
                        elif c["media_type"] == 2:
                            video_counter = video_counter + 1
                        counter = counter + 1
                counter = counter + 1

        if counter > 0:
            data = {
                    "photos": photo_counter,
                    "videos": video_counter
                }

            self.status.print_output([data], ['Photos', 'Videos'], ['photos', 'videos'])

        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)