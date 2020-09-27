import datetime
import collections
import re
import os
import logging

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

from .config import Config, STATUS_EXPIRED, STATUS_DISABLED

LOGGER = logging.getLogger("widgets")

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
        self.expiration_label.setText(expiration)

    def decommision(self):
        #TODO: disconnect?
        pass

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
        self.config.status_changed.connect(self.on_status_changed)

        self.needs_reload.connect(self.config.reload)
        self.needs_refresh.connect(self.config.refresh)
        self.instance_enabled.connect(self.config.set_enable)

        self.logger = LOGGER.getChild("AWSSSOLoginTrayIcon")

    def on_reload(self, sso_instances):
        pass

    def on_status_changed(self, sso_id, status, expiration):
        self.logger.debug('on_status_changed id=%s status=%s exp=%s', sso_id, status, expiration)
        if status == STATUS_EXPIRED:
            self.expired.add(sso_id)
        else:
            self.expired.discard(sso_id)

        if status == STATUS_EXPIRED and self.expired:
            verb = "have" if len(self.expired) > 1 else "has"
            ids = ', '.join(sorted(self.expired))
            self.showMessage("AWS SSO", "{} {} expired, click to log in".format(ids, verb))

    def _on_activated(self, activation_reason):
        self.logger.debug('on_sys_tray_icon_activated', activation_reason)

    def _on_notification_clicked(self):
        self.logger.debug('on_notification_clicked expired=%s', sorted(self.expired))
        for sso_id in sorted(self.expired):
            self.needs_refresh.emit(sso_id)

class AWSSSOLoginWindow(QWidget):

    needs_reload = pyqtSignal()
    needs_refresh = pyqtSignal([str], [str, bool])
    instance_enabled = pyqtSignal(str, bool)

    def __init__(self, config):
        super().__init__()

        self.outer_layout = QVBoxLayout()
        self.setLayout(self.outer_layout)

        self.instances_widget = QGroupBox("SSO instances")
        self.outer_layout.addWidget(self.instances_widget)

        self.instances_grid_layout = QGridLayout()

        self.instances_widget.setLayout(self.instances_grid_layout)

        self.config = config

        self.widget_index = {}

        self.config.reloaded.connect(self.on_reload)
        self.config.status_changed.connect(self.on_status_changed)

        self.needs_reload.connect(self.config.reload)
        self.needs_refresh.connect(self.config.refresh)
        self.instance_enabled.connect(self.config.set_enable)

        self.logger = LOGGER.getChild("AWSSSOLoginWindow")

    def on_reload(self, sso_instances):
        self.logger.debug('on_reload ids=%s', sso_instances)

        #TODO: reset grid
        #TODO: column labels

        missing_instances = set(self.widget_index.keys())
        for i, sso_id in enumerate(sso_instances):
            sso_instance_widgets = SSOInstanceWidgets(sso_id)
            self.instances_grid_layout.addWidget(sso_instance_widgets.checkbox,             i, 0)
            self.instances_grid_layout.addWidget(sso_instance_widgets.sso_id_label,      i, 1)
            self.instances_grid_layout.addWidget(sso_instance_widgets.status_label,         i, 2)
            self.instances_grid_layout.addWidget(sso_instance_widgets.expiration_label,     i, 3)
            self.instances_grid_layout.addWidget(sso_instance_widgets.refresh_button,       i, 4)
            self.instances_grid_layout.addWidget(sso_instance_widgets.force_refresh_button, i, 5)

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


    def on_status_changed(self, sso_id, status, expiration):
        self.logger.debug('on_status_changed id=%s status=%s exp=%s', sso_id, status, expiration)
        sso_instance_widgets = self.widget_index[sso_id]
        sso_instance_widgets.update_status(status, expiration)
