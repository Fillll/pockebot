# encoding:utf-8

import time
from pprint import pprint

from pocket import Pocket
import pocket_client

import config


class PocketbotPocketSlave(object):
    '''docstring for PocketbotPocketSlave'''

    def __init__(self, app_key):
        super(PocketbotPocketSlave, self).__init__()
        self.pocket_key = app_key
        self.access_token = None

    def set_access_token(self, access_token):
        self.access_token = access_token
        self.pocket_instance = Pocket(self.pocket_key, self.access_token)

    def get_request_token(self):
        return Pocket.get_request_token(consumer_key=self.pocket_key,
                                        redirect_uri=config.redirect_uri)

    def get_auth_url(self, request_token):
        return Pocket.get_auth_url(code=request_token,
                                   redirect_uri=config.redirect_uri)

    def get_access_token(self, request_token):
        user_credentials = Pocket.get_credentials(consumer_key=self.pocket_key,
                                                  code=request_token)
        return user_credentials['access_token']

    async def add_url(self, url, tags=None):
        if tags is None:
            tags = list()
        else:
            tags = tags[:]
        tags = ','.join(tags)
        trials = 0
        success = False
        item = {}
        item_id = None
        while not success and trials < 5:
            res = await pocket_client.add(self.pocket_key,
                                          self.access_token,
                                          url,
                                          tags)
            item_id, item = res
            if item.get('response_code') is not None:
                success = True
            trials += 1
        title = item.get('title', 'PockeError')
        item_id = item_id or -1
        lang = item.get('lang', 'en')
        resolved_url = item.get('resolved_url', 'http://fillll.ru/pockebot.html')
        timing = 0
        if title is not None:
            timing = (int(item.get('word_count', 0)) / 150) + 1
        item = {
            'timing': timing,
            'title': title,
            'url': url,
            'resolved_url': resolved_url,
            'lang': lang
        }
        # pprint({'a': item_id, 'b': item})
        return item_id, item

    def add_tags(self, items, tags=None):
        if not isinstance(tags, list):
            tags = ['pockebot']
        tags = ','.join(tags)
        # print(items, tags)
        for item in items:
            self.pocket_instance.tags_add(item, tags).commit()
