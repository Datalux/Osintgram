import datetime
import json
import sys
import urllib

from geopy.geocoders import Nominatim
from instagram_private_api import Client as AppClient
from prettytable import PrettyTable

from src import printcolors as pc


class Osintgram:
    api = None
    api2 = None
    geolocator = Nominatim()
    user_id = None
    target_id = None
    is_private = True
    target = ""
    writeFile = False
    jsonDump = False

    def __init__(self, target, is_file, is_json):
        u = self.__getUsername__()
        p = self.__getPassword__()
        print("\nAttempt to login...")
        self.api = AppClient(auto_patch=True, authenticate=True, username=u, password=p)
        self.setTarget(target)
        self.writeFile = is_file
        self.jsonDump = is_json

    def setTarget(self, target):
        self.target = target
        user = self.get_user(target)
        self.target_id = user['id']
        self.is_private = user['is_private']
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

    def __printTargetBanner__(self):
        pc.printout("\nLogged as ", pc.GREEN)
        pc.printout(self.api.username, pc.CYAN)
        pc.printout(" (" + str(self.api.authenticated_user_id) + ") ")
        pc.printout("target: ", pc.GREEN)
        pc.printout(str(self.target), pc.CYAN)
        pc.printout(" (private: " + str(self.is_private) + ")")
        print('\n')

    def change_target(self):
        pc.printout("Insert new target username: ", pc.YELLOW)
        line = input()
        self.setTarget(line)
        return

    def get_addrs(self):
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
            return

        pc.printout("Searching for target localizations...\n")

        data = self.__get_feed__()

        locations = {}

        for post in data:
            if post['location'] is not None:
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
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
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
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
            return

        pc.printout("Searching for target total comments...\n")

        comments_counter = 0
        posts = 0

        data = self.__get_feed__()

        for post in data:
            comments_counter += post['comment_count']

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
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
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
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
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
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
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

    def get_user_info(self):
        try:
            content = urllib.request.urlopen("https://www.instagram.com/" + str(self.target) + "/?__a=1")
            data = json.load(content)
            data = data['graphql']['user']

            pc.printout("[ID] ", pc.GREEN)
            pc.printout(str(data['id']) + '\n')
            pc.printout("[FULL NAME] ", pc.RED)
            pc.printout(str(data['full_name']) + '\n')
            pc.printout("[BIOGRAPHY] ", pc.CYAN)
            pc.printout(str(data['biography']) + '\n')
            pc.printout("[FOLLOWED] ", pc.GREEN)
            pc.printout(str(data['edge_followed_by']['count']) + '\n')
            pc.printout("[FOLLOW] ", pc.BLUE)
            pc.printout(str(data['edge_follow']['count']) + '\n')
            pc.printout("[BUSINESS ACCOUNT] ", pc.RED)
            pc.printout(str(data['is_business_account']) + '\n')
            if data['is_business_account']:
                pc.printout("[BUSINESS CATEGORY] ")
                pc.printout(str(data['business_category_name']) + '\n')
            pc.printout("[VERIFIED ACCOUNT] ", pc.CYAN)
            pc.printout(str(data['is_verified']) + '\n')

            if self.jsonDump:
                user = {
                    'id': data['id'],
                    'full_name': data['full_name'],
                    'biography': data['biography'],
                    'edge_followed_by': data['edge_followed_by']['count'],
                    'edge_follow': data['edge_follow']['count'],
                    'is_business_account': data['is_business_account'],
                    'is_verified': data['is_verified']
                }
                json_file_name = "output/" + self.target + "_info.json"
                with open(json_file_name, 'w') as f:
                    json.dump(user, f)

        except urllib.error.HTTPError as err:
            if err.code == 404:
                print("Oops... " + str(self.target) + " non exist, please enter a valid username.")
                sys.exit(2)

    def get_total_likes(self):
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
            return

        pc.printout("Searching for target total likes...\n")

        like_counter = 0
        posts = 0

        data = self.__get_feed__()

        for post in data:
            like_counter += post['like_count']

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
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
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

    def get_photo_description(self):
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
            return

        content = urllib.request.urlopen("https://www.instagram.com/" + str(self.target) + "/?__a=1")
        data = json.load(content)
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
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
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
        try:
            content = urllib.request.urlopen("https://www.instagram.com/" + str(self.target) + "/?__a=1")

            data = json.load(content)

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
        except urllib.error.HTTPError as err:
            if err.code == 404:
                print("Oops... " + str(self.target) + " non exist, please enter a valid username.")
                sys.exit(2)

    def get_user_stories(self):
        if self.is_private:
            pc.printout("Impossible to execute command: user has private profile\n", pc.RED)
            return

        pc.printout("Searching for target stories...\n")

        endpoint = 'feed/user/{id!s}/story/'.format(**{'id': self.target_id})
        content = urllib.request.urlopen("https://www.instagram.com/" + endpoint)
        data = json.load(content)
        counter = 0

        if data['reel'] is not None:  # no stories avaibile
            for i in data['reel']['items']:
                story_id = i["id"]
                if i["media_type"] == 1:  # it's a photo
                    url = i['image_versions2']['candidates'][0]['url']
                    end = "output/" + self.target + "_" + story_id + ".jpg"
                    urllib.request.urlretrieve(url, end)
                    counter += 1

                elif i["media_type"] == 2:  # it's a gif or video
                    url = i['video_versions'][0]['url']
                    end = "output/" + self.target + "_" + story_id + ".mp4"
                    urllib.request.urlretrieve(url, end)
                    counter += 1

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
        try:
            content = urllib.request.urlopen("https://www.instagram.com/" + username + "/?__a=1")
            data = json.load(content)
            if self.writeFile:
                file_name = "output/" + self.target + "_user_id.txt"
                file = open(file_name, "w")
                file.write(str(data['graphql']['user']['id']))
                file.close()

            user = dict()
            user['id'] = data['graphql']['user']['id']
            user['is_private'] = data['graphql']['user']['is_private']

            return user

        except urllib.error.HTTPError as err:
            if err.code == 404:
                print("Oops... " + username + " non exist, please enter a valid username.")
                sys.exit(2)

        return None

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
