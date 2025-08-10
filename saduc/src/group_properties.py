#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/group_properties.py
#
# Description:
# This file contains the dialog for viewing and editing group properties.
#
# -----------------------------------------------------------------------------

import logging
import ldap.dn
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QLineEdit, 
    QRadioButton, QGroupBox, QHBoxLayout, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView
)

from i18n_manager import I18nManager
from samba_backend import get_group_properties, BASE_DN

# Constants for groupType bits
GROUP_TYPE_SECURITY = 0x80000000
GROUP_TYPE_UNIVERSAL = 0x00000008
GROUP_TYPE_GLOBAL = 0x00000002
GROUP_TYPE_DOMAIN_LOCAL = 0x00000004

class GroupPropertiesDialog(QDialog):
    """Dialog for viewing and editing group properties."""
    def __init__(self, samba_conn, group_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.group_dn = group_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.setWindowTitle(self.i18n.get_string("group_properties.window_title"))
        self.setMinimumSize(500, 400)

        self._create_widgets()
        self._create_layout()
        self._load_group_data()

    def _create_widgets(self):
        self.tab_widget = QTabWidget()
        self.general_tab = QWidget()
        self.members_tab = QWidget()
        self.member_of_tab = QWidget()

        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("group_properties.tab.general"))
        self.tab_widget.addTab(self.members_tab, self.i18n.get_string("group_properties.tab.members"))
        self.tab_widget.addTab(self.member_of_tab, self.i18n.get_string("group_properties.tab.member_of"))

        # General Tab Widgets
        self.group_name_edit = QLineEdit()
        self.group_name_edit.setReadOnly(True)
        self.description_edit = QLineEdit()
        
        self.group_scope_box = QGroupBox(self.i18n.get_string("group_properties.groupbox.scope"))
        self.domain_local_radio = QRadioButton(self.i18n.get_string("group_properties.radio.domain_local"))
        self.global_radio = QRadioButton(self.i18n.get_string("group_properties.radio.global"))
        self.universal_radio = QRadioButton(self.i18n.get_string("group_properties.radio.universal"))

        self.group_type_box = QGroupBox(self.i18n.get_string("group_properties.groupbox.type"))
        self.security_radio = QRadioButton(self.i18n.get_string("group_properties.radio.security"))
        self.distribution_radio = QRadioButton(self.i18n.get_string("group_properties.radio.distribution"))

        # Members Tab Widgets
        self.members_table = QTableWidget()

        # Member Of Tab Widgets
        self.member_of_table = QTableWidget()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

        # General Tab Layout
        general_layout = QFormLayout(self.general_tab)
        general_layout.addRow(self.i18n.get_string("group_properties.label.group_name"), self.group_name_edit)
        general_layout.addRow(self.i18n.get_string("group_properties.label.description"), self.description_edit)
        
        scope_layout = QHBoxLayout()
        scope_layout.addWidget(self.domain_local_radio)
        scope_layout.addWidget(self.global_radio)
        scope_layout.addWidget(self.universal_radio)
        self.group_scope_box.setLayout(scope_layout)
        general_layout.addRow(self.group_scope_box)

        type_layout = QHBoxLayout()
        type_layout.addWidget(self.security_radio)
        type_layout.addWidget(self.distribution_radio)
        self.group_type_box.setLayout(type_layout)
        general_layout.addRow(self.group_type_box)

        # Members Tab Layout
        members_layout = QVBoxLayout(self.members_tab)
        members_layout.addWidget(self.members_table)
        self.members_table.setColumnCount(2)
        self.members_table.setHorizontalHeaderLabels([
            self.i18n.get_string("group_properties.header.name"),
            self.i18n.get_string("group_properties.header.folder")
        ])
        header_members = self.members_table.horizontalHeader()
        header_members.setSectionResizeMode(0, QHeaderView.Interactive)
        header_members.setSectionResizeMode(1, QHeaderView.Stretch)
        self.members_table.resizeColumnToContents(0)

        # Member Of Tab Layout
        member_of_layout = QVBoxLayout(self.member_of_tab)
        member_of_layout.addWidget(self.member_of_table)
        self.member_of_table.setColumnCount(2)
        self.member_of_table.setHorizontalHeaderLabels([
            self.i18n.get_string("group_properties.header.name"),
            self.i18n.get_string("group_properties.header.folder")
        ])
        header_member_of = self.member_of_table.horizontalHeader()
        header_member_of.setSectionResizeMode(0, QHeaderView.Interactive)
        header_member_of.setSectionResizeMode(1, QHeaderView.Stretch)
        self.member_of_table.resizeColumnToContents(0)

    def _get_display_path_from_dn(self, dn_string):
        domain_parts = [p.split('=')[1] for p in BASE_DN.split(',') if p.lower().startswith('dc=')]
        domain = ".".join(domain_parts)

        try:
            dn_parts = ldap.dn.str2dn(dn_string)
            if len(dn_parts) <= 1:
                return domain
            
            parent_dn_parts = dn_parts[1:]
            parent_dn_string = ldap.dn.dn2str(parent_dn_parts)

            base_dn_parts = ldap.dn.str2dn(BASE_DN)

            len_parent = len(parent_dn_parts)
            len_base = len(base_dn_parts)
            
            if len_parent < len_base:
                 relative_parts = parent_dn_parts
            else:
                if parent_dn_parts[len_parent-len_base:] == base_dn_parts:
                    relative_parts = parent_dn_parts[:len_parent-len_base]
                else:
                    relative_parts = parent_dn_parts

            if not relative_parts:
                return domain

            path_components = [rdn[0][1] for rdn in reversed(relative_parts)]
            return f"{domain}/{'/'.join(path_components)}"

        except Exception as e:
            self.logger.warning(f"Could not parse DN '{dn_string}' to create display path: {e}")
            try:
                return ldap.dn.dn2str(ldap.dn.str2dn(dn_string)[1:])
            except:
                return dn_string

    def _load_group_data(self):
        group_props = get_group_properties(self.samba_conn, self.group_dn)
        if not group_props:
            self.logger.error(f"Could not load properties for group: {self.group_dn}")
            return

        # General Tab
        self.group_name_edit.setText(group_props.get('cn', [''])[0])
        self.description_edit.setText(group_props.get('description', [''])[0])

        group_type = int(group_props.get('groupType', ['0'])[0])

        if group_type & GROUP_TYPE_SECURITY:
            self.security_radio.setChecked(True)
        else:
            self.distribution_radio.setChecked(True)

        if group_type & GROUP_TYPE_UNIVERSAL:
            self.universal_radio.setChecked(True)
        elif group_type & GROUP_TYPE_GLOBAL:
            self.global_radio.setChecked(True)
        elif group_type & GROUP_TYPE_DOMAIN_LOCAL:
            self.domain_local_radio.setChecked(True)

        # Members Tab
        self.members_table.setRowCount(0)
        members = group_props.get('member', [])
        for member_dn in members:
            cn = member_dn.split(',')[0].replace('CN=', '') if 'CN=' in member_dn else member_dn
            row = self.members_table.rowCount()
            self.members_table.insertRow(row)
            self.members_table.setItem(row, 0, QTableWidgetItem(cn))
            display_path = self._get_display_path_from_dn(member_dn)
            self.members_table.setItem(row, 1, QTableWidgetItem(display_path))

        # Member Of Tab
        self.member_of_table.setRowCount(0)
        member_of = group_props.get('memberOf', [])
        for group_dn in member_of:
            cn = group_dn.split(',')[0].replace('CN=', '') if 'CN=' in group_dn else group_dn
            row = self.member_of_table.rowCount()
            self.member_of_table.insertRow(row)
            self.member_of_table.setItem(row, 0, QTableWidgetItem(cn))
            display_path = self._get_display_path_from_dn(group_dn)
            self.member_of_table.setItem(row, 1, QTableWidgetItem(display_path))

    def apply_changes(self):
        # This is a placeholder for now
        self.logger.info("Apply changes clicked, but not yet implemented.")
        pass