import datetime
import json
import sys
import urllib
import codecs
from pathlib import Path

import ssl

ssl._create_default_https_context = ssl._create_unverified_context

from geopy.geocoders import Nominatim
from hikerapi import Client as AppClient
from hikerapi import __version__ as hk

from prettytable import PrettyTable

from src import printcolors as pc
from src import config


class HikerCLI:
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
        access_key = config.getHikerToken()
        self.cli_mode = is_cli
        if not is_cli:
            print("\nConnect to HikerAPI...")
        self.api = AppClient(token=access_key)
        self.setTarget(target)
        self.writeFile = is_file
        self.jsonDump = is_json

    def setTarget(self, target):
        self.target = target
        self.user = self.get_user(target)
        self.target_id = self.user["pk"]
        self.is_private = self.user["is_private"]
        self.__printTargetBanner__()
        self.output_dir = self.output_dir + "/" + str(self.target)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def __get_feed__(self, limit=-1):
        data = []
        next_page_id = ""
        while True:
            pc.printout("@", pc.CYAN)
            result = self.api.user_medias_v2(self.target_id, page_id=next_page_id)
            data.extend(result.get("response", {}).get("items", []))
            next_page_id = result.get("next_page_id")
            if limit > -1 and len(data) >= limit:
                break
            if not next_page_id:
                break
        return data

    def __get_comments__(self, media_id, limit=-1):
        data = []
        next_page_id = ""
        while True:
            pc.printout("@", pc.CYAN)
            try:
                result = self.api.media_comments_v2(media_id, page_id=next_page_id)
            except Exception as e:
                msg = str(e)
                pc.printout(msg, pc.RED)
                if "Entries not found" in msg:
                    return data
                raise e
            data.extend(result.get("response", {}).get("comments", []))
            next_page_id = result.get("next_page_id")
            if limit > -1 and len(data) >= limit:
                break
            if not next_page_id:
                break
        return data

    def __printTargetBanner__(self):
        pc.printout("Target: ", pc.GREEN)
        pc.printout(str(self.target), pc.CYAN)
        pc.printout(" [" + str(self.target_id) + "]")
        if self.is_private:
            pc.printout(" [PRIVATE PROFILE]", pc.BLUE)
        print("\n")

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
            if "location" in post and post["location"] is not None:
                if "lat" in post["location"] and "lng" in post["location"]:
                    lat = post["location"]["lat"]
                    lng = post["location"]["lng"]
                    locations[str(lat) + ", " + str(lng)] = post.get("taken_at")

        address = {}
        for k, v in locations.items():
            details = self.geolocator.reverse(k)
            unix_timestamp = datetime.datetime.fromtimestamp(v)
            address[details.address] = unix_timestamp.strftime("%Y-%m-%d %H:%M:%S")

        sort_addresses = sorted(address.items(), key=lambda p: p[1], reverse=True)

        if len(sort_addresses) > 0:
            t = PrettyTable()

            t.field_names = ["Post", "Address", "Time"]
            t.align["Post"] = "l"
            t.align["Address"] = "l"
            t.align["Time"] = "l"
            pc.printout(
                "\nWoohoo! We found " + str(len(sort_addresses)) + " addresses\n",
                pc.GREEN,
            )

            i = 1

            json_data = {}
            addrs_list = []

            for address, time in sort_addresses:
                t.add_row([str(i), address, time])

                if self.jsonDump:
                    addr = {"address": address, "time": time}
                    addrs_list.append(addr)

                i = i + 1

            if self.writeFile:
                file_name = self.output_dir + "/" + self.target + "_addrs.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data["address"] = addrs_list
                json_file_name = self.output_dir + "/" + self.target + "_addrs.json"
                with open(json_file_name, "w") as f:
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
                file_name = self.output_dir + "/" + self.target + "_captions.txt"
                file = open(file_name, "w")

            for s in captions:
                print(s + "\n")

                if self.writeFile:
                    file.write(s + "\n")

            if self.jsonDump:
                json_data["captions"] = captions
                json_file_name = (
                    self.output_dir + "/" + self.target + "_followings.json"
                )
                with open(json_file_name, "w") as f:
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

        data = self.__get_feed__()

        comments = [int(p["comment_count"]) for p in data]
        posts = len(comments)
        comments_counter = sum(comments)
        min_ = min(comments)
        max_ = max(comments)
        avg = int(comments_counter / posts)
        result = f" comments in {posts} posts (min: {min_}, max: {max_}, avg: {avg})\n"

        if self.writeFile:
            file_name = self.output_dir + "/" + self.target + "_comments.txt"
            file = open(file_name, "w")
            file.write(
                str(comments_counter) + " comments in " + str(posts) + " posts\n"
            )
            file.close()

        if self.jsonDump:
            json_data = {"comment_counter": comments_counter, "posts": posts}
            json_file_name = self.output_dir + "/" + self.target + "_comments.json"
            with open(json_file_name, "w") as f:
                json.dump(json_data, f)

        pc.printout(str(comments_counter), pc.MAGENTA)
        pc.printout(result)

    def get_comment_data(self):
        if self.check_private_profile():
            return

        pc.printout("Retrieving all comments, this may take a moment...\n")
        data = self.__get_feed__()

        _comments = []
        t = PrettyTable(["POST ID", "ID", "Username", "Comment"])
        t.align["POST ID"] = "l"
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Comment"] = "l"

        for post in data:
            post_id = post.get("id")
            comments = self.__get_comments__(post_id)
            for comment in comments:
                comment = {
                    "post_id": post_id,
                    "user_id": comment.get("user_id"),
                    "username": comment.get("user", {}).get("username"),
                    "comment": comment.get("text"),
                }
                t.add_row(
                    [
                        post_id,
                        comment["user_id"],
                        comment["username"],
                        comment["comment"],
                    ]
                )
                _comments.append(comment)

        print(t)
        if self.writeFile:
            file_name = self.output_dir + "/" + self.target + "_comment_data.txt"
            with open(file_name, "w") as f:
                f.write(str(t))
                f.close()

        if self.jsonDump:
            file_name_json = self.output_dir + "/" + self.target + "_comment_data.json"
            with open(file_name_json, "w") as f:
                f.write('{ "Comments":[ \n')
                f.write("\n".join(json.dumps(comment) for comment in _comments) + ",\n")
                f.write("]} ")

    def get_followers(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target followers...\n")

        followers = []
        next_page_id = ""
        while True:
            pc.printout("@", pc.CYAN)
            result = self.api.user_followers_v2(self.target_id, page_id=next_page_id)
            followers.extend(result.get("response", {}).get("users", []))
            next_page_id = result.get("next_page_id")
            if not next_page_id:
                break

        print("\n")

        t = PrettyTable(["ID", "Username", "Full Name"])
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Full Name"] = "l"

        items = []
        for user in followers:
            u = {
                "id": user["pk"],
                "username": user["username"],
                "full_name": user["full_name"],
                "profile_pic_url": user["profile_pic_url"],
                "is_private": user["is_private"],
                "is_verified": user["is_verified"],
            }
            t.add_row([str(u["id"]), u["username"], u["full_name"]])

            if self.jsonDump:
                items.append(u)

        if self.writeFile:
            file_name = self.output_dir + "/" + self.target + "_followers.txt"
            file = open(file_name, "w")
            file.write(str(t))
            file.close()

        if self.jsonDump:
            json_data = {"followers": items}
            json_file_name = self.output_dir + "/" + self.target + "_followers.json"
            with open(json_file_name, "w") as f:
                json.dump(json_data, f)

        print(t)

    def get_followings(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target followings...\n")

        following = []
        next_page_id = ""
        while True:
            pc.printout("@", pc.CYAN)
            result = self.api.user_following_v2(self.target_id, page_id=next_page_id)
            following.extend(result.get("response", {}).get("users", []))
            next_page_id = result.get("next_page_id")
            if not next_page_id:
                break

        print("\n")

        t = PrettyTable(["ID", "Username", "Full Name"])
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Full Name"] = "l"

        items = []
        for user in following:
            u = {
                "id": user["pk"],
                "username": user["username"],
                "full_name": user["full_name"],
                "profile_pic_url": user["profile_pic_url"],
                "is_private": user["is_private"],
                "is_verified": user["is_verified"],
            }
            t.add_row([str(u["id"]), u["username"], u["full_name"]])

            if self.jsonDump:
                items.append(u)

        if self.writeFile:
            file_name = self.output_dir + "/" + self.target + "_followings.txt"
            file = open(file_name, "w")
            file.write(str(t))
            file.close()

        if self.jsonDump:
            json_data = {"followings": items}
            json_file_name = self.output_dir + "/" + self.target + "_followings.json"
            with open(json_file_name, "w") as f:
                json.dump(json_data, f)

        print(t)

    def get_hashtags(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target hashtags...\n")

        data = self.__get_feed__()

        hashtags = []
        for post in data:
            if post["caption"] is not None:
                caption = post["caption"]["text"]
                for s in caption.split():
                    if s.startswith("#"):
                        hashtags.append(s)

        if len(hashtags) > 0:
            hashtag_counter = {}

            for i in hashtags:
                if i in hashtag_counter:
                    hashtag_counter[i] += 1
                else:
                    hashtag_counter[i] = 1

            ssort = sorted(
                hashtag_counter.items(), key=lambda value: value[1], reverse=True
            )

            file = None
            hashtags_list = []

            if self.writeFile:
                file_name = self.output_dir + "/" + self.target + "_hashtags.txt"
                file = open(file_name, "w")

            print()
            for hashtag, v in ssort:
                line = f"{v}. {hashtag}"
                print(line)
                if self.writeFile:
                    file.write(f"{line}\n")
                if self.jsonDump:
                    hashtags_list.append(hashtag)

            if file is not None:
                file.close()

            if self.jsonDump:
                json_data = {"hashtags": hashtags_list}
                json_file_name = self.output_dir + "/" + self.target + "_hashtags.json"
                with open(json_file_name, "w") as f:
                    json.dump(json_data, f)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user_info(self):
        data = self.user
        pc.printout("[ID] ", pc.GREEN)
        pc.printout(str(data["pk"]) + "\n")
        pc.printout("[FULL NAME] ", pc.RED)
        pc.printout(str(data["full_name"]) + "\n")
        pc.printout("[BIOGRAPHY] ", pc.CYAN)
        pc.printout(str(data["biography"]) + "\n")
        pc.printout("[FOLLOWED] ", pc.BLUE)
        pc.printout(str(data["follower_count"]) + "\n")
        pc.printout("[FOLLOW] ", pc.GREEN)
        pc.printout(str(data["following_count"]) + "\n")
        pc.printout("[MEDIA] ", pc.CYAN)
        pc.printout(str(data["media_count"]) + "\n")
        pc.printout("[BUSINESS ACCOUNT] ", pc.RED)
        pc.printout(str(data["is_business"]) + "\n")
        if data["is_business"]:
            if not data["can_hide_category"]:
                pc.printout("[BUSINESS CATEGORY] ")
                pc.printout(str(data["category"]) + "\n")
        pc.printout("[VERIFIED ACCOUNT] ", pc.CYAN)
        pc.printout(str(data["is_verified"]) + "\n")
        if "public_email" in data and data["public_email"]:
            pc.printout("[EMAIL] ", pc.BLUE)
            pc.printout(str(data["public_email"]) + "\n")
        pc.printout("[HD PROFILE PIC] ", pc.GREEN)
        pc.printout(str(data["hd_profile_pic_url_info"]["url"]) + "\n")
        if "fb_page_call_to_action_id" in data and data["fb_page_call_to_action_id"]:
            pc.printout("[FB PAGE] ", pc.RED)
            pc.printout(str(data["connected_fb_page"]) + "\n")
        if "whatsapp_number" in data and data["whatsapp_number"]:
            pc.printout("[WHATSAPP NUMBER] ", pc.GREEN)
            pc.printout(str(data["whatsapp_number"]) + "\n")
        if "city_name" in data and data["city_name"]:
            pc.printout("[CITY] ", pc.YELLOW)
            pc.printout(str(data["city_name"]) + "\n")
        if "address_street" in data and data["address_street"]:
            pc.printout("[ADDRESS STREET] ", pc.RED)
            pc.printout(str(data["address_street"]) + "\n")
        if "contact_phone_number" in data and data["contact_phone_number"]:
            pc.printout("[CONTACT PHONE NUMBER] ", pc.CYAN)
            pc.printout(str(data["contact_phone_number"]) + "\n")

        if self.jsonDump:
            user = {
                "id": data["pk"],
                "full_name": data["full_name"],
                "biography": data["biography"],
                "edge_followed_by": data["follower_count"],
                "edge_follow": data["following_count"],
                "is_business_account": data["is_business"],
                "is_verified": data["is_verified"],
                "profile_pic_url_hd": data["hd_profile_pic_url_info"]["url"],
            }
            if "public_email" in data and data["public_email"]:
                user["email"] = data["public_email"]
            if (
                "fb_page_call_to_action_id" in data
                and data["fb_page_call_to_action_id"]
            ):
                user["connected_fb_page"] = data["fb_page_call_to_action_id"]
            if "whatsapp_number" in data and data["whatsapp_number"]:
                user["whatsapp_number"] = data["whatsapp_number"]
            if "city_name" in data and data["city_name"]:
                user["city_name"] = data["city_name"]
            if "address_street" in data and data["address_street"]:
                user["address_street"] = data["address_street"]
            if "contact_phone_number" in data and data["contact_phone_number"]:
                user["contact_phone_number"] = data["contact_phone_number"]

            json_file_name = self.output_dir + "/" + self.target + "_info.json"
            with open(json_file_name, "w") as f:
                json.dump(user, f)

    def get_total_likes(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target total likes...\n")

        data = self.__get_feed__()

        likes = [int(p["like_count"]) for p in data]
        posts = len(likes)
        like_counter = sum(likes)
        min_ = min(likes)
        max_ = max(likes)
        avg = int(like_counter / posts)
        result = f" likes in {posts} posts (min: {min_}, max: {max_}, avg: {avg})\n"

        if self.writeFile:
            file_name = self.output_dir + "/" + self.target + "_likes.txt"
            file = open(file_name, "w")
            file.write(str(like_counter) + result)
            file.close()

        if self.jsonDump:
            json_data = {
                "like_counter": like_counter,
                "posts": posts,
                "min": min_,
                "max": max_,
                "avg": avg,
            }
            json_file_name = self.output_dir + "/" + self.target + "_likes.json"
            with open(json_file_name, "w") as f:
                json.dump(json_data, f)

        pc.printout(f"\n{like_counter}", pc.MAGENTA)
        pc.printout(result)

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
                file_name = self.output_dir + "/" + self.target + "_mediatype.txt"
                file = open(file_name, "w")
                file.write(
                    str(photo_counter)
                    + " photos and "
                    + str(video_counter)
                    + " video posted by target\n"
                )
                file.close()

            pc.printout(
                "\nWoohoo! We found "
                + str(photo_counter)
                + " photos and "
                + str(video_counter)
                + " video posted by target\n",
                pc.GREEN,
            )

            if self.jsonDump:
                json_data = {"photos": photo_counter, "videos": video_counter}
                json_file_name = self.output_dir + "/" + self.target + "_mediatype.json"
                with open(json_file_name, "w") as f:
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
            comments = self.__get_comments__(post["id"])
            for comment in comments:
                if not any(u["id"] == comment["user"]["pk"] for u in users):
                    user = {
                        "id": comment["user"]["pk"],
                        "username": comment["user"]["username"],
                        "full_name": comment["user"]["full_name"],
                        "counter": 1,
                    }
                    users.append(user)
                else:
                    for user in users:
                        if user["id"] == comment["user"]["pk"]:
                            user["counter"] += 1
                            break

        if len(users) > 0:
            ssort = sorted(users, key=lambda value: value["counter"], reverse=True)

            json_data = {}

            t = PrettyTable()

            t.field_names = ["Comments", "ID", "Username", "Full Name"]
            t.align["Comments"] = "l"
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"

            for u in ssort:
                t.add_row([str(u["counter"]), u["id"], u["username"], u["full_name"]])

            print(t)

            if self.writeFile:
                file_name = (
                    self.output_dir + "/" + self.target + "_users_who_commented.txt"
                )
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data["users_who_commented"] = ssort
                json_file_name = (
                    self.output_dir + "/" + self.target + "_users_who_commented.json"
                )
                with open(json_file_name, "w") as f:
                    json.dump(json_data, f)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_people_who_tagged(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for users who tagged target...\n")

        posts = []
        next_page_id = ""
        while True:
            pc.printout("@", pc.CYAN)
            resp = self.api.user_tag_medias_v2(self.target_id, page_id=next_page_id)
            posts.extend(resp.get("response", {}).get("items", []))
            next_page_id = resp.get("next_page_id")
            if not next_page_id:
                break

        if len(posts) > 0:
            pc.printout(f"\nWoohoo! We found {len(posts)} medias\n", pc.GREEN)
            users = {}

            for post in posts:
                tag = post["user"]
                pk = tag["pk"]
                if pk in users:
                    users[pk]["counter"] += 1
                    continue
                users[pk] = {
                    "id": pk,
                    "username": tag["username"],
                    "full_name": tag["full_name"],
                    "counter": 1,
                }

            users = users.values()
            ssort = sorted(users, key=lambda value: value["counter"], reverse=True)
            t = PrettyTable()
            t.field_names = ["Medias", "ID", "Username", "Full Name"]
            t.align["Medias"] = "l"
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"

            for u in ssort:
                t.add_row([str(u["counter"]), u["id"], u["username"], u["full_name"]])

            print(t)

            if self.writeFile:
                file_name = (
                    self.output_dir + "/" + self.target + "_users_who_tagged.txt"
                )
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data = {"users_who_tagged": ssort}
                json_file_name = (
                    self.output_dir + "/" + self.target + "_users_who_tagged.json"
                )
                with open(json_file_name, "w") as f:
                    json.dump(json_data, f)
        else:
            pc.printout("\nSorry! No results found :-(\n", pc.RED)

    def get_photo_description(self):
        if self.check_private_profile():
            return
        pc.printout("Instagram has disabled this functionality.\n", pc.RED)

    def get_user_photo(self):
        if self.check_private_profile():
            return

        limit = -1
        pc.printout("How many photos you want to download (default all): ", pc.YELLOW)
        user_input = input()

        try:
            if user_input.lower() in ("", "all"):
                pc.printout("Downloading all photos available...\n")
            else:
                limit = int(user_input)
                pc.printout(f"Downloading {user_input} photos...\n")
        except ValueError:
            pc.printout("Wrong value entered\n", pc.RED)
            return

        data = self.__get_feed__(limit=limit)
        print()
        counter = 0
        for item in data:
            if "image_versions2" in item:
                if limit > -1 and counter >= limit:
                    break
                counter += 1
                url = item["image_versions2"]["candidates"][0]["url"]
                photo_id = item["id"]
                end = self.output_dir + "/" + self.target + "_" + photo_id + ".jpg"
                urllib.request.urlretrieve(url, end)
                sys.stdout.write("\rDownloaded %i" % counter)
                sys.stdout.flush()
            else:
                carousel = item["carousel_media"]
                for i in carousel:
                    if limit > -1 and counter >= limit:
                        break
                    counter += 1
                    url = i["image_versions2"]["candidates"][0]["url"]
                    photo_id = i["id"]
                    end = self.output_dir + "/" + self.target + "_" + photo_id + ".jpg"
                    urllib.request.urlretrieve(url, end)
                    sys.stdout.write("\rDownloaded %i" % counter)
                    sys.stdout.flush()

        pc.printout(
            f"\nWoohoo! We downloaded {counter} medias (saved in {self.output_dir} folder) \n",
            pc.GREEN,
        )

    def get_user_propic(self):
        data = self.user
        if "hd_profile_pic_url_info" in data:
            url = data["hd_profile_pic_url_info"]["url"]
        else:
            # get better quality photo
            items = len(data["hd_profile_pic_versions"])
            url = data["hd_profile_pic_versions"][items - 1]["url"]

        if url != "":
            end = self.output_dir + "/" + self.target + "_propic.jpg"
            urllib.request.urlretrieve(url, end)
            pc.printout("Target propic saved in output folder\n", pc.GREEN)

        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user_stories(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for target stories...\n")
        data = self.api.user_stories_v2(self.target_id)
        counter = 0
        if data["reel"]:  # no stories avaibile
            items = data["reel"].get("items", [])
            counter = len(items)
            for i in items:
                pc.printout("@", pc.CYAN)
                story_id = i["id"]
                if i["media_type"] == 1:  # photo
                    url = i["image_versions2"]["candidates"][0]["url"]
                    end = self.output_dir + "/" + self.target + "_" + story_id + ".jpg"
                    urllib.request.urlretrieve(url, end)
                elif i["media_type"] == 2:  # video
                    url = i["video_versions"][0]["url"]
                    end = self.output_dir + "/" + self.target + "_" + story_id + ".mp4"
                    urllib.request.urlretrieve(url, end)

        if counter > 0:
            pc.printout(
                f"\n{counter} target stories saved in output folder\n", pc.GREEN
            )
        else:
            pc.printout("\nSorry! No results found :-(\n", pc.RED)

    def get_people_tagged_by_user(self):
        pc.printout("Searching for users tagged by target...\n")

        pks = []
        username = []
        full_name = []
        tagged = []
        counter = 1

        data = self.__get_feed__()

        for post in data:
            usertags = post.get("usertags", [])
            for tag in usertags:
                u = tag.get("user", {})
                if u["pk"] not in pks:
                    pks.append(u["pk"])
                    username.append(u["username"])
                    full_name.append(u["full_name"])
                    tagged.append(1)
                else:
                    index = pks.index(u["pk"])
                    tagged[index] += 1
                counter += 1

        if len(pks) > 0:
            t = PrettyTable()

            t.field_names = ["Posts", "Full Name", "Username", "ID"]
            t.align["Posts"] = "l"
            t.align["Full Name"] = "l"
            t.align["Username"] = "l"
            t.align["ID"] = "l"

            pc.printout(
                f"\nWoohoo! We found {len(pks)} ({counter}) users\n",
                pc.GREEN,
            )

            json_data = {}
            tagged_list = []

            for i in range(len(pks)):
                t.add_row([tagged[i], full_name[i], username[i], str(pks[i])])

                if self.jsonDump:
                    tag = {
                        "post": tagged[i],
                        "full_name": full_name[i],
                        "username": username[i],
                        "id": pks[i],
                    }
                    tagged_list.append(tag)

            if self.writeFile:
                file_name = self.output_dir + "/" + self.target + "_tagged.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data["tagged"] = tagged_list
                json_file_name = self.output_dir + "/" + self.target + "_tagged.json"
                with open(json_file_name, "w") as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def get_user(self, username):
        data = self.api.user_by_username_v2(username)
        if "error" in data:
            pc.printout(
                "Oops... {error}\n".format(**data),
                pc.RED,
            )
            exit(2)
        elif "detail" in data:
            pc.printout(
                f"Oops... {self.target} non exist, please enter a valid username ({data['detail']})\n",
                pc.RED,
            )
            exit(2)
        user = data["user"]
        if self.writeFile:
            file_name = self.output_dir + "/" + self.target + "_user_id.txt"
            file = open(file_name, "w")
            file.write(str(user["pk"]))
            file.close()
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

    def to_json(self, python_object):
        if isinstance(python_object, bytes):
            return {
                "__class__": "bytes",
                "__value__": codecs.encode(python_object, "base64").decode(),
            }
        raise TypeError(repr(python_object) + " is not JSON serializable")

    def from_json(self, json_object):
        if "__class__" in json_object and json_object["__class__"] == "bytes":
            return codecs.decode(json_object["__value__"].encode(), "base64")
        return json_object

    def check_private_profile(self):
        if self.is_private:
            pc.printout(
                "Impossible to execute command: user has private profile\n", pc.RED
            )
            return True
        return False

    def get_contact_info(
        self, func, from_key, to_key, json_key, file_name, title, field, help_text
    ):
        if self.check_private_profile():
            return

        items = []
        pc.printout(f"{help_text}... this can take a few minutes\n")

        next_page_id = ""
        while True:
            pc.printout("@", pc.CYAN)
            result = func(self.target_id, page_id=next_page_id)
            items.extend(result.get("response", {}).get("users", []))
            next_page_id = result.get("next_page_id")
            if not next_page_id:
                break

        print("\n")

        pc.printout(
            f"Do you want to get all {title} (for {len(items)} users)? y/n: ", pc.YELLOW
        )
        value = input()
        if value.lower() in ["y", "yes"]:
            value = len(items)
        elif value == "":
            print("\n")
            return
        elif value.lower() in ["n", "no"]:
            while True:
                try:
                    pc.printout(f"How many {title} do you want to get? ", pc.YELLOW)
                    new_value = int(input())
                    value = new_value - 1
                    break
                except ValueError:
                    pc.printout("Error! Please enter a valid integer!", pc.RED)
                    print("\n")
                    continue
        else:
            pc.printout("Error! Please enter y/n :-)", pc.RED)
            print("\n")
            return

        results = []
        for follow in items:
            pc.printout("@", pc.CYAN)
            user = self.api.user_by_id_v2(follow["pk"])
            if item := user["user"].get(from_key):
                follow[to_key] = item
                results.append(follow)
                if len(results) > value:
                    break

        if len(results) > 0:
            t = PrettyTable(["ID", "Username", "Full Name", field])
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"
            t.align[field] = "l"

            for node in results:
                t.add_row(
                    [str(node["id"]), node["username"], node["full_name"], node[to_key]]
                )

            if self.writeFile:
                file_name = self.output_dir + "/" + self.target + f"_{file_name}.txt"
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data = {json_key: results}
                json_file_name = (
                    self.output_dir + "/" + self.target + f"_{file_name}.json"
                )
                with open(json_file_name, "w") as f:
                    json.dump(json_data, f)

            print(t)
        else:
            pc.printout("\nSorry! No results found :-(\n", pc.RED)

    def get_fwersemail(self):
        return self.get_contact_info(
            self.api.user_followers_v2,
            from_key="public_email",
            to_key="email",
            json_key="followers_email",
            file_name="_fwersemail",
            title="emails",
            field="Email",
            help_text="Searching for emails of target followers",
        )

    def get_fwingsemail(self):
        return self.get_contact_info(
            self.api.user_following_v2,
            from_key="public_email",
            to_key="email",
            json_key="followings_email",
            file_name="_fwingsemail",
            title="emails",
            field="Email",
            help_text="Searching for emails of users followed by target",
        )

    def get_fwersnumber(self):
        return self.get_contact_info(
            self.api.user_followers_v2,
            from_key="contact_phone_number",
            to_key="contact_phone_number",
            json_key="followers_phone_numbers",
            file_name="_fwersnumber",
            title="phone numbers",
            field="Phone",
            help_text="Searching for phone numbers of users followers",
        )

    def get_fwingsnumber(self):
        return self.get_contact_info(
            self.api.user_following_v2,
            from_key="contact_phone_number",
            to_key="contact_phone_number",
            json_key="followings_phone_numbers",
            file_name="_fwingsnumber",
            title="phone numbers",
            field="Phone",
            help_text="Searching for phone numbers of users followed by target",
        )

    def get_comments(self):
        if self.check_private_profile():
            return

        pc.printout("Searching for users who commented...\n")

        data = self.__get_feed__()
        users = []

        for post in data:
            comments = self.__get_comments__(post["id"])
            for comment in comments:
                print(comment["text"])

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
            ssort = sorted(users, key=lambda value: value["counter"], reverse=True)
            t = PrettyTable()

            t.field_names = ["Comments", "ID", "Username", "Full Name"]
            t.align["Comments"] = "l"
            t.align["ID"] = "l"
            t.align["Username"] = "l"
            t.align["Full Name"] = "l"

            for u in ssort:
                t.add_row([str(u["counter"]), u["id"], u["username"], u["full_name"]])

            print(t)

            if self.writeFile:
                file_name = (
                    self.output_dir + "/" + self.target + "_users_who_commented.txt"
                )
                file = open(file_name, "w")
                file.write(str(t))
                file.close()

            if self.jsonDump:
                json_data = {"users_who_commented": ssort}
                json_file_name = (
                    self.output_dir + "/" + self.target + "_users_who_commented.json"
                )
                with open(json_file_name, "w") as f:
                    json.dump(json_data, f)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)

    def clear_cache(self):
        pc.printout("Cache is already empty.\n", pc.GREEN)
