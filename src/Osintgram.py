import datetime
import json
import sys
import urllib
import os
import codecs

import requests

from geopy.geocoders import Nominatim
from instagram_private_api import Client as AppClient
from instagram_private_api import ClientCookieExpiredError, ClientLoginRequiredError, ClientError

from prettytable import PrettyTable

from src import printcolors as pc


class Osintgram:
    api = None
    api2 = None
    geolocator = Nominatim()
    user_id = None
    target_id = None
    is_private = True
    following = False
    target = ""
    writeFile = False
    jsonDump = False

    def __init__(self, target, is_file, is_json):
        u = self.__getUsername__()
        p = self.__getPassword__()
        print("\nAttempt to login...")
        self.login(u, p)
        self.setTarget(target)
        self.writeFile = is_file
        self.jsonDump = is_json

    def setTarget(self, target):
        self.target = target
        user = self.get_user(target)
        self.target_id = user['id']
        self.is_private = user['is_private']
        self.following = self.check_following()
        self.__printTargetBanner__()

    def __getUsername__(self):
        try:
            u = open("config/username.conf", "r").read()
            u = u.replace("\n", "")
            return u
        except FileNotFoundError:
            pc.printout("Error: file \"config/username.conf\" not found!", pc.RED)
            pc.printout("\n")
            sys.exit(0)

    def __getPassword__(self):
        try:
            p = open("config/pw.conf", "r").read()
            p = p.replace("\n", "")
            return p
        except FileNotFoundError:
            pc.printout("Error: file \"config/pw.conf\" not found!", pc.RED)
            pc.printout("\n")
            sys.exit(0)

    def __get_feed__(self):
        data = []

        result = self.api.user_feed(str(self.target_id))
        data.extend(result.get('items', []))

        next_max_id = result.get('next_max_id')
        while next_max_id:
            results = self.api.user_feed(str(self.target_id), max_id=next_max_id)
            data.extend(results.get('items', []))
            next_max_id = results.get('next_max_id')

        return data

    def __get_comments__(self, media_id):
        comments = []

        result = self.api.media_comments(str(media_id))
        comments.extend(result.get('comments', []))

        next_max_id = result.get('next_max_id')
        while next_max_id:
            results = self.api.media_comments(str(media_id), max_id=next_max_id)
            comments.extend(results.get('comments', []))
            next_max_id = results.get('next_max_id')

        return comments

    def __printTargetBanner__(self):
        pc.printout("\nLogged as ", pc.GREEN)
        pc.printout(self.api.username, pc.CYAN)
        pc.printout(". Target: ", pc.GREEN)
        pc.printout(str(self.target), pc.CYAN)
        pc.printout(" [" + str(self.target_id) + "]")
        if self.is_private:
            pc.printout(" [PRIVATE PROFILE]", pc.BLUE)
        if self.following:
            pc.printout(" [FOLLOWING]", pc.GREEN)
        else:
            pc.printout(" [NOT FOLLOWING]", pc.RED)

        print('\n')

    def change_target(self):
        pc.printout("Insert new target username: ", pc.YELLOW)
        line = input()
        self.setTarget(line)
        return

    def get_addrs(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target localizations...\n")

        data = self.__get_feed__()

        locations = {}

        for post in data:
            if 'location' in post and post['location'] is not None:
                lat = post['location']['lat']
                lng = post['location']['lng']
                locations[str(lat) + ', ' + str(lng)] = post.get('taken_at')

        address = {}
        for k, v in locations.items():
            details = self.geolocator.reverse(k)
            unix_timestamp = datetime.datetime.fromtimestamp(v)
            address[details.address] = unix_timestamp.strftime('%Y-%m-%d %H:%M:%S')

        sort_addresses = sorted(address.items(), key=lambda p: p[1], reverse=True)

        if len(sort_addresses) > 0:
            t = PrettyTable()

            t.field_names = ['Post', 'Address', 'time']
            t.align["Post"] = "l"
            t.align["Address"] = "l"
            t.align["Time"] = "l"
            pc.printout("\nWoohoo! We found " + str(len(sort_addresses)) + " addresses\n", pc.GREEN)

            i = 1

            json_data = {}
            addrs_list = []

            for address, time in sort_addresses:
                t.add_row([str(i), address, time])

                if self.jsonDump:
                    addr = {
                        'address': address,
                        'time': time
                    }
                    addrs_list.append(addr)

                i = i + 1

            if self.writeFile:
                file_name = "output/" + self.target + "_addrs.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['address'] = addrs_list
                json_file_name = "output/" + self.target + "_addrs.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_captions(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target captions...\n")

        captions = []

        data = self.__get_feed__()
        counter = 0

        try:
            for item in data:
                if "caption" in item:
                    if item["caption"] is not None:
                        text = item["caption"]["text"]
                        captions.append(text)
                        counter = counter + 1
                        sys.stdout.write("\rFound %i" % counter)
                        sys.stdout.flush()

        except AttributeError:
            pass

        except KeyError:
            pass

        json_data = {}

        if counter > 0:
            pc.printout("\nWoohoo! We found " + str(counter) + " captions\n", pc.GREEN)

            file = None

            if self.writeFile:
                file_name = "output/" + self.target + "_captions.txt"
                file = open(file_name, "w")

            for s in captions:
                print(s + "\n")

                if self.writeFile:
                    file.write(s + "\n")

            if self.jsonDump:
                json_data['captions'] = captions
                json_file_name = "output/" + self.target + "_followings.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            if file is not None:
                file.close()

        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

        return

    def get_total_comments(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target total comments...\n")

        comments_counter = 0
        posts = 0

        data = self.__get_feed__()

        for post in data:
            comments_counter += post['comment_count']
            posts += 1

        if self.writeFile:
            file_name = "output/" + self.target + "_comments.txt"
            file = open(file_name, "w")
            file.write(str(comments_counter) + " comments in " + str(posts) + " posts\n")
            file.close()

        if self.jsonDump:
            json_data = {
                'comment_counter': comments_counter,
                'posts': posts
            }
            json_file_name = "output/" + self.target + "_comments.json"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        pc.printout(str(comments_counter), pc.MAGENTA)
        pc.printout(" comments in " + str(posts) + " posts\n")

    def get_followers(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target followers...\n")

        followers = []

        rank_token = AppClient.generate_uuid()
        data = self.api.user_followers(str(self.target_id), rank_token=rank_token)

        for user in data['users']:
            u = {
                'id': user['pk'],
                'username': user['username'],
                'full_name': user['full_name']
            }
            followers.append(u)

        t = PrettyTable(['ID', 'Username', 'Full Name'])
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Full Name"] = "l"

        json_data = {}
        followings_list = []

        for node in followers:
            t.add_row([str(node['id']), node['username'], node['full_name']])

            if self.jsonDump:
                follow = {
                    'id': node['id'],
                    'username': node['username'],
                    'full_name': node['full_name']
                }
                followings_list.append(follow)

        if self.writeFile:
            file_name = "output/" + self.target + "_followers.txt"
            file = open(file_name, "w")
            file.write(str(t))
            file.close()

        if self.jsonDump:
            json_data['followers'] = followers
            json_file_name = "output/" + self.target + "_followers.json"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        print(t)

    def get_followings(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target followings...\n")

        followings = []

        rank_token = AppClient.generate_uuid()
        data = self.api.user_following(str(self.target_id), rank_token=rank_token)

        for user in data['users']:
            u = {
                'id': user['pk'],
                'username': user['username'],
                'full_name': user['full_name']
            }
            followings.append(u)

        t = PrettyTable(['ID', 'Username', 'Full Name'])
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Full Name"] = "l"

        json_data = {}
        followings_list = []

        for node in followings:
            t.add_row([str(node['id']), node['username'], node['full_name']])

            if self.jsonDump:
                follow = {
                    'id': node['id'],
                    'username': node['username'],
                    'full_name': node['full_name']
                }
                followings_list.append(follow)

        if self.writeFile:
            file_name = "output/" + self.target + "_followings.txt"
            file = open(file_name, "w")
            file.write(str(t))
            file.close()

        if self.jsonDump:
            json_data['followings'] = followings_list
            json_file_name = "output/" + self.target + "_followings.json"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        print(t)

    def get_hashtags(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target hashtags...\n")

        hashtags = []
        counter = 1
        texts = []

        data = self.api.user_feed(str(self.target_id))
        texts.extend(data.get('items', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            results = self.api.user_feed(str(self.target_id), max_id=next_max_id)
            texts.extend(results.get('items', []))
            next_max_id = results.get('next_max_id')

        for post in texts:
            if post['caption'] is not None:
                caption = post['caption']['text']
                for s in caption.split():
                    if s.startswith('#'):
                        hashtags.append(s.encode('UTF-8'))
                        counter += 1

        if len(hashtags) > 0:
            hashtag_counter = {}

            for i in hashtags:
                if i in hashtag_counter:
                    hashtag_counter[i] += 1
                else:
                    hashtag_counter[i] = 1

            ssort = sorted(hashtag_counter.items(), key=lambda value: value[1], reverse=True)

            file = None
            json_data = {}
            hashtags_list = []

            if self.writeFile:
                file_name = "output/" + self.target + "_hashtags.txt"
                file = open(file_name, "w")

            for k, v in ssort:
                hashtag = str(k.decode('utf-8'))
                print(str(v) + ". " + hashtag)
                if self.writeFile:
                    file.write(str(v) + ". " + hashtag + "\n")
                if self.jsonDump:
                    hashtags_list.append(hashtag)

            if file is not None:
                file.close()

            if self.jsonDump:
                json_data['hashtags'] = hashtags_list
                json_file_name = "output/" + self.target + "_hashtags.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user_info(self):
        content = requests.get("https://www.instagram.com/" + str(self.target) + "/?__a=1")

        if content.status_code == 404:
            print("Oops... " + str(self.target) + " non exist, please enter a valid username.")
            sys.exit(2)

        data = content.json()
        data = data['graphql']['user']

        pc.printout("[ID] ", pc.GREEN)
        pc.printout(str(data['id']) + '\n')
        pc.printout("[FULL NAME] ", pc.RED)
        pc.printout(str(data['full_name']) + '\n')
        pc.printout("[BIOGRAPHY] ", pc.CYAN)
        pc.printout(str(data['biography']) + '\n')
        pc.printout("[FOLLOWED] ", pc.BLUE)
        pc.printout(str(data['edge_followed_by']['count']) + '\n')
        pc.printout("[FOLLOW] ", pc.GREEN)
        pc.printout(str(data['edge_follow']['count']) + '\n')
        pc.printout("[BUSINESS ACCOUNT] ", pc.RED)
        pc.printout(str(data['is_business_account']) + '\n')
        if data['is_business_account']:
            pc.printout("[BUSINESS CATEGORY] ")
            pc.printout(str(data['business_category_name']) + '\n')
        pc.printout("[VERIFIED ACCOUNT] ", pc.CYAN)
        pc.printout(str(data['is_verified']) + '\n')
        if data['business_email']:
            pc.printout("[BUSINESS EMAIL] ", pc.BLUE)
            pc.printout(str(data['business_email']) + '\n')
        pc.printout("[HD PROFILE PIC] ", pc.GREEN)
        pc.printout(str(data['profile_pic_url_hd']) + '\n')
        if data['connected_fb_page']:
            pc.printout("[FB PAGE] ", pc.RED)
            pc.printout(str(data['business_email']) + '\n')

        if self.jsonDump:
            user = {
                'id': data['id'],
                'full_name': data['full_name'],
                'biography': data['biography'],
                'edge_followed_by': data['edge_followed_by']['count'],
                'edge_follow': data['edge_follow']['count'],
                'is_business_account': data['is_business_account'],
                'is_verified': data['is_verified'],
                'profile_pic_url_hd': data['profile_pic_url_hd']
            }
            if data['business_email']:
                user['business_email'] = data['business_email']
            if data['connected_fb_page']:
                user['connected_fb_page'] = data['connected_fb_page']

            json_file_name = "output/" + self.target + "_info.json"
            with open(json_file_name, 'w') as f:
                json.dump(user, f)

    def get_total_likes(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target total likes...\n")

        like_counter = 0
        posts = 0

        data = self.__get_feed__()

        for post in data:
            like_counter += post['like_count']
            posts += 1

        if self.writeFile:
            file_name = "output/" + self.target + "_likes.txt"
            file = open(file_name, "w")
            file.write(str(like_counter) + " likes in " + str(like_counter) + " posts\n")
            file.close()

        if self.jsonDump:
            json_data = {
                'like_counter': like_counter,
                'posts': like_counter
            }
            json_file_name = "output/" + self.target + "_likes.json"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        pc.printout(str(like_counter), pc.MAGENTA)
        pc.printout(" likes in " + str(posts) + " posts\n")

    def get_media_type(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target captions...\n")

        counter = 0
        photo_counter = 0
        video_counter = 0

        data = self.__get_feed__()

        for post in data:
            if "media_type" in post:
                if post["media_type"] == 1:
                    photo_counter = photo_counter + 1
                elif post["media_type"] == 2:
                    video_counter = video_counter + 1
                counter = counter + 1
                sys.stdout.write("\rChecked %i" % counter)
                sys.stdout.flush()

        sys.stdout.write(" posts")
        sys.stdout.flush()

        if counter > 0:

            if self.writeFile:
                file_name = "output/" + self.target + "_mediatype.txt"
                file = open(file_name, "w")
                file.write(str(photo_counter) + " photos and " + str(video_counter) + " video posted by target\n")
                file.close()

            pc.printout("\nWoohoo! We found " + str(photo_counter) + " photos and " + str(video_counter) +
                        " video posted by target\n", pc.GREEN)

            if self.jsonDump:
                json_data = {
                    "photos": photo_counter,
                    "videos": video_counter
                }
                json_file_name = "output/" + self.target + "_mediatype.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_people_who_commented(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for users who commented...\n")

        data = self.__get_feed__()
        users = []

        for post in data:
            comments = self.__get_comments__(post['id'])
            for comment in comments:
                if not any(u['id'] == comment['user']['pk'] for u in users):
                    user = {
                        'id': comment['user']['pk'],
                        'username': comment['user']['username'],
                        'full_name': comment['user']['full_name'],
                        'counter': 1
                    }
                    users.append(user)
                else:
                    for user in users:
                        if user['id'] == comment['user']['pk']:
                            user['counter'] += 1
                            break

        if len(users) > 0:
            ssort = sorted(users, key=lambda value: value['counter'], reverse=True)

            json_data = {}

            t = PrettyTable()

            t.field_names = ['Comments', 'ID', 'Username', 'Full Name']
            t.align["Comments"] = "l"
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"

            for u in ssort:
                t.add_row([str(u['counter']), u['id'], u['username'], u['full_name']])

            print(t)

            if self.writeFile:
                file_name = "output/" + self.target + "_users_who_commented.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['users_who_commented'] = ssort
                json_file_name = "output/" + self.target + "_users_who_commented.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_people_who_tagged(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for users who tagged target...\n")

        posts = []

        result = self.api.usertag_feed(self.target_id)
        posts.extend(result.get('items', []))

        next_max_id = result.get('next_max_id')
        while next_max_id:
            results = self.api.user_feed(str(self.target_id), max_id=next_max_id)
            posts.extend(results.get('items', []))
            next_max_id = results.get('next_max_id')

        if len(posts) > 0:
            pc.printout("\nWoohoo! We found " + str(len(posts)) + " photos\n", pc.GREEN)

            users = []

            for post in posts:
                if not any(u['id'] == post['user']['pk'] for u in users):
                    user = {
                        'id': post['user']['pk'],
                        'username': post['user']['username'],
                        'full_name': post['user']['full_name'],
                        'counter': 1
                    }
                    users.append(user)
                else:
                    for user in users:
                        if user['id'] == post['user']['pk']:
                            user['counter'] += 1
                            break

            ssort = sorted(users, key=lambda value: value['counter'], reverse=True)

            json_data = {}

            t = PrettyTable()

            t.field_names = ['Photos', 'ID', 'Username', 'Full Name']
            t.align["Photos"] = "l"
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"

            for u in ssort:
                t.add_row([str(u['counter']), u['id'], u['username'], u['full_name']])

            print(t)

            if self.writeFile:
                file_name = "output/" + self.target + "_users_who_tagged.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['users_who_tagged'] = ssort
                json_file_name = "output/" + self.target + "_users_who_tagged.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_photo_description(self):
        if self.check_private_profile():
            return

        content = requests.get("https://www.instagram.com/" + str(self.target) + "/?__a=1")
        data = content.json()

        dd = data['graphql']['user']['edge_owner_to_timeline_media']['edges']

        if len(dd) > 0:
            pc.printout("\nWoohoo! We found " + str(len(dd)) + " descriptions\n", pc.GREEN)

            count = 1

            t = PrettyTable(['Photo', 'Description'])
            t.align["Photo"] = "l"
            t.align["Description"] = "l"

            json_data = {}
            descriptions_list = []

            for i in dd:
                node = i.get('node')
                descr = node.get('accessibility_caption')
                t.add_row([str(count), descr])

                if self.jsonDump:
                    description = {
                        'description': descr
                    }
                    descriptions_list.append(description)

                count += 1

            if self.writeFile:
                file_name = "output/" + self.target + "_photodes.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['descriptions'] = descriptions_list
                json_file_name = "output/" + self.target + "_descriptions.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user_photo(self):
        if self.check_private_profile():
            return

        limit = -1
        pc.printout("How many photos you want to download (default all): ", pc.YELLOW)
        user_input = input()
        try:
            if user_input == "":
                pc.printout("Downloading all photos avaible...\n")
            else:
                limit = int(user_input)
                pc.printout("Downloading " + user_input + " photos...\n")

        except ValueError:
            pc.printout("Wrong value entered\n", pc.RED)
            return

        data = []
        counter = 0

        result = self.api.user_feed(str(self.target_id))
        data.extend(result.get('items', []))

        next_max_id = result.get('next_max_id')
        while next_max_id:
            results = self.api.user_feed(str(self.target_id), max_id=next_max_id)
            data.extend(results.get('items', []))
            next_max_id = results.get('next_max_id')

        try:
            for item in data:
                if counter == limit:
                    break
                if "image_versions2" in item:
                    counter = counter + 1
                    url = item["image_versions2"]["candidates"][0]["url"]
                    photo_id = item["id"]
                    end = "output/" + self.target + "_" + photo_id + ".jpg"
                    urllib.request.urlretrieve(url, end)
                    sys.stdout.write("\rDownloaded %i" % counter)
                    sys.stdout.flush()
                else:
                    carousel = item["carousel_media"]
                    for i in carousel:
                        if counter == limit:
                            break
                        counter = counter + 1
                        url = i["image_versions2"]["candidates"][0]["url"]
                        photo_id = i["id"]
                        end = "output/" + self.target + "_" + photo_id + ".jpg"
                        urllib.request.urlretrieve(url, end)
                        sys.stdout.write("\rDownloaded %i" % counter)
                        sys.stdout.flush()

        except AttributeError:
            pass

        except KeyError:
            pass

        sys.stdout.write(" photos")
        sys.stdout.flush()

        pc.printout("\nWoohoo! We downloaded " + str(counter) + " photos (saved in output/ folder) \n", pc.GREEN)

    def get_user_propic(self):
        content = requests.get("https://www.instagram.com/" + str(self.target) + "/?__a=1")

        if content.status_code == 404:
            print("Oops... " + str(self.target) + " non exist, please enter a valid username.")
            sys.exit(2)

        data = content.json()

        uurl = data["graphql"]["user"]
        if "profile_pic_url_hd" in uurl:
            URL = data["graphql"]["user"]["profile_pic_url_hd"]
        else:
            URL = data["graphql"]["user"]["profile_pic_url"]

        if URL != "":
            end = "output/" + self.target + "_propic.jpg"
            urllib.request.urlretrieve(URL, end)
            pc.printout("Target propic saved in output folder\n", pc.GREEN)

        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user_stories(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target stories...\n")

        data = self.api.user_reel_media(str(self.target_id))

        counter = 0

        if data['items'] is not None:  # no stories avaibile
            counter = data['media_count']
            for i in data['items']:
                story_id = i["id"]
                if i["media_type"] == 1:  # it's a photo
                    url = i['image_versions2']['candidates'][0]['url']
                    end = "output/" + self.target + "_" + story_id + ".jpg"
                    urllib.request.urlretrieve(url, end)

                elif i["media_type"] == 2:  # it's a gif or video
                    url = i['video_versions'][0]['url']
                    end = "output/" + self.target + "_" + story_id + ".mp4"
                    urllib.request.urlretrieve(url, end)

        if counter > 0:
            pc.printout(str(counter) + " target stories saved in output folder\n", pc.GREEN)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_people_tagged_by_user(self):
        pc.printout("Searching for users tagged by target...\n")

        ids = []
        username = []
        full_name = []
        post = []
        counter = 1

        data = self.__get_feed__()

        try:
            for i in data:
                if "usertags" in i:
                    c = i.get('usertags').get('in')
                    for cc in c:
                        if cc.get('user').get('pk') not in ids:
                            ids.append(cc.get('user').get('pk'))
                            username.append(cc.get('user').get('username'))
                            full_name.append(cc.get('user').get('full_name'))
                            post.append(1)
                        else:
                            index = ids.index(cc.get('user').get('pk'))
                            post[index] += 1
                        counter = counter + 1
        except AttributeError as ae:
            pc.printout("\nERROR: an error occurred: ", pc.RED)
            print(ae)
            print("")
            pass

        if len(ids) > 0:
            t = PrettyTable()

            t.field_names = ['Posts', 'Full Name', 'Username', 'ID']
            t.align["Posts"] = "l"
            t.align["Full Name"] = "l"
            t.align["Username"] = "l"
            t.align["ID"] = "l"

            pc.printout("\nWoohoo! We found " + str(len(ids)) + " (" + str(counter) + ") users\n", pc.GREEN)

            json_data = {}
            tagged_list = []

            for i in range(len(ids)):
                t.add_row([post[i], full_name[i], username[i], str(ids[i])])

                if self.jsonDump:
                    tag = {
                        'post': post[i],
                        'full_name': full_name[i],
                        'username': username[i],
                        'id': ids[i]
                    }
                    tagged_list.append(tag)

            if self.writeFile:
                file_name = "output/" + self.target + "_tagged.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['tagged'] = tagged_list
                json_file_name = "output/" + self.target + "_tagged.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user(self, username):
        content = requests.get("https://www.instagram.com/" + username + "/?__a=1")

        if content.status_code == 404:
            print("Oops... " + str(self.target) + " non exist, please enter a valid username.")
            sys.exit(2)

        data = content.json()

        if self.writeFile:
            file_name = "output/" + self.target + "_user_id.txt"
            file = open(file_name, "w")
            file.write(str(data['graphql']['user']['id']))
            file.close()

        user = dict()
        user['id'] = data['graphql']['user']['id']
        user['is_private'] = data['graphql']['user']['is_private']

        return user

    def set_write_file(self, flag):
        if flag:
            pc.printout("Write to file: ")
            pc.printout("enabled", pc.GREEN)
            pc.printout("\n")
        else:
            pc.printout("Write to file: ")
            pc.printout("disabled", pc.RED)
            pc.printout("\n")

        self.writeFile = flag

    def set_json_dump(self, flag):
        if flag:
            pc.printout("Export to JSON: ")
            pc.printout("enabled", pc.GREEN)
            pc.printout("\n")
        else:
            pc.printout("Export to JSON: ")
            pc.printout("disabled", pc.RED)
            pc.printout("\n")

        self.jsonDump = flag

    def login(self, u, p):
        try:
            settings_file = "config/settings.json"
            if not os.path.isfile(settings_file):
                # settings file does not exist
                print('Unable to find file: {0!s}'.format(settings_file))

                # login new
                self.api = AppClient(auto_patch=True, authenticate=True, username=u, password=p,
                                     on_login=lambda x: self.onlogin_callback(x, settings_file))

            else:
                with open(settings_file) as file_data:
                    cached_settings = json.load(file_data, object_hook=self.from_json)
                # print('Reusing settings: {0!s}'.format(settings_file))

                # reuse auth settings
                self.api = AppClient(
                    username=u, password=p,
                    settings=cached_settings,
                    on_login=lambda x: self.onlogin_callback(x, settings_file))

        except (ClientCookieExpiredError, ClientLoginRequiredError) as e:
            print('ClientCookieExpiredError/ClientLoginRequiredError: {0!s}'.format(e))

            # Login expired
            # Do relogin but use default ua, keys and such
            self.api = AppClient(auto_patch=True, authenticate=True, username=u, password=p,
                                 on_login=lambda x: self.onlogin_callback(x, settings_file))

        except ClientError as e:
            # pc.printout('ClientError {0!s} (Code: {1:d}, Response: {2!s})'.format(e.msg, e.code, e.error_response), pc.RED)
            error = json.loads(e.error_response)
            pc.printout(error['message'], pc.RED)
            pc.printout("\n")
            exit(9)

    def to_json(self, python_object):
        if isinstance(python_object, bytes):
            return {'__class__': 'bytes',
                    '__value__': codecs.encode(python_object, 'base64').decode()}
        raise TypeError(repr(python_object) + ' is not JSON serializable')

    def from_json(self, json_object):
        if '__class__' in json_object and json_object['__class__'] == 'bytes':
            return codecs.decode(json_object['__value__'].encode(), 'base64')
        return json_object

    def onlogin_callback(self, api, new_settings_file):
        cache_settings = api.settings
        with open(new_settings_file, 'w') as outfile:
            json.dump(cache_settings, outfile, default=self.to_json)
            # print('SAVED: {0!s}'.format(new_settings_file))

    def check_following(self):
        endpoint = 'users/{user_id!s}/full_detail_info/'.format(**{'user_id': self.target_id})
        return self.api._call_api(endpoint)['user_detail']['user']['friendship_status']['following']

    def check_private_profile(self):
        if self.is_private and not self.following:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
            send = input("Do you want send a follow request? [Y/N]: ")
            if send.lower() == "y":
                self.api.friendships_create(self.target_id)
                print("Sent a follow request to target. Use this command after target accepting the request.")

            return True
        return False

    def get_fwersemail(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for emails of target followers... this can take a few minutes\n")

        followers = []

        rank_token = AppClient.generate_uuid()
        data = self.api.user_followers(str(self.target_id), rank_token=rank_token)

        for user in data['users']:
            u = {
                'id': user['pk'],
                'username': user['username'],
                'full_name': user['full_name']
            }
            followers.append(u)

        results = []

        for follow in followers:
            content = requests.get("https://www.instagram.com/" + str(follow['username']) + "/?__a=1")
            data = content.json()
            data = data['graphql']['user']
            if data['business_email']:
                follow['email'] = data['business_email']
                results.append(follow)

        if len(results) > 0:

            t = PrettyTable(['ID', 'Username', 'Full Name', 'Email'])
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"
            t.align["Email"] = "l"

            json_data = {}

            for node in results:
                t.add_row([str(node['id']), node['username'], node['full_name'], node['email']])

            if self.writeFile:
                file_name = "output/" + self.target + "_fwersemail.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['followers_email'] = results
                json_file_name = "output/" + self.target + "_fwersemail.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_fwingsemail(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for emails of users followed by target... this can take a few minutes\n")

        followings = []

        rank_token = AppClient.generate_uuid()
        data = self.api.user_following(str(self.target_id), rank_token=rank_token)

        for user in data['users']:
            u = {
                'id': user['pk'],
                'username': user['username'],
                'full_name': user['full_name']
            }
            followings.append(u)

        results = []

        for follow in followings:
            content = requests.get("https://www.instagram.com/" + str(follow['username']) + "/?__a=1")
            data = content.json()
            data = data['graphql']['user']
            if data['business_email']:
                follow['email'] = data['business_email']
                results.append(follow)

        if len(results) > 0:

            t = PrettyTable(['ID', 'Username', 'Full Name', 'Email'])
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"
            t.align["Email"] = "l"

            json_data = {}

            for node in results:
                t.add_row([str(node['id']), node['username'], node['full_name'], node['email']])

            if self.writeFile:
                file_name = "output/" + self.target + "_fwingsemail.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['followings_email'] = results
                json_file_name = "output/" + self.target + "_fwingsemail.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)
