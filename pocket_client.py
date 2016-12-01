# -*- coding: utf-8 -*-

import aiohttp
import logging
import json
import collections


logger = logging.getLogger(__name__)


class PocketException(Exception):
    pass


async def add(consumer_key, access_token, url, tags):
    data = {
        'url': url,
        'consumer_key': consumer_key,
        'access_token': access_token,
        'tags': tags,
    }
    headers = {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Accept': 'application/json',
    }
    async with aiohttp.ClientSession() as session:
        async with session.post('https://getpocket.com/v3/add',
                                data=json.dumps(data),
                                headers=headers) as response:
            if response.status == 200:
                text = await response.text()
                item = json.loads(text)['item']
                item_id = item['item_id']
                return item_id, item
            else:
                logger.error('Pocket returned code {}'.format(response.status))
                logger.error(await response.text())
                raise PocketException()