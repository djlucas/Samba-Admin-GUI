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
import os
import copy
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QHBoxLayout, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QMessageBox, QGroupBox,
    QRadioButton, QTableWidgetItem, QFrame, QTextEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap

from i18n_manager import I18nManager
from samba_backend import get_computer_properties, BASE_DN, get_group_properties, update_object_attributes, get_group_by_rid, get_user_properties, get_all_computer_attributes_with_schema_info, get_forest_root_info
from ntds_settings_dialog import NtdsSettingsDialog
from rotating_tab_widget import RotatingTabWidget
from tab_styles import STYLE_DEFAULT
from shared_properties_tabs import ObjectTab, SecurityTab, ManagedByTab, MemberOfTab, PasswordReplicationTab, EmailTab, LAPSTab
from attribute_editor import AttributeEditorTab

# Constants for userAccountControl flags
UAC_ACCOUNT_DISABLED = 0x0002
UAC_WORKSTATION_TRUST_ACCOUNT = 0x1000
UAC_SERVER_TRUST_ACCOUNT = 0x2000
UAC_TRUSTED_FOR_DELEGATION = 0x80000
UAC_TRUSTED_TO_AUTH_FOR_DELEGATION = 0x1000000

class ComputerPropertiesDialog(QDialog):
    """Dialog for viewing and editing computer properties."""
    def __init__(self, samba_conn, computer_dn, advanced_view=False, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.computer_dn = computer_dn
        self.advanced_view = advanced_view
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.computer_props = {}
        self.schema_info = {}
        self.editable_computer_props = {}

        self.setWindowTitle(self.i18n.get_string("computer_properties.window_title"))
        self.setMinimumSize(450, 400)
        self.resize(450, 600)

        self._create_widgets()
        self._create_layout()
        self._load_computer_data()
        self._connect_signals()

    def _create_widgets(self):
        self.tab_widget = RotatingTabWidget(logger=self.logger)
        self.tab_widget.setTabStyle(STYLE_DEFAULT)

        self._create_general_tab()
        self._create_os_tab()
        self._create_delegation_tab()
        self._create_location_tab()

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)

    def _create_general_tab(self):
        self.general_tab = QWidget()
        self.computer_name_header = QLabel()
        self.computer_name_pre2k = QLineEdit()
        self.dns_name_edit = QLineEdit()
        self.dc_type_edit = QLineEdit()
        self.site_edit = QLineEdit()
        self.description_edit = QLineEdit()
        self.ntds_settings_btn = QPushButton("NTDS Settings...")

    def _create_os_tab(self):
        self.os_tab = QWidget()
        self.os_name_edit = QLineEdit()
        self.os_version_edit = QLineEdit()
        self.os_service_pack_edit = QLineEdit()

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

    def _create_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

        self._layout_general_tab()
        self._layout_os_tab()
        self._layout_delegation_tab()
        self._layout_location_tab()

    def _connect_signals(self):
        """Connect all UI element signals to the attribute change handler."""
        self.widget_to_attribute_map = {
            self.computer_name_pre2k: 'sAMAccountName',
            self.description_edit: 'description',
            self.os_name_edit: 'operatingSystem',
            self.os_version_edit: 'operatingSystemVersion',
            self.os_service_pack_edit: 'operatingSystemServicePack',
            self.location_edit: 'location',
        }

        for widget, attr_name in self.widget_to_attribute_map.items():
            if isinstance(widget, QLineEdit):
                widget.editingFinished.connect(self._on_attribute_change)
            elif isinstance(widget, QTextEdit):
                widget.textChanged.connect(self._on_attribute_change)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._on_attribute_change)
            elif isinstance(widget, QCheckBox):
                widget.stateChanged.connect(self._on_attribute_change)
            elif isinstance(widget, QRadioButton):
                widget.toggled.connect(self._on_attribute_change)
        
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Apply).clicked.connect(self.apply_changes)
        self.trust_specified_radio.toggled.connect(self.specified_services_group.setEnabled)
        self.ntds_settings_btn.clicked.connect(self._open_ntds_settings_dialog)

    def _on_attribute_change(self):
        """Handle changes to any attribute field."""
        sender = self.sender()
        if sender in self.widget_to_attribute_map:
            attr_name = self.widget_to_attribute_map[sender]
            
            new_value = ''
            if isinstance(sender, (QLineEdit)):
                new_value = sender.text()
            elif isinstance(sender, QTextEdit):
                new_value = sender.toPlainText()
            elif isinstance(sender, QComboBox):
                new_value = sender.currentText()
            elif isinstance(sender, QCheckBox):
                new_value = 'TRUE' if sender.isChecked() else 'FALSE'
            elif isinstance(sender, QRadioButton) and sender.isChecked():
                # Special handling for radio buttons if needed
                pass

            # Special handling for sAMAccountName
            if attr_name == 'sAMAccountName':
                new_value += '$'

            # Update the editable properties dictionary
            if attr_name in self.editable_computer_props:
                if self.editable_computer_props.get(attr_name, ['']) != [new_value]:
                    self.logger.debug(f"Attribute '{attr_name}' changed from '{self.editable_computer_props.get(attr_name, [''])[0]}' to '{new_value}'")
                    self.editable_computer_props[attr_name] = [new_value]
            else:
                self.logger.debug(f"Attribute '{attr_name}' set to '{new_value}'")
                self.editable_computer_props[attr_name] = [new_value]

    def _layout_general_tab(self):
        self.tab_widget.addTab(self.general_tab, self.i18n.get_string("computer_properties.tab.general"))
        layout = QVBoxLayout(self.general_tab)

        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'computer.png')
        pixmap = QPixmap(icon_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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

        ntds_layout = QHBoxLayout()
        ntds_layout.addWidget(self.ntds_settings_btn)
        ntds_layout.addStretch()
        layout.addLayout(ntds_layout)

        layout.addStretch()

    def _layout_os_tab(self):
        self.tab_widget.addTab(self.os_tab, self.i18n.get_string("computer_properties.tab.os"))
        layout = QFormLayout(self.os_tab)
        layout.addRow(self.i18n.get_string("computer_properties.label.os_name"), self.os_name_edit)
        layout.addRow(self.i18n.get_string("computer_properties.label.os_version"), self.os_version_edit)
        layout.addRow(self.i18n.get_string("computer_properties.label.os_service_pack"), self.os_service_pack_edit)

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
        icon_path = os.path.join(os.path.dirname(__file__), 'res', 'icons', 'location.png')
        pixmap = QPixmap(icon_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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

    def _load_computer_data(self):
        """Load computer data from Active Directory, including schema info."""
        self.computer_props, self.schema_info = get_all_computer_attributes_with_schema_info(self.samba_conn, self.computer_dn)
        if not self.computer_props:
            self.logger.error(f"Could not load properties for computer: {self.computer_dn}")
            return

        self.editable_computer_props = copy.deepcopy(self.computer_props)
        self._populate_all_tabs()

    def _populate_all_tabs(self):
        """Populate all tabs with data from self.computer_props."""
        # General Tab
        cn = self.computer_props.get('cn', [''])[0]
        self.computer_name_header.setText(cn)
        self.computer_name_pre2k.setText(self.computer_props.get('sAMAccountName', [''])[0].rstrip('$'))
        self.dns_name_edit.setText(self.computer_props.get('dNSHostName', [''])[0])
        self.dns_name_edit.setReadOnly(True)
        self.description_edit.setText(self.computer_props.get('description', [''])[0])

        uac = int(self.computer_props.get('userAccountControl', ['0'])[0])
        if uac & UAC_SERVER_TRUST_ACCOUNT:
            dc_type = "Domain Controller"
            self.ntds_settings_btn.show()
            server_ref_dn = self.computer_props.get('serverReferenceBL', [None])[0]
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
            self.ntds_settings_btn.hide()
        self.dc_type_edit.setText(dc_type)
        self.dc_type_edit.setReadOnly(True)
        self.site_edit.setReadOnly(True)

        # OS Tab
        self.os_name_edit.setText(self.computer_props.get('operatingSystem', [''])[0])
        self.os_version_edit.setText(self.computer_props.get('operatingSystemVersion', [''])[0])
        self.os_service_pack_edit.setText(self.computer_props.get('operatingSystemServicePack', [''])[0])


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

        allowed_services = self.computer_props.get('msDS-AllowedToDelegateTo', [])
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
        self.location_edit.setText(self.computer_props.get('location', [''])[0])
        self.browse_location_btn.clicked.connect(self._browse_location)


        # Add tabs in specified order
        if not self.advanced_view:
            # Normal view: General, Operating System, Member Of, Delegation, LAPS, Location, Managed By
            self.tab_widget.addTab(MemberOfTab(self.samba_conn, self.computer_dn, self.computer_props, show_primary_group=True), self.i18n.get_string("computer_properties.tab.member_of"))
            self.tab_widget.addTab(LAPSTab(self.samba_conn, self.computer_dn), self.i18n.get_string("computer_properties.tab.laps"))
            self.tab_widget.addTab(ManagedByTab(self.samba_conn, self.computer_props), self.i18n.get_string("computer_properties.tab.managed_by"))
        else:
            # Advanced view:
            # Row 1: General, Operating System, Member Of, Delegation, Password Replication
            # Row 2: LAPS, Location, Managed By, Object, Security, Attribute Editor, E-mail
            self.tab_widget.addTab(MemberOfTab(self.samba_conn, self.computer_dn, self.computer_props, show_primary_group=True), self.i18n.get_string("computer_properties.tab.member_of"))
            self.tab_widget.addTab(PasswordReplicationTab(self.samba_conn, self.computer_dn), self.i18n.get_string("user_properties.tab.password_replication"))
            # Row 2
            self.tab_widget.addTab(LAPSTab(self.samba_conn, self.computer_dn), self.i18n.get_string("computer_properties.tab.laps"))
            self.tab_widget.addTab(ManagedByTab(self.samba_conn, self.computer_props), self.i18n.get_string("computer_properties.tab.managed_by"))
            self.tab_widget.addTab(ObjectTab(self.samba_conn, self.computer_dn, self.computer_props), self.i18n.get_string("user_properties.tab.object"))
            self.tab_widget.addTab(SecurityTab(self.samba_conn, self.computer_dn), self.i18n.get_string("user_properties.tab.security"))
            self.tab_widget.addTab(AttributeEditorTab(self.samba_conn, self.computer_dn), "Attribute Editor")
            self.tab_widget.addTab(EmailTab(self.samba_conn, self.computer_dn, self.computer_props), self.i18n.get_string("user_properties.tab.email"))


    def _open_ntds_settings_dialog(self):
        computer_props = get_computer_properties(self.samba_conn, self.computer_dn)
        ntds_dn = "CN=NTDS Settings," + computer_props.get('serverReferenceBL', [None])[0]
        if not ntds_dn:
            QMessageBox.warning(self, "Error", "Could not determine the NTDS Settings DN.")
            return

        dialog = NtdsSettingsDialog(self.samba_conn, ntds_dn, self)
        dialog.exec_()

    def apply_changes(self):
        """Apply the changes made in the dialog to the local computer object."""
        self.logger.info("Applying changes for computer object (read-only mode)")
        
        # Properties are already updated via _on_attribute_change()
        # Just sync editable props to main props for other tabs
        self.computer_props.update(self.editable_computer_props)
        
        # Show read-only dialog but keep dialog open
        QMessageBox.information(
            self, 
            "Read-Only Mode", 
            "This application is currently in read-only mode. Changes cannot be saved to Active Directory."
        )
    
    def accept(self):
        """Override accept to show read-only dialog before closing."""
        # Sync editable props to main props
        self.computer_props.update(self.editable_computer_props)
        
        # Show read-only dialog
        QMessageBox.information(
            self, 
            "Read-Only Mode", 
            "This application is currently in read-only mode. Changes cannot be saved to Active Directory."
        )
        
        # Close the dialog
        super().accept()
    
    def _browse_location(self):
        """Open location browsing dialog."""
        from search_dialogs import ContainerBrowserDialog
        
        dialog = ContainerBrowserDialog(self.samba_conn, self)
        if dialog.exec_() == QDialog.Accepted:
            selected_container = dialog.get_selected_object()
            if selected_container:
                # Update the location field with the container DN
                location_dn = selected_container['dn']
                display_name = selected_container['display_name']
                
                self.location_edit.setText(location_dn)
                
                # Update the local properties
                if 'location' in self.widget_to_attribute_map.values():
                    self.editable_computer_props['location'] = [location_dn]
                
                self.logger.info(f"Selected location: {display_name} ({location_dn})")