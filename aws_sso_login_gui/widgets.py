import datetime
import collections
import re
import os
import logging

import dateutil

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

from .config import (
    Config,
    STATUS_VALID,
    STATUS_EXPIRED,
    STATUS_REFRESHING,
    STATUS_REFRESH_FAILED,
    STATUS_DISABLED,
)

LOGGER = logging.getLogger("widgets")

def status_to_style(status):
    if status in [STATUS_VALID]:
        return "{}"
    elif status in [STATUS_EXPIRED, STATUS_REFRESH_FAILED]:
        return "QLabel { color : red }"
    elif status in [STATUS_REFRESHING]:
        return "QLabel { color : orange }"
    elif status in [STATUS_DISABLED]:
        return "QLabel { color : gray }"
    else:
        return "{}"

class SSOInstanceWidgets(QObject):
    def __init__(self, sso_id):
        super().__init__()
        self.sso_id = sso_id

        self.checkbox = QCheckBox()
        self.sso_id_label = QLabel(sso_id)
        self.status_label = QLabel('UNKNOWN')
        self.expiration_label = QLabel('UNKNOWN')
        self.refresh_button = QPushButton('Refresh')
        self.force_refresh_button = QPushButton('Force refresh')

        self.checkbox.setChecked(True)
        self.refresh_button.setEnabled(False)

        self.logger = LOGGER.getChild("SSOInstanceWidgets[{}]".format(self.sso_id))

    def update_status(self, status, expiration):
        self.logger.debug('update_status status=%s exp=%s', status, expiration)
        self.status_label.setText(status)
        self.status_label.setStyleSheet(status_to_style(status))
        if status == STATUS_DISABLED:
            self.refresh_button.setEnabled(False)
            self.force_refresh_button.setEnabled(False)
        else:
            self.force_refresh_button.setEnabled(True)
            if status in [STATUS_EXPIRED]:
                self.refresh_button.setEnabled(True)
            else:
                self.refresh_button.setEnabled(False)

        #TODO: parse and display something friendly
        expiration_text = expiration
        if expiration:
            exp_dt = datetime.datetime.fromisoformat(expiration)
            local_tz = dateutil.tz.gettz()
            exp_dt_local = exp_dt.astimezone(local_tz)
            expiration_text = exp_dt_local.strftime('%Y-%M-%d %H:%M:%S')
        self.expiration_label.setText(expiration_text)

    def decommision(self):
        #TODO: disconnect?
        pass

