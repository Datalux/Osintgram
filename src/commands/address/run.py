from prettytable import PrettyTable
from src import printcolors as pc
import sys
import datetime as dt
import os
from src.CommandFather import CommandFather
import time as time


class Command(CommandFather):

    def __init__(self, status, api):
        super().__init__(status)
        self.status = status
        self.osintgram = api

    def run(self):
        if self.osintgram.check_private_profile():
            return

        pc.printout("Searching for " + self.osintgram.target + " localizations...\n")

        posts = []
        rank_token = self.osintgram.generate_uuid()
        data = self.osintgram.get_api().user_feed(str(self.osintgram.target_id), rank_token=rank_token)
        posts.extend(data.get('items', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            if(int(super().get_option('output_limit')) > 0 and len(posts) >= int(super().get_option('output_limit'))):
                break

            if(int(super().get_option('delay')) > 0):
                time.time.sleep(int(super().get_option('delay')))

            sys.stdout.write("\rCatched %i posts" % len(posts))
            sys.stdout.flush()
            results = self.osintgram.get_api().user_feed(str(self.osintgram.target_id), max_id=next_max_id, rank_token=rank_token)
            posts.extend(results.get('items', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i posts\n" % len(posts))
        sys.stdout.flush()

        locations = {}

        for post in posts:
            if 'location' in post and post['location'] is not None:
                if 'lat' in post['location'] and 'lng' in post['location']:
                    lat = post['location']['lat']
                    lng = post['location']['lng']
                    locations[str(lat) + ', ' + str(lng)] = post.get('taken_at')

        address = {}
        for k, v in locations.items():
            details = self.osintgram.geolocator.reverse(k)
            if not details:
                continue
            unix_timestamp = dt.datetime.fromtimestamp(v)
            address[details.address] = unix_timestamp.strftime('%Y-%m-%d %H:%M:%S')

        sort_addresses = sorted(address.items(), key=lambda p: p[1], reverse=True)

        if len(sort_addresses) > 0:
            output = []
            i = 0
            for address, time in sort_addresses:
                if(int(super().get_option('output_limit')) > 0 and i >= int(super().get_option('output_limit'))):
                    break

                output.append({
                    'post': str(i+1),
                    'address': address,
                    'time': time
                })

                i += 1

            self.status.print_output(output, ['Post', 'Address', 'time'], ['post', 'address', 'time'])
            pc.printout("\nWoohoo! We found " + str(len(sort_addresses)) + " addresses\n", pc.GREEN)

        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)
