from InstagramAPI import InstagramAPI 
from geopy.geocoders import Nominatim
import sys
import argparse
import datetime
from collections import OrderedDict
import json
from prettytable import PrettyTable
import urllib
from requests.exceptions import HTTPError
import printcolors as pc



class Osintgram:
    api = None
    geolocator = Nominatim()
    user_id = None
    target = ""

    def __init__(self, target):
        self.target = target
        u = self.__getUsername__()
        p = self.__getPassword__()
        self.api = InstagramAPI(u, p)
        print("\nAttempt to login...\n")
        self.api.login()
        pc.printout("Logged as ", pc.GREEN)
        pc.printout(self.api.username, pc.CYAN)
        pc.printout(" (" + str(self.api.username_id) + ") ")
        pc.printout("target: ", pc.GREEN)
        pc.printout(str(self.target), pc.CYAN)
        print('\n')

    def __getUsername__(self):
        u = open("config/username.conf", "r").read()
        u = u.replace("\n", "")
        return u
    
    def __getPassword__(self):
        p = open("config/pw.conf", "r").read()
        p = p.replace("\n", "")
        return p

    def __getAdressesTimes__(self, id):
        only_id = {} #var only for max_next_id parameter | pagination
        photos = [] # only photos
        hashtags = []
        a = None #helper
        while True:
            if (a == None):
                self.api.getUserFeed(id)
                a = self.api.LastJson['items']#photos 00, 01, 02...
                only_id = self.api.LastJson #all LastJson with max_id param
            else:
                self.api.getUserFeed(id, only_id['next_max_id']) #passing parameter max_id
                only_id = self.api.LastJson
                a = self.api.LastJson['items']

            photos.append(a)

            if not 'next_max_id' in only_id:
                break


        locations = {}

        for i in photos: #extract location from photos, related
            for j in i:
                if 'lat' in j.keys():
                    lat = j.get('lat')
                    lng = j.get('lng')

                    locations[str(lat) + ', ' + str(lng)] = j.get('taken_at')

        address = {}
        for k,v in locations.items():
            details = self.geolocator.reverse(k) #locate for key
            unix_timestamp = datetime.datetime.fromtimestamp(v) # read timestamp as a value
            address[details.address] = unix_timestamp.strftime('%Y-%m-%d %H:%M:%S')


        sort_addresses = sorted(address.items(), key=lambda p: p[1], reverse=True)  #sorting

        return sort_addresses 


    def __getUserFollowigs__(self, id):
        following = []
        next_max_id = True
        while next_max_id:
            # first iteration hack
            if next_max_id is True:
                next_max_id = ''
            _ = self.api.getUserFollowings(id, maxid=next_max_id)
            following.extend(self.api.LastJson.get('users', []))
            next_max_id = self.api.LastJson.get('next_max_id', '')

        len(following)
        unique_following = {
            f['pk']: f
            for f in following
        }
        len(unique_following)
        return following

    def __getTotalFollowers__(self, user_id):
        followers = []
        next_max_id = True
        while next_max_id:
            # first iteration hack
            if next_max_id is True:
                next_max_id = ''

            _ = self.api.getUserFollowers(user_id, maxid=next_max_id)
            followers.extend(self.api.LastJson.get('users', []))
            next_max_id = self.api.LastJson.get('next_max_id', '')

        return followers

        
    def getHashtags(self, id):
        pc.printout("Searching for target hashtags...\n")

        text = []
        only_id = {}
        a = None #helper
        hashtags = []
        counter = 1
        while True:
            if (a == None):
                self.api.getUserFeed(id)
                a = self.api.LastJson['items']#photos 00, 01, 02...
                only_id = self.api.LastJson #all LastJson with max_id param
                with open('data.json', 'w') as outfile:
                    json.dump(only_id, outfile)
                
            else:
                self.api.getUserFeed(id, only_id['next_max_id']) #passing parameter max_id
                only_id = self.api.LastJson
                a = self.api.LastJson['items']

            try:
                for i in a:
                    c = i.get('caption', {}).get('text')
                    text.append(c)
                    #print str(counter) + ' ' + c
                    counter = counter +1
            except AttributeError:
                pass

            if not 'next_max_id' in only_id:
                break

        hashtag_counter = {}

        for i in text:
            for j in i.split():
                if j.startswith('#'):
                    hashtags.append(j.encode('UTF-8'))

        for i in hashtags:
            if i in hashtag_counter:
                hashtag_counter[i] += 1
            else:
                hashtag_counter[i] = 1

        sortE = sorted(hashtag_counter.items(), key=lambda value: value[1], reverse=True)

        for k,v in sortE:
            print( str(v) + ". " + str(k.decode('utf-8')))

    def getTotalLikes(self, id):
        pc.printout("Searching for target total likes...\n")

        like_counter = 0
        only_id = {}
        a = None #helper
        counter = 0
        while True:
            if (a == None):
                self.api.getUserFeed(id)
                a = self.api.LastJson['items']#photos 00, 01, 02...
                only_id = self.api.LastJson #all LastJson with max_id param
            else:
                self.api.getUserFeed(id, only_id['next_max_id']) #passing parameter max_id
                only_id = self.api.LastJson
                a = self.api.LastJson['items']
            try:
                for i in a:
                    c = int(i.get('like_count'))
                    like_counter += c
                    counter = counter +1
            except AttributeError:
                pass

            if not 'next_max_id' in only_id:
                break
        pc.printout(str(like_counter), pc.MAGENTA)
        pc.printout(" likes in " + str(counter) + " posts\n")
    
    def getTotalComments(self, id):
        pc.printout("Searching for target total comments...\n")

        comment_counter = 0
        only_id = {}
        a = None #helper
        counter = 0
        while True:
            if (a == None):
                self.api.getUserFeed(id)
                a = self.api.LastJson['items']#photos 00, 01, 02...
                only_id = self.api.LastJson #all LastJson with max_id param
            else:
                self.api.getUserFeed(id, only_id['next_max_id']) #passing parameter max_id
                only_id = self.api.LastJson
                a = self.api.LastJson['items']
            try:
                for i in a:
                    c = int(i.get('comment_count'))
                    comment_counter += c
                    counter = counter +1
            except AttributeError:
                pass

            if not 'next_max_id' in only_id:
                break
        pc.printout(str(comment_counter), pc.MAGENTA)
        pc.printout(" comments in " + str(counter) + " posts\n")

    def getPeopleTaggedByUser(self, id):
        pc.printout("Searching for users tagged by target...\n")
        
        ids = []
        username = []
        full_name = []
        post = []
        only_id = {}
        a = None #helper
        counter = 1
        while True:
            if (a == None):
                self.api.getUserFeed(id)
                a = self.api.LastJson['items']#photos 00, 01, 02...
                only_id = self.api.LastJson #all LastJson with max_id param

                
            else:
                self.api.getUserFeed(id, only_id['next_max_id']) #passing parameter max_id
                only_id = self.api.LastJson
                a = self.api.LastJson['items']

            try:
                for i in a:
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
                        counter = counter +1
            except AttributeError:
                pass

            if not 'next_max_id' in only_id:
                break

        if len(ids) > 0:
            t = PrettyTable()

            t.field_names = ['Posts', 'Full Name', 'Username', 'ID']
            t.align["Posts"] = "l"
            t.align["Full Name"] = "l"
            t.align["Username"] = "l"
            t.align["ID"] = "l"
            
            pc.printout("\nWoohoo! We found " + str(len(ids)) + " (" + str(counter) + ") users\n", pc.GREEN)

            for i in range(len(ids)):
                t.add_row([post[i], full_name[i], username[i], str(ids[i])])

            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)



    def getAddrs(self, id):
        pc.printout("Searching for target address... this may take a few minutes...\n")
        addrs = self.__getAdressesTimes__(id)
        t = PrettyTable()

        t.field_names = ['Post', 'Address', 'time']
        t.align["Post"] = "l"
        t.align["Address"] = "l"
        t.align["Time"] = "l"
        pc.printout("\nWoohoo! We found " + str(len(addrs)) + " addresses\n", pc.GREEN)

        i = 1
        for address, time in addrs:
            t.add_row([str(i), address, time])
            i = i + 1
        print(t)

    def getFollowers(self, id):
        pc.printout("Searching for target followers...\n")

        followers = self.__getTotalFollowers__(id)
        t = PrettyTable(['ID', 'Username', 'Full Name'])
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Full Name"] = "l"
        
        for i in followers:
            t.add_row([str(i['pk']), i['username'], i['full_name']])
        print(t)

    def getFollowings(self, id):
        pc.printout("Searching for target followings...\n")

        followings = self.__getUserFollowigs__(id)
        t = PrettyTable(['ID', 'Username', 'Full Name'])
        t.align["ID"] = "l"
        t.align["Username"] = "l"
        t.align["Full Name"] = "l"
        
        for i in followings:
            t.add_row([str(i['pk']), i['username'], i['full_name']])
        print(t)

    def getUserID(self, username):
        try:
            content = urllib.request.urlopen("https://www.instagram.com/" + username + "/?__a=1" )
        except urllib.error.HTTPError as err: 
            if(err.code == 404):
                print("Oops... " + username + " non exist, please enter a valid username.")
                sys.exit(2)

        data = json.load(content)
        return data['graphql']['user']['id']

    def getUserInfo(self):
        try:
            content = urllib.request.urlopen("https://www.instagram.com/" + str(self.target) + "/?__a=1" )
        except urllib.error.HTTPError as err: 
            if(err.code == 404):
                print("Oops... " + str(self.target) + " non exist, please enter a valid username.")
                sys.exit(2)

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
        if data['is_business_account'] == True:
            pc.printout("[BUSINESS CATEGORY] ")
            pc.printout(str(data['business_category_name']) + '\n')
        pc.printout("[VERIFIED ACCOUNT] ", pc.CYAN)
        pc.printout(str(data['is_verified']) + '\n')


    def getPhotoDescription(self):
        content = self.api.SendRequest2(self.target + '/?__a=1')
        data = self.api.LastJson
        dd = data['graphql']['user']['edge_owner_to_timeline_media']['edges']

        if len(dd) > 0:
            pc.printout("\nWoohoo! We found " + str(len(dd)) + " descriptions\n", pc.GREEN)

            count = 1

            t = PrettyTable(['Photo', 'Description'])
            t.align["Photo"] = "l"
            t.align["Description"] = "l"
            
            for i in dd:
                node = i.get('node')
                t.add_row([str(count), node.get('accessibility_caption')])
                count += 1
            print(t)
        else:
            pc.printout("Sorry! No results found :-(\n", pc.RED)


            


        
        


        



    


        



    



