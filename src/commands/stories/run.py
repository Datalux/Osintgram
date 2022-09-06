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
            
        pc.printout("Searching for " + self.osintgram.target + " stories...\n")

        data = self.osintgram.get_api().user_reel_media(str(self.osintgram.target_id))

        counter = 0

        if data['items'] is not None:  # no stories avaibile
            counter = data['media_count']
            for i in data['items']:
                story_id = i["id"]
                if i["media_type"] == 1:  # it's a photo
                    url = i['image_versions2']['candidates'][0]['url']
                    end = super().get_option('output_path') + "/" + self.osintgram.target + "_" + story_id + ".jpg"
                    urllib.request.urlretrieve(url, end)

                elif i["media_type"] == 2:  # it's a gif or video
                    url = i['video_versions'][0]['url']
                    end = super().get_option('output_path') + "/" + self.osintgram.target + "_" + story_id + ".mp4"
                    urllib.request.urlretrieve(url, end)

        if counter > 0:
            pc.printout(str(counter) + " target stories saved in output folder\n", pc.GREEN)
        else:
            pc.printout("Sorry! " + self.osintgram.target + " has no stories available :-(\n", pc.RED)
