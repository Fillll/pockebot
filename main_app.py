#encoding:utf-8

import sys
import argparse
import asyncio
import re
import urllib.request as req
from os.path import join
from pprint import pprint
import time

import yaml
import requests
import telepot
from telepot.delegate import per_from_id
from telepot.aio.delegate import create_open
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton

import config
import config.translation as tr
import db_actions as db
import pocket_actions as pocket
from audio_actions import make_an_audio


class PocketBot(telepot.aio.helper.ChatHandler):
    def __init__(self, seed_tuple, timeout, is_main=True, config=None):
        super(PocketBot, self).__init__(seed_tuple, timeout)
        self.visit_time = 0
        self.find_url = re.compile('(https?://[^\s]+)')
        self.find_tag = re.compile("#[\w']+")
        self.mongo = db.PockebotDBSlave(config)
        self.is_main = is_main
        self.messages = list()
        self.pocket_client = pocket.PocketbotPocketSlave(config['pocket_token'])
        # For forwarding /feedback messages
        self.stuff_bot = telepot.Bot(config['support_bot_token'])
        self.dev_group_chat = config['developers_group']
        # User state
        self.lang = 'en'
        self.tags_promt = True
        self.set_pockebot_tag = True
        self.session_cnt = 0
        self.audio = False
        self.request_chat_id = None
        self._edit_msg_ident = None
        self._editor = None
        self.waiting_for_menu_action = False
        self.reading_time_tag = True

    async def on_close(self, ex):
        await self._cancel_last()
        self.mongo.save_unrecognized_messages(self.messages)
        state = {
            'lang': self.lang,
            'tags_promt': self.tags_promt,
            'set_pockebot_tag': self.set_pockebot_tag,
            'reading_time_tag': self.reading_time_tag,
            'audio': self.audio,
            'stat': {
                'session_cnt': self.session_cnt + 1
            },
            'tech': {
                '_edit_msg_ident': self._edit_msg_ident,
                'waiting_for_menu_action': False
            }
        }
        self.mongo.save_state(state)

    # def __del__(self):
    #     self.on_close()

    def __debug_print(self, what):
        if not self.is_main:
            pprint(what)

    def get_state(self):
        state = self.mongo.get_state()
        self.lang = state.get('lang', 'en')
        self.tags_promt = state.get('tags_promt', True)
        self.set_pockebot_tag = state.get('set_pockebot_tag', True)
        self.reading_time_tag = state.get('reading_time_tag', True)
        self.audio = state.get('audio', False)
        self.session_cnt = state.get('stat', dict()).get('session_cnt', 0)
        self._edit_msg_ident = state.get('tech', dict()).get('_edit_msg_ident')
        if self._edit_msg_ident is None:
            self._edit_msg_ident = (1, 1)
        self._edit_msg_ident = tuple(self._edit_msg_ident)
        self._editor = telepot.aio.helper.Editor(self.bot, self._edit_msg_ident)
        self.waiting_for_menu_action = state.get('tech', {}).get('waiting_for_menu_action', False)

    def is_user_known(self):
        if self.pocket_client.access_token is None:
            access_key, _ = self.mongo.get_access_key()
            if access_key is None:
                return False
            else:
                self.pocket_client.set_access_token(access_key)
                self.get_state()
                return True
        return True

    def make_authorization(self):
        access_key, is_old_user = self.mongo.get_access_key()
        if access_key is None:
            self.mongo.save_authorization_log(why='Found no access key.')

            self.request_token = self.mongo.get_request_key()
            msg = None
            if self.request_token is not None:
                # If auth step 2 fails, msg will be None.
                msg = self.make_authorization_2()

            if msg is None:
                msg = self.make_authorization_1()

            if is_old_user:
                msg = self.say('sorry_but_v2') + msg

            return msg

    def make_authorization_1(self):
        self.request_token = self.pocket_client.get_request_token()
        self.mongo.save_authorization_log(why='Got request token.',
                                          request_token=self.request_token)
        auth_url = self.pocket_client.get_auth_url(self.request_token)
        msg = self.say('auth_me') + '[' + auth_url + '](' + auth_url + ')'
        return msg

    def make_authorization_2(self):
        try:
            access_token = self.pocket_client.get_access_token(self.request_token)
            self.mongo.save_authorization_log(why='Got access token.')
        except:
            self.mongo.save_authorization_log(why='Use old request token.',
                                              error=str(sys.exc_info()[0]))
            return None

        self.mongo.save_access_token(access_token)
        return self.say('auth_complete')

    def get_tags_keyboard(self):
        def pairwise(iterable):
            n = len(iterable)
            res = []
            for i in range(int(n / 2)):
                res.append(['#%s' % iterable[2 * i], '#%s' % iterable[2 * i + 1]])
                if 2 * (i + 1) + 1 == n:
                    res.append(['#%s' % iterable[2 * (i + 1)]])
            if n == 1:
                res.append(['#%s' % iterable[0]])
            return res

        used_tags = self.mongo.get_ordered_tags()
        buttons = pairwise(used_tags)
        keyboard = {'hide_keyboard': True}
        if len(used_tags) > 0 and self.tags_promt is True:
            buttons.append(['/help ❓', '/news 📰'])
            keyboard = {'keyboard': buttons}
        return keyboard

    async def add(self, urls, tags, text):
        self.mongo.update_tags_stat(tags)
        keyboard = self.get_tags_keyboard()
        if len(urls) > 0:
            if self.set_pockebot_tag:
                tags.append('pockebot')
            items = {}
            for i, url in enumerate(urls):
                key, val = await self.pocket_client.add_url(url, tags)
                items[key] = val
                if items[key]['title'] is None:
                    items[key]['title'] = self.say('unknown_title')
                items[key]['response_text'] = '{title} _(~{timing} {mins})_\n'.format(title=items[key]['title'],
                                                                                      timing=int(items[key]['timing']),
                                                                                      mins=self.say('minutes'))
                if self.reading_time_tag:
                    t = int(items[key]['timing'])
                    if t == 1:
                        timing_tag = '~timing: 1 min'
                    elif t <= 5:
                        timing_tag = '~timing: 1-5 min'
                    elif t <= 10:
                        timing_tag = '~timing: 5-10 min'
                    elif t <= 20:
                        timing_tag = '~timing: 10-20 min'
                    elif t <= 30:
                        timing_tag = '~timing: 20-30 min'
                    elif t > 30:
                        timing_tag = '~timing: 30+ min'
                    self.pocket_client.add_tags([key], [timing_tag])

            if len(items) > 1:
                what = '\n'
                for i, item in enumerate(items):
                    what += str(i + 1) + '. ' + items[item]['response_text']
            else:
                
                key = list(items.keys())[0]
                what = ' ' + str(items[key]['response_text'])
            response = self.say('added') + what

            self.mongo.save_url_response(text=text,
                                         saved_items=items)
            return response, keyboard

        elif len(tags) > 0:
            if self.set_pockebot_tag:
                tags.append('pockebot')
            last_items = self.mongo.get_last_items()
            self.pocket_client.add_tags(last_items, tags)
            return self.say('tags_added'), keyboard

    def parse(self, text):
        def dot_problem(s):
            # It is impossible to store dots as keys in mongodb. That is the
            # best work around I found. If you find better,
            # you know what to do :)
            # http://stackoverflow.com/questions/8429318/how-to-use-dot-in-field-name
            return s.replace('.', '\uff0e')

        def extract_hash_tags(s):
            # return list(set(dot_problem(part[1:]) for part in s.split() if part.startswith('#') and len(part) > 1))
            tags_list = self.find_tag.findall(s)
            if tags_list is None:
                return list()
            else:
                return [i[1:] for i in tags_list]

        def is_url_without_http(url):
            # Massive crutch
            request = req.Request(url)
            try:
                response = req.urlopen(request)
                return True
            except:
                try:
                    request = requests.get(url)
                    if request.status_code == 200:
                        return True
                    else:
                        return False
                except:
                    return False

        tags = extract_hash_tags(text)
        self.mongo.update_tags_stat(tags)

        urls = []
        candidates = text.split()
        for candidate in candidates:
            self.__debug_print(candidate)
            if self.find_url.search(candidate.lower()) is not None:
                urls.append(candidate)
                self.__debug_print('First type url.')
            elif is_url_without_http('http://' + candidate):
                urls.append('http://' + candidate)
                self.__debug_print('Second type url.')
            elif is_url_without_http('https://' + candidate):
                urls.append('https://' + candidate)
                self.__debug_print('Third type url.')
            else:
                self.__debug_print('Fourth type nonurl.')

        return urls, tags

    def store_feedback(self, message):
        self.mongo.save_feedback(message=message)
        self.stuff_bot.sendMessage(self.dev_group_chat, '#feedback_from_pockebot is below:')
        time.sleep(1.23456)
        self.stuff_bot.sendMessage(self.dev_group_chat, message)

    def store_contacts(self, message):
        if self.visit_time == 0:
            self.mongo.save_credentials(message)

    def say(self, what=None):
        if what is None:
            what = 'pocket_error'
        try:
            message = getattr(tr, what)[self.lang]
        except KeyError:
            message = getattr(tr, what)['en']
        return message

    def process_command(self, inbox):
        def on_sym(word, value, on_off):
            if value is on_off:
                return '✔ %s' % word
            return word
        to_send_msg = self.say('unknown_command')
        keyboard = {'hide_keyboard': True}
        words = inbox.split()
        if words[0] == '/help' and self.known_user:
            to_send_msg = self.say('help')
        elif words[0] == '/help' and not self.known_user:
            to_send_msg = self.say('help_for_new')
        elif words[0] == '/feedback' and len(words) == 1:
            to_send_msg = self.say('no_feedback')
        elif words[0] == '/feedback' and len(words) > 1:
            self.store_feedback(inbox)
            to_send_msg = self.say('got_feedback')
        elif words[0] == '/news':
            to_send_msg = self.say('news')
        elif words[0] == '/settings':
            to_send_msg = self.say('select_one')
            self.waiting_for_menu_action = True
            # self.hide_keyboard()
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='Language', callback_data='/lang'),
                 InlineKeyboardButton(text='Tags', callback_data='/tags')],
                [InlineKeyboardButton(text='Audio', callback_data='/audio')],
                [InlineKeyboardButton(text='Cancel', callback_data='/cancel')],
            ])
        # TAGS
        elif words[0] == '/tags':
            if len(words) == 1:
                to_send_msg = None
                tags_promt_on = on_sym('Tags promt on', self.tags_promt, True)
                tags_promt_off = on_sym('Tags promt off', self.tags_promt, False)
                pockebot_tag_on = on_sym('Pockebot tag on', self.set_pockebot_tag, True)
                pockebot_tag_off = on_sym('Pockebot tag off', self.set_pockebot_tag, False)
                reading_time_tag_on = on_sym('Reading time tag on', self.reading_time_tag, True)
                reading_time_tag_off = on_sym('Reading time tag off', self.reading_time_tag, False)
                
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=tags_promt_on, callback_data='/tags promt on'),
                     InlineKeyboardButton(text=tags_promt_off, callback_data='/tags promt off')],
                    [InlineKeyboardButton(text=pockebot_tag_on, callback_data='/tags pockebot on'),
                     InlineKeyboardButton(text=pockebot_tag_off, callback_data='/tags pockebot off')],
                    [InlineKeyboardButton(text=reading_time_tag_on, callback_data='/tags reading on'),
                     InlineKeyboardButton(text=reading_time_tag_off, callback_data='/tags reading off')],
                    [InlineKeyboardButton(text='Cancel', callback_data='/cancel')]
                    ]
                )
            elif words[1] == 'promt':
                if words[2] == 'on':
                    self.tags_promt = True
                    to_send_msg = self.say('ok')
                elif words[2] == 'off':
                    self.tags_promt = False
                    to_send_msg = self.say('ok')
            elif words[1] == 'pockebot':
                if words[2] == 'on':
                    self.set_pockebot_tag = True
                    to_send_msg = self.say('ok')
                elif words[2] == 'off':
                    self.set_pockebot_tag = False
                    to_send_msg = self.say('ok')
            elif words[1] == 'reading':
                if words[2] == 'on':
                    self.reading_time_tag = True
                    to_send_msg = self.say('ok')
                elif words[2] == 'off':
                    self.reading_time_tag = False
                    to_send_msg = self.say('ok')
            else:
                to_send_msg = self.say('use_keyboard')
        elif words[0] == '/cancel':
            self._cancel_last()
            to_send_msg = self.say('ok')
        # LANG
        elif words[0] == '/lang':
            if len(words) == 1:
                to_send_msg = None
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='English', callback_data='/lang en'),
                     InlineKeyboardButton(text='Russian', callback_data='/lang ru')],
                    [InlineKeyboardButton(text='Italian', callback_data='/lang it'),
                     InlineKeyboardButton(text='Portuguese', callback_data='/lang pt')],
                    [InlineKeyboardButton(text='Other', callback_data='/lang other')],
                    [InlineKeyboardButton(text='Cancel', callback_data='/cancel')]
                ])
            elif words[1] == 'en':
                self.lang = 'en'
                to_send_msg = self.say('ok')
            elif words[1] == 'ru':
                self.lang = 'ru'
                to_send_msg = self.say('ok')
            elif words[1] == 'it':
                self.lang = 'it'
                to_send_msg = self.say('ok')
            elif words[1] == 'pt':
                self.lang = 'pt'
                to_send_msg = self.say('ok')
            else:
                to_send_msg = self.say('new_lang')
        # AUDIO
        elif words[0] == '/audio':
            if len(words) == 1:
                to_send_msg = None
                audio_on = on_sym('Audio on (Deep beta!)', self.audio, True)
                audio_off = on_sym('Audio off', self.audio, False)

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=audio_on, callback_data='/audio on'),
                     InlineKeyboardButton(text=audio_off, callback_data='/audio off')],
                    [InlineKeyboardButton(text='Cancel', callback_data='/cancel')]
                ])
            elif words[1] == 'on':
                self.audio = True
                to_send_msg = self.say('ok')
            elif words[1] == 'off':
                self.audio = False
                to_send_msg = self.say('ok')
        return to_send_msg, keyboard

    def get_urls_and_tags(self, msg):
        urls_list = []
        tags_list = []

        if 'entities' in msg:
            for entity in msg['entities']:
                if entity['type'] == 'text_link':
                    msg['text'] = msg.get('text', '') + ' ' + entity['url']
                    urls_list.append(entity['url'])
                elif entity['type'] == 'url':
                    start = entity['offset']
                    end = entity['offset'] + entity['length']
                    url = msg['text'][start:end]
                    if not (url.startswith('http://') or url.startswith('https://')):
                        url = 'http://' + url
                    urls_list.append(url)
                elif entity['type'] == 'hashtag':
                    start = entity['offset'] + 1
                    end = entity['offset'] + entity['length']
                    tags_list.append(msg['text'][start:end])

        if len(urls_list) == 0 and len(tags_list) == 0:
            if 'caption' in msg:
                u, t = self.parse(msg['caption'])
                urls_list.extend(u)
                tags_list.extend(t)
            if 'text' in msg:
                u, t = self.parse(msg['text'])
                urls_list.extend(u)
                tags_list.extend(t)
        return urls_list, tags_list

    def need_audio(self):
        last_items = self.mongo.get_last_entry()
        val = max(last_items.keys())
        item = last_items[val]
        url = item['resolved_url']
        lang = item['lang']
        filename = str(self.request_chat_id) + '_' + val + '.mp3'
        try:
            make_an_audio(url, filename, lang)
            return filename
        except:
            return None

    def has_command(self, msg):
        if 'entities' in msg:
            for entity in msg['entities']:
                if entity['type'] == 'bot_command' and entity['offset'] == 0:
                    return True
        return False

    async def _cancel_last(self):
        if self._editor:
            await self._editor.editMessageReplyMarkup(reply_markup=None)
            self._editor = None
            self._edit_msg_ident = None

    async def on_callback_query(self, msg):
        query_id, self.request_chat_id, query_data = telepot.glance(msg, flavor='callback_query')
        self.mongo.chat_id = self.request_chat_id
        self.store_contacts(msg)
        self.known_user = self.is_user_known()
        self.__debug_print('>')
        self.__debug_print('> callback')
        self.__debug_print(msg)
        to_send_msg, keyboard = self.process_command(query_data)

        if to_send_msg is None:
            await self._editor.editMessageReplyMarkup(reply_markup=keyboard)
            self.waiting_for_menu_action = True
        else:
            await self._cancel_last()
            sent = await self.sender.sendMessage(to_send_msg, reply_markup=keyboard, parse_mode='Markdown')
            self._editor = telepot.aio.helper.Editor(self.bot, sent)
            self._edit_msg_ident = telepot.message_identifier(sent)
            self.waiting_for_menu_action = False

    async def on_chat_message(self, msg):
        content_type, chat_type, self.request_chat_id = telepot.glance(msg)
        self.mongo.chat_id = self.request_chat_id
        self.store_contacts(msg)
        self.known_user = self.is_user_known()
        self.__debug_print('>')
        # self.__debug_print(msg)

        if self.waiting_for_menu_action is True:
            await self._cancel_last()
        self.waiting_for_menu_action = False

        any_commands = self.has_command(msg)

        if 'text' not in msg:
            msg['text'] = '±notext±'

        if chat_type == 'private':

            keyboard = {'hide_keyboard': True}
            to_send_msg = self.say('pocket_error')
            self.visit_time += 1
            inbox = msg['text']

            if any_commands and (self.known_user or (not self.known_user and inbox != '/start Done' and inbox != '/start')):
                to_send_msg, keyboard = self.process_command(inbox)
            else:
                if self.known_user:
                    urls, tags = self.get_urls_and_tags(msg)
                    if len(urls) > 0 or len(tags) > 0:
                        to_send_msg, keyboard = await self.add(urls, tags, inbox)
                        if len(urls) > 0 and self.audio is True:
                            filename = self.need_audio()
                            if filename is not None:
                                f = open(join('audio', filename), 'rb')
                                await self.sender.sendVoice(f, reply_markup=keyboard)
                    else:
                        self.messages.append(msg)
                        to_send_msg, keyboard = self.say('nothing'), {'hide_keyboard': True}
                else:
                    to_send_msg = self.make_authorization()

            # Send message. Always update keyboard and always `Markdown` mode. Be careful messages
            # with `_` in text are dagerous.
            sent = await self.sender.sendMessage(to_send_msg, reply_markup=keyboard, parse_mode='Markdown')
            self._editor = telepot.aio.helper.Editor(self.bot, sent)
            self._edit_msg_ident = telepot.message_identifier(sent)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='conf/prod.yml')
    args = parser.parse_args()
    with open(args.config) as config_file:
        config = yaml.load(config_file.read())
    # Is it main app or test app
    is_main = config['pockebot_is_main']

    # Got Telegram bot access token
    # config_manager = db.PockebotDBSlave(config)
    # token = config_manager.get_bot_token()
    token = config['telegram_token']

    bot = telepot.aio.DelegatorBot(token, [
        (per_from_id(), create_open(PocketBot,
                                    timeout=60,
                                    is_main=is_main,
                                    config=config)),
    ])
    loop = asyncio.get_event_loop()

    loop.create_task(bot.message_loop())
    print('Listening ...')

    loop.run_forever()


if __name__ == '__main__':
    main()