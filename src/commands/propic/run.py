from prettytable import PrettyTable
from src import printcolors as pc
import urllib
from instagram_private_api import ClientError
import json
from src.CommandFather import CommandFather


class Command(CommandFather):

    def __init__(self, status, api):
        super().__init__(status)
        self.status = status
        self.osintgram = api

    def run(self):
        try:
            super().create_folder_if_not_exists()
            
            endpoint = 'users/{user_id!s}/full_detail_info/'.format(**{'user_id': self.osintgram.target_id})
            content = self.osintgram.get_api()._call_api(endpoint)

            data = content['user_detail']['user']

            if "hd_profile_pic_url_info" in data:
                URL = data["hd_profile_pic_url_info"]['url']
            else:
                #get better quality photo
                items = len(data['hd_profile_pic_versions'])
                URL = data["hd_profile_pic_versions"][items-1]['url']

            if URL != "":
                end = super().get_option('output_path') + "/" + self.osintgram.target + "_propic.jpg"
                urllib.request.urlretrieve(URL, end)
                pc.printout("Target propic saved in output folder\n", pc.GREEN)

            else:
                pc.printout("Sorry! No results found :-(\n", pc.RED)
        
        except ClientError as e:
            error = json.loads(e.error_response)
            print(error['message'])
            print(error['error_title'])
            self.status.release()
