#encoding:utf-8

import argparse
import time
from os.path import join

import yaml
import telepot
import pymongo


def send(bot, tg_id, text):
    print('Sending...')
    try:
        bot.sendMessage(tg_id, text, parse_mode='Markdown')
        time.sleep(2)
    except Exception as e:
        print(e)
        time.sleep(10)


def main(config, file_with_msg):
    with open(file_with_msg) as f:
        text_to_send = f.read()
    bot = telepot.Bot(config['telegram_token'])
    mongo = pymongo.MongoClient(host=config['mongo']['host'])
    people = mongo[config['mongo']['db']]['people']
    already_sent = mongo[config['mongo']['db']]['people_sent']
    cursor = people.find({})
    count = 0
    for record in cursor:
        print('>> {}'.format(count))
        print(record)
        if already_sent.find_one({'id': record['id']}) is None:
            already_sent.insert_one({'id': record['id']})
            send(bot, record['id'], text_to_send)
        count += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=join('config', 'prod.yml'))
    parser.add_argument('--text')
    args = parser.parse_args()
    with open(args.config) as config_file:
        config = yaml.load(config_file.read())
    main(config, args.text)
