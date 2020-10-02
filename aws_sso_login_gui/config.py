import datetime
import collections
import re
import os
import logging
import configparser
import traceback

import botocore.session
from botocore.utils import tzutc

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QThread

from .token_fetcher import SSOTokenFetcher
from .config_file_writer import write_values as write_config_profile_values

LOGGER = logging.getLogger("config")

STATUS_VALID = 'valid'
STATUS_EXPIRED = 'expired'
STATUS_REFRESHING = 'refreshing'
STATUS_REFRESH_FAILED = 'refresh_failed'
STATUS_DISABLED = 'disabled'
def _status_from_expired(expired):
    return STATUS_EXPIRED if expired else STATUS_VALID

class SSOInstance(QObject):
    status_changed = pyqtSignal(str, str, str)

    def __init__(self, sso_id, start_url, region, token_fetcher,
                time_fetcher=None):
        super().__init__()
        self._sso_id = sso_id
        self._start_url = start_url
        self._region = region
        self.profile_names = []
        self._enabled = True
        self._status = STATUS_EXPIRED
        self._expiration = None

        if not time_fetcher:
            time_fetcher = self._utc_now
        self._time_fetcher = time_fetcher

        self._token_fetcher = token_fetcher

        self._timer = QTimer()
        self._timer.setSingleShot(True)

        self._timer.timeout.connect(self._timer_event)

        self.logger = LOGGER.getChild("SSOInstance[{}]".format(sso_id))

    def _utc_now(self):
        return datetime.datetime.now(tzutc())

    def decommision(self):
        self._enabled = False
        self._timer.stop()

    @property
    def sso_id(self):
        return self._sso_id

    @property
    def start_url(self):
        return self._start_url

    @property
    def region(self):
        return self._region

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        old_value = self._enabled
        if value != old_value:
            self._enabled = value
            self.update_timer()
            self._emit()

    def get_status(self, update=False, _emit=True):
        changed = False
        if not self._enabled:
            return STATUS_DISABLED
        if not update:
            return self._status
        if self._status in [STATUS_REFRESHING, STATUS_DISABLED]:
            return self._status
        expired = self._token_fetcher.needs_refresh(self.start_url)
        if not expired and not self._expiration:
            self._expiration = self._token_fetcher.get_expiration(self.start_url)
            changed = True
        new_status = _status_from_expired(expired)
        old_status = self._status
        if new_status != old_status:
            self._status = new_status
            changed = True
        if changed and _emit:
            self._emit()
        return self._status

    def refresh(self, force_refresh=False):
        self.logger.info('Refreshing')
        if not self._enabled:
            return
        self._status = STATUS_REFRESHING
        self._emit()
        expiration = self._token_fetcher.fetch_token(self.start_url, force_refresh=force_refresh)
        #TODO: error handling
        self._status = STATUS_VALID
        self._expiration = expiration
        self.logger.info("Refreshed with expiration %s", self._expiration)
        self.update_timer()
        self._emit()

    @property
    def expiration(self):
        return self._expiration

    @expiration.setter
    def expiration(self, value):
        self._expiration = value
        self.update_timer(emit_on_expired=True)

    def update_timer(self, emit_on_expired=False):
        if not self._enabled:
            self.logger.debug("disabled, stopping timer")
            self._timer.stop()
            return
        if not self._expiration:
            return
        time_remaining = (self._expiration - self._time_fetcher()).total_seconds()
        if time_remaining <= 0:
            if self._status != STATUS_REFRESHING:
                self.logger.debug("no time remaining, setting status to expired")
                self._status = STATUS_EXPIRED
                self._expiration = None
                if emit_on_expired:
                    self._emit()
            else:
                self.logger.debug("no time remaining, but refresh in progress")
        else:
            self._timer.start(time_remaining*1000)
            self.logger.debug("timer started %s", time_remaining)

    def _timer_event(self):
        self.logger.debug("Timer expired")
        if self._status in [STATUS_VALID, STATUS_REFRESH_FAILED]:
            self._status = STATUS_EXPIRED
            self._emit()

    def _emit(self):
        expiration = self.expiration
        if expiration is None:
            expiration = ''
        else:
            expiration = expiration.isoformat()
        status = STATUS_DISABLED if not self._enabled else self._status
        self.status_changed.emit(self.sso_id, status, expiration)

