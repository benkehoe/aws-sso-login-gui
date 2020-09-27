import logging
import time
import argparse

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

from . import fakes, widgets, token_fetcher
from .config import Config

LOGGER = logging.getLogger("app")

logging.basicConfig(level=logging.DEBUG)

cache = {}

SESSION = None
def get_session():
    global SESSION
    if not SESSION:
        import botocore.session
        SESSION = botocore.session.Session()
    return SESSION

def get_config_loader(parser, args):
    if args.fake_config:
        import botocore.configloader
        config_data = botocore.configloader.load_config(args.fake_config)
        return fakes.get_config_loader(config_data['profiles'])
    session = get_session()
    def config_loader():
        return session.full_config['profiles']
    return config_loader

def get_token_fetcher_kwargs(parser, args):
    kwargs = {}
    if args.token_fetcher_controls:
        parser.error("Not implemented")
    if args.fake_token_fetcher:
        kwargs['delay'] = 20
    kwargs['on_pending_authorization'] = token_fetcher.on_pending_authorization
    return kwargs

def get_token_fetcher_creator(parser, args):
    kwargs = get_token_fetcher_kwargs(parser, args)
    if args.fake_token_fetcher:
        token_fetcher_creator = fakes.get_token_fetcher_creator(**kwargs)
    else:
        kwargs['session'] = get_session()
        token_fetcher_creator = token_fetcher.get_token_fetcher_creator(**kwargs)
    return token_fetcher_creator

def initialize(parser, app, config_loader, token_fetcher_creator):
    icon = QIcon("sso-icon.png")

    app.setWindowIcon(icon)

    thread = QThread()

    config = Config(config_loader, token_fetcher_creator)

    config.moveToThread(thread)

    thread.started.connect(config.reload)

    window = widgets.AWSSSOLoginWindow(config)
    tray_icon = widgets.AWSSSOLoginTrayIcon(icon, config)

    return config, thread, window, tray_icon

class ThreadIdLogger(QObject):
    def __init__(self, thread_name):
        super().__init__()
        self.thread_name = thread_name

    def log_id(self):
        LOGGER.debug('%s thread id: %i', self.thread_name, int(QThread.currentThreadId()))

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--log-level', '-l', choices=['DEBUG', 'INFO'])

    parser.add_argument('--fake-config')

    parser.add_argument('--fake-token-fetcher', action='store_true')

    parser.add_argument('--token-fetcher-controls', action='store_true')

    args = parser.parse_args()

    log_kwargs = {}
    if args.log_level:
        log_kwargs['level'] = getattr(logging, args.log_level)
    logging.basicConfig(**log_kwargs)

    app = QApplication([])

    config_loader = get_config_loader(parser, args)

    token_fetcher_creator = get_token_fetcher_creator(parser, args)

    config, thread, window, tray_icon = initialize(parser, app, config_loader, token_fetcher_creator)

    window.show()
    tray_icon.show()

    ThreadIdLogger("main").log_id()
    worker_thread_logger = ThreadIdLogger("worker")
    worker_thread_logger.moveToThread(thread)
    thread.started.connect(worker_thread_logger.log_id)

    thread.start()

    def on_close():
        print('on_close')
        thread.terminate()

    app.lastWindowClosed.connect(on_close)

    return app.exec_()
