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

        data = []
        counter = 0

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

        try:
            super().create_folder_if_not_exists()

            for item in data:
                if(int(super().get_option('output_limit')) > 0 and counter == int(super().get_option('output_limit'))):
                    break

                if "image_versions2" in item:
                    counter = counter + 1
                    url = item["image_versions2"]["candidates"][0]["url"]
                    photo_id = item["id"]
                    end = super().get_option('output_path') + "/" + self.osintgram.target + "_" + photo_id + ".jpg"
                    urllib.request.urlretrieve(url, end)
                    sys.stdout.write("\rDownloaded %i" % counter)
                    sys.stdout.flush()
                else:
                    carousel = item["carousel_media"]
                    for i in carousel:
                        if(int(super().get_option('output_limit')) > 0 and counter == int(super().get_option('output_limit'))):
                            break
                        counter = counter + 1
                        url = i["image_versions2"]["candidates"][0]["url"]
                        photo_id = i["id"]
                        end = super().get_option('output_path') + "/" + self.osintgram.target + "_" + photo_id + ".jpg"
                        urllib.request.urlretrieve(url, end)
                        sys.stdout.write("\rDownloaded %i" % counter)
                        sys.stdout.flush()

        except AttributeError:
            pass

        except KeyError:
            pass

        sys.stdout.write(" photos")
        sys.stdout.flush()

        pc.printout("\nWoohoo! We downloaded " + str(counter) + " photos (saved in " + super().get_option('output_path') +  " folder) \n", pc.GREEN)
