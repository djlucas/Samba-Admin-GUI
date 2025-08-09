#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/user_properties.py
#
# Description:
# This file contains the dialog for viewing and editing user properties.
#
# -----------------------------------------------------------------------------

import logging
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
    QCheckBox, QPushButton, QHBoxLayout, QDialogButtonBox
)

from i18n_manager import I18nManager
from samba_backend import get_user_properties

# Constants for userAccountControl bits
UAC_ACCOUNT_DISABLED = 0x0002
UAC_DONT_EXPIRE_PASSWORD = 0x10000
UAC_PASSWORD_CANT_CHANGE = 0x0040

class UserPropertiesDialog(QDialog):
    """Dialog for viewing and editing user properties."""
    def __init__(self, samba_conn, user_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.user_dn = user_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.setWindowTitle(self.i18n.get_string("user_properties.window_title"))
        self.setMinimumSize(500, 400)

        self._create_widgets()
        self._create_layout()
        self._load_user_data()

    def _create_widgets(self):
        self.tab_widget = QTabWidget()
        self.general_tab = QWidget()
        self.account_tab = QWidget()
        self.member_of_tab = QWidget()

        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("user_properties.tab.general"))
        self.tab_widget.addTab(self.account_tab, self.i18n.get_string("user_properties.tab.account"))
        self.tab_widget.addTab(self.member_of_tab, self.i18n.get_string("user_properties.tab.member_of"))

        # General Tab Widgets
        self.first_name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()
        self.display_name_edit = QLineEdit()
        self.description_edit = QLineEdit()

        # Account Tab Widgets
        self.user_logon_name_edit = QLineEdit()
        self.user_must_change_password_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.must_change_password"))
        self.user_cannot_change_password_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.cannot_change_password"))
        self.password_never_expires_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.password_never_expires"))
        self.account_disabled_check = QCheckBox(self.i18n.get_string("user_properties.checkbox.account_disabled"))

        # Member Of Tab Widgets
        # This will be a list view of groups, for now a placeholder
        self.member_of_layout = QVBoxLayout()
        self.member_of_tab.setLayout(self.member_of_layout)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        # self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

        # General Tab Layout
        general_layout = QFormLayout(self.general_tab)
        general_layout.addRow(self.i18n.get_string("user_properties.label.first_name"), self.first_name_edit)
        general_layout.addRow(self.i18n.get_string("user_properties.label.last_name"), self.last_name_edit)
        general_layout.addRow(self.i18n.get_string("user_properties.label.display_name"), self.display_name_edit)
        general_layout.addRow(self.i18n.get_string("user_properties.label.description"), self.description_edit)

        # Account Tab Layout
        account_layout = QVBoxLayout(self.account_tab)
        account_form_layout = QFormLayout()
        account_form_layout.addRow(self.i18n.get_string("user_properties.label.user_logon_name"), self.user_logon_name_edit)
        account_layout.addLayout(account_form_layout)
        account_layout.addWidget(self.user_must_change_password_check)
        account_layout.addWidget(self.user_cannot_change_password_check)
        account_layout.addWidget(self.password_never_expires_check)
        account_layout.addWidget(self.account_disabled_check)
        account_layout.addStretch()

    def _load_user_data(self):
        user_props = get_user_properties(self.samba_conn, self.user_dn)
        if not user_props:
            self.logger.error(f"Could not load properties for user: {self.user_dn}")
            # Optionally, show an error message to the user
            return

        # General Tab
        self.first_name_edit.setText(user_props.get('givenName', [''])[0])
        self.last_name_edit.setText(user_props.get('sn', [''])[0])
        self.display_name_edit.setText(user_props.get('displayName', [''])[0])
        self.description_edit.setText(user_props.get('description', [''])[0])

        # Account Tab
        self.user_logon_name_edit.setText(user_props.get('sAMAccountName', [''])[0])

        uac = int(user_props.get('userAccountControl', ['0'])[0])
        self.account_disabled_check.setChecked(uac & UAC_ACCOUNT_DISABLED)
        self.password_never_expires_check.setChecked(uac & UAC_DONT_EXPIRE_PASSWORD)
        self.user_cannot_change_password_check.setChecked(uac & UAC_PASSWORD_CANT_CHANGE)
        # The "user must change password" is not a UAC flag, it's a separate attribute (pwdLastSet=0)
        # This is a simplification for now.

        # Member Of Tab
        # TODO: Populate memberOf list

    def apply_changes(self):
        # This is a placeholder for now
        self.logger.info("Apply changes clicked, but not yet implemented.")
        pass
