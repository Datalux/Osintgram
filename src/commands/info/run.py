import yaml
import readline
import signal
from prettytable import PrettyTable
from src import printcolors as pc
from src import utils as utils
import json
import sys
import time
from instagram_private_api import ClientError

from src.CommandFather import CommandFather


class Command(CommandFather):

    def __init__(self, status, api):
        super().__init__(status)
        self.status = status
        self.osintgram = api

        try:
            endpoint = 'users/{user_id!s}/full_detail_info/'.format(**{'user_id': self.osintgram.target_id})
            content = self.osintgram.get_api()._call_api(endpoint)
           
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

            self.status.print_output(user, no_table = True)

        except ClientError as e:
            print(e)
            pc.printout("Oops... user " + str(self.osintgram.target) + " not exist, please enter a valid username.", pc.RED)
            pc.printout("\n")

        self.status.release()
