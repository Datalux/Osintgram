import datetime
import json
import sys
import urllib
import os
import codecs
from pathlib import Path

import requests
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

from geopy.geocoders import Nominatim
from instagram_private_api import Client as AppClient
from instagram_private_api import ClientCookieExpiredError, ClientLoginRequiredError, ClientError, ClientThrottledError

from prettytable import PrettyTable

from src import printcolors as pc
from src import config


class Osintgram:
    api = None
    api2 = None
    geolocator = Nominatim(user_agent="http")
    user_id = None
    target_id = None
    is_private = True
    following = False
    target = ""
    writeFile = False
    jsonDump = False
    cli_mode = False
    output_dir = "output"


    def __init__(self, target, is_file, is_json, is_cli, output_dir, clear_cookies):
        self.output_dir = output_dir or self.output_dir
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        u = config.getUsername()
        p = config.getPassword()
        self.clear_cookies(clear_cookies)
        self.cli_mode = is_cli
        if not is_cli:
          print("\nAttempt to login...")
        self.login(u, p)
        self.setTarget(target, True)
        self.writeFile = is_file
        self.jsonDump = is_json

    def clear_cookies(self,clear_cookies):
        if clear_cookies:
            self.clear_cache()

    def setTarget(self, target, show_output):
        self.target = target
        user = self.get_user(target)
        self.target_id = user['id']
        self.is_private = user['is_private']
        self.following = self.check_following()
        if(show_output):
            self.__printTargetBanner__()

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
        self.setTarget(line, True)
        return

    def get_addrs(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " localizations...\n")

        data = self.__get_feed__()

        locations = {}

        for post in data:
            if 'location' in post and post['location'] is not None:
                if 'lat' in post['location'] and 'lng' in post['location']:
                    lat = post['location']['lat']
                    lng = post['location']['lng']
                    locations[str(lat) + ', ' + str(lng)] = post.get('taken_at')

        address = {}
        for k, v in locations.items():
            details = self.geolocator.reverse(k)
            if not details:
                continue
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
                file_name = self.output_dir + "/" + self.target + "_addrs.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['address'] = addrs_list
                json_file_name = self.output_dir + "/" + self.target + "_addrs.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_captions(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " captions...\n")

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
                file_name = self.output_dir + "/" + self.target + "_captions.txt"
                file = open(file_name, "w")

            for s in captions:
                print(s + "\n")

                if self.writeFile:
                    file.write(s + "\n")

            if self.jsonDump:
                json_data['captions'] = captions
                json_file_name = self.output_dir + "/" + self.target + "_followings.json"
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

        pc.printout("Searching for " + self.target + " total comments...\n")

        comments_counter = 0
        posts = 0

        data = self.__get_feed__()

        for post in data:
            comments_counter += post['comment_count']
            posts += 1

        if self.writeFile:
            file_name = self.output_dir + "/" + self.target + "_comments.txt"
            file = open(file_name, "w")
            file.write(str(comments_counter) + " comments in " + str(posts) + " posts\n")
            file.close()

        if self.jsonDump:
            json_data = {
                'comment_counter': comments_counter,
                'posts': posts
            }
            json_file_name = self.output_dir + "/" + self.target + "_comments.json"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        pc.printout(str(comments_counter), pc.MAGENTA)
        pc.printout(" comments in " + str(posts) + " posts\n")

    def get_comment_data(self):
        if self.check_private_profile():
            return

        pc.printout("Retrieving all comments, this may take a moment...\n")
        data = self.__get_feed__()
        
        _comments = []
        t = PrettyTable(['POST ID', 'ID', 'Username', 'Comment'])
        t.align["POST ID"] = "l"
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Comment"] = "l"

        for post in data:
            post_id = post.get('id')
            comments = self.api.media_n_comments(post_id)
            for comment in comments:
                t.add_row([post_id, comment.get('user_id'), comment.get('user').get('username'), comment.get('text')])
                comment = {
                        "post_id": post_id,
                        "user_id":comment.get('user_id'), 
                        "username": comment.get('user').get('username'),
                        "comment": comment.get('text')
                    }
                _comments.append(comment)
        
        print(t)
        if self.writeFile:
            file_name = self.output_dir + "/" + self.target + "_comment_data.txt"
            with open(file_name, 'w') as f:
                f.write(str(t))
                f.close()
        
        if self.jsonDump:
            file_name_json = self.output_dir + "/" + self.target + "_comment_data.json"
            with open(file_name_json, 'w') as f:
                f.write("{ \"Comments\":[ \n")
                f.write(',\n'.join(json.dumps(comment) for comment in _comments) + '\n')
                f.write("]} ")


    def get_followers(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " followers...\n")

        _followers = []
        followers = []


        rank_token = AppClient.generate_uuid()
        data = self.api.user_followers(str(self.target_id), rank_token=rank_token)

        _followers.extend(data.get('users', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            sys.stdout.write("\rCatched %i followers" % len(_followers))
            sys.stdout.flush()
            results = self.api.user_followers(str(self.target_id), rank_token=rank_token, max_id=next_max_id)
            _followers.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i followers" % len(_followers))
        sys.stdout.flush()

        print("\n")
            
        for user in _followers:
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
            file_name = self.output_dir + "/" + self.target + "_followers.txt"
            file = open(file_name, "w")
            file.write(str(t))
            file.close()

        if self.jsonDump:
            json_data['followers'] = followers
            json_file_name = self.output_dir + "/" + self.target + "_followers.json"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        print(t)

    def get_followings(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " followings...\n")

        _followings = []
        followings = []

        rank_token = AppClient.generate_uuid()
        data = self.api.user_following(str(self.target_id), rank_token=rank_token)

        _followings.extend(data.get('users', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            sys.stdout.write("\rCatched %i followings" % len(_followings))
            sys.stdout.flush()
            results = self.api.user_following(str(self.target_id), rank_token=rank_token, max_id=next_max_id)
            _followings.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i followings" % len(_followings))
        sys.stdout.flush()

        print("\n")

        for user in _followings:
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
            file_name = self.output_dir + "/" + self.target + "_followings.txt"
            file = open(file_name, "w")
            file.write(str(t))
            file.close()

        if self.jsonDump:
            json_data['followings'] = followings_list
            json_file_name = self.output_dir + "/" + self.target + "_followings.json"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        print(t)

    def get_hashtags(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " hashtags...\n")

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
                file_name = self.output_dir + "/" + self.target + "_hashtags.txt"
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
                json_file_name = self.output_dir + "/" + self.target + "_hashtags.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user_info(self):
        try:
            endpoint = 'users/{user_id!s}/full_detail_info/'.format(**{'user_id': self.target_id})
            content = self.api._call_api(endpoint)
           
            data = content['user_detail']['user']

            pc.printout("[ID] ", pc.GREEN)
            pc.printout(str(data['pk']) + '\n')
            pc.printout("[FULL NAME] ", pc.RED)
            pc.printout(str(data['full_name']) + '\n')
            pc.printout("[BIOGRAPHY] ", pc.CYAN)
            pc.printout(str(data['biography']) + '\n')
            pc.printout("[FOLLOWED] ", pc.BLUE)
            pc.printout(str(data['follower_count']) + '\n')
            pc.printout("[FOLLOW] ", pc.GREEN)
            pc.printout(str(data['following_count']) + '\n')
            pc.printout("[BUSINESS ACCOUNT] ", pc.RED)
            pc.printout(str(data['is_business']) + '\n')
            if data['is_business']:
                if not data['can_hide_category']:
                    pc.printout("[BUSINESS CATEGORY] ")
                    pc.printout(str(data['category']) + '\n')
            pc.printout("[VERIFIED ACCOUNT] ", pc.CYAN)
            pc.printout(str(data['is_verified']) + '\n')
            if 'public_email' in data and data['public_email']:
                pc.printout("[EMAIL] ", pc.BLUE)
                pc.printout(str(data['public_email']) + '\n')
            pc.printout("[HD PROFILE PIC] ", pc.GREEN)
            pc.printout(str(data['hd_profile_pic_url_info']['url']) + '\n')
            if 'fb_page_call_to_action_id' in data and data['fb_page_call_to_action_id']: 
                pc.printout("[FB PAGE] ", pc.RED)
                pc.printout(str(data['connected_fb_page']) + '\n')
            if 'whatsapp_number' in data and data['whatsapp_number']:
                pc.printout("[WHATSAPP NUMBER] ", pc.GREEN)
                pc.printout(str(data['whatsapp_number']) + '\n')
            if 'city_name' in data and data['city_name']:
                pc.printout("[CITY] ", pc.YELLOW)
                pc.printout(str(data['city_name']) + '\n')
            if 'address_street' in data and data['address_street']:
                pc.printout("[ADDRESS STREET] ", pc.RED)
                pc.printout(str(data['address_street']) + '\n')
            if 'contact_phone_number' in data and data['contact_phone_number']:
                pc.printout("[CONTACT PHONE NUMBER] ", pc.CYAN)
                pc.printout(str(data['contact_phone_number']) + '\n')

            if self.jsonDump:
                user = {
                    'id': data['pk'],
                    'full_name': data['full_name'],
                    'biography': data['biography'],
                    'edge_followed_by': data['follower_count'],
                    'edge_follow': data['following_count'],
                    'is_business_account': data['is_business'],
                    'is_verified': data['is_verified'],
                    'profile_pic_url_hd': data['hd_profile_pic_url_info']['url']
                }
                if 'public_email' in data and data['public_email']:
                    user['email'] = data['public_email']
                if 'fb_page_call_to_action_id' in data and data['fb_page_call_to_action_id']: 
                    user['connected_fb_page'] = data['fb_page_call_to_action_id']
                if 'whatsapp_number' in data and data['whatsapp_number']:
                    user['whatsapp_number'] = data['whatsapp_number']
                if 'city_name' in data and data['city_name']:
                    user['city_name'] = data['city_name']
                if 'address_street' in data and data['address_street']:
                    user['address_street'] = data['address_street']
                if 'contact_phone_number' in data and data['contact_phone_number']:
                    user['contact_phone_number'] = data['contact_phone_number']

                json_file_name = self.output_dir + "/" + self.target + "_info.json"
                with open(json_file_name, 'w') as f:
                    json.dump(user, f)

        except ClientError as e:
            print(e)
            pc.printout("Oops... " + str(self.target) + " non exist, please enter a valid username.", pc.RED)
            pc.printout("\n")
            exit(2)

    def get_total_likes(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " total likes...\n")

        like_counter = 0
        posts = 0

        data = self.__get_feed__()

        for post in data:
            like_counter += post['like_count']
            posts += 1

        if self.writeFile:
            file_name = self.output_dir + "/" + self.target + "_likes.txt"
            file = open(file_name, "w")
            file.write(str(like_counter) + " likes in " + str(like_counter) + " posts\n")
            file.close()

        if self.jsonDump:
            json_data = {
                'like_counter': like_counter,
                'posts': like_counter
            }
            json_file_name = self.output_dir + "/" + self.target + "_likes.json"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        pc.printout(str(like_counter), pc.MAGENTA)
        pc.printout(" likes in " + str(posts) + " posts\n")

    def get_media_type(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " captions...\n")

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
                file_name = self.output_dir + "/" + self.target + "_mediatype.txt"
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
                json_file_name = self.output_dir + "/" + self.target + "_mediatype.json"
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
                file_name = self.output_dir + "/" + self.target + "_users_who_commented.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['users_who_commented'] = ssort
                json_file_name = self.output_dir + "/" + self.target + "_users_who_commented.json"
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
                file_name = self.output_dir + "/" + self.target + "_users_who_tagged.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['users_who_tagged'] = ssort
                json_file_name = self.output_dir + "/" + self.target + "_users_who_tagged.json"
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
                file_name = self.output_dir + "/" + self.target + "_photodes.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['descriptions'] = descriptions_list
                json_file_name = self.output_dir + "/" + self.target + "_descriptions.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user_photo(self):
        if self.check_private_profile():
            return

        limit = -1
        if self.cli_mode:
            user_input = ""
        else:
            pc.printout("How many photos you want to download (default all): ", pc.YELLOW)
            user_input = input()
          
        try:
            if user_input == "":
                pc.printout("Downloading all photos available...\n")
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
                    end = self.output_dir + "/" + self.target + "_" + photo_id + ".jpg"
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
                        end = self.output_dir + "/" + self.target + "_" + photo_id + ".jpg"
                        urllib.request.urlretrieve(url, end)
                        sys.stdout.write("\rDownloaded %i" % counter)
                        sys.stdout.flush()

        except AttributeError:
            pass

        except KeyError:
            pass

        sys.stdout.write(" photos")
        sys.stdout.flush()

        pc.printout("\nWoohoo! We downloaded " + str(counter) + " photos (saved in " + self.output_dir + " folder) \n", pc.GREEN)

    def get_user_propic(self):

        try:
            endpoint = 'users/{user_id!s}/full_detail_info/'.format(**{'user_id': self.target_id})
            content = self.api._call_api(endpoint)

            data = content['user_detail']['user']

            if "hd_profile_pic_url_info" in data:
                URL = data["hd_profile_pic_url_info"]['url']
            else:
                #get better quality photo
                items = len(data['hd_profile_pic_versions'])
                URL = data["hd_profile_pic_versions"][items-1]['url']

            if URL != "":
                end = self.output_dir + "/" + self.target + "_propic.jpg"
                urllib.request.urlretrieve(URL, end)
                pc.printout("Target propic saved in output folder\n", pc.GREEN)

            else:
                pc.printout("Sorry! No results found :-(\n", pc.RED)
        
        except ClientError as e:
            error = json.loads(e.error_response)
            print(error['message'])
            print(error['error_title'])
            exit(2)

    def get_user_stories(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " stories...\n")

        data = self.api.user_reel_media(str(self.target_id))

        counter = 0

        if data['items'] is not None:  # no stories avaibile
            counter = data['media_count']
            for i in data['items']:
                story_id = i["id"]
                if i["media_type"] == 1:  # it's a photo
                    url = i['image_versions2']['candidates'][0]['url']
                    end = self.output_dir + "/" + self.target + "_" + story_id + ".jpg"
                    urllib.request.urlretrieve(url, end)

                elif i["media_type"] == 2:  # it's a gif or video
                    url = i['video_versions'][0]['url']
                    end = self.output_dir + "/" + self.target + "_" + story_id + ".mp4"
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
                file_name = self.output_dir + "/" + self.target + "_tagged.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['tagged'] = tagged_list
                json_file_name = self.output_dir + "/" + self.target + "_tagged.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user(self, username):
        try:
            content = self.api.username_info(username)
            if self.writeFile:
                file_name = self.output_dir + "/" + self.target + "_user_id.txt"
                file = open(file_name, "w")
                file.write(str(content['user']['pk']))
                file.close()

            user = dict()
            user['id'] = content['user']['pk']
            user['is_private'] = content['user']['is_private']

            return user
        except ClientError as e:
            pc.printout('ClientError {0!s} (Code: {1:d}, Response: {2!s})'.format(e.msg, e.code, e.error_response), pc.RED)
            error = json.loads(e.error_response)
            if 'message' in error:
                print(error['message'])
            if 'error_title' in error:
                print(error['error_title'])
            if 'challenge' in error:
                print("Please follow this link to complete the challenge: " + error['challenge']['url'])    
            sys.exit(2)
        

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
                print(f'Unable to find file: {settings_file!s}')

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
            print(f'ClientCookieExpiredError/ClientLoginRequiredError: {e!s}')

            # Login expired
            # Do relogin but use default ua, keys and such
            self.api = AppClient(auto_patch=True, authenticate=True, username=u, password=p,
                                 on_login=lambda x: self.onlogin_callback(x, settings_file))

        except ClientError as e:
            pc.printout('ClientError {0!s} (Code: {1:d}, Response: {2!s})'.format(e.msg, e.code, e.error_response), pc.RED)
            error = json.loads(e.error_response)
            pc.printout(error['message'], pc.RED)
            pc.printout(": ", pc.RED)
            pc.printout(e.msg, pc.RED)
            pc.printout("\n")
            if 'challenge' in error:
                print("Please follow this link to complete the challenge: " + error['challenge']['url'])
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
        if str(self.target_id) == self.api.authenticated_user_id:
            return True
        endpoint = 'users/{user_id!s}/full_detail_info/'.format(**{'user_id': self.target_id})
        return self.api._call_api(endpoint)['user_detail']['user']['friendship_status']['following']

    def check_private_profile(self):
        if self.is_private and not self.following:
            pc.printout("Impossible to execute command: " + self.target + " has private profile\n", pc.RED)
            send = input("Do you want send a follow request? [Y/N]: ")
            if send.lower() == "y":
                self.api.friendships_create(self.target_id)
                print("Sent a follow request to target. Use this command after target accepting the request.")

            return True
        return False

    def get_fwersemail(self):
        if self.check_private_profile():
            return

        followers = []
        
        try:

            pc.printout("Searching for emails of target followers... this can take a few minutes\n")

            rank_token = AppClient.generate_uuid()
            data = self.api.user_followers(str(self.target_id), rank_token=rank_token)

            for user in data.get('users', []):
                u = {
                    'id': user['pk'],
                    'username': user['username'],
                    'full_name': user['full_name']
                }
                followers.append(u)

            next_max_id = data.get('next_max_id')
            while next_max_id:
                results = self.api.user_followers(str(self.target_id), rank_token=rank_token, max_id=next_max_id)
                
                for user in results.get('users', []):
                    u = {
                        'id': user['pk'],
                        'username': user['username'],
                        'full_name': user['full_name']
                    }
                    followers.append(u)

                next_max_id = results.get('next_max_id')
            
            
            print("\n")

            results = []
            
            pc.printout("Do you want to get all emails? y/n: ", pc.YELLOW)
            value = input()
            
            if value == str("y") or value == str("yes") or value == str("Yes") or value == str("YES"):
                value = len(followers)
            elif value == str(""):
                print("\n")
                return
            elif value == str("n") or value == str("no") or value == str("No") or value == str("NO"):
                while True:
                    try:
                        pc.printout("How many emails do you want to get? ", pc.YELLOW)
                        new_value = int(input())
                        value = new_value - 1
                        break
                    except ValueError:
                        pc.printout("Error! Please enter a valid integer!", pc.RED)
                        print("\n")
                        return
            else:
                pc.printout("Error! Please enter y/n :-)", pc.RED)
                print("\n")
                return

            for follow in followers:
                sys.stdout.write("\rCatched %i followers email" % len(results))
                sys.stdout.flush()
                user = self.api.user_info(str(follow['id']))
                if 'public_email' in user['user'] and user['user']['public_email']:
                    follow['email'] = user['user']['public_email']
                    if len(results) > value:
                        break
                    results.append(follow)
            sys.stdout.write("\rCatched %i followers email" % len(results))
            sys.stdout.flush()

        except ClientThrottledError  as e:
            pc.printout("\nError: Instagram blocked the requests. Please wait a few minutes before you try again.", pc.RED)
            pc.printout("\n")

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
                file_name = self.output_dir + "/" + self.target + "_fwersemail.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['followers_email'] = results
                json_file_name = self.output_dir + "/" + self.target + "_fwersemail.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_fwingsemail(self):
        if self.check_private_profile():
            return

        followings = []

        try:

            pc.printout("Searching for emails of users followed by target... this can take a few minutes\n")

            rank_token = AppClient.generate_uuid()
            data = self.api.user_following(str(self.target_id), rank_token=rank_token)

            for user in data.get('users', []):
                u = {
                    'id': user['pk'],
                    'username': user['username'],
                    'full_name': user['full_name']
                }
                followings.append(u)

            next_max_id = data.get('next_max_id')
            
            while next_max_id:
                results = self.api.user_following(str(self.target_id), rank_token=rank_token, max_id=next_max_id)

                for user in results.get('users', []):
                    u = {
                        'id': user['pk'],
                        'username': user['username'],
                        'full_name': user['full_name']
                    }
                    followings.append(u)

                next_max_id = results.get('next_max_id')
        
            results = []
            
            pc.printout("Do you want to get all emails? y/n: ", pc.YELLOW)
            value = input()
            
            if value == str("y") or value == str("yes") or value == str("Yes") or value == str("YES"):
                value = len(followings)
            elif value == str(""):
                print("\n")
                return
            elif value == str("n") or value == str("no") or value == str("No") or value == str("NO"):
                while True:
                    try:
                        pc.printout("How many emails do you want to get? ", pc.YELLOW)
                        new_value = int(input())
                        value = new_value - 1
                        break
                    except ValueError:
                        pc.printout("Error! Please enter a valid integer!", pc.RED)
                        print("\n")
                        return
            else:
                pc.printout("Error! Please enter y/n :-)", pc.RED)
                print("\n")
                return

            for follow in followings:
                sys.stdout.write("\rCatched %i followings email" % len(results))
                sys.stdout.flush()
                user = self.api.user_info(str(follow['id']))
                if 'public_email' in user['user'] and user['user']['public_email']:
                    follow['email'] = user['user']['public_email']
                    if len(results) > value:
                        break
                    results.append(follow)
            sys.stdout.write("\rCatched %i followings email" % len(results))
            sys.stdout.flush()
        
        except ClientThrottledError as e:
            pc.printout("\nError: Instagram blocked the requests. Please wait a few minutes before you try again.", pc.RED)
            pc.printout("\n")
        
        print("\n")

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
                file_name = self.output_dir + "/" + self.target + "_fwingsemail.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['followings_email'] = results
                json_file_name = self.output_dir + "/" + self.target + "_fwingsemail.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_fwersnumber(self):
        if self.check_private_profile():
            return
       
        try:

            pc.printout("Searching for phone numbers of users followers... this can take a few minutes\n")

            followers = []

            rank_token = AppClient.generate_uuid()
            data = self.api.user_followers(str(self.target_id), rank_token=rank_token)

            for user in data.get('users', []):
                u = {
                    'id': user['pk'],
                    'username': user['username'],
                    'full_name': user['full_name']
                }
                followers.append(u)

            next_max_id = data.get('next_max_id')
            
            while next_max_id:
                results = self.api.user_followers(str(self.target_id), rank_token=rank_token, max_id=next_max_id)

                for user in results.get('users', []):
                    u = {
                        'id': user['pk'],
                        'username': user['username'],
                        'full_name': user['full_name']
                    }
                    followers.append(u)

                next_max_id = results.get('next_max_id')
       
            results = []
        
            pc.printout("Do you want to get all phone numbers? y/n: ", pc.YELLOW)
            value = input()
            
            if value == str("y") or value == str("yes") or value == str("Yes") or value == str("YES"):
                value = len(followers)
            elif value == str(""):
                print("\n")
                return
            elif value == str("n") or value == str("no") or value == str("No") or value == str("NO"):
                while True:
                    try:
                        pc.printout("How many phone numbers do you want to get? ", pc.YELLOW)
                        new_value = int(input())
                        value = new_value - 1
                        break
                    except ValueError:
                        pc.printout("Error! Please enter a valid integer!", pc.RED)
                        print("\n")
                        return
            else:
                pc.printout("Error! Please enter y/n :-)", pc.RED)
                print("\n")
                return

            for follow in followers:
                sys.stdout.write("\rCatched %i followers phone numbers" % len(results))
                sys.stdout.flush()
                user = self.api.user_info(str(follow['id']))
                if 'contact_phone_number' in user['user'] and user['user']['contact_phone_number']:
                    follow['contact_phone_number'] = user['user']['contact_phone_number']
                    if len(results) > value:
                        break
                    results.append(follow)
            sys.stdout.write("\rCatched %i followers phone numbers" % len(results))
            sys.stdout.flush()

        except ClientThrottledError as e:
            pc.printout("\nError: Instagram blocked the requests. Please wait a few minutes before you try again.", pc.RED)
            pc.printout("\n")
        
        print("\n")

        if len(results) > 0:
            t = PrettyTable(['ID', 'Username', 'Full Name', 'Phone'])
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"
            t.align["Phone number"] = "l"

            json_data = {}

            for node in results:
                t.add_row([str(node['id']), node['username'], node['full_name'], node['contact_phone_number']])

            if self.writeFile:
                file_name = self.output_dir + "/" + self.target + "_fwersnumber.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['followers_phone_numbers'] = results
                json_file_name = self.output_dir + "/" + self.target + "_fwersnumber.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_fwingsnumber(self):
        if self.check_private_profile():
            return

        followings = []

        try:

            pc.printout("Searching for phone numbers of users followed by target... this can take a few minutes\n")


            rank_token = AppClient.generate_uuid()
            data = self.api.user_following(str(self.target_id), rank_token=rank_token)

            for user in data.get('users', []):
                u = {
                    'id': user['pk'],
                    'username': user['username'],
                    'full_name': user['full_name']
                }
                followings.append(u)

            next_max_id = data.get('next_max_id')
            
            while next_max_id:
                results = self.api.user_following(str(self.target_id), rank_token=rank_token, max_id=next_max_id)

                for user in results.get('users', []):
                    u = {
                        'id': user['pk'],
                        'username': user['username'],
                        'full_name': user['full_name']
                    }
                    followings.append(u)

                next_max_id = results.get('next_max_id')
        
            results = []
            
            pc.printout("Do you want to get all phone numbers? y/n: ", pc.YELLOW)
            value = input()
            
            if value == str("y") or value == str("yes") or value == str("Yes") or value == str("YES"):
                value = len(followings)
            elif value == str(""):
                print("\n")
                return
            elif value == str("n") or value == str("no") or value == str("No") or value == str("NO"):
                while True:
                    try:
                        pc.printout("How many phone numbers do you want to get? ", pc.YELLOW)
                        new_value = int(input())
                        value = new_value - 1
                        break
                    except ValueError:
                        pc.printout("Error! Please enter a valid integer!", pc.RED)
                        print("\n")
                        return
            else:
                pc.printout("Error! Please enter y/n :-)", pc.RED)
                print("\n")
                return

            for follow in followings:
                sys.stdout.write("\rCatched %i followings phone numbers" % len(results))
                sys.stdout.flush()
                user = self.api.user_info(str(follow['id']))
                if 'contact_phone_number' in user['user'] and user['user']['contact_phone_number']:
                    follow['contact_phone_number'] = user['user']['contact_phone_number']
                    if len(results) > value:
                        break
                    results.append(follow)
            sys.stdout.write("\rCatched %i followings phone numbers" % len(results))
            sys.stdout.flush()

        except ClientThrottledError as e:
            pc.printout("\nError: Instagram blocked the requests. Please wait a few minutes before you try again.", pc.RED)
            pc.printout("\n")

        print("\n")

        if len(results) > 0:
            t = PrettyTable(['ID', 'Username', 'Full Name', 'Phone'])
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"
            t.align["Phone number"] = "l"

            json_data = {}

            for node in results:
                t.add_row([str(node['id']), node['username'], node['full_name'], node['contact_phone_number']])

            if self.writeFile:
                file_name = self.output_dir + "/" + self.target + "_fwingsnumber.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['followings_phone_numbers'] = results
                json_file_name = self.output_dir + "/" + self.target + "_fwingsnumber.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_comments(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for users who commented...\n")

        data = self.__get_feed__()
        users = []

        for post in data:
            comments = self.__get_comments__(post['id'])
            for comment in comments:
                print(comment['text'])
                
                # if not any(u['id'] == comment['user']['pk'] for u in users):
                #     user = {
                #         'id': comment['user']['pk'],
                #         'username': comment['user']['username'],
                #         'full_name': comment['user']['full_name'],
                #         'counter': 1
                #     }
                #     users.append(user)
                # else:
                #     for user in users:
                #         if user['id'] == comment['user']['pk']:
                #             user['counter'] += 1
                #             break

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
                file_name = self.output_dir + "/" + self.target + "_users_who_commented.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data['users_who_commented'] = ssort
                json_file_name = self.output_dir + "/" + self.target + "_users_who_commented.json"
                with open(json_file_name, 'w') as f:
                    json.dump(json_data, f)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_followers_subset(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " followers...\n")

        target_1 = self.target
        _followers_target_1 = []
        _followers_target_2 = []
        followers_subset = []


        rank_token = AppClient.generate_uuid()
        data = self.api.user_followers(str(self.target_id), rank_token=rank_token)

        _followers_target_1.extend(data.get('users', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            sys.stdout.write("\rCatched %i followers" % len(_followers_target_1))
            sys.stdout.flush()
            results = self.api.user_followers(str(self.target_id), rank_token=rank_token, max_id=next_max_id)
            _followers_target_1.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i followers" % len(_followers_target_1))
        sys.stdout.flush()

        print("\n")

        pc.printout("Insert target two username: ", pc.YELLOW)
        line = input()
        self.setTarget(line, False)
        target_2 = self.target
        if self.check_private_profile():
            return


        pc.printout("Searching for " + self.target + " followers...\n")

        rank_token = AppClient.generate_uuid()
        data = self.api.user_followers(str(self.target_id), rank_token=rank_token)

        _followers_target_2.extend(data.get('users', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            sys.stdout.write("\rCatched %i followers" % len(_followers_target_2))
            sys.stdout.flush()
            results = self.api.user_followers(str(self.target_id), rank_token=rank_token, max_id=next_max_id)
            _followers_target_2.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
            sys.stdout.write("\rCatched %i followers" % len(_followers_target_2))
            sys.stdout.flush()
            
        print("\n")
            
        for user in _followers_target_1:
            ff = list(filter(lambda x: x['pk'] == user['pk'], _followers_target_2))
            if(len(ff) > 0):
                f = {
                    'id': ff[0]['pk'],
                    'username': ff[0]['username'],
                    'full_name': ff[0]['full_name']
                }
                followers_subset.append(f)

        t = PrettyTable(['ID', 'Username', 'Full Name'])
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Full Name"] = "l"

        json_data = {}
        followings_subset_list = []

        for node in followers_subset:
            t.add_row([str(node['id']), node['username'], node['full_name']])

            if self.jsonDump:
                follow = {
                    'id': node['id'],
                    'username': node['username'],
                    'full_name': node['full_name']
                }
                followings_subset_list.append(follow)

        if self.writeFile:
            file_name = self.output_dir + "/" + target_1 + "-" + target_2 + "_followers.txt"
            file = open(file_name, "w")
            file.write(str(t))
            file.close()

        if self.jsonDump:
            json_data['followers'] = followers_subset
            json_file_name = self.output_dir + "/" + target_1 + "-" + target_2 + "_followers.txt"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        print(t)
        pc.printout("Founded " + str(len(followers_subset)) + " users!\n", pc.GREEN)

    def get_followings_subset(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for " + self.target + " followings...\n")

        target_1 = self.target
        _followings_target_1 = []
        _followings_target_2 = []
        followers_subset = []


        rank_token = AppClient.generate_uuid()
        data = self.api.user_followers(str(self.target_id), rank_token=rank_token)

        _followings_target_1.extend(data.get('users', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            sys.stdout.write("\rCatched %i followings" % len(_followings_target_1))
            sys.stdout.flush()
            results = self.api.user_followers(str(self.target_id), rank_token=rank_token, max_id=next_max_id)
            _followings_target_1.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i followings" % len(_followings_target_2))
        sys.stdout.flush()

        print("\n")

        pc.printout("Insert target two username: ", pc.YELLOW)
        line = input()
        self.setTarget(line, False)
        target_2 = self.target
        if self.check_private_profile():
            return


        pc.printout("Searching for " + self.target + " followings...\n")

        rank_token = AppClient.generate_uuid()
        data = self.api.user_followers(str(self.target_id), rank_token=rank_token)

        _followings_target_2.extend(data.get('users', []))

        next_max_id = data.get('next_max_id')
        while next_max_id:
            sys.stdout.write("\rCatched %i followings" % len(_followings_target_2))
            sys.stdout.flush()
            results = self.api.user_followers(str(self.target_id), rank_token=rank_token, max_id=next_max_id)
            _followings_target_2.extend(results.get('users', []))
            next_max_id = results.get('next_max_id')
        sys.stdout.write("\rCatched %i followings" % len(_followings_target_2))
        sys.stdout.flush()

        print("\n")
            
        for user in _followings_target_1:
            ff = list(filter(lambda x: x['pk'] == user['pk'], _followings_target_2))
            if(len(ff) > 0):
                f = {
                    'id': ff[0]['pk'],
                    'username': ff[0]['username'],
                    'full_name': ff[0]['full_name']
                }
                followers_subset.append(f)

        t = PrettyTable(['ID', 'Username', 'Full Name'])
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Full Name"] = "l"

        json_data = {}
        followings_subset_list = []

        for node in followers_subset:
            t.add_row([str(node['id']), node['username'], node['full_name']])

            if self.jsonDump:
                follow = {
                    'id': node['id'],
                    'username': node['username'],
                    'full_name': node['full_name']
                }
                followings_subset_list.append(follow)

        if self.writeFile:
            file_name = self.output_dir + "/" + target_1 + "-" + target_2 + "_followings.txt"
            file = open(file_name, "w")
            file.write(str(t))
            file.close()

        if self.jsonDump:
            json_data['followings'] = followers_subset
            json_file_name = self.output_dir + "/" + target_1 + "-" + target_2 + "_followings.txt"
            with open(json_file_name, 'w') as f:
                json.dump(json_data, f)

        print(t)
        pc.printout("Founded " + str(len(followers_subset)) + " users!\n", pc.GREEN)


    def clear_cache(self):
        try:
            f = open("config/settings.json",'w')
            f.write("{}")
            pc.printout("Cache Cleared.\n",pc.GREEN)
        except FileNotFoundError:
            pc.printout("Settings.json don't exist.\n",pc.RED)
        finally:
            f.close()
