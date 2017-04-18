#!/usr/bin/env python
'''
Front-end for the Securitybot database.
'''
# Python includes
import argparse
import json
from csv import reader
import logging
import os

# Tornado includes
import tornado.httpserver
import tornado.ioloop
import tornado.netutil
import tornado.web

# Securitybot includes
import securitybot_api as api
from securitybot.tasker.tasker import Escalation
from securitybot.util import init_scribe_logging, init_sentry_logging

# Typing
from typing import Sequence


class BaseHandler(tornado.web.RequestHandler):
    pass


# Sentry integration
SENTRY_DSN = os.getenv('SENTRY_DSN')
if SENTRY_DSN:
    from raven.contrib.tornado import SentryMixin
    BaseHandler.__bases__ = (SentryMixin,) + BaseHandler.__bases__


def get_endpoint(handler, defaults, callback):
    '''
    Makes a call to an API endpoint, using parameters from default.
    '''
    try:
        args = {}
        for name, default, parser in defaults:
            arg = handler.get_argument(name, default=None)
            if arg is None:
                args[name] = default
            else:
                args[name] = parser(arg)
        handler.write(callback(**args))
    except Exception as e:
        handler.write(api.exception_response(e))


# List of tuples of name, default, parser
QUERY_ARGUMENTS = [
    ('limit', 50, int),
    ('titles', None, lambda s: list(reader([s]))[0]),
    ('ldap', None, lambda s: list(reader([s]))[0]),
    ('status', None, int),
    ('performed', None, int),
    ('authenticated', None, int),
    ('after', None, int),
    ('before', None, int),
]


class QueryHandler(BaseHandler):
    def get(self):
        get_endpoint(self, QUERY_ARGUMENTS, api.query)


IGNORED_ARGUMENTS = [
    ('limit', 50, int),
    ('ldap', None, lambda s: list(reader([s]))[0]),
]


class IgnoredHandler(BaseHandler):
    def get(self):
        get_endpoint(self, IGNORED_ARGUMENTS, api.ignored)


BLACKLIST_ARGUMENTS = [
    ('limit', 50, int),
]


class BlacklistHandler(BaseHandler):
    def get(self):
        get_endpoint(self, BLACKLIST_ARGUMENTS, api.blacklist)


class NewAlertHandler(BaseHandler):
    def post(self):
        response = api.build_response()
        post_args = {}
        for name in ['title', 'ldap', 'description', 'reason']:
            post_args[name] = self.get_argument(name, default=None)
            if post_args[name] is None:
                response['error'] += 'ERROR: {} must be specified!\n'.format(name)
        post_args['url'] = self.get_argument('url', default=None)

        escalation_list = self.escalation_list_from_json(self.get_argument('escalation', default=None))
        logging.debug('Escalation list: %s' % (str(escalation_list), ))
        if all(v is not None for v in post_args.values()):
            self.write(api.create_alert(post_args['ldap'],
                                        post_args['title'],
                                        post_args['description'],
                                        post_args['reason'],
                                        url=post_args['url'],
                                        escalation=escalation_list
                                        ))
        else:
            self.write(response)

    def escalation_list_from_json(self, raw_json):
        if not raw_json:
            logging.debug('Received escalation parameter is empty')
            return []

        try:
            escalation_list = json.loads(raw_json)
        except ValueError:
            logging.warning("Parsing JSON from 'escalation' parameter failed.")
            return []

        if not isinstance(escalation_list, list):
            logging.debug("Escalation list is not a list.")
            return []

        result = []
        for escalation_dict in escalation_list:
            if isinstance(escalation_dict, dict):
                try:
                    ldap = escalation_dict.get('ldap', '')
                    delay_sec = int(escalation_dict.get('delay_in_sec', 0))
                    logging.debug("Adding to escalation '%s' with %d sec delay." % (ldap, delay_sec))
                    result.append(Escalation(ldap, delay_sec))
                except (ValueError, TypeError):
                    logging.debug("Couldn't convert delay_in_sec to integer")
        return result


class IndexHandler(BaseHandler):
    def get(self):
        self.render()

    def render(self):
        self.write(self.render_string("templates/index.html"))


class HealthcheckHandler(BaseHandler):
    def get(self):
        self.write('200 OK')


class SecuritybotService(object):
    '''Registers handlers and kicks off the HTTPServer and IOLoop'''

    def __init__(self, port):
        # type: (str, str, bool) -> None
        self.requests = 0
        self.port = port
        static_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static/')
        self._app = tornado.web.Application([
            (r'/', IndexHandler),
            (r'/healthcheck', HealthcheckHandler),
            (r'/api/query', QueryHandler),
            (r'/api/ignored', IgnoredHandler),
            (r'/api/blacklist', BlacklistHandler),
            (r'/api/create', NewAlertHandler),
        ],
            xsrf_cookie=True,
            static_path=static_path,
        )
        self.server = tornado.httpserver.HTTPServer(self._app)
        self.sockets = tornado.netutil.bind_sockets(self.port, '0.0.0.0')
        self.server.add_sockets(self.sockets)

        # Sentry integration
        if SENTRY_DSN:
            from raven.contrib.tornado import AsyncSentryClient
            self._app.sentry_client = AsyncSentryClient(SENTRY_DSN)

        for s in self.sockets:
            sockname = s.getsockname()
            logging.info('Listening on {socket}, port {port}'
                         .format(socket=sockname[0], port=sockname[1]))

    def start(self):
        # type: () -> None
        logging.info('Starting.')
        tornado.ioloop.IOLoop.instance().start()

    def stop(self):
        # type: () -> None
        logging.info('Stopping.')
        self.server.stop()

    def get_socket(self):
        # type: () -> Sequence[str]
        return self.sockets[0].getsockname()[:2]


def init():
    # type: () -> None
    logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s %(levelname)s] %(message)s')

    init_scribe_logging()
    init_sentry_logging()
    api.init_api()


def main(port):
    # type: (int) -> None
    logging.info('Starting up!')
    try:
        service = SecuritybotService(str(port))

        def shutdown():
            logging.info('Shutting down!')
            service.stop()
            logging.info('Stopped.')
            os._exit(0)

        service.start()
    except Exception as e:
        logging.error('Uncaught exception: {e}'.format(e=e))


if __name__ == '__main__':
    init()
    logging.warning("Securitybot [frontend] restarted.")
    parser = argparse.ArgumentParser(description='Securitybot frontend')
    parser.add_argument('--port', dest='port', default='8888', type=int)
    args = parser.parse_args()

    main(args.port)