class AWSSSOLoginWindow(QWidget):

    needs_reload = pyqtSignal()
    needs_refresh = pyqtSignal([str], [str, bool])
    instance_enabled = pyqtSignal(str, bool)

    needs_import = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()

        self.config = config

        self.outer_layout = QVBoxLayout()
        self.setLayout(self.outer_layout)

        self.instances_widget = None
        self.instances_grid_layout = None

        self.widget_index = {}

        self.needs_reload.connect(self.config.reload)
        self.needs_refresh.connect(self.config.refresh)
        self.instance_enabled.connect(self.config.set_enable)
        self.needs_import.connect(self.config.import_config)

        self.config.reloaded.connect(self.on_reload)
        self.config.reload_status_update_finished.connect(self.on_reload_status_update_finished)
        self.config.status_changed.connect(self.on_status_changed)
        self.config.import_finished.connect(self.on_import_finished)

        self.buttons_widget = QWidget()
        self.outer_layout.addWidget(self.buttons_widget)

        self.buttons_layout = QHBoxLayout()
        self.buttons_widget.setLayout(self.buttons_layout)

        self.import_button = QPushButton("Import settings")
        self.buttons_layout.addWidget(self.import_button)
        self.import_button.clicked.connect(self.on_import_clicked)

        self.reload_button = QPushButton("Reload settings")
        self.buttons_layout.addWidget(self.reload_button)
        self.reload_button.clicked.connect(self.needs_reload)

        self.logger = LOGGER.getChild("AWSSSOLoginWindow")

    def on_reload(self, sso_instances):
        self.logger.debug('on_reload ids=%s', sso_instances)

        #TODO: reset grid
        if self.instances_widget:
            self.outer_layout.removeItem(self.outer_layout.itemAt(0))
            self.instances_widget.hide()

        self.instances_widget = QGroupBox("SSO instances")
        self.outer_layout.insertWidget(0, self.instances_widget)

        self.instances_grid_layout = QGridLayout()

        self.instances_widget.setLayout(self.instances_grid_layout)

        missing_instances = set(self.widget_index.keys())

        timezone_name = datetime.datetime.now(dateutil.tz.gettz()).strftime('%Z')

        self.instances_grid_layout.addWidget(QLabel("Enabled"), 0, 0)
        self.instances_grid_layout.addWidget(QLabel("SSO instance"), 0, 1)
        self.instances_grid_layout.addWidget(QLabel("Status"),       0, 2)
        self.instances_grid_layout.addWidget(QLabel("Expiration ({})".format(timezone_name)),   0, 3)

        for i, sso_id in enumerate(sso_instances):
            sso_instance_widgets = SSOInstanceWidgets(sso_id)
            self.instances_grid_layout.addWidget(sso_instance_widgets.checkbox,             i+1, 0)
            self.instances_grid_layout.addWidget(sso_instance_widgets.sso_id_label,         i+1, 1)
            self.instances_grid_layout.addWidget(sso_instance_widgets.status_label,         i+1, 2)
            self.instances_grid_layout.addWidget(sso_instance_widgets.expiration_label,     i+1, 3)
            self.instances_grid_layout.addWidget(sso_instance_widgets.refresh_button,       i+1, 4)
            self.instances_grid_layout.addWidget(sso_instance_widgets.force_refresh_button, i+1, 5)

            def on_checkbox_change(check_state, sso_id=sso_id):
                self.logger.debug('on_checkbox_change id=%s state=%s', sso_id, ['Unchecked', 'PartiallyChecked', 'Checked'][check_state])
                enabled = check_state == 2
                self.instance_enabled.emit(sso_id, enabled)
            sso_instance_widgets.checkbox.stateChanged.connect(on_checkbox_change)

            def on_click_refresh(value, sso_id=sso_id): # kwarg to capture current value of variable
                self.logger.debug('on_click_refresh id=%s value=%s', sso_id, value)
                self.needs_refresh.emit(sso_id)
            sso_instance_widgets.refresh_button.clicked.connect(on_click_refresh)

            def on_click_force_refresh(value, sso_id=sso_id): # kwarg to capture current value of variable
                self.logger.debug('on_click_force_refresh id=%s value=%s', sso_id, value)
                self.needs_refresh.emit(sso_id, True)
            sso_instance_widgets.force_refresh_button.clicked.connect(on_click_force_refresh)

            self.widget_index[sso_id] = sso_instance_widgets
            missing_instances.discard(sso_id)

        for sso_id in missing_instances:
            sso_instance_widgets = self.widget_index.pop(sso_id)
            sso_instance_widgets.decommision()

    def on_reload_status_update_finished(self):
        pass

    def on_status_changed(self, sso_id, status, expiration):
        self.logger.debug('on_status_changed id=%s status=%s exp=%s', sso_id, status, expiration)
        sso_instance_widgets = self.widget_index[sso_id]
        sso_instance_widgets.update_status(status, expiration)

    def on_import_clicked(self):
        self.logger.debug("on_import_clicked")
        filename = QFileDialog.getOpenFileName(filter="INI files (*.ini)")[0]
        if not filename:
            return
        self.logger.info("Importing from %s", filename)
        self.needs_import.emit(filename)

    def on_import_finished(self, profile_names, error_str):
        self.logger.debug("on_import_finished: %s %s", profile_names, error_str)
        if error_str:
            message = 'Error during import: {}'.format(error_str)
        elif len(profile_names) == 0:
            message = 'Warning: no profiles found'
        elif len(profile_names) == 1:
            message = 'Successfully imported profile: {}'.format(profile_names[0])
        else:
            message = 'Successfully imported profiles: {}'.format(', '.join(profile_names))

        message_box = QMessageBox()
        message_box.setText(message)
        message_box.exec_()

class AWSSSOLoginTrayIcon(QSystemTrayIcon):
    needs_reload = pyqtSignal()
    needs_refresh = pyqtSignal([str], [str, bool])
    instance_enabled = pyqtSignal(str, bool)

    def __init__(self, icon, config):
        super().__init__(icon)
        self.setToolTip("AWS SSO")

        self.config = config

        self.expired = set()

        self.activated.connect(self._on_activated)
        self.messageClicked.connect(self._on_notification_clicked)

        self.config.reloaded.connect(self.on_reload)
        self.config.reload_status_update_finished.connect(self.on_reload_status_update_finished)
        self.config.status_changed.connect(self.on_status_changed)

        self.needs_reload.connect(self.config.reload)
        self.needs_refresh.connect(self.config.refresh)
        self.instance_enabled.connect(self.config.set_enable)

        self._reloading = False

        self.logger = LOGGER.getChild("AWSSSOLoginTrayIcon")

    def _show_message(self):
        if self.expired:
            verb = "have" if len(self.expired) > 1 else "has"
            ids = ', '.join(sorted(self.expired))
            self.showMessage("AWS SSO", "{} {} expired, click to log in".format(ids, verb))

    def on_reload(self, sso_ids):
        for sso_id in list(self.expired):
            if sso_id not in sso_ids:
                self.logger.debug("Removing %s from expired list", sso_id)
                self.expired.discard(sso_id)
        self._reloading = True

    def on_reload_status_update_finished(self):
        if self._reloading:
            self._show_message()
            self._reloading = False

    def on_status_changed(self, sso_id, status, expiration):
        self.logger.debug('on_status_changed id=%s status=%s exp=%s', sso_id, status, expiration)
        if status == STATUS_EXPIRED:
            self.expired.add(sso_id)
        else:
            self.expired.discard(sso_id)

        if not self._reloading and status == STATUS_EXPIRED and self.expired:
            self._show_message()

    def _on_activated(self, activation_reason):
        self.logger.debug('on_sys_tray_icon_activated', activation_reason)

    def _on_notification_clicked(self):
        self.logger.debug('on_notification_clicked expired=%s', sorted(self.expired))
        for sso_id in sorted(self.expired):
            self.needs_refresh.emit(sso_id)