class Config(QObject):

    status_changed = pyqtSignal(str, str, str)
    reloaded = pyqtSignal(list)
    reload_status_update_finished = pyqtSignal()

    import_finished = pyqtSignal(list, str)

    def __init__(self, config_loader, token_fetcher_creator,
                session_fetcher=None, time_fetcher=None):
        super().__init__()
        self.config_loader = config_loader
        self._token_fetcher_creator = token_fetcher_creator
        self.ignore_list = []
        self.sso_instances = {}
        self.misconfigured_profiles = []
        self._token_fetchers = {}

        self._session_fetcher = session_fetcher
        self._time_fetcher = time_fetcher

        self.logger = LOGGER.getChild("Config")

    @pyqtSlot()
    def reload(self):
        self.logger.info("Reloading")
        self._load_instances()
        instances = sorted(self.sso_instances.keys())
        self.reloaded.emit(instances)
        for sso_id, instance in self.sso_instances.items():
            status = instance.get_status(update=True, _emit=False)
            self.logger.info("Loaded SSO instance %s (%s) for profiles %s", sso_id, status, instance.profile_names)
            instance._emit()
        self.reload_status_update_finished.emit()

    @pyqtSlot(str)
    @pyqtSlot(str, bool)
    def refresh(self, sso_id, force_refresh=False):
        instance = self.sso_instances[sso_id]
        instance.refresh(force_refresh=force_refresh)

    @pyqtSlot(str, bool)
    def set_enable(self, sso_id, enable):
        self.sso_instances[sso_id].enabled = enable

    @pyqtSlot()
    def update_timers(self):
        for sso_id, instance in self.sso_instances.items():
            instance.update_timer(emit_on_expired=True)

    def _on_instance_status_changed(self, sso_id, status, expiration):
        self.logger.debug("Status changed id=%s status=%s exp=%s", sso_id, status, expiration)
        self.status_changed.emit(sso_id, status, expiration)

    def _load_instances(self):
        config = self.config_loader()
        self.misconfigured_profiles.clear()
        missing_sso_instances = set(self.sso_instances.keys())
        for profile_name, profile_data in config.items():
            self.logger.debug("profile %s: %s", profile_name, profile_data)
            #TODO: warn on misconfigured profiles
            if 'sso_start_url' in profile_data and 'sso_region' in profile_data:
                self.logger.debug("%s is an SSO profile", profile_name)

                start_url = profile_data['sso_start_url']
                region = profile_data['sso_region']

                if any(re.search(pattern, start_url) for pattern in self.ignore_list):
                    self.logger.debug("Ignorning profile")
                    continue

                sso_id = start_url

                https_prefix = 'https://'
                if sso_id.startswith(https_prefix):
                    sso_id = sso_id[len(https_prefix):]

                start_url_suffix = '/start'
                if sso_id.endswith(start_url_suffix):
                    sso_id = sso_id[:-len(start_url_suffix)]

                awsapps_domain = '.awsapps.com'
                if sso_id.endswith(awsapps_domain):
                    sso_id = sso_id[:-len(awsapps_domain)]

                self.logger.info("SSO id %s for start URL %s", sso_id, start_url)

                if sso_id not in self.sso_instances:
                    self.logger.debug("Creating instance")
                    token_fetcher = self._get_token_fetcher(region)
                    self.sso_instances[sso_id] = SSOInstance(sso_id, start_url, region, token_fetcher, time_fetcher=self._time_fetcher)
                    self.sso_instances[sso_id].status_changed.connect(self._on_instance_status_changed)

                self.sso_instances[sso_id].profile_names.append(profile_name)

                missing_sso_instances.discard(sso_id)

        self.logger.info("Removed SSO instances: %s", list(missing_sso_instances))
        for sso_id in missing_sso_instances:
            sso_instance = self.sso_instances.pop(sso_id)
            sso_instance.decommision()

    def _get_token_fetcher(self, region):
        if region not in self._token_fetchers:
            self.logger.debug("Creating token fetcher for region %s", region)
            self._token_fetchers[region] = self._token_fetcher_creator(region)
        return self._token_fetchers[region]

    @pyqtSlot(str)
    def import_config(self, filename):
        try:
            parser = configparser.ConfigParser()
            result = parser.read(filename)

            profile_prefix = 'profile '
            profiles = {}
            for section in parser.sections():
                profile_name = section
                if profile_name.startswith(profile_prefix):
                    profile_name = profile_name[len(profile_prefix):]
                profiles[profile_name] = dict(parser.items(section))

            session = self._session_fetcher()

            for profile_name, profile_data in profiles.items():
                self.logger.info('writing profile %s', profile_name)
                write_config_profile_values(session, profile_name, profile_data)

            self.import_finished.emit(list(profiles.keys()), '')
            self.reload()
        except Exception as e:
            logger.error("An error occurred during import: %s\n%s", str(e), traceback.format_exc())
            self.import_finished.emit([], str(e))
