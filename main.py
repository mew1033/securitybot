#!/usr/bin/env python
import logging

from securitybot.bot import SecurityBot
from securitybot.chat.slack import Slack
from securitybot.tasker.sql_tasker import SQLTasker
from securitybot.auth.duo import DuoAuth
from securitybot.sql import init_sql
from os import getenv

import duo_client

CONFIG = {}
SLACK_KEY = getenv('SLACK_API_TOKEN', 'slack_api_token')
DUO_INTEGRATION = getenv('DUO_INTEGRATION_KEY')
DUO_SECRET = getenv('DUO_SECRET_KEY')
DUO_ENDPOINT = getenv('DUO_ENDPOINT')
REPORTING_CHANNEL = getenv('REPORTING_CHANNEL', 'some_slack_channel_id')
ICON_URL = 'https://dl.dropboxusercontent.com/s/t01pwfrqzbz3gzu/securitybot.png'

def init():
    # Setup logging
    logging.basicConfig(level=logging.DEBUG,
                        format='[%(asctime)s %(levelname)s] %(message)s')
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('usllib3').setLevel(logging.WARNING)

def main():
    init()
    init_sql()

    # Create components needed for Securitybot
    auth_builder = None
    if DUO_INTEGRATION and DUO_SECRET and DUO_ENDPOINT:
        duo_api = duo_client.Auth(
            ikey=DUO_INTEGRATION,
            skey=DUO_SECRET,
            host=DUO_ENDPOINT
        )
        auth_builder = lambda name: DuoAuth(duo_api, name)

    chat = Slack('securitybot', SLACK_KEY, ICON_URL)
    tasker = SQLTasker()

    sb = SecurityBot(chat, tasker, auth_builder, REPORTING_CHANNEL, 'config/bot.yaml')
    sb.run()

if __name__ == '__main__':
    main()
