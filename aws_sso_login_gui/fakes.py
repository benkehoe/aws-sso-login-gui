import random
import string
import datetime
import hashlib
import time
import logging

from botocore.utils import tzutc
from botocore.compat import total_seconds

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QDateTimeEdit, QCheckBox, QPushButton, QFormLayout, QLineEdit, QVBoxLayout

LOGGER = logging.getLogger("fakes")

def get_config_loader(config):
    def config_loader():
        return config
    return config_loader

def get_token_fetcher_creator(on_pending_authorization,
        token_cache=None,
        time_fetcher=None,
        sleep=None,
        delay=None):
    def token_fetcher_creator(region):
        return FakeTokenFetcher(
            region=region,
            on_pending_authorization=on_pending_authorization,
            cache=token_cache,
            time_fetcher=time_fetcher,
            sleep=sleep,
            delay=delay,
        )
    return token_fetcher_creator

class FakeTokenFetcher:
    _EXPIRY_WINDOW = 5

    def __init__(self, region, on_pending_authorization,
            cache=None,
            time_fetcher=None,
            sleep=None,
            delay=None):
        self._sso_region = region
        self._on_pending_authorization = on_pending_authorization

        if cache is None:
            cache = {}
        self._cache = cache

        if time_fetcher is None:
            time_fetcher = self._utc_now
        self._time_fetcher = time_fetcher

        if not sleep:
            sleep = time.sleep
        self._sleep = sleep

        self._delay = delay

    def _utc_now(self):
        return datetime.datetime.now(tzutc())

    def _parse_if_needed(self, value):
        if isinstance(value, datetime.datetime):
            return value
        return dateutil.parser.parse(value)

    def _is_expired(self, response):
        end_time = self._parse_if_needed(response['expiresAt'])
        seconds = total_seconds(end_time - self._time_fetcher())
        return seconds < self._EXPIRY_WINDOW

    def _get_cache_key(self, start_url):
        return hashlib.sha1(start_url.encode('utf-8')).hexdigest()

    def get_expiration(self, start_url):
        cache_key = self._get_cache_key(start_url)
        if cache_key in self._cache:
            token = self._cache[cache_key]
            end_time = self._parse_if_needed(token['expiresAt'])
            return end_time

    def refresh_deadline(self, start_url):
        cache_key = self._get_cache_key(start_url)
        if cache_key in self._cache:
            token = self._cache[cache_key]
            end_time = self._parse_if_needed(token['expiresAt'])
            seconds = total_seconds(end_time - self._time_fetcher())
            return end_time - datetime.timedelta(seconds=self._EXPIRY_WINDOW)
        return None

    def needs_refresh(self, start_url):
        cache_key = self._get_cache_key(start_url)
        if cache_key in self._cache:
            token = self._cache[cache_key]
            return self._is_expired(token)
        return True

    def fetch_token(self, start_url, force_refresh=False):
        cache_key = self._get_cache_key(start_url)
        # Only obey the token cache if we are not forcing a refresh.
        if not force_refresh and cache_key in self._cache:
            token = self._cache[cache_key]
            if not self._is_expired(token):
                return token

        #user_code = 'user_code_' + ''.join(random.choice(string.ascii_uppercase+string.digits) for _ in range(6))
        user_code = random.choice(USER_CODES)

        authorization = {
            'deviceCode': 'deviceCode',
            'userCode': user_code,
            'verificationUri': 'https://images.google.com',
            'verificationUriComplete': 'https://google.com/search?tbm=isch&q=' + user_code,
            'expiresAt': self._time_fetcher() + datetime.timedelta(minutes=5),
        }

        self._on_pending_authorization(**authorization)

        if callable(self._delay):
            self._delay()
        elif self._delay:
            LOGGER.debug("Delaying for {} seconds".format(self._delay))
            self._sleep(self._delay)

        access_token = ''.join(random.choice(string.ascii_uppercase+string.digits) for _ in range(16))
        token = {
            'startUrl': start_url,
            'region': self._sso_region,
            'accessToken': access_token,
            'expiresAt': self._time_fetcher() + datetime.timedelta(minutes=1)
        }

        self._cache[cache_key] = token

        return self.refresh_deadline(start_url)

USER_CODES = [
    'kitten',
    'puppy',
    'chinchilla',
    'otter',
    'quokka',
]

class ControlsWidget(QWidget):
    time_changed = pyqtSignal()

    def __init__(self, test_token_fetcher):
        super().__init__()

        self._time = datetime.datetime.now(tz=tzutc())
        self._delay = 5

        self._outer_layout = QVBoxLayout()

        self.setLayout(self._outer_layout)

        self._widget = QWidget()
        self._layout = QFormLayout()
        self._widget.setLayout(self._layout)

        self._time_fetcher_input = QDateTimeEdit(self._time)
        self._layout.addRow("Current time", self._time_fetcher_input)

        self._time_fetcher_input.dateTimeChanged.connect(self._on_time_changed)

        self._delay_input = QLineEdit(str(self._delay))
        if test_token_fetcher:
            self._layout.addRow("Fake token fetcher login delay", self._delay_input)

        self._outer_layout.addWidget(self._widget)

        self._save_button = QPushButton("Save")
        self._outer_layout.addWidget(self._save_button)

        self._save_button.clicked.connect(self._on_save)

        self.logger = LOGGER.getChild("ControlsWidget")

    def _utc_now(self):
        return datetime.datetime.now(tzutc())

    def _on_time_changed(self, qt_datetime):
        pass

    def _on_save(self):
        self._delay = float(self._delay_input.text())
        time_value = self._time_fetcher_input.dateTime()
        self._time = datetime.datetime.fromtimestamp(time_value.toSecsSinceEpoch(), tz=tzutc())
        self.logger.debug("delay set: %s", self._delay)
        self.logger.debug("time set:  %s", self._time.isoformat())
        self.time_changed.emit()

    def get_time(self):
        return self._time

    def delay(self):
        value = float(self._delay_input.text())
        time.sleep(value)
