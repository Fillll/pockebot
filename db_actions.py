#encoding:utf-8

from datetime import datetime
from pprint import pprint

from pymongo import MongoClient


class PockebotDBSlave(object):
    '''
    docstring for PockebotDBSlave
    '''
    def __init__(self, config):
        super(PockebotDBSlave, self).__init__()
        self.chat_id = -1
        if config['mongo']['use_auth']:
            uri = 'mongodb://{user}:{password}@{host}:{port}/{db}'.format(
                **config['mongo']
            )
        else:
            uri = 'mongodb://{host}:{port}/{db}'.format(
                **config['mongo']
            )
        self.client = MongoClient(uri)
        self.db = self.client[config['mongo']['db']]

    def get_pocket_key_v1(self):
        config = self.db['config']
        return config.find_one()['APP_KEY']

    def get_pocket_key_v2(self):
        config = self.db['config']
        return config.find_one()['APP_KEY_v2']

    def get_bot_token(self):
        config = self.db['config']
        return config.find_one()['BOT_TOKEN']

    def get_access_key_v1(self):
        access_keys = self.db['access_keys']
        result = access_keys.find_one({'chat_id': self.chat_id})
        if result is None:
            return None
        return result.get('access_token', None)

    def get_access_key_v2(self):
        access_keys = self.db['access_keys_v2']
        result = access_keys.find_one({'chat_id': self.chat_id})
        if result is None:
            return None
        return result.get('access_token', None)

    def get_access_key(self):
        is_old_user = False
        if self.get_access_key_v1() is not None:
            is_old_user = True
        key_v2 = self.get_access_key_v2()
        return key_v2, is_old_user

    def save_unrecognized_messages(self, messages):
        if len(messages) > 0:
            doc = {
                'chat_id': self.chat_id,
                'ts': datetime.utcnow(),
                'messages': messages
            }
            self._save_something('messages', doc)

    def save_authorization_log(self, **kwargs):
        info = {
            'chat_id': self.chat_id,
            'ts': datetime.utcnow()
        }
        info.update(kwargs)
        self._save_something('request_keys_v2', info)

    def get_request_key(self):
        request_keys = self.db['request_keys_v2']
        res = request_keys.find({'chat_id': self.chat_id})
        request_tokens = {}
        request_token = None
        for item in res:
            if 'request_token' in item:
                request_tokens[item['ts']] = item['request_token']
        if len(request_tokens) > 0:
            # print(sorted(request_tokens.items(), reverse=True))
            request_token = sorted(request_tokens.items(), reverse=True)[0]
        return request_token

    def _save_something(self, collection, data):
        coll = self.db[collection]
        coll.insert_one(data)

    def save_access_token(self, token):
        doc = {
            'chat_id': self.chat_id,
            'access_token': token,
            'ts': datetime.utcnow()
        }
        self._save_something('access_keys_v2', doc)

    def move_access_tocken(self, tocken):
        access_keys = self.db['access_keys_v2']
        data = access_keys.find_one({'chat_id': self.chat_id})
        self._save_something('old_access_keys', data)
        access_keys.delete_one({'chat_id': self.chat_id})

    def save_url_response(self, **kwargs):
        info = {
            'chat_id': self.chat_id,
            'ts': datetime.utcnow()
        }
        # response_to_save = dict()
        # for i in kwargs.values():
        #     response_to_save[kwargs[]]
        info.update(kwargs)
        # pprint(info)
        self._save_something('urls', info)

    def save_feedback(self, **kwargs):
        info = {
            'chat_id': self.chat_id,
            'ts': datetime.utcnow()
        }
        info.update(kwargs)
        self._save_something('feedback', info)

    def save_credentials(self, msg):
        people_storage = self.db['people']
        if people_storage.find_one({'id': msg['from']['id']}) is None:
            people_storage.insert_one(msg['from'])
        chats_storage = self.db['chats']
        if chats_storage.find_one({'id': msg['chat']['id']}) is None:
            chats_storage.insert_one(msg['chat'])

    def update_tags_stat(self, tags):
        tags_storage = self.db['tags']
        res = tags_storage.find_one({'chat_id': self.chat_id})
        stat = {}
        if res is not None:
            stat = res['stat']
        for tag in tags:
            stat[tag] = stat.get(tag, 0) + 1

        if res is None:
            tags_storage.insert_one({'chat_id': self.chat_id,
                                     'stat': stat})
        else:
            tags_storage.update_one({'chat_id': self.chat_id},
                                    {'$set': {'stat': stat}})

    def get_last_items(self):
        url_storage = self.db['urls']
        urls = url_storage.find_one({'chat_id': self.chat_id}, sort=[('ts', -1)])
        if urls is not None:
            items = urls.get('saved_items', {}).keys()
            return items
        else:
            return None

    def get_last_entry(self):
        url_storage = self.db['urls']
        urls = url_storage.find_one({'chat_id': self.chat_id}, sort=[('ts', -1)])
        if urls is not None:
            items = urls.get('saved_items', {})
            return items
        else:
            return None

    def get_ordered_tags(self):
        tags_storage = self.db['tags']
        res = tags_storage.find_one({'chat_id': self.chat_id})
        if res is None:
            return None
        tags = res['stat']
        ordered_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)
        # print(ordered_tags)
        return [tag[0] for tag in ordered_tags]

    def get_state(self):
        state_storage = self.db['state']
        res = state_storage.find_one({'chat_id': self.chat_id})
        if res is None:
            return dict()
        return res.get('state', dict())

    def save_state(self, state):
        state['stat']['ts'] = datetime.utcnow()
        state_storage = self.db['state']
        res = state_storage.find_one({'chat_id': self.chat_id})
        if res is None:
            state_storage.insert_one({'chat_id': self.chat_id,
                                     'state': state})
        else:
            state_storage.update_one({'chat_id': self.chat_id},
                                     {'$set': {'state': state}})
