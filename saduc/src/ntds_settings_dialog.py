#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# SADUC (Samba Active Directory Users and Computers)
#
# src/ntds_settings_dialog.py
#
# Description:
# This file contains the dialog for NTDS Settings properties.
#
# -----------------------------------------------------------------------------

import logging
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QLineEdit, QCheckBox, QPushButton, QDialogButtonBox, QComboBox,
    QLabel, QFrame, QTabWidget, QTableWidget, QHeaderView, QTableWidgetItem
)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt

from i18n_manager import I18nManager
from samba_backend import get_ntds_settings, get_query_policies, get_replication_connections, format_ldap_guid, BASE_DN

class NtdsSettingsDialog(QDialog):
    """Dialog for viewing and editing NTDS Settings properties."""
    def __init__(self, samba_conn, ntds_dn, parent=None):
        super().__init__(parent)
        self.samba_conn = samba_conn
        self.ntds_dn = ntds_dn
        self.logger = logging.getLogger("saduc_app." + self.__class__.__name__)
        self.i18n = I18nManager()

        self.setWindowTitle("NTDS Settings Properties")
        self.setMinimumSize(500, 550)

        self._create_widgets()
        self._create_layout()
        self._load_data()

    def _create_widgets(self):
        # Header
        self.header_icon = QLabel()
        self.header_icon.setPixmap(QIcon("src/res/icons/site_settings.png").pixmap(32, 32))
        self.header_label = QLabel("<b>NTDS Settings</b>")

        # Tabs
        self.tab_widget = QTabWidget()
        self.general_tab = QWidget()
        self.connections_tab = QWidget()

        # General Tab Widgets
        self.description_edit = QLineEdit()
        self.query_policy_combo = QComboBox()
        self.dns_alias_edit = QLineEdit()
        self.dns_alias_edit.setReadOnly(True)
        self.global_catalog_check = QCheckBox("Global Catalog")
        self.gc_note_label = QLabel("The amount of time it will take to publish the Global Catalog varies depending on your replication topology.")
        self.gc_note_label.setWordWrap(True)

        # Connections Tab Widgets
        self.replicate_from_table = QTableWidget()
        self.replicate_to_table = QTableWidget()

        # Dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def _create_layout(self):
        main_layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(self.header_icon)
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        # --- General Tab Layout ---
        general_layout = QVBoxLayout(self.general_tab)
        form_layout = QFormLayout()
        form_layout.addRow("Description:", self.description_edit)
        form_layout.addRow("Query policy:", self.query_policy_combo)
        form_layout.addRow("DNS Alias:", self.dns_alias_edit)
        general_layout.addLayout(form_layout)
        general_layout.addWidget(self.global_catalog_check)
        general_layout.addWidget(self.gc_note_label)
        general_layout.addStretch()

        # --- Connections Tab Layout ---
        connections_layout = QVBoxLayout(self.connections_tab)
        connections_layout.addWidget(QLabel("Replicate from:"))
        connections_layout.addWidget(self.replicate_from_table)
        connections_layout.addWidget(QLabel("Replicate to:"))
        connections_layout.addWidget(self.replicate_to_table)
        self._setup_table(self.replicate_from_table)
        self._setup_table(self.replicate_to_table)

        self.tab_widget.addTab(self.general_tab, "General")
        self.tab_widget.addTab(self.connections_tab, "Connections")

        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.button_box)

    def _setup_table(self, table):
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Name", "Site"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.verticalHeader().hide()

    def _load_data(self):
        ntds_props = get_ntds_settings(self.samba_conn, self.ntds_dn)
        if not ntds_props:
            self.logger.error(f"Could not load NTDS Settings for DN: {self.ntds_dn}")
            return

        self.description_edit.setText(ntds_props.get('description', [''])[0])
        
        policies = get_query_policies(self.samba_conn)
        self.query_policy_combo.addItems(policies)
        current_policy_dn = ntds_props.get('queryPolicyObject', [None])[0]
        if current_policy_dn:
            try:
                current_policy_cn = current_policy_dn.split(',')[0].split('=')[1]
                self.query_policy_combo.setCurrentText(current_policy_cn)
            except IndexError:
                self.logger.warning(f"Could not parse CN from query policy DN: {current_policy_dn}")
        else:
            self.query_policy_combo.setCurrentText("Default Query Policy")

        guid_bytes = ntds_props.get('objectGUID')
        if guid_bytes:
            guid_str = format_ldap_guid(guid_bytes)
            domain_name = ".".join(p.split('=')[1] for p in BASE_DN.split(',') if p.lower().startswith('dc='))
            dns_alias = f"{guid_str}._msdcs.{domain_name}"
            self.dns_alias_edit.setText(dns_alias)

        options = int(ntds_props.get('options', ['0'])[0])
        if options & 1:
            self.global_catalog_check.setChecked(True)
        else:
            self.global_catalog_check.setChecked(False)

        from_conns, to_conns = get_replication_connections(self.samba_conn, self.ntds_dn)
        self._populate_connections_table(self.replicate_from_table, from_conns)
        self._populate_connections_table(self.replicate_to_table, to_conns)

    def _populate_connections_table(self, table, connections):
        table.setRowCount(0)
        for conn in connections:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(conn.get('name', 'N/A')))
            table.setItem(row, 1, QTableWidgetItem(conn.get('site', 'N/A')))