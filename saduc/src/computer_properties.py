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
import ldap.dn
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QHBoxLayout, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QMessageBox, QGroupBox,
    QRadioButton, QTableWidgetItem, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap

from i18n_manager import I18nManager
from samba_backend import get_computer_properties, BASE_DN, get_group_properties, update_object_attributes, get_group_by_rid, get_user_properties

# Constants for userAccountControl flags
UAC_ACCOUNT_DISABLED = 0x0002
UAC_WORKSTATION_TRUST_ACCOUNT = 0x1000
UAC_SERVER_TRUST_ACCOUNT = 0x2000
UAC_TRUSTED_FOR_DELEGATION = 0x80000
UAC_TRUSTED_TO_AUTH_FOR_DELEGATION = 0x1000000

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
        self._connect_signals()
        self._load_computer_data()

    def _create_widgets(self):
        self.tab_widget = QTabWidget()

        self._create_general_tab()
        self._create_os_tab()
        self._create_member_of_tab()
        self._create_delegation_tab()
        self._create_location_tab()
        self._create_managed_by_tab()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)

    def _create_general_tab(self):
        self.general_tab = QWidget()
        self.computer_name_header = QLabel()
        self.computer_name_pre2k = QLineEdit()
        self.dns_name_edit = QLineEdit()
        self.dc_type_edit = QLineEdit()
        self.site_edit = QLineEdit()
        self.description_edit = QLineEdit()

    def _create_os_tab(self):
        self.os_tab = QWidget()
        self.os_name_edit = QLineEdit()
        self.os_version_edit = QLineEdit()
        self.os_service_pack_edit = QLineEdit()

    def _create_member_of_tab(self):
        self.member_of_tab = QWidget()
        self.member_of_table = QTableWidget()
        self.add_to_group_btn = QPushButton(self.i18n.get_string("user_properties.button.add"))
        self.remove_from_group_btn = QPushButton(self.i18n.get_string("user_properties.button.remove"))
        self.set_primary_btn = QPushButton(self.i18n.get_string("user_properties.button.set_primary"))
        self.primary_group_label = QLabel()

    def _create_delegation_tab(self):
        self.delegation_tab = QWidget()
        self.delegation_info_label = QLabel(self.i18n.get_string("computer_properties.delegation.info_text"))
        self.dont_trust_radio = QRadioButton(self.i18n.get_string("computer_properties.delegation.radio_dont_trust"))
        self.trust_any_radio = QRadioButton(self.i18n.get_string("computer_properties.delegation.radio_trust_any"))
        self.trust_specified_radio = QRadioButton(self.i18n.get_string("computer_properties.delegation.radio_trust_specified"))
        self.kerberos_only_radio = QRadioButton(self.i18n.get_string("computer_properties.delegation.radio_kerberos_only"))
        self.any_protocol_radio = QRadioButton(self.i18n.get_string("computer_properties.delegation.radio_any_protocol"))
        self.services_table = QTableWidget()
        self.add_service_btn = QPushButton(self.i18n.get_string("user_properties.button.add"))
        self.remove_service_btn = QPushButton(self.i18n.get_string("user_properties.button.remove"))
        self.specified_services_group = QGroupBox()
        self.specified_services_group.setEnabled(False)

    def _create_location_tab(self):
        self.location_tab = QWidget()
        self.location_edit = QLineEdit()
        self.browse_location_btn = QPushButton(self.i18n.get_string("computer_properties.location.button_browse"))

    def _create_managed_by_tab(self):
        self.managed_by_tab = QWidget()
        self.manager_name_edit = QLineEdit()
        self.change_manager_btn = QPushButton(self.i18n.get_string("user_properties.button.change"))
        self.manager_properties_btn = QPushButton(self.i18n.get_string("action_pane.menu.properties"))
        self.clear_manager_btn = QPushButton(self.i18n.get_string("computer_properties.managed_by.button_clear"))
        self.manager_office_label = QLabel()
        self.manager_street_label = QLabel()
        self.manager_city_state_label = QLabel()
        self.manager_country_label = QLabel()
        self.manager_telephone_label = QLabel()
        self.manager_fax_label = QLabel()

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

        self._layout_general_tab()
        self._layout_os_tab()
        self._layout_member_of_tab()
        self._layout_delegation_tab()
        self._layout_location_tab()
        self._layout_managed_by_tab()

    def _connect_signals(self):
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        self.trust_specified_radio.toggled.connect(self.specified_services_group.setEnabled)
        self.manager_name_edit.textChanged.connect(self._update_managed_by_buttons)
        self.change_manager_btn.clicked.connect(self._change_manager)

    def _layout_general_tab(self):
        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("computer_properties.tab.general"))
        layout = QVBoxLayout(self.general_tab)

        header_layout = QHBoxLayout()
        icon_label = QLabel()
        pixmap = QPixmap("src/res/icons/computer.png").scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(pixmap)
        icon_label.setFixedSize(40, 40)
        self.computer_name_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(icon_label)
        header_layout.addWidget(self.computer_name_header)
        header_layout.addStretch()

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)

        form_layout = QFormLayout()
        form_layout.addRow(self.i18n.get_string("computer_properties.label.computer_name_pre2k"), self.computer_name_pre2k)
        form_layout.addRow(self.i18n.get_string("computer_properties.label.dns_name"), self.dns_name_edit)
        form_layout.addRow(self.i18n.get_string("computer_properties.label.dc_type"), self.dc_type_edit)
        form_layout.addRow(self.i18n.get_string("computer_properties.label.site"), self.site_edit)
        form_layout.addRow(self.i18n.get_string("computer_properties.label.description"), self.description_edit)

        layout.addLayout(header_layout)
        layout.addWidget(separator)
        layout.addLayout(form_layout)
        layout.addStretch()

    def _layout_os_tab(self):
        self.tab_widget.addTab(self.os_tab, self.i18n.get_string("computer_properties.tab.os"))
        layout = QFormLayout(self.os_tab)
        layout.addRow(self.i18n.get_string("computer_properties.label.os_name"), self.os_name_edit)
        layout.addRow(self.i18n.get_string("computer_properties.label.os_version"), self.os_version_edit)
        layout.addRow(self.i18n.get_string("computer_properties.label.os_service_pack"), self.os_service_pack_edit)

    def _layout_member_of_tab(self):
        self.tab_widget.addTab(self.member_of_tab, self.i18n.get_string("computer_properties.tab.member_of"))
        layout = QVBoxLayout(self.member_of_tab)
        self.member_of_table.setColumnCount(2)
        self.member_of_table.setHorizontalHeaderLabels([
            self.i18n.get_string("user_properties.header.name"),
            self.i18n.get_string("user_properties.header.folder")
        ])
        self.member_of_table.setSortingEnabled(True)
        self.member_of_table.verticalHeader().hide()
        self.member_of_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        header = self.member_of_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.member_of_table)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_to_group_btn)
        button_layout.addWidget(self.remove_from_group_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        primary_layout = QHBoxLayout()
        primary_layout.addWidget(QLabel(self.i18n.get_string("user_properties.label.primary_group")))
        primary_layout.addWidget(self.primary_group_label)
        primary_layout.addWidget(self.set_primary_btn)
        primary_layout.addStretch()
        layout.addLayout(primary_layout)

    def _layout_delegation_tab(self):
        self.tab_widget.addTab(self.delegation_tab, self.i18n.get_string("computer_properties.tab.delegation"))
        layout = QVBoxLayout(self.delegation_tab)
        self.delegation_info_label.setWordWrap(True)
        layout.addWidget(self.delegation_info_label)

        layout.addWidget(self.dont_trust_radio)
        layout.addWidget(self.trust_any_radio)
        layout.addWidget(self.trust_specified_radio)

        specified_layout = QVBoxLayout(self.specified_services_group)
        protocol_layout = QHBoxLayout()
        protocol_layout.addWidget(self.kerberos_only_radio)
        protocol_layout.addWidget(self.any_protocol_radio)
        protocol_layout.addStretch()
        specified_layout.addLayout(protocol_layout)

        specified_layout.addWidget(QLabel(self.i18n.get_string("computer_properties.delegation.label_services")))
        self.services_table.setColumnCount(2)
        self.services_table.setHorizontalHeaderLabels(["Service Type", "User or Computer"])
        header = self.services_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        specified_layout.addWidget(self.services_table)

        service_buttons = QHBoxLayout()
        service_buttons.addWidget(self.add_service_btn)
        service_buttons.addWidget(self.remove_service_btn)
        service_buttons.addStretch()
        specified_layout.addLayout(service_buttons)

        layout.addWidget(self.specified_services_group)
        layout.addStretch()

    def _layout_location_tab(self):
        self.tab_widget.addTab(self.location_tab, self.i18n.get_string("computer_properties.tab.location"))
        layout = QVBoxLayout(self.location_tab)

        header_layout = QHBoxLayout()
        icon_label = QLabel()
        pixmap = QPixmap("src/res/icons/location.png").scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(pixmap)
        header_layout.addWidget(icon_label)
        header_layout.addStretch()

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)

        location_layout = QHBoxLayout()
        location_layout.addWidget(self.location_edit)
        location_layout.addWidget(self.browse_location_btn)

        form_layout = QFormLayout()
        form_layout.addRow(self.i18n.get_string("computer_properties.label.location"), location_layout)

        layout.addLayout(header_layout)
        layout.addWidget(separator)
        layout.addLayout(form_layout)
        layout.addStretch()

    def _layout_managed_by_tab(self):
        self.tab_widget.addTab(self.managed_by_tab, self.i18n.get_string("computer_properties.tab.managed_by"))
        layout = QVBoxLayout(self.managed_by_tab)

        manager_group = QGroupBox()
        form_layout = QFormLayout(manager_group)

        name_layout = QHBoxLayout()
        name_layout.addWidget(self.manager_name_edit)
        name_layout.addWidget(self.change_manager_btn)
        form_layout.addRow(self.i18n.get_string("user_properties.label.name"), name_layout)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.manager_properties_btn)
        button_layout.addWidget(self.clear_manager_btn)
        form_layout.addRow(button_layout)

        form_layout.addRow(self.i18n.get_string("user_properties.label.office"), self.manager_office_label)
        form_layout.addRow(self.i18n.get_string("user_properties.label.street"), self.manager_street_label)
        form_layout.addRow(self.i18n.get_string("user_properties.label.city_state"), self.manager_city_state_label)
        form_layout.addRow(self.i18n.get_string("user_properties.label.country"), self.manager_country_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        form_layout.addRow(separator)

        form_layout.addRow(self.i18n.get_string("user_properties.label.telephone"), self.manager_telephone_label)
        form_layout.addRow(self.i18n.get_string("user_properties.label.fax"), self.manager_fax_label)

        layout.addWidget(manager_group)
        layout.addStretch()

    def _load_computer_data(self):
        computer_props = get_computer_properties(self.samba_conn, self.computer_dn)
        if not computer_props:
            self.logger.error(f"Could not load properties for computer: {self.computer_dn}")
            return

        # General Tab
        cn = computer_props.get('cn', [''])[0]
        self.computer_name_header.setText(cn)
        self.computer_name_pre2k.setText(computer_props.get('sAMAccountName', [''])[0].rstrip('$'))
        self.dns_name_edit.setText(computer_props.get('dNSHostName', [''])[0])
        self.dns_name_edit.setReadOnly(True)
        self.description_edit.setText(computer_props.get('description', [''])[0])

        uac = int(computer_props.get('userAccountControl', ['0'])[0])
        if uac & UAC_SERVER_TRUST_ACCOUNT:
            dc_type = "Domain Controller"
            server_ref_dn = computer_props.get('serverReferenceBL', [None])[0]
            if server_ref_dn:
                try:
                    dn_parts = ldap.dn.str2dn(server_ref_dn)
                    for i, rdn in enumerate(dn_parts):
                        if rdn[0][0].lower() == 'cn' and rdn[0][1].lower() == 'sites':
                            if i > 0:
                                site_rdn = dn_parts[i-1]
                                if site_rdn[0][0].lower() == 'cn':
                                    self.site_edit.setText(site_rdn[0][1])
                                    break
                except Exception as e:
                    self.logger.warning(f"Could not parse site from serverReferenceBL DN '{server_ref_dn}': {e}")
        else:
            dc_type = "Workstation or Server"
        self.dc_type_edit.setText(dc_type)
        self.dc_type_edit.setReadOnly(True)
        self.site_edit.setReadOnly(True)

        # OS Tab
        self.os_name_edit.setText(computer_props.get('operatingSystem', [''])[0])
        self.os_version_edit.setText(computer_props.get('operatingSystemVersion', [''])[0])
        self.os_service_pack_edit.setText(computer_props.get('operatingSystemServicePack', [''])[0])

        # Member Of Tab
        self.member_of_table.setRowCount(0)
        primary_group_id = computer_props.get('primaryGroupID', ['515'])[0]
        member_of_dns = computer_props.get('memberOf', [])

        primary_group_info = get_group_by_rid(self.samba_conn, primary_group_id)
        if not primary_group_info:
            primary_group_info = {'dn': f"CN=Domain Computers,CN=Users,{BASE_DN}", 'cn': 'Domain Computers', 'displayName': 'Domain Computers'}

        other_groups = []
        for group_dn in member_of_dns:
            group_props = get_group_properties(self.samba_conn, group_dn, ['cn', 'displayName'])
            if group_props:
                info = {'dn': group_dn, 'cn': group_props.get('cn', [group_dn])[0], 'displayName': group_props.get('displayName', [group_props.get('cn', [group_dn])[0]])[0]}
                if group_dn != primary_group_info['dn']:
                    other_groups.append(info)

        all_groups = [primary_group_info] + other_groups
        for group_info in all_groups:
            row = self.member_of_table.rowCount()
            self.member_of_table.insertRow(row)
            name = group_info.get('displayName', group_info.get('cn', self.i18n.get_string("common.unknown")))
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, group_info['dn'])
            self.member_of_table.setItem(row, 0, name_item)
            path_item = QTableWidgetItem(self._get_display_path_from_dn(group_info['dn']))
            self.member_of_table.setItem(row, 1, path_item)

        self.primary_group_label.setText(primary_group_info.get('displayName', primary_group_info.get('cn', self.i18n.get_string("common.unknown"))))

        # Delegation Tab
        if uac & UAC_TRUSTED_TO_AUTH_FOR_DELEGATION:
            self.trust_specified_radio.setChecked(True)
            # Check for protocol transition
            if uac & UAC_TRUSTED_FOR_DELEGATION:
                self.any_protocol_radio.setChecked(True)
            else:
                self.kerberos_only_radio.setChecked(True)
        elif uac & UAC_TRUSTED_FOR_DELEGATION:
            self.trust_any_radio.setChecked(True)
        else:
            self.dont_trust_radio.setChecked(True)

        allowed_services = computer_props.get('msDS-AllowedToDelegateTo', [])
        self.services_table.setRowCount(0)
        for service in allowed_services:
            row = self.services_table.rowCount()
            self.services_table.insertRow(row)
            parts = service.split('/')
            service_type = parts[0]
            user_or_computer = "/".join(parts[1:])
            self.services_table.setItem(row, 0, QTableWidgetItem(service_type))
            self.services_table.setItem(row, 1, QTableWidgetItem(user_or_computer))

        # Location Tab
        self.location_edit.setText(computer_props.get('location', [''])[0])
        self.browse_location_btn.setEnabled(False)

        # Managed By Tab
        manager_dn = computer_props.get('managedBy', [None])[0]
        if manager_dn:
            manager_props = get_user_properties(self.samba_conn, manager_dn)
            if manager_props:
                self.manager_name_edit.setText(manager_props.get('displayName', [''])[0])
                self.manager_office_label.setText(manager_props.get('physicalDeliveryOfficeName', [''])[0])
                self.manager_street_label.setText(manager_props.get('streetAddress', [''])[0])
                city = manager_props.get('l', [''])[0]
                state = manager_props.get('st', [''])[0]
                self.manager_city_state_label.setText(f"{city}, {state}")
                self.manager_country_label.setText(manager_props.get('co', [''])[0])
                self.manager_telephone_label.setText(manager_props.get('telephoneNumber', [''])[0])
                self.manager_fax_label.setText(manager_props.get('facsimileTelephoneNumber', [''])[0])
        self._update_managed_by_buttons()


    def apply_changes(self):
        self.logger.info("Apply changes clicked, but not yet implemented.")
        pass

    def _get_display_path_from_dn(self, dn_string):
        domain_parts = [p.split('=')[1] for p in BASE_DN.split(',') if p.lower().startswith('dc=')]
        domain = ".".join(domain_parts)
        try:
            parent_dn_string = ldap.dn.dn2str(ldap.dn.str2dn(dn_string)[1:])
            base_dn_string = BASE_DN
            relative_dn_string = parent_dn_string
            if parent_dn_string.lower().endswith(base_dn_string.lower()):
                end_index = len(parent_dn_string) - len(base_dn_string)
                relative_dn_string = parent_dn_string[:end_index].rstrip(',')
            if not relative_dn_string:
                return domain
            relative_parts = ldap.dn.str2dn(relative_dn_string)
            path_components = [rdn[0][1] for rdn in reversed(relative_parts)]
            return f"{domain}/{'/'.join(path_components)}"
        except Exception as e:
            self.logger.warning(f"Could not parse DN '{dn_string}' to create display path: {e}")
            return dn_string

    def _add_to_group(self):
        QMessageBox.information(self, "Not Implemented", "Adding objects to groups is not yet implemented.")

    def _remove_from_group(self):
        QMessageBox.information(self, "Not Implemented", "Removing objects from groups is not yet implemented.")

    def _set_primary_group(self):
        current_row = self.member_of_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a group to set as primary.")
            return
        selected_item = self.member_of_table.item(current_row, 0)
        group_dn = selected_item.data(Qt.UserRole)
        group_props = get_group_properties(self.samba_conn, group_dn, ['primaryGroupToken'])
        if not group_props or 'primaryGroupToken' not in group_props:
            QMessageBox.critical(self, "Error", f"Could not retrieve the group RID for {group_dn}.")
            return
        new_primary_id = group_props['primaryGroupToken'][0]
        modifications = [(ldap.MOD_REPLACE, 'primaryGroupID', [new_primary_id.encode('utf-8')])]
        success, message = update_object_attributes(self.samba_conn, self.computer_dn, modifications)
        if success:
            QMessageBox.information(self, "Success", "Primary group updated successfully.")
            self._load_computer_data()
        else:
            QMessageBox.critical(self, "Error", f"Failed to update primary group: {message}")

    def _update_managed_by_buttons(self):
        has_manager = bool(self.manager_name_edit.text())
        self.manager_properties_btn.setEnabled(has_manager)
        self.clear_manager_btn.setEnabled(has_manager)

    def _change_manager(self):
        QMessageBox.information(self, "Not Implemented", "A user search dialog is not yet implemented.")