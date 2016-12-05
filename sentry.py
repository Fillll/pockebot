#enconding:utf-8

from os.path import join
import logging

import yaml
from raven import Client
from raven.handlers.logging import SentryHandler
from raven.conf import setup_logging


with open(join('config', 'sentry.yml')) as config_file:
    config = yaml.load(config_file.read())


if 'sentry_secret' in config:
    client = Client(config['sentry_secret'], auto_log_stacks=True)
    handler = SentryHandler(client)
    setup_logging(handler)
else:
    client = None
    logging.info('Sentry.io not loaded')


def report_error(fn):
    def wrapper(*args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception:
            if client:  # has sentry instance
                client.captureException()
            else:
                logging.exception('Exception Ignored.')
    return wrapper
