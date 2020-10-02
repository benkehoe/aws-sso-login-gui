import logging
import time
import os
import argparse

from PyQt5 import QtCore, QtWidgets, QtGui

from . import fakes, widgets, token_fetcher
from .config import Config

LOGGER = logging.getLogger("app")

logging.basicConfig(level=logging.DEBUG)

def get_session_vars(home_dir=None):
    if home_dir:
        return {
            'config_file': (None, None, os.path.expanduser(os.path.join(home_dir, '.aws.', 'config')), None),
            'credentials_file': (None, None, os.path.expanduser(os.path.join(home_dir, '.aws.', 'credentials')), None),
        }

SESSION = None
def get_session(refresh=False, home_dir=None):
    global SESSION
    if not SESSION or refresh:
        import botocore.session
        SESSION = botocore.session.Session(session_vars=get_session_vars(home_dir=home_dir))
    return SESSION

def get_config_loader(parser, args):
    if args.fake_config:
        import botocore.configloader
        config_data = botocore.configloader.load_config(args.fake_config)
        return fakes.get_config_loader(config_data['profiles'])
    def config_loader():
        session = get_session(refresh=True, home_dir=args.home_dir)
        return session.full_config['profiles']
    return config_loader

def get_token_fetcher_kwargs(parser, args):
    kwargs = {}
    if args.token_fetcher_controls:
        controls = fakes.ControlsWidget()
        if args.fake_token_fetcher:
            kwargs['delay'] = controls.delay
    else:
        controls = None
        if args.fake_token_fetcher:
            kwargs['delay'] = 20
    kwargs['on_pending_authorization'] = token_fetcher.on_pending_authorization
    if args.home_dir:
        kwargs['home_dir'] = args.home_dir
    return kwargs, controls

def get_token_fetcher_creator(parser, args):
    kwargs, controls = get_token_fetcher_kwargs(parser, args)
    if args.fake_token_fetcher:
        token_fetcher_creator = fakes.get_token_fetcher_creator(**kwargs)
    else:
        kwargs['session'] = get_session()
        token_fetcher_creator = token_fetcher.get_token_fetcher_creator(**kwargs)
    return token_fetcher_creator, controls

def initialize(parser, app, config_loader, token_fetcher_creator, time_fetcher=None):
    icon = QtGui.QIcon("sso-icon.ico")

    # app.setWindowIcon(icon)

    thread = QtCore.QThread()

    config = Config(config_loader, token_fetcher_creator, time_fetcher=time_fetcher, session_fetcher=get_session)

    config.moveToThread(thread)

    thread.started.connect(config.reload)

    window = widgets.AWSSSOLoginWindow(icon, config)
    tray_icon = widgets.AWSSSOLoginTrayIcon(icon, config)

    return config, thread, window, tray_icon

class ThreadIdLogger(QtCore.QObject):
    def __init__(self, thread_name):
        super().__init__()
        self.thread_name = thread_name

    def log_id(self):
        LOGGER.debug('%s thread id: %i', self.thread_name, int(QtCore.QThread.currentThreadId()))

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--log-level', '-l', choices=['DEBUG', 'INFO'])

    parser.add_argument('--fake-config')

    parser.add_argument('--fake-token-fetcher', action='store_true')

    parser.add_argument('--token-fetcher-controls', action='store_true')

    parser.add_argument('--home-dir')

    parser.add_argument('--wsl', nargs=2, metavar=('DISTRO', 'USER'))

    args = parser.parse_args()

    log_kwargs = {}
    if args.log_level:
        log_kwargs['level'] = getattr(logging, args.log_level)
    logging.basicConfig(**log_kwargs)

    if args.wsl:
        args.home_dir = os.path.join(r"\\wsl$", args.wsl[0], 'home', args.wsl[1])

    app = QtWidgets.QApplication([])

    config_loader = get_config_loader(parser, args)

    token_fetcher_creator, controls = get_token_fetcher_creator(parser, args)

    time_fetcher = None
    if controls:
        time_fetcher = controls.get_time

    config, thread, window, tray_icon = initialize(parser, app, config_loader, token_fetcher_creator, time_fetcher=time_fetcher)

    window.show()
    tray_icon.show()

    if controls:
        controls.time_changed.connect(config.update_timers)
        controls.setParent(window, QtCore.Qt.Window)
        controls.show()


    ThreadIdLogger("main").log_id()
    worker_thread_logger = ThreadIdLogger("worker")
    worker_thread_logger.moveToThread(thread)
    thread.started.connect(worker_thread_logger.log_id)

    thread.start()

    def on_close():
        LOGGER.debug('on_close')
        thread.terminate()

    app.lastWindowClosed.connect(on_close)

    return app.exec_()
