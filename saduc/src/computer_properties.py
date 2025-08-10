#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/computer_properties.py
#
# Description:
# This file contains the dialog for viewing and editing computer properties.
#
# -----------------------------------------------------------------------------

import logging
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
    QCheckBox, QPushButton, QHBoxLayout, QDialogButtonBox
)

from i18n_manager import I18nManager
from samba_backend import get_computer_properties

class ComputerPropertiesDialog(QDialog):
    """Dialog for viewing and editing computer properties."""
    def __init__(self, samba_conn, computer_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.computer_dn = computer_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.setWindowTitle(self.i18n.get_string("computer_properties.window_title"))
        self.setMinimumSize(500, 400)
        self.resize(650, 600)

        self._create_widgets()
        self._create_layout()
        self._load_computer_data()

    def _create_widgets(self):
        self.tab_widget = QTabWidget()
        self.general_tab = QWidget()
        self.os_tab = QWidget()
        self.member_of_tab = QWidget()
        self.delegation_tab = QWidget()
        self.location_tab = QWidget()
        self.managed_by_tab = QWidget()

        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("computer_properties.tab.general"))
        self.tab_widget.addTab(self.os_tab, self.i18n.get_string("computer_properties.tab.os"))
        self.tab_widget.addTab(self.member_of_tab, self.i18n.get_string("computer_properties.tab.member_of"))
        self.tab_widget.addTab(self.delegation_tab, self.i18n.get_string("computer_properties.tab.delegation"))
        self.tab_widget.addTab(self.location_tab, self.i18n.get_string("computer_properties.tab.location"))
        self.tab_widget.addTab(self.managed_by_tab, self.i18n.get_string("computer_properties.tab.managed_by"))
       
        # General Tab Widgets
        self.computer_name_edit = QLineEdit()
        self.computer_name_edit.setReadOnly(True)
        self.dns_name_edit = QLineEdit()
        self.description_edit = QLineEdit()

        # OS Tab Widgets
        self.os_name_edit = QLineEdit()
        self.os_version_edit = QLineEdit()
        self.os_service_pack_edit = QLineEdit()

        # Member Of Tab Widgets
        self.member_of_layout = QVBoxLayout()
        self.member_of_tab.setLayout(self.member_of_layout)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # Delegation Tab Widgets
        self.delegation_layout = QVBoxLayout()
        self.delegation_tab.setLayout(self.delegation_layout)

        # Location Tab Widgets
        self.location_layout = QVBoxLayout()
        self.location_tab.setLayout(self.location_layout)

        # Managed By Tab Widgets
        self.managed_by_layout = QVBoxLayout()
        self.managed_by_tab.setLayout(self.delegation_layout)

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

        # General Tab Layout
        general_layout = QFormLayout(self.general_tab)
        general_layout.addRow(self.i18n.get_string("computer_properties.label.computer_name"), self.computer_name_edit)
        general_layout.addRow(self.i18n.get_string("computer_properties.label.dns_name"), self.dns_name_edit)
        general_layout.addRow(self.i18n.get_string("computer_properties.label.description"), self.description_edit)

        # OS Tab Layout
        os_layout = QFormLayout(self.os_tab)
        os_layout.addRow(self.i18n.get_string("computer_properties.label.os_name"), self.os_name_edit)
        os_layout.addRow(self.i18n.get_string("computer_properties.label.os_version"), self.os_version_edit)
        os_layout.addRow(self.i18n.get_string("computer_properties.label.os_service_pack"), self.os_service_pack_edit)

        # Delegation Tab Layout
        delegation_layout = QFormLayout(self.delegation_tab)
        
        # Location Tab Layout
        location_layout = QFormLayout(self.location_tab)

        # Member Of Tab Layout
        member_of_layout = QFormLayout(self.member_of_tab)

    def _load_computer_data(self):
        computer_props = get_computer_properties(self.samba_conn, self.computer_dn)
        if not computer_props:
            self.logger.error(f"Could not load properties for computer: {self.computer_dn}")
            return

        # General Tab
        self.computer_name_edit.setText(computer_props.get('cn', [''])[0])
        self.dns_name_edit.setText(computer_props.get('dNSHostName', [''])[0])
        self.description_edit.setText(computer_props.get('description', [''])[0])

        # OS Tab
        self.os_name_edit.setText(computer_props.get('operatingSystem', [''])[0])
        self.os_version_edit.setText(computer_props.get('operatingSystemVersion', [''])[0])
        self.os_service_pack_edit.setText(computer_props.get('operatingSystemServicePack', [''])[0])

        # Member Of Tab
        # TODO: Populate memberOf list


        # Delgation Tab
        # TODO: Populate Delegate Tab

        # Location Tab
        # TODO: Populate Location Tab

        # Managed By Tab
        # TODO: Populate Managed By Tab

    def apply_changes(self):
        # This is a placeholder for now
        self.logger.info("Apply changes clicked, but not yet implemented.")
        pass
